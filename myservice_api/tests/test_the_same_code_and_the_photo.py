"""Handoff 61, in-registry — the parts that are not the reprint, the photos
or the room codes (each of those has its own file).

* §0b ruling 1 — IAD's evidence behind `evidence:read`: which roles hold
  it (pinned against the scope table), and a credential with VENDRA'S EXACT
  scopes (`assets:read assets:write candidates:read`) told the count and
  refused the file. Driven through real tokens; Vendra's own secret is not
  on this machine, so its scopes are what is reproduced, by name.
* §0b ruling 6 — the category counts are one grouped query, not one per
  row: the number of queries does not grow with the number of categories.
* §2 (R10) — a candidate is not verified, marked missing, found, or given
  any other status, under every writer.
* §3 (R9) — the default `tag_id` schema has no make or model, and a chair
  with no brand is received; a customised schema keeps what it says.
* §6 — `updated_since` reads what it can and refuses what it cannot.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestEvidenceScope,/myservice_api:TestCandidateNotOnTheRegister,/myservice_api:TestCategoryCountsGrouped,/myservice_api:TestChairWithNoBrand,/myservice_api:TestUpdatedSinceParser \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import uuid
from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import (
    CadraHttpCase, CadraTransactionCase)
from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused)

from .test_receipt_gates import CHECKLIST, EVIDENCE, GateCrew

#: The five roles that read IAD's evidence (ruling 1 on report 60).
READERS = ('myservice_asset_register.group_iad_vfm_officer',
           'myservice_asset_register.group_iad_vfm_approver',
           'myservice_asset_register.group_register_maker',
           'myservice_asset_register.group_register_checker',
           'myservice_api.group_auditor')
#: Vendra's credential's scopes on `test19` (myservice_api_client 'vendra').
VENDRA_SCOPES = 'assets:read assets:write candidates:read'


@tagged('post_install', '-at_install')
class TestEvidenceScope(GateCrew, CadraHttpCase):
    """The papers are IAD's: who may open them, proved by acting."""

    def setUp(self):
        super().setUp()
        from odoo.addons.myservice_api.controllers import utils
        self.utils = utils
        self._setup_crew()
        self.unit = self._to('vfm_verified')
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_param('myservice_api.jwt_secret'):
            ICP.set_param('myservice_api.jwt_secret', uuid.uuid4().hex)
        tag = uuid.uuid4().hex[:8]
        self.vendra = self.create_api_client({
            'name': 'evidence probe (Vendra scopes)',
            'client_id': 'evprobe_vendra_%s' % tag, 'scopes': VENDRA_SCOPES})
        self.reader = self.create_api_client({
            'name': 'evidence probe (reader)',
            'client_id': 'evprobe_reader_%s' % tag,
            'scopes': 'candidates:read evidence:read'})
        self.secrets = {c.client_id: c.rotate_secret()
                        for c in (self.vendra, self.reader)}

    def _get(self, client, path):
        r = self.url_open(
            '/api/v1/auth/token',
            data=json.dumps({'client_id': client.client_id,
                             'client_secret': self.secrets[client.client_id]}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()['data']['access_token']
        return self.url_open(path,
                             headers={'Authorization': 'Bearer %s' % token})

    def _file_id(self):
        files = [f for v in self.unit._gate_evidence() for f in v['files']]
        self.assertEqual(len(files), 1)
        return files[0].id

    def test_the_scope_table_gives_the_papers_to_the_five_and_nobody_else(
            self):
        holders = {xmlid for xmlid, scopes in self.utils.GROUP_SCOPES
                   if self.utils.SCOPE_EVIDENCE_READ in scopes}
        self.assertEqual(holders, set(READERS))
        # Vendra's and every Asset User's `candidates:read` is NOT it.
        self.assertNotIn(self.utils.SCOPE_EVIDENCE_READ,
                         dict(self.utils.GROUP_SCOPES)[
                             'myservice_asset_register.group_asset_user'])
        self.assertNotIn(self.utils.SCOPE_EVIDENCE_READ, VENDRA_SCOPES.split())
        self.assertTrue(self.utils.SCOPE_EVIDENCE_READ.endswith(':read'),
                        'the Auditor is pinned read-only')

    def test_vendras_scopes_are_told_the_count_and_nothing_more(self):
        r = self._get(self.vendra, '/api/v1/assets/%d/evidence' % self.unit.id)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()['data']
        self.assertIs(data['readable'], False)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['summary'], 'IAD evidence: 1 item')
        self.assertEqual(data['verifications'], [])
        self.assertNotIn('sighting.txt', r.text)
        r = self._get(self.vendra, '/api/v1/assets/%d/evidence/%d'
                      % (self.unit.id, self._file_id()))
        self.assertEqual(r.status_code, 403, r.text[:300])
        self.assertIn('evidence:read', r.text)

    def test_vendras_scopes_read_the_history_without_the_papers(self):
        r = self._get(self.vendra, '/api/v1/assets/%d/history' % self.unit.id)
        self.assertEqual(r.status_code, 200, r.text[:300])
        verify = [e for e in r.json()['data']['events']
                  if (e.get('detail') or {}).get('action') == 'verify']
        self.assertTrue(verify, r.text[:600])
        evidence = verify[0]['detail']['evidence']
        # The count, and nothing more — as `/evidence` answers.
        self.assertEqual(set(evidence), {'attachments'})
        self.assertEqual(evidence['attachments']['count'], 1)
        self.assertNotIn('checklist', evidence)

    def test_a_reader_is_served_the_papers(self):
        r = self._get(self.reader, '/api/v1/assets/%d/evidence' % self.unit.id)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()['data']
        self.assertIs(data['readable'], True)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['verifications'][0]['files'][0]['name'],
                         EVIDENCE[0]['name'])
        r = self._get(self.reader, '/api/v1/assets/%d/evidence/%d'
                      % (self.unit.id, self._file_id()))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.content, b'sighted on the loading bay')


@tagged('post_install', '-at_install')
class TestCandidateNotOnTheRegister(GateCrew, CadraTransactionCase):
    """R10: not on the register, so not missing from it — under every
    writer, the form and a script included."""

    def setUp(self):
        super().setUp()
        self._setup_crew()

    def _refused(self, fn):
        with self.assertRaises(GateRefused) as caught:
            fn()
        self.assertEqual(caught.exception.kind, 'not_on_the_register')
        return str(caught.exception.args[0])

    def test_a_candidate_is_not_verified_missing_found_or_restated(self):
        unit = self._candidate()
        words = self._refused(lambda: unit.action_verify())
        self.assertIn('verified once it is registered', words)
        words = self._refused(lambda: unit.action_mark_missing(
            reason='not on the shelf'))
        self.assertIn('cannot be missing from a register', words)
        self._refused(lambda: unit.write({'state': 'in_repair'}))
        self._refused(lambda: unit.write(
            {'last_verified_date': date.today()}))
        unit.invalidate_recordset()
        self.assertEqual(unit.state, 'active')
        self.assertFalse(unit.last_verified_date)

    def test_a_receipt_cannot_arrive_missing_or_in_repair(self):
        for state in ('missing', 'in_repair'):
            with self.subTest(state=state):
                self._refused(lambda: self.env['nrs.asset'].sudo().create({
                    'name': 'Arrives %s' % state,
                    'category_id': self.category.id,
                    'serial_number': 'SN-H61-%s' % uuid.uuid4().hex[:10],
                    'make': 'Dell', 'model_name': 'Latitude 7430',
                    'register_state': 'captured', 'state': state}))
        self._refused(lambda: self.env['nrs.asset'].sudo().create({
            'name': 'Arrives verified', 'category_id': self.category.id,
            'serial_number': 'SN-H61-%s' % uuid.uuid4().hex[:10],
            'make': 'Dell', 'model_name': 'Latitude 7430',
            'register_state': 'captured',
            'last_verified_date': date.today()}))

    def test_naming_the_fields_unchanged_passes(self):
        unit = self._candidate()
        unit.write({'state': unit.state, 'last_verified_date': False})
        self.assertEqual(unit.register_state, 'captured')

    def test_a_registered_asset_is_unaffected(self):
        unit = self._to('registered')
        unit.action_verify()
        self.assertEqual(unit.last_verified_date, date.today())
        unit.action_mark_missing(reason='not at its desk')
        self.assertEqual(unit.state, 'missing')


@tagged('post_install', '-at_install')
class TestCategoryCountsGrouped(CadraTransactionCase):
    """Ruling 6 on report 60: one grouped count, whatever the row count."""

    def _queries(self, categories):
        categories.invalidate_recordset(['asset_count',
                                         'asset_depreciating_count'])
        before = self.env.cr.sql_log_count
        for c in categories:
            c.asset_count
            c.asset_depreciating_count
        return self.env.cr.sql_log_count - before

    def test_the_count_does_not_grow_with_the_taxonomy(self):
        Category = self.env['nrs.asset.category']
        few = Category.create([{'name': 'H61 count %d' % i} for i in range(2)])
        many = Category.create([{'name': 'H61 count %d' % i}
                                for i in range(2, 22)])
        self.env['nrs.asset'].create([
            {'name': 'H61 counted', 'category_id': c.id} for c in few + many])
        self.assertEqual(self._queries(few), self._queries(many))
        self.assertLessEqual(self._queries(many), 6)
        for c in few + many:
            self.assertEqual(c.asset_count, self.env['nrs.asset'].search_count(
                [('category_id', '=', c.id)]))


@tagged('post_install', '-at_install')
class TestChairWithNoBrand(GateCrew, CadraTransactionCase):
    """R9: make and model are not mandatory BY DEFAULT for `tag_id`."""

    def setUp(self):
        super().setUp()
        self._setup_crew()
        self.chairs = self.env['nrs.asset.category'].create({
            'name': 'H61 chairs', 'identification_mode': 'tag_id',
            'sap_asset_class': '2000'})

    def test_the_default_schema_is_description_colour_material_dimensions(
            self):
        self.assertEqual(self.chairs._mandatory_attributes(),
                         ('name', 'colour', 'material', 'dimensions'))

    def test_a_chair_with_no_brand_is_received(self):
        chair = self.env['nrs.asset'].sudo().create({
            'name': 'Visitor chair', 'category_id': self.chairs.id,
            'colour': 'Grey', 'material': 'Fabric',
            'dimensions': '55x55x90 cm', 'register_state': 'captured'})
        self.assertEqual(chair.identification_mode, 'tag_id')
        self.assertFalse(chair.make)

    def test_a_customised_schema_keeps_what_it_says(self):
        self.chairs.write({'class_attributes_schema': {
            'mandatory': ['name', 'make', 'colour']}})
        self.assertEqual(self.chairs._mandatory_attributes(),
                         ('name', 'make', 'colour'))
        with self.assertRaises(UserError):
            self.env['nrs.asset'].sudo().create({
                'name': 'Branded chair', 'category_id': self.chairs.id,
                'colour': 'Grey', 'register_state': 'captured'})


@tagged('post_install', '-at_install')
class TestUpdatedSinceParser(CadraTransactionCase):
    """§6: the door for `updated_since` — a time it can read, or a 400."""

    def setUp(self):
        super().setUp()
        from odoo.addons.myservice_api.controllers.v1_assets import (
            _parse_updated_since)
        from odoo.addons.myservice_api.controllers.query_params import (
            BadFilter)
        self.parse = _parse_updated_since
        self.BadFilter = BadFilter

    def test_what_it_reads(self):
        self.assertIsNone(self.parse(None))
        self.assertIsNone(self.parse(''))
        self.assertEqual(self.parse('2026-10-15'), datetime(2026, 10, 15))
        self.assertEqual(self.parse('2026-10-15T09:30:00'),
                         datetime(2026, 10, 15, 9, 30))
        self.assertEqual(self.parse('2026-10-15 09:30:00.123456'),
                         datetime(2026, 10, 15, 9, 30, 0, 123456))
        self.assertEqual(self.parse('2026-10-15T09:30:00Z'),
                         datetime(2026, 10, 15, 9, 30))
        # Lagos is UTC+1: 10:30 there is 09:30 UTC, which is what is stored.
        self.assertEqual(self.parse('2026-10-15T10:30:00+01:00'),
                         datetime(2026, 10, 15, 9, 30))

    def test_what_it_refuses(self):
        for raw in ('yesterday', '2026-13-01', '15/10/2026', '1697360000',
                    '2026-10-15T25:00', 'null'):
            with self.subTest(raw=raw), self.assertRaises(self.BadFilter) as c:
                self.parse(raw)
            self.assertEqual(c.exception.details['updated_since'], raw)
