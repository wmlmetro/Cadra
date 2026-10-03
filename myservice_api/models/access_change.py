"""The forward record of who was granted or removed from what, and by whom.

Specification §13.4 asks for "access changes for any user (per period)".
Handoff 23 measured six places that change could have been recorded and found
all six empty, for one reason: `res_groups_users_rel` is two integer columns,
`(gid, uid)`, with a primary key over both and `ON DELETE CASCADE` on each
foreign key. It carries no timestamp and no actor, so a grant writes nothing
that outlives it and a removal deletes the only evidence it ever happened.

That is a property of the schema and no query can work around it. The
reconstruction of PAST grants is NRS's decision — INT-10 §2.10b holds the
three options — but the forward record is not that decision, and every week
without one is a week of the register that can never be recovered.

So this model is the forward record. It is modelled on `nrs.asset.custody`
and shares its argument: `create`, `write` and `unlink` are guarded on the
model rather than by ACL, because an ACL is configuration and a record whose
whole value is that nobody can alter it must refuse the administrator too.


WHERE THE HOOKS GO, AND WHY IT IS NOT JUST `res.users.write`
------------------------------------------------------------

Handoff 14 was told the transfer route was the only writer of `custodian_id`;
an exhaustive search found six, and recording at the asserted single point
would have produced an audit record with invisible holes. So the writers were
enumerated before this was designed, and the handoff's own list was wrong in
three places. Measured against Odoo 19 core, not assumed:

1. **`res.users.write` with `group_ids`.** The obvious one, and the one the
   admin user form actually uses — `res_user_group_ids_field.js` collapses its
   sub-widgets into a single `(6, 0, ids)` command on the REAL field before the
   RPC. Odoo 19 deleted the reified `sel_groups_*` / `in_group_*` pseudo-fields
   entirely, so there is no longer a separate form path to miss.

2. **`res.users.create` with groups — and without them.** Every seed script,
   `auth_signup`'s `_create_user_from_template` (a `copy()`, and `group_ids` is
   `copy=True`) and the API client provisioner land here, not on `write`. Note
   that a create carrying NO group key still lands the user in `base.group_user`
   via `_default_groups()`, so the vals are not the truth — see the diffing
   note below.

3. **`res.groups.write` with `user_ids`.** The same change made from the other
   side. It never calls `res.users.write` — both directions converge only in
   the generic m2m flush in `orm/fields_relational.py`. `scripts/bootstrap.py`
   writes this way, and so do eight security XML files that re-apply on EVERY
   module upgrade rather than only on install.

4. **`res.groups.write` with `implied_ids`.** This is the one the handoff got
   backwards, and it matters most. On Odoo 15 the transitive closure was
   materialised into the membership table. **On Odoo 19 it is not:**
   `res.groups.all_implied_ids` is declared `compute='_compute_all_implied_ids'`
   with no `store=True`, and `res.users.all_group_ids` is computed at read time
   from it. So adding an implication grants every member of that group the
   rights of another group while writing **zero** rows to
   `res_groups_users_rel` — there are no "implied rows" for an auditor to ask
   about, only an implication edge.

   `res.config.settings` group toggles are this case, not case 1: `_apply_group`
   and `_remove_group` write `implied_ids` and never touch `res.users` at all.

   An implication change is therefore an effective-access change that a
   membership record would miss completely. It is recorded here as its own
   event rather than folded into the others, because it is genuinely a
   different fact: it moves what a group MEANS, not who is in it.

5. **`res.users.unlink`.** A cascade erases every membership row for that user.
   Without a hook the record would end mid-sentence, which is the same defect
   in a different place.

6. **`res.groups.create` with `user_ids` or `implied_ids`, and
   `res.groups.unlink`.** Found by a review AFTER this docstring first claimed
   the list was exhaustive at four — which is the failure CLAUDE.md describes,
   committed in the file warning against it. A security XML record can create a
   group already populated: `myservice_security/security/security_groups.xml`
   declares `group_security_admin` with both `implied_ids` and `user_ids` on
   the record, so on a cold install it never passes through `write`. And
   `ON DELETE CASCADE` sits on BOTH foreign keys of the relation, so deleting a
   group erases membership exactly as deleting a user does.

   **The list has now been wrong twice. Treat a seventh as likely, not
   impossible.**

What is deliberately NOT covered, and cannot be: raw SQL against the relation
table, and a direct `call_kw` from any client with RPC access. Both converge on
the ORM m2m flush, so only a database trigger would catch them — and a trigger
would still not see case 4, which never touches that table. The boundary is
stated here rather than implied, because a record that does not say where it
stops is the instrument this programme keeps finding.


WHY THE HOOKS DIFF THE MEMBERSHIP INSTEAD OF READING `vals`
-----------------------------------------------------------

Every hook snapshots the real membership before calling `super()` and compares
it with the real membership after. Parsing the command list in `vals` would be
wrong four separate ways: `(6, 0, ids)` does not say what it replaced,
`_default_groups()` puts a user in a group when the create carried no group key
at all, a `Command.link` on a row that already exists is a no-op that must not
produce a record, and an implication edge changes nothing in `vals` on the user
side. The diff is the only thing that reports what actually moved.

It also makes the eight upgrade-time security XML writes silent when they are
re-applying links that are already there, which is what stops this record
filling with noise on every module upgrade.
"""

from odoo import models, fields, api, _
from odoo import SUPERUSER_ID
from odoo.exceptions import UserError

from .role_names import role_alias

# The flag `_record` sets on itself. `create` refuses without it, so the single
# entry point is enforced by the model and not by the access rules — the same
# shape as `nrs.asset.custody` and `workflow.dispatch.log`, and for the same
# reason: an ACL is one bad merge away from being `1,1,1,1`.
ACCESS_CHANGE_APPEND_KEY = 'cadra_access_change_append'

# The context key a caller sets to say WHERE a change came from. Anything that
# does not set it lands on `direct`, the honest label for "somebody changed
# membership and did not say why".
ACCESS_CHANGE_SOURCE_KEY = 'cadra_access_change_source'

# The context key that suppresses recording. Set ONLY by the backfill-free
# install path below, never by application code: a switch that turns the record
# off is a hole in it, so it exists in exactly one place and is named for what
# it does.
ACCESS_CHANGE_SKIP_KEY = 'cadra_access_change_skip'

#: The actor written when a change cannot be attributed to a person. Report 23
#: measured 100% of the ACL stamps in this estate as `uid 1`, and a record that
#: renders those as "the system administrator granted this" is worse than no
#: record: it invents a person. An upgrade, a cron and the CLI all arrive as
#: SUPERUSER and all say so.
SYSTEM_ACTOR = '__system__'

ACCESS_EVENT_GRANTED = 'granted'
ACCESS_EVENT_REMOVED = 'removed'
ACCESS_EVENT_IMPLIED_ADDED = 'implied_added'
ACCESS_EVENT_IMPLIED_REMOVED = 'implied_removed'


# Translated at the call, not at import: `_()` evaluated at class-build time
# resolves against no context and freezes one language into the module. The
# string is a LITERAL inside the function because Odoo's PO extractor scans
# literal arguments and would never see a variable.
def _append_only_message():
    return _(
        "The access record is append-only. An access-change record cannot be "
        "edited or deleted once written — not through the interface, not over "
        "the API, and not as an administrator with sudo. The history is the "
        "evidence; correct the membership instead, which writes a new row."
    )


def _no_hand_written_rows_message():
    return _(
        "An access-change record cannot be created directly. Rows are written "
        "only as a side effect of group membership actually changing, so that "
        "the record says what happened rather than what somebody typed. "
        "Change the user's groups instead."
    )


class MyserviceApiAccessChange(models.Model):
    """One access change. Append-only, and it means it.

    `write` and `unlink` raise unconditionally, so the guard holds under
    `sudo()` too — which is the point: every API route in this codebase calls
    `sudo()` on every request, so a guard expressed as configuration would be
    exactly as strong as the promise that nobody ever calls it.
    """

    _name = 'myservice.api.access.change'
    _description = 'Access Change Record'
    # Chronological, because a record reads forwards. `id` breaks ties inside a
    # single transaction, where every row shares one timestamp.
    _order = 'changed_at, id'

    event = fields.Selection([
        (ACCESS_EVENT_GRANTED, 'Group granted'),
        (ACCESS_EVENT_REMOVED, 'Group removed'),
        # Not membership. The group's MEANING changed — see the module
        # docstring, case 4. Kept distinct so a reader counting grants is never
        # silently handed an implication edge.
        (ACCESS_EVENT_IMPLIED_ADDED, 'Implication added'),
        (ACCESS_EVENT_IMPLIED_REMOVED, 'Implication removed'),
    ], string='Event', required=True, index=True)

    # Null on the two implication events, which are about a pair of groups and
    # name no user. `ondelete='set null'` rather than cascade: deleting a user
    # must not erase the record of what they were given.
    user_id = fields.Many2one(
        'res.users', string='User', ondelete='set null', index=True)

    # The identity as it read AT THE TIME. A `res.users` can be deleted and the
    # m2o then goes null, so without these an append-only row could still be
    # emptied of its content from the outside — the same argument as the
    # custody chain's `*_name` columns, and the reason a deleted account still
    # leaves a legible history here.
    user_login = fields.Char(string='User Login (as recorded)')
    user_name = fields.Char(string='User Name (as recorded)')

    group_id = fields.Many2one(
        'res.groups', string='Group', ondelete='set null', index=True)
    group_name = fields.Char(string='Group (as recorded)')

    # The second group in an implication edge: `group_id` implies this one.
    # Null on the membership events.
    implied_group_id = fields.Many2one(
        'res.groups', string='Implied Group', ondelete='set null')
    implied_group_name = fields.Char(string='Implied Group (as recorded)')

    changed_at = fields.Datetime(
        string='Changed At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO MADE THE CHANGE. Null when the change cannot be attributed to a
    # person, in which case `actor` carries `__system__` and `attributable` is
    # False. The three are written together and never diverge.
    changed_by_id = fields.Many2one(
        'res.users', string='Changed By', ondelete='set null')
    # The acting account's LOGIN, snapshotted for the same reason the subject's
    # is: `changed_by_id` goes null when that account is deleted, and a display
    # name is not unique. Without this the actor survives deletion less well
    # than the person they acted on, which is the wrong way round on a record
    # whose purpose is saying who did it.
    changed_by_login = fields.Char(string='Changed By Login (as recorded)')
    actor = fields.Char(
        string='Actor (as recorded)', required=True, index=True,
        help="The acting user's name as it read at the time, or `__system__` "
             "for a change made by an upgrade, a cron or the command line.")
    attributable = fields.Boolean(
        string='Attributable', required=True, default=False, index=True,
        help="False when the change was made as SUPERUSER and cannot honestly "
             "be attributed to a person.")

    source = fields.Selection([
        ('user_write', 'User record — groups changed'),
        ('user_create', 'User record — created'),
        ('user_unlink', 'User record — deleted'),
        ('group_write', 'Group record — members changed'),
        ('group_implied', 'Group record — implication changed'),
        ('direct', 'Direct write'),
    ], string='Source', required=True, default='direct', index=True)

    # ── Append-only ───────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """Refuse a row that did not come from membership actually changing."""
        if not self.env.context.get(ACCESS_CHANGE_APPEND_KEY):
            raise UserError(_no_hand_written_rows_message())
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_append_only_message())

    def unlink(self):
        raise UserError(_append_only_message())

    # ── The measured start of the record ──────────────────────────────

    @api.model
    def record_starts_at(self):
        """The earliest row this tenant holds, or None.

        Read at request time and never cached, because the honest answer
        changes the moment the first change is recorded. It is deliberately
        NOT the migration date: a tenant upgraded and then left alone has a
        record that begins when something first happened on it, and claiming
        the upgrade instant would assert coverage of a period in which nothing
        was being written down.
        """
        row = self.sudo().search([], order='changed_at, id', limit=1)
        return row.changed_at or None

    # ── The single writer ─────────────────────────────────────────────

    @api.model
    def _resolve_actor(self):
        """Who to blame, honestly. Returns (user_id, label, attributable, login).

        `uid 1` is an upgrade, a cron or the CLI. It is never a person, and
        naming it "OdooBot" or "Administrator" would be an invention — so the
        row says `__system__` and flags itself unattributable rather than
        offering a name somebody could put in a finding.
        """
        uid = self.env.uid
        if not uid or uid == SUPERUSER_ID:
            return False, SYSTEM_ACTOR, False, False
        user = self.env['res.users'].sudo().browse(uid).exists()
        if not user:
            return False, SYSTEM_ACTOR, False, False
        return (user.id, user.name or user.login or SYSTEM_ACTOR, True,
                user.login or False)

    @api.model
    def _record(self, event, *, user=None, group=None, implied_group=None,
                source=None, changed_at=None):
        """Append one row. The only way a row is ever written."""
        changed_by_id, actor, attributable, actor_login = self._resolve_actor()
        vals = {
            'event': event,
            'user_id': user.id if user else False,
            'user_login': (user.login if user else False) or False,
            'user_name': (user.name if user else False) or False,
            'group_id': group.id if group else False,
            'group_name': (self._group_label(group) if group else False) or False,
            'implied_group_id': implied_group.id if implied_group else False,
            'implied_group_name': (
                self._group_label(implied_group) if implied_group else False) or False,
            'changed_at': changed_at or fields.Datetime.now(),
            'changed_by_id': changed_by_id,
            'changed_by_login': actor_login,
            'actor': actor,
            'attributable': attributable,
            'source': source or self.env.context.get(
                ACCESS_CHANGE_SOURCE_KEY) or 'direct',
        }
        return self.sudo().with_context(
            **{ACCESS_CHANGE_APPEND_KEY: True}).create(vals)

    @api.model
    def _record_many(self, rows):
        """Append several rows in one `create`, sharing one timestamp.

        Membership changes arrive in batches — a `(6, 0, ids)` command can
        add three groups and remove two in a single write — and they are one
        event in time. One `create` call keeps that true and keeps the write
        cost of the hooks proportional to what changed rather than to how many
        groups a user holds.
        """
        if not rows:
            return self.browse()
        changed_by_id, actor, attributable, actor_login = self._resolve_actor()
        now = fields.Datetime.now()
        vals_list = []
        for row in rows:
            user = row.get('user')
            group = row.get('group')
            implied = row.get('implied_group')
            vals_list.append({
                'event': row['event'],
                'user_id': user.id if user else False,
                'user_login': (user.login if user else False) or False,
                'user_name': (user.name if user else False) or False,
                'group_id': group.id if group else False,
                'group_name': (self._group_label(group) if group else False) or False,
                'implied_group_id': implied.id if implied else False,
                'implied_group_name': (
                    self._group_label(implied) if implied else False) or False,
                'changed_at': row.get('changed_at') or now,
                'changed_by_id': changed_by_id,
                'changed_by_login': actor_login,
                'actor': actor,
                'attributable': attributable,
                'source': row.get('source') or 'direct',
            })
        return self.sudo().with_context(
            **{ACCESS_CHANGE_APPEND_KEY: True}).create(vals_list)

    @api.model
    def _group_label(self, group):
        """`full_name` where it exists, `name` otherwise.

        `full_name` is a non-stored compute contributed by `base`, and reading
        it on a group whose category was deleted can come back empty. The
        snapshot must never be blank, so it falls back rather than trusting it.
        """
        if not group:
            return False
        group = group.sudo()
        # `full_name` is a non-stored compute contributed by `base`; on a group
        # whose category was deleted it can come back empty, which is a value
        # problem rather than an exception. Narrow by design — handoff 15
        # classified fifty broad handlers in this tree and 24 were hiding a
        # live fault, so this one does not catch anything.
        # The published alias first (handoff 44 §3), so the record names
        # `base.group_system` as the refusal and `/users` do. Rows written
        # before 2026-10-02 keep the name they were written with.
        return role_alias(group) or group.full_name or group.name
