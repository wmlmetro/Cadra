"""An unvalidated dict reaching the model is the defect — handoff 37.

Handoff 33 §A2/§A4, taken as written by 37 §2B: the shared secret in front
of the identity webhook is not validation, and SIX call sites hand a dict to
`nrs.sap.sync.log.process_sap_payload` — the identity webhook, its `/test`
route, `POST /api/v1/integrations/sap/employee-sync`, the xlsx import job,
the CSV wizard and `scripts/load_employees_xlsx.py`. Until handoff 32 the
v1 route accepted anything and silently dropped what the model does not
read, which is how `status` — a key the published schema, the endpoint
reference's example, the demo card and this repo's own pytest all sent —
went nowhere under a 200 for the life of the feed. Handoff 32 fixed the ONE
door; the other five still dropped unknown keys in silence, and the CSV
wizard passes every unrecognised spreadsheet column straight through.

So the rule now lives ON THE MODEL, once, where all six callers meet it:
a payload carrying a key `process_sap_payload` does not read is refused
whole — an error log row naming the keys and the accepted set, nothing
written to the employee. It is a RETURN, not a raise, because the webhook
has no row handler and a raise there is an unhandled fault.

Run with:
    odoo -d <db> -u myservice_identity --stop-after-init --test-enable \\
         --test-tags /myservice_identity --workers=0 \\
         --http-port=8099 --gevent-port=8098
"""
import json

from odoo.tests import tagged
from odoo.addons.myservice_identity.controllers import sap_webhook
from odoo.addons.myservice_nrs_base.tests.common import (
    CadraHttpCase,
    CadraTransactionCase,
)

SAP_SECRET_PARAM = sap_webhook.SAP_SECRET_PARAM
SAP_SYNC_URL = '/api/sap/employee-sync'

#: Used only inside these transactions. Nothing is committed.
SAP_SECRET = 'h37-sap-validation-probe-secret'


@tagged('post_install', '-at_install')
class TestSapPayloadValidation(CadraTransactionCase):
    """The model refuses what it does not read, for every caller at once."""

    IR_NEW = 'IR-H37-VAL-NEW'
    IR_EXISTING = 'IR-H37-VAL-EXISTING'

    def setUp(self):
        super().setUp()
        self.Log = self.env['nrs.sap.sync.log']
        self.Employee = self.env['hr.employee']
        self.assertFalse(
            self.Employee.search_count(
                [('ir_number', 'in', [self.IR_NEW, self.IR_EXISTING])]),
            'these IR numbers are reserved for this test')

    def test_an_unknown_key_is_refused_whole_and_writes_no_employee(self):
        """`status` is the key the schema published and nothing ever read
        (handoff 32). On the model it is now a refusal, not a silence."""
        employee, log = self.Log.process_sap_payload(
            {'ir_number': self.IR_NEW, 'displayName': 'H37 Probe',
             'status': 'active'},
            sync_type='webhook')
        self.assertIsNone(employee)
        self.assertEqual(log.status, 'error')
        self.assertEqual(log.ir_number, self.IR_NEW)
        self.assertIn('status', log.error_message)
        self.assertFalse(
            self.Employee.search_count([('ir_number', '=', self.IR_NEW)]),
            'the refusal wrote the employee anyway — the accepted keys '
            'beside the unknown one must not land')

    def test_the_refusal_names_every_unknown_key_and_the_accepted_set(self):
        _employee, log = self.Log.process_sap_payload(
            {'ir_number': self.IR_NEW, 'costCenterX': 'A1', 'foo': 1},
            sync_type='csv_import')
        self.assertEqual(log.status, 'error')
        for key in ('costCenterX', 'foo'):
            self.assertIn(key, log.error_message)
        # The accepted set is in the message, so an operator reading the
        # errored row can repair the file without opening the source.
        for key in ('ir_number', 'employmentStatus', 'displayName'):
            self.assertIn(key, log.error_message)
        self.assertIn('nothing written', log.error_message)

    def test_an_update_is_refused_too_and_changes_nothing(self):
        existing = self.Employee.create(
            {'name': 'H37 Existing', 'ir_number': self.IR_EXISTING,
             'job_title': 'Original Title'})
        employee, log = self.Log.process_sap_payload(
            {'ir_number': self.IR_EXISTING, 'jobTitle': 'New Title',
             'status': 'active'},
            sync_type='api')
        self.assertIsNone(employee)
        self.assertEqual(log.status, 'error')
        self.assertEqual(
            existing.job_title, 'Original Title',
            'a refused payload updated the employee with the keys it '
            'accepted — the refusal must be whole')

    def test_unknown_keys_are_refused_before_the_missing_ir_number(self):
        """The whole body is read before anything is acted on, so a payload
        wrong in two ways is refused for its keys, with `UNKNOWN` on the
        row — the same order the v1 route's pre-flight gives a batch."""
        _employee, log = self.Log.process_sap_payload(
            {'event': 'Hire', 'not_a_key': True}, sync_type='manual')
        self.assertEqual(log.status, 'error')
        self.assertEqual(log.ir_number, 'UNKNOWN')
        self.assertIn('not_a_key', log.error_message)

    def test_an_accepted_payload_still_lands(self):
        """The guard refuses the unknown, never the documented."""
        employee, log = self.Log.process_sap_payload(
            {'ir_number': self.IR_NEW, 'displayName': 'H37 Accepted',
             'jobTitle': 'Engineer', 'employmentStatus': 'active'},
            sync_type='webhook')
        self.assertEqual(log.status, 'success')
        self.assertTrue(employee)
        self.assertEqual(employee.ir_number, self.IR_NEW)
        self.assertEqual(employee.job_title, 'Engineer')


@tagged('post_install', '-at_install')
class TestSapWebhookRefusesUnknownKeys(CadraHttpCase):
    """The identity door inherits the model's refusal, per row.

    The route itself is unchanged (handoff 37 §2A's condition): the secret
    gate, the shapes it accepts and its response envelope are exactly
    handoff 17's. What changed is underneath every door at once — a row
    carrying an unknown key now comes back `status: 'error'` in `results[]`
    instead of being processed without the key.
    """

    IR_DOOR = 'IR-H37-DOOR-PROBE'

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(SAP_SECRET_PARAM, SAP_SECRET)
        self.env.flush_all()

    def tearDown(self):
        # The transaction rolls back; the ormcached `_get_param` does not.
        self.env.registry.clear_cache('stable')
        super().tearDown()

    def _post(self, params):
        response = self.url_open(
            SAP_SYNC_URL,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'id': None, 'params': params}),
            headers={'Content-Type': 'application/json',
                     'X-SAP-Webhook-Secret': SAP_SECRET},
            timeout=120,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('result', body, body)
        return body['result']

    def test_a_row_with_an_unknown_key_errors_and_writes_nothing(self):
        result = self._post(
            {'ir_number': self.IR_DOOR, 'displayName': 'H37 Door Probe',
             'status': 'active'})
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('processed'), 1)
        row = result['results'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIsNone(row['employee_id'])
        self.assertFalse(
            self.env['hr.employee'].search_count(
                [('ir_number', '=', self.IR_DOOR)]),
            'the webhook wrote an employee off a payload the model refused')
