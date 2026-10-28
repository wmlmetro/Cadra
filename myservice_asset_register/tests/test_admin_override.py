"""Handoff 70, in-registry — who the administrator override is for.

The HTTP suite (`tests/test_the_administrator.py`) drives the override end to
end as the demo administrator. Two of the handoff's cases cannot be made
over the API, and are pinned here instead:

* a MACHINE credential whose user is in `base.group_system` — handoff 42's
  guard refuses that grant over the API — never overrides;
* a NON-administrator is held to the no-two-gates rule with the switch on —
  over the API the role exclusions keep two gate roles off one person.

The request's verified claims are what tells a person's token from a
machine's (`aud: frontend`, stamped by `/auth/login` only), so the tests
stand in for the request by patching the one reader of them.

Run with:
    odoo -d test19 -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register:TestAdminOverride \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..models import admin_override
from ..models.admin_override import admin_overrides
from ..models.asset_gates import GateRefused


@tagged('post_install', '-at_install')
class TestAdminOverride(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        Users = self.env['res.users'].sudo()

        def person(login, *xmlids):
            return Users.create({
                'name': login, 'login': login,
                'email': '%s@override.example' % login,
                'group_ids': [(4, self.env.ref(x).id) for x in
                              ('base.group_user',) + xmlids]})

        self.admin = person('h70-admin', 'base.group_system')
        self.manager = person(
            'h70-manager', 'myservice_asset_register.group_asset_manager')
        category = self.env['nrs.asset.category'].create(
            {'name': 'Override Test Category', 'code': 'H70'})
        self.asset = self.env['nrs.asset'].sudo().create(
            {'name': 'Override probe', 'category_id': category.id})

    def _switch(self, on):
        self.env['ir.config_parameter'].sudo().set_param(
            admin_override.ADMIN_OVERRIDE_PARAM, 'true' if on else 'false')
        # Read with raw SQL, as the route reads it after its flush.
        self.env.flush_all()

    def _token(self, user, person=True):
        claims = {'uid': user.id, 'scopes': ['admin']}
        if person:
            claims['aud'] = admin_override.PERSON_AUDIENCE
        return patch.object(admin_override, '_request_claims',
                            return_value=claims)

    def _earlier_gate(self, user):
        """`user` verified this unit: the rule now bars them from approving."""
        self.env['nrs.asset.event']._record(
            self.asset, 'gate_fired', actor=user, from_value='vfm_pending',
            to_value='vfm_verified', gate='verify', gate_action='verify')

    def test_absent_means_off(self):
        self.env.cr.execute("DELETE FROM ir_config_parameter WHERE key = %s",
                            (admin_override.ADMIN_OVERRIDE_PARAM,))
        self.assertFalse(admin_override.override_switched_on(self.env))
        with self._token(self.admin):
            self.assertFalse(admin_overrides(self.env, self.admin))

    def test_only_a_person_who_is_an_administrator_with_the_switch_on(self):
        self._switch(True)
        with self._token(self.admin):
            self.assertTrue(admin_overrides(self.env, self.admin))
        with self._token(self.admin, person=False):
            self.assertFalse(admin_overrides(self.env, self.admin),
                             'a machine credential never overrides')
        with self._token(self.manager):
            self.assertFalse(admin_overrides(self.env, self.manager))
        with self._token(self.manager):
            self.assertFalse(admin_overrides(self.env, self.admin),
                             'a token that names someone else is not theirs')
        # Outside a request: the back office, a shell, a cron.
        self.assertFalse(admin_overrides(self.env, self.admin))
        self._switch(False)
        with self._token(self.admin):
            self.assertFalse(admin_overrides(self.env, self.admin))

    def test_the_no_two_gates_rule_is_lifted_for_nobody_else(self):
        self._switch(True)
        for user, person in ((self.manager, True), (self.admin, False)):
            self._earlier_gate(user)
            asset = self.asset.with_user(user)
            with self._token(user, person=person), \
                    self.assertRaises(GateRefused) as refused:
                asset._assert_two_gates('approve')
            self.assertEqual(refused.exception.kind, 'segregation_of_duties')
            with self._token(user, person=person):
                self.assertTrue(asset._two_gates_refusal('approve'))

    def test_the_administrator_gets_the_sentence_it_lifted(self):
        self._switch(True)
        self._earlier_gate(self.admin)
        asset = self.asset.with_user(self.admin)
        with self._token(self.admin):
            lifted = asset._assert_two_gates('approve')
            self.assertIsNone(asset._two_gates_refusal('approve'))
        self.assertTrue(lifted.startswith('You verified this unit on '))
        self.assertTrue(lifted.endswith('a different person must approve '
                                        'it.'), lifted)
        # Nothing to lift is not an override: their own gate again.
        with self._token(self.admin):
            self.assertIsNone(asset._assert_two_gates('verify'))
