"""The combinations of roles nobody may be granted — Addendum A §4, rule 2.

Handoff 58 §5. Rule 1 — nobody fires two gates on one unit — is per record
and lives with the gates (`asset_gates._assert_two_gates`). Rule 2 stops the
wrong combination being GRANTED in the first place: a person who is both the
Register Maker and the Register Checker can be refused at every unit, but
should not hold the pair at all.

THE TABLE
---------
`nrs.role.exclusion` — two groups, `active`, and a `reason` in words. Seeded
(`data/role_exclusions.xml`, noupdate, so an owner's edit survives an
upgrade) with the addendum's defaults:

* Store with any IAD, Asset Controller, Tag-Issuing Unit, Register Maker or
  Register Checker role — six rows. **Store is the Asset Officer**, the role
  that holds `assets:write` and so fires the receipt gate. NOT Asset User:
  every gate role IMPLIES Asset User (`asset_security.xml`), and a human
  tagger holds Asset User beside the Tag-Issuing Unit by ruling (handoff
  41), so an exclusion on Asset User would forbid every gate role to every
  person who holds one.
* Register Maker with Register Checker.
* IAD Officer with IAD Approver.

WHERE IT IS ENFORCED
--------------------
On the model, under every writer of membership, beside `access_guard.py` —
the same six doors that file names, judged the same way: snapshot, write,
snapshot, judge, raise. Judged on EFFECTIVE membership (`all_group_ids`,
implication included), so an Asset Manager — who implies the Asset Officer —
is refused an IAD role exactly as an Officer is. Only a pair the write
CREATES is refused: a person who already holds a forbidden pair is not
revoked (§5) and may still be granted something unrelated.

Unlike `access_guard.py`, this is NOT only the API's rule: the back office
meets it too, because a role combination is wrong whoever grants it. Two
things are deliberately outside it:

* **An API credential's user.** Its groups are derived mechanically from its
  scopes (`utils.groups_for_scopes`, CLAUDE.md rule 7) and grant the token
  nothing; refusing them would make every scope edit fail. The no-two-gates
  rule still holds for a credential, per unit.
* **Module install and upgrade** (`registry.ready` is false): an upgrade
  re-applies security XML and must never be refused by a table an owner
  edited.

A refusal is an `AccessError` — `403 forbidden` on the API with the sentence
as the message, a dialog in the back office — and an exception rolls the
write back, the access record's rows included.

THE CONFIGURATION RECORD
------------------------
Every create and change writes `cadra.role_exclusion.<id>` — the row the
configuration-change report shows (it reads `ir.config_parameter` and
nothing else), with the person and the time. Nothing reads it back.
"""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .access_guard import _role_name, forget_group_memberships

CONFIG_KEY = 'cadra.role_exclusion.%d'


class NRSRoleExclusion(models.Model):
    _name = 'nrs.role.exclusion'
    # Self-labelled like every model a credential can create (handoff 26): a
    # `settings:write` credential creates rows through `POST
    # /settings/role-exclusions`, and a test's row must say so on its face.
    _inherit = ['cadra.test.fixture.mixin']
    _description = 'Role exclusion (roles no one person may hold together)'
    _order = 'id'

    group_a = fields.Many2one('res.groups', string='Role', required=True,
                              ondelete='cascade', index=True)
    group_b = fields.Many2one('res.groups', string='Cannot be held with',
                              required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True)
    reason = fields.Text(required=True,
                         help='Why one person may not hold both — said in '
                              'every refusal.')

    @api.constrains('group_a', 'group_b', 'reason')
    def _check_pair(self):
        for rec in self:
            if rec.group_a == rec.group_b:
                raise ValidationError(_(
                    'A role cannot exclude itself.'))
            if not (rec.reason or '').strip():
                raise ValidationError(_(
                    'An exclusion needs a reason, in words.'))
            twin = self.with_context(active_test=False).search_count([
                ('id', '!=', rec.id),
                '|', '&', ('group_a', '=', rec.group_a.id),
                          ('group_b', '=', rec.group_b.id),
                     '&', ('group_a', '=', rec.group_b.id),
                          ('group_b', '=', rec.group_a.id)])
            if twin:
                raise ValidationError(_(
                    '%(a)s and %(b)s already have an exclusion; change that '
                    'one instead.', a=_role_name(rec.group_a),
                    b=_role_name(rec.group_b)))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._record_configuration()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'active', 'reason', 'group_a', 'group_b'} & set(vals):
            self._record_configuration()
        return result

    def _record_configuration(self):
        Params = self.env['ir.config_parameter'].sudo()
        for rec in self:
            Params.set_param(CONFIG_KEY % rec.id, '%s; %s × %s; %s' % (
                'on' if rec.active else 'off', _role_name(rec.group_a),
                _role_name(rec.group_b), (rec.reason or '').strip()))

    # ── who holds a forbidden pair now ────────────────────────────────

    @api.model
    def _credential_user_ids(self):
        return set(self.env['myservice.api.client'].sudo().with_context(
            active_test=False).search([]).mapped('user_id').ids)

    def _holders(self, users=None):
        """`{exclusion_id: res.users}` — the PEOPLE (credentials left out)
        holding both roles of each exclusion in `self`, effective."""
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        credentials = self._credential_user_ids()
        out = {}
        for rec in self:
            domain = [('all_group_ids', 'in', rec.group_a.ids),
                      ('share', '=', False)]
            if users is not None:
                domain.append(('id', 'in', users.ids))
            holders = Users.search(domain).filtered(
                lambda u: rec.group_b in u.all_group_ids
                and u.id not in credentials)
            out[rec.id] = holders
        return out


def _forbidden_pairs(env, group_ids):
    """The ACTIVE exclusions both of whose roles are in `group_ids`.

    `active` named in the domain, never left to `active_test`: the Users
    routes look people up with `active_test=False` (a deactivated account is
    still somebody you can manage), the write inherits that context, and an
    exclusion that was switched off went on refusing grants — found by
    `tests/test_gates_kept.py` switching one off over HTTP."""
    exclusions = env['nrs.role.exclusion'].sudo().with_context(
        active_test=False).search([('active', '=', True)])
    return exclusions.filtered(
        lambda x: x.group_a.id in group_ids and x.group_b.id in group_ids)


def _exclusion_message(exclusion):
    return _(
        "%(a)s and %(b)s cannot be held by one person: %(reason)s "
        "(Role exclusion — Settings → Role exclusions.)",
        a=_role_name(exclusion.group_a), b=_role_name(exclusion.group_b),
        reason=(exclusion.reason or '').strip().rstrip('.') + '.')


def _judge(env, users, before):
    """Raise for the first person whose write CREATED a forbidden pair."""
    if not env.registry.ready:
        return
    credentials = env['nrs.role.exclusion']._credential_user_ids()
    prefix = env['myservice.api.client'].CLIENT_USER_LOGIN_PREFIX
    for user in users.sudo():
        # The login prefix as well as the link: `_provision_client_user`
        # creates the user BEFORE the client row that names it exists, so a
        # brand-new credential (bootstrap on a fresh database, CI, a client's
        # first bring-up) would otherwise be judged as a person and refused —
        # found by the verification pass. Only an administrator in the back
        # office can choose such a login for a person; said in DECISIONS.
        if user.id in credentials or user.share \
                or (user.login or '').startswith(prefix):
            continue
        now = set(user.all_group_ids.ids)
        was = before.get(user.id, set())
        for exclusion in _forbidden_pairs(env, now):
            pair = {exclusion.group_a.id, exclusion.group_b.id}
            if not pair <= was:
                # The membership just read is cached with the groups the
                # rollback is about to undo (handoff 66).
                forget_group_memberships(env)
                raise AccessError(_exclusion_message(exclusion))


def _effective_snapshot(users):
    return {u.id: set(u.all_group_ids.ids) for u in users.sudo()}


class ResUsersRoleExclusion(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        _judge(self.env, users, {})
        return users

    def write(self, vals):
        judge = 'group_ids' in vals
        before = _effective_snapshot(self) if judge else None
        result = super().write(vals)
        if judge:
            self.invalidate_recordset(['all_group_ids'])
            _judge(self.env, self, before)
        return result


class ResGroupsRoleExclusion(models.Model):
    _inherit = 'res.groups'

    def write(self, vals):
        judge = 'user_ids' in vals
        # The members now AND the people the commands name: a person linked
        # from this side is not a member yet, and without their own "before"
        # a pair they already held would read as one this write created.
        named = set()
        for cmd in (vals.get('user_ids') or []) if judge else []:
            if isinstance(cmd, int):
                named.add(cmd)
            elif isinstance(cmd, (list, tuple)) and cmd:
                if cmd[0] == 4 and len(cmd) > 1:
                    named.add(cmd[1])
                elif cmd[0] == 6 and len(cmd) > 2:
                    named.update(cmd[2] or [])
        before_users = (self.sudo().user_ids
                        | self.env['res.users'].sudo().browse(sorted(named))
                        ) if judge else None
        before = _effective_snapshot(before_users) if judge else None
        result = super().write(vals)
        if judge:
            users = self.sudo().user_ids | before_users
            users.invalidate_recordset(['all_group_ids'])
            _judge(self.env, users, before)
        return result
