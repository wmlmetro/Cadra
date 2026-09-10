"""Unset configuration refuses; it does not substitute a default.

Handoff 17 item B. Three `auth='none'` routes in this module guarded
themselves with a credential that had a fallback literal in the source:

  * `POST /api/myservice/assets/export`      — the whole asset register, JSON
  * `GET  /api/myservice/assets/export/csv`  — the whole asset register, CSV
  * `POST /api/sap/employee-sync`            — inbound employee writes

`get_param(key, 'SOME_LITERAL')` means that on a tenant where the parameter
was never set, the credential is a string committed to this repository. That
is the one failure mode a credential check cannot survive, because "nobody
configured this" and "the caller presented the right key" become the same code
path — and nothing in the response, the log or the metrics distinguishes them.

So the assertions here are mostly about the ABSENT case, which is the case
that had no test and no noise:

  1. with the parameter unset, each route refuses;
  2. the refusal is written to the log at ERROR, naming the parameter key, so
     an operator finds the misconfiguration rather than a leak;
  3. with it set, the right header authenticates;
  4. a wrong header does not;
  5. the CSV route's deprecated `?api_key=` still works and announces itself;
  6. neither literal appears anywhere in this module's source any more.

**These are real HTTP tests.** `ir.config_parameter` writes made in the test
body ARE visible to the request, because `HttpCase.setUpClass` puts the
registry in test mode and the HTTP worker serves from a `TestCursor` sharing
this transaction. (The exception documented in
`myservice_barcode_station/tests/test_print_url_route.py` is a *separate*
read/write cursor taken from the registry — that one is a genuinely different
connection. Nothing here takes one.)

Run with **--workers=0**. Under the prefork server `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so every test in this class ERRORS in setUpClass and the run reports
"0 failed" — a green that executed nothing:

    odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_identity \\
         --stop-after-init --test-enable --test-tags /myservice_identity \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import os

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.myservice_identity.controllers import redhubs_api, sap_webhook

REDHUBS_LOGGER = redhubs_api._logger.name
SAP_LOGGER = sap_webhook._logger.name

REDHUBS_KEY_PARAM = redhubs_api.REDHUBS_KEY_PARAM
SAP_SECRET_PARAM = sap_webhook.SAP_SECRET_PARAM

JSON_EXPORT_URL = '/api/myservice/assets/export'
CSV_EXPORT_URL = '/api/myservice/assets/export/csv'
SAP_SYNC_URL = '/api/sap/employee-sync'

#: Values used only inside this transaction. Nothing is committed.
REDHUBS_KEY = 'h17-redhubs-probe-key'
SAP_SECRET = 'h17-sap-probe-secret'

CSV_HEADER = 'Asset Code'


@tagged('post_install', '-at_install')
class TestExternalCredentials(HttpCase):

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()

    def tearDown(self):
        # The transaction rolls back, but `_get_param` is ormcached on the
        # registry, which does not. A test that unset a parameter would
        # otherwise leave a cached "absent" behind for the live tenant.
        self.env.registry.clear_cache('stable')
        super().tearDown()

    # -- helpers ---------------------------------------------------------

    def _set(self, key, value):
        """Set or (with ``False``) remove a parameter, and make it visible.

        `set_param` clears the `stable` ormcache itself; the flush is what
        makes the row visible to the raw SQL `_get_param` runs on the request's
        own cursor, which shares this transaction.
        """
        self.ICP.set_param(key, value)
        self.env.flush_all()

    def _unset_all(self):
        self._set(REDHUBS_KEY_PARAM, False)
        self._set(SAP_SECRET_PARAM, False)

    def _set_all(self):
        self._set(REDHUBS_KEY_PARAM, REDHUBS_KEY)
        self._set(SAP_SECRET_PARAM, SAP_SECRET)

    def _rpc(self, url, headers=None, params=None):
        """Call a `type='json'` route and return its `result` payload."""
        all_headers = {'Content-Type': 'application/json'}
        all_headers.update(headers or {})
        response = self.url_open(
            url,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'id': None, 'params': params or {}}),
            headers=all_headers,
            timeout=120,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(
            'result', body,
            'the route raised instead of answering; JSON-RPC body was %s' % body)
        return body['result']

    def _csv(self, headers=None, query=None):
        url = CSV_EXPORT_URL
        if query:
            url += '?' + query
        return self.url_open(url, headers=headers or {}, timeout=120)

    #: A payload carrying no IR number, so the SAP route proves it got PAST
    #: the credential check without creating or touching an employee. The log
    #: row it does create rolls back with this transaction.
    SAP_PROBE = {'event': 'CadraH17AuthProbe'}

    # -- 1 + 2: unset configuration refuses, loudly ----------------------

    def test_the_json_export_refuses_when_the_key_is_unset(self):
        self._unset_all()
        with self.assertLogs(REDHUBS_LOGGER, level='ERROR') as captured:
            result = self._rpc(JSON_EXPORT_URL,
                               headers={'X-API-Key': REDHUBS_KEY})
        self.assertEqual(result, {'success': False, 'error': 'Unauthorized'})
        line = '\n'.join(captured.output)
        self.assertIn(REDHUBS_KEY_PARAM, line,
                      'the log must name the parameter an operator has to set')
        self.assertIn(JSON_EXPORT_URL, line)

    def test_the_csv_export_refuses_401_when_the_key_is_unset(self):
        self._unset_all()
        with self.assertLogs(REDHUBS_LOGGER, level='ERROR') as captured:
            response = self._csv(headers={'X-API-Key': REDHUBS_KEY})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(
            CSV_HEADER, response.text,
            'an unconfigured tenant answered the asset register to a caller '
            'holding a key that authenticates nothing')
        self.assertIn(REDHUBS_KEY_PARAM, '\n'.join(captured.output))

    def test_the_sap_webhook_refuses_when_the_secret_is_unset(self):
        self._unset_all()
        with self.assertLogs(SAP_LOGGER, level='ERROR') as captured:
            result = self._rpc(SAP_SYNC_URL,
                               headers={'X-SAP-Webhook-Secret': SAP_SECRET},
                               params=self.SAP_PROBE)
        self.assertEqual(result, {'success': False, 'error': 'Unauthorized'})
        line = '\n'.join(captured.output)
        self.assertIn(SAP_SECRET_PARAM, line)
        self.assertIn(SAP_SYNC_URL, line)

    def test_an_empty_stored_value_refuses_too(self):
        """A parameter set to the empty string is not a credential.

        `get_param` answers `False` for an absent parameter and `''` for an
        empty one; both must refuse rather than compare-equal to a caller who
        sent no header at all.
        """
        self._set(REDHUBS_KEY_PARAM, '')
        with self.assertLogs(REDHUBS_LOGGER, level='ERROR'):
            response = self._csv(headers={'X-API-Key': ''})
        self.assertEqual(response.status_code, 401)

    # -- 3: configured, the right header works ---------------------------

    def test_the_right_header_authenticates_on_all_three_routes(self):
        self._set_all()

        result = self._rpc(JSON_EXPORT_URL, headers={'X-API-Key': REDHUBS_KEY})
        self.assertTrue(result.get('success'))
        self.assertIn('assets', result)

        response = self._csv(headers={'X-API-Key': REDHUBS_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertIn(CSV_HEADER, response.text)

        result = self._rpc(SAP_SYNC_URL,
                           headers={'X-SAP-Webhook-Secret': SAP_SECRET},
                           params=self.SAP_PROBE)
        self.assertNotEqual(
            result.get('error'), 'Unauthorized',
            'a correct secret was refused')
        self.assertTrue(result.get('success'))

    # -- 4: a wrong value is refused -------------------------------------

    def test_a_wrong_header_is_refused_on_all_three_routes(self):
        self._set_all()

        result = self._rpc(JSON_EXPORT_URL, headers={'X-API-Key': 'wrong'})
        self.assertEqual(result, {'success': False, 'error': 'Unauthorized'})

        response = self._csv(headers={'X-API-Key': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(CSV_HEADER, response.text)

        result = self._rpc(SAP_SYNC_URL,
                           headers={'X-SAP-Webhook-Secret': 'wrong'},
                           params=self.SAP_PROBE)
        self.assertEqual(result, {'success': False, 'error': 'Unauthorized'})

    def test_no_header_at_all_is_refused(self):
        """The empty-header case is the one a fallback used to paper over."""
        self._set_all()
        self.assertEqual(self._csv().status_code, 401)
        self.assertEqual(
            self._rpc(JSON_EXPORT_URL),
            {'success': False, 'error': 'Unauthorized'})

    # -- 5: the deprecated query parameter, and its end date -------------

    def test_the_csv_route_still_accepts_api_key_and_says_it_is_deprecated(self):
        self._set_all()
        with self.assertLogs(REDHUBS_LOGGER, level='WARNING') as captured:
            response = self._csv(query='api_key=%s' % REDHUBS_KEY)
        self.assertEqual(response.status_code, 200)
        self.assertIn(CSV_HEADER, response.text)
        line = '\n'.join(captured.output)
        self.assertIn('DEPRECATED', line)
        self.assertIn('ip=', line,
                      'the deprecation warning must name the caller, or the '
                      'migration has no way to find who is still on it')
        self.assertNotIn(REDHUBS_KEY, line,
                         'the credential must never reach the log')

    def test_a_wrong_query_parameter_is_still_a_401(self):
        """Deprecated is not unchecked."""
        self._set_all()
        response = self._csv(query='api_key=wrong')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(CSV_HEADER, response.text)

    def test_the_header_does_not_trigger_the_deprecation_warning(self):
        """Only the query parameter is deprecated, so only it may warn.

        A warning on every call would make the log useless for finding the
        callers that actually have to migrate.
        """
        self._set_all()
        with self.assertNoLogs(REDHUBS_LOGGER, level='WARNING'):
            self.assertEqual(
                self._csv(headers={'X-API-Key': REDHUBS_KEY}).status_code, 200)

    # -- 6: the literals cannot come back --------------------------------

    def test_the_fallback_literals_appear_nowhere_in_this_module(self):
        """A source guard, so the default cannot return by copy-paste.

        The needles are assembled from halves on purpose: this file is itself
        inside the tree it scans, and a guard that fails on its own text is a
        guard nobody keeps.
        """
        needles = ('NRS_REDHUBS_' + 'KEY_2025',
                   'NRS_SAP_WEBHOOK_' + 'SECRET_2025')
        module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        readable = ('.py', '.xml', '.csv', '.md', '.txt', '.js', '.yml', '.yaml')

        offenders = []
        for dirpath, dirnames, filenames in os.walk(module_root):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for filename in filenames:
                if not filename.endswith(readable):
                    continue
                path = os.path.join(dirpath, filename)
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
                for needle in needles:
                    if needle in text:
                        offenders.append('%s carries %s' % (
                            os.path.relpath(path, module_root), needle))

        self.assertEqual(
            offenders, [],
            'A credential literal is back in the source. An unset '
            'ir.config_parameter must REFUSE, never fall back to a string '
            'that is public in git history:\n  ' + '\n  '.join(offenders))
