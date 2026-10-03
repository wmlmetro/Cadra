"""A scanned serial number finds its asset. Handoff 38 §A.

NRS, 30 September: *"I just scan the serial number, it shows me the asset
details immediately."* The station searched tag number and asset code only,
while the `/api/v1` twins documented *"Tag, asset code, or serial number"*.
These tests pin the resolution both routes now share (`_resolve_lookup`):
precedence, the serial rule, ambiguity, and what a pending or scrapped tag
does — plus one real HTTP round trip per route so the published keys are
proved on the wire and not only on the helper.
"""
import json
import uuid

from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import (
    CadraHttpCase, CadraTransactionCase)
from odoo.addons.myservice_barcode_station.controllers.main import (
    _escape_like, _resolve_lookup)

MANAGER_GROUP = 'myservice_asset_register.group_asset_manager'


class _Fixtures:

    def _category(self):
        return self.env['nrs.asset.category'].create(
            {'name': 'Lookup test category %s' % uuid.uuid4().hex[:6],
             'code': 'LKP'})

    def _tagged(self, serial=None, **vals):
        asset = self.env['nrs.asset'].create(dict(
            {'name': 'Lookup tagged asset', 'category_id': self.category.id,
             'serial_number': serial}, **vals))
        self.assertTrue(asset.active_tag_id)
        return asset

    def _untagged(self, serial=None, **vals):
        # `nrs.asset.create` mints a tag only when `tag_source` is absent and
        # no `asset_tag` is given; an explicit source and no number leaves
        # the asset with no label at all, which is how an imported asset
        # that has never been labelled looks.
        asset = self.env['nrs.asset'].create(dict(
            {'name': 'Lookup untagged asset', 'category_id': self.category.id,
             'serial_number': serial, 'tag_source': 'other'}, **vals))
        self.assertFalse(asset.active_tag_id)
        self.assertFalse(asset.tag_ids)
        return asset

    def _serial(self):
        return 'SN-%s' % uuid.uuid4().hex[:10].upper()


@tagged('post_install', '-at_install')
class TestResolveLookup(_Fixtures, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self._category()

    def _hit(self, q):
        return _resolve_lookup(self.env, q)

    def test_a_tag_number_resolves_as_before(self):
        asset = self._tagged()
        hit = self._hit(asset.active_tag_id.name.lower())
        self.assertTrue(hit['found'])
        self.assertEqual(hit['matched_by'], 'tag_number')
        self.assertEqual(hit['asset'], asset)
        self.assertEqual(hit['tag'], asset.active_tag_id)
        self.assertTrue(hit['tagged'])

    def test_an_asset_code_resolves(self):
        asset = self._tagged()
        hit = self._hit(asset.asset_code)
        self.assertEqual(hit['matched_by'], 'asset_code')
        self.assertEqual(hit['asset'], asset)

    def test_the_serial_of_a_tagged_asset_resolves(self):
        """The case that found nothing until handoff 38."""
        serial = self._serial()
        asset = self._tagged(serial=serial)
        hit = self._hit(serial)
        self.assertTrue(hit['found'], hit)
        self.assertEqual(hit['matched_by'], 'serial_number')
        self.assertEqual(hit['asset'], asset)
        self.assertEqual(hit['tag'], asset.active_tag_id)
        self.assertTrue(hit['tagged'])

    def test_the_serial_of_an_untagged_asset_resolves_and_says_untagged(self):
        serial = self._serial()
        asset = self._untagged(serial=serial)
        hit = self._hit(serial)
        self.assertTrue(hit['found'], hit)
        self.assertEqual(hit['matched_by'], 'serial_number')
        self.assertEqual(hit['asset'], asset)
        self.assertFalse(hit['tag'])
        self.assertFalse(hit['tagged'])

    def test_a_scanner_s_trailing_space_and_case_do_not_matter(self):
        serial = self._serial()
        asset = self._tagged(serial=serial)
        for q in (serial + ' ', ' ' + serial, serial.lower(), '\t%s\r\n' % serial):
            hit = self._hit(q)
            self.assertEqual(hit.get('asset'), asset, repr(q))

    def test_internal_whitespace_and_leading_zeros_are_significant(self):
        """`nrs19` holds 574 serials with a space inside and ten beginning
        with `0`; collapsing either would merge real serials."""
        self._tagged(serial='00C58E1408')
        self._tagged(serial='PROBOOK 440 G3')
        self.assertFalse(self._hit('C58E1408')['found'])
        self.assertFalse(self._hit('PROBOOK440G3')['found'])
        self.assertTrue(self._hit('00C58E1408')['found'])
        self.assertTrue(self._hit('PROBOOK 440 G3')['found'])

    def test_like_wildcards_in_a_serial_are_literal(self):
        a = self._tagged(serial='SN_100%')
        self._tagged(serial='SNX100Y')
        hit = self._hit('SN_100%')
        self.assertTrue(hit['found'], hit)
        self.assertEqual(hit['asset'], a)
        self.assertEqual(_escape_like('a_b%c\\d'), 'a\\_b\\%c\\\\d')

    def test_a_serial_on_two_assets_is_an_ambiguous_miss_not_a_pick(self):
        serial = self._serial()
        self._tagged(serial=serial)
        self._tagged(serial=serial.lower())
        hit = self._hit(serial)
        self.assertFalse(hit['found'])
        self.assertTrue(hit['ambiguous'])
        self.assertEqual(hit['matched_by'], 'serial_number')
        self.assertEqual(hit['matches'], 2)
        self.assertIn('2 assets', hit['error'])

    def test_precedence_a_tag_beats_a_serial_that_reads_the_same(self):
        """No tenant has such a pair (0 of 8, measured), so one is made."""
        tagged = self._tagged()
        number = tagged.active_tag_id.name
        decoy = self._tagged(serial=number)
        hit = self._hit(number)
        self.assertEqual(hit['matched_by'], 'tag_number')
        self.assertEqual(hit['asset'], tagged)
        self.assertNotEqual(hit['asset'], decoy)

    def test_precedence_an_asset_code_beats_a_serial(self):
        a = self._tagged()
        decoy = self._tagged(serial=a.asset_code)
        hit = self._hit(a.asset_code)
        self.assertEqual(hit['matched_by'], 'asset_code')
        self.assertEqual(hit['asset'], a)
        self.assertNotEqual(hit['asset'], decoy)

    def test_a_pending_tag_does_not_resolve_by_number_but_its_asset_does(self):
        """Handoff 38 §A.4: the tag-number path is NOT widened. A tag whose
        replacement is pending is still on the asset, so a scan of the
        asset's serial or code finds the asset and names that tag."""
        serial = self._serial()
        asset = self._tagged(serial=serial)
        tag = asset.active_tag_id
        Users = self.env['res.users']
        field = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'
        login = 'lookup-approver-%s' % uuid.uuid4().hex[:6]
        approver = Users.create({
            'name': login, 'login': login, 'email': login + '@example.com',
            field: [(6, 0, [self.env.ref('base.group_user').id,
                            self.env.ref(MANAGER_GROUP).id])]})
        tag.action_request_replacement(reason='damaged', approver=approver)
        self.assertEqual(tag.state, 'pending')
        self.assertFalse(self._hit(tag.name)['found'])
        hit = self._hit(serial)
        self.assertTrue(hit['found'])
        self.assertEqual(hit['tag'], tag)
        self.assertEqual(hit['tag'].state, 'pending')
        self.assertFalse(hit['tagged'], 'no ACTIVE tag')

    def test_a_scrapped_tag_number_does_not_resolve(self):
        asset = self._tagged()
        tag = asset.active_tag_id
        tag.with_context(cadra_tag_capture=True).write(
            {'state': 'scrapped', 'label_state': 'scrapped'})
        self.assertFalse(self._hit(tag.name)['found'])

    def test_nothing_matches_says_so(self):
        hit = self._hit('NOTHING-%s' % uuid.uuid4().hex)
        self.assertFalse(hit['found'])
        self.assertNotIn('ambiguous', hit)
        self.assertIn('No active tag, asset code or serial number', hit['error'])

    def test_a_blank_query_is_a_miss(self):
        self.assertFalse(self._hit('   ')['found'])


@tagged('post_install', '-at_install')
class TestLookupRoutesOnTheWire(_Fixtures, CadraHttpCase):
    """One round trip per route: the published keys, as a client sees them."""

    def setUp(self):
        super().setUp()
        self.category = self._category()
        self.password = 'h38-lookup-route'
        Users = self.env['res.users']
        field = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'
        login = 'h38_lookup_user_%s' % uuid.uuid4().hex[:6]
        self.operator = Users.create({
            'name': login, 'login': login, 'password': self.password,
            field: [(6, 0, [
            # A SYSTEM ADMINISTRATOR since handoff 45: the back-office
            # station's routes are `auth='user'`, and no session but an
            # administrator's reaches one any more (`myservice_api/models/
            # backoffice_session.py`). A tagger uses the app's station.
                self.env.ref('base.group_user').id,
                self.env.ref('base.group_system').id,
                self.env.ref('myservice_asset_register.group_asset_user').id,
            ])]})

    def _call(self, path, **params):
        response = self.url_open(
            path,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn('error', body, body.get('error'))
        return body['result']

    def test_barcode_lookup_publishes_matched_by_and_the_serial(self):
        serial = self._serial()
        asset = self._tagged(serial=serial)
        self.authenticate(self.operator.login, self.password)
        hit = self._call('/barcode/lookup', query=serial + ' ')
        self.assertTrue(hit['found'], hit)
        self.assertEqual(hit['matched_by'], 'serial_number')
        self.assertEqual(hit['serial_number'], serial)
        self.assertTrue(hit['tagged'])
        self.assertEqual(hit['tag_id'], asset.active_tag_id.id)
        self.assertEqual(hit['tag_number'], asset.active_tag_id.name)
        self.assertEqual(hit['asset_id'], asset.id)
        untagged = self._untagged(serial=self._serial())
        hit = self._call('/barcode/lookup', query=untagged.serial_number)
        self.assertTrue(hit['found'], hit)
        self.assertFalse(hit['tagged'])
        self.assertIsNone(hit['tag_id'])
        self.assertEqual(hit['tag_number'], '')
        self.assertEqual(hit['asset_id'], untagged.id)

    def test_portal_lookup_publishes_matched_by_and_no_ids(self):
        serial = self._serial()
        asset = self._tagged(serial=serial)
        hit = self._call('/tags/lookup', query=serial)
        self.assertTrue(hit['found'], hit)
        self.assertEqual(hit['matched_by'], 'serial_number')
        self.assertEqual(hit['tag_number'], asset.active_tag_id.name)
        self.assertEqual(hit['asset_name'], asset.name)
        self.assertNotIn('asset_id', hit)
        self.assertNotIn('tag_id', hit)
