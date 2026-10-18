"""Handoff 63 §1 and §5.5, in-registry — who reads the SAP mirror, and who
imports it.

* `sap_mirror:read` is the Asset Controller's, the Register Maker's and
  Checker's and the Auditor's (and the `admin` wildcard's) — pinned against
  the scope table, and NOT an Asset User's;
* a credential with VENDRA'S EXACT scopes (`assets:read assets:write
  candidates:read`, `myservice_api_client 'vendra'` on `test19`) is refused
  every mirror read — Vendra's own secret is not on this machine, so its
  scopes are what is reproduced, by name (the 61 pattern);
* a credential holding `settings:write` without `admin` — what an Asset
  Manager's token carries — is refused the import, in words;
* the `admin` credential's upload is `202` and the run, read to its end,
  creates what the file holds; a second upload while one is queued is a
  `409` naming it.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestSapMirrorScope \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import uuid

from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase
from odoo.addons.myservice_asset_register.tests import (
    sap_export_shapes as shapes)

#: The four roles that read the mirror (handoff 63 §1), beside `admin`.
READERS = ('myservice_asset_register.group_asset_controller',
           'myservice_asset_register.group_register_maker',
           'myservice_asset_register.group_register_checker',
           'myservice_api.group_auditor')
VENDRA_SCOPES = 'assets:read assets:write candidates:read'


@tagged('post_install', '-at_install')
class TestSapMirrorScope(CadraHttpCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.myservice_api.controllers import utils
        self.utils = utils
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_param('myservice_api.jwt_secret'):
            ICP.set_param('myservice_api.jwt_secret', uuid.uuid4().hex)
        tag = uuid.uuid4().hex[:8]
        self.clients = {
            name: self.create_api_client({
                'name': 'sap mirror probe (%s)' % name,
                'client_id': 'sapprobe_%s_%s' % (name, tag), 'scopes': scopes})
            for name, scopes in (
                ('vendra', VENDRA_SCOPES),
                ('reader', 'sap_mirror:read'),
                ('settings', 'settings:write sap_mirror:read'),
                ('admin', 'admin'))}
        self.secrets = {n: c.rotate_secret() for n, c in self.clients.items()}

    def _token(self, name):
        c = self.clients[name]
        r = self.url_open(
            '/api/v1/auth/token',
            data=json.dumps({'client_id': c.client_id,
                             'client_secret': self.secrets[name]}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['data']['access_token']

    def _get(self, name, path):
        return self.url_open(path, headers={
            'Authorization': 'Bearer %s' % self._token(name)})

    def _upload(self, name, data):
        return self.url_open(
            '/api/v1/sap-assets/imports',
            files={'file': ('export.xlsx', data)},
            headers={'Authorization': 'Bearer %s' % self._token(name)})

    def test_the_scope_table_gives_the_mirror_to_the_four_and_nobody_else(self):
        holders = {xmlid for xmlid, scopes in self.utils.GROUP_SCOPES
                   if self.utils.SCOPE_SAP_MIRROR_READ in scopes}
        self.assertEqual(holders, set(READERS))
        self.assertNotIn(self.utils.SCOPE_SAP_MIRROR_READ, dict(
            self.utils.GROUP_SCOPES)['myservice_asset_register.group_asset_user'])
        self.assertNotIn(self.utils.SCOPE_SAP_MIRROR_READ,
                         VENDRA_SCOPES.split())
        self.assertTrue(self.utils.SCOPE_SAP_MIRROR_READ.endswith(':read'),
                        'the Auditor is pinned read-only')

    def test_vendras_scopes_are_refused_every_mirror_read(self):
        for path in ('/api/v1/sap-assets', '/api/v1/sap-assets/imports',
                     '/api/v1/sap-assets/match?description=chair',
                     '/api/v1/reports/sap-coverage'):
            r = self._get('vendra', path)
            self.assertEqual(r.status_code, 403, path)
            self.assertIn('sap_mirror:read', r.json()['error']['message'])
            self.assertEqual(self._get('reader', path).status_code, 200, path)

    def test_settings_write_without_admin_is_refused_the_import(self):
        Run = self.env['nrs.sap.import.run'].sudo()
        before = Run.search_count([])
        r = self._upload('settings', shapes.build_xlsx(
            [shapes.record('2S%s1' % uuid.uuid4().hex[:6])]))
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("System Administrator's act", r.json()['error']['message'])
        self.assertEqual(Run.search_count([]), before, 'nothing was recorded')

    def test_the_administrators_upload_runs_and_one_runs_at_a_time(self):
        u = uuid.uuid4().hex[:6].upper()
        Run = self.env['nrs.sap.import.run'].sudo()
        Run.search([('state', 'in', ('queued', 'running'))]).write(
            {'state': 'failed'})
        r = self._upload('admin', shapes.build_xlsx(
            [shapes.record('2A%s%03d' % (u, i)) for i in range(3)]))
        self.assertEqual(r.status_code, 202, r.text)
        run = Run.browse(r.json()['data']['id'])
        self.assertEqual(run.state, 'queued')
        again = self._upload('admin', shapes.build_xlsx(
            [shapes.record('2B%s1' % u)]))
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn('One import runs at a time',
                      again.json()['error']['message'])
        run._run_to_end()
        self.assertEqual((run.state, run.created_count), ('done', 3))
        self.assertFalse(run._attachment())
