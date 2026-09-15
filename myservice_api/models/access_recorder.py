"""The hooks that make group membership a recorded fact.

Four overrides on two core models, because the membership relation is writable
from four structurally different directions and only one of them is
`res.users.write`. The enumeration and the evidence for each are in the module
docstring of `access_change.py`; this file is the mechanism.

Every hook has the same shape:

    before = snapshot()
    result = super()...
    after  = snapshot()
    record(after - before, before - after)

It diffs the real relation rather than reading `vals`, which is what makes it
correct for `(6, 0, ids)` replacements, for `_default_groups()` putting a user
in a group the create never mentioned, and for the eight security XML files
that re-link existing rows on every module upgrade — those produce an empty
diff and therefore no rows, which is what keeps the record free of upgrade
noise.

**Nothing here changes who may grant what.** This is a record, not a mechanism:
no hook refuses a write, no hook alters one, and removing the whole file would
leave every access decision in this system exactly as it is.
"""

from odoo import models, api

from .access_change import (
    ACCESS_CHANGE_SKIP_KEY,
    ACCESS_EVENT_GRANTED,
    ACCESS_EVENT_IMPLIED_ADDED,
    ACCESS_EVENT_IMPLIED_REMOVED,
    ACCESS_EVENT_REMOVED,
)

#: The field names, resolved rather than assumed. Odoo 19 renamed the user side
#: from `groups_id` to `group_ids` and the group side from `users` to
#: `user_ids`; the 15-era spelling is still what a reader expects, so both are
#: probed and the first that exists wins. `audit_access.py` does the same thing
#: for the same reason.
_USER_GROUPS_FIELDS = ('group_ids', 'groups_id')
_GROUP_USERS_FIELDS = ('user_ids', 'users')


def _field_name(record_set, candidates):
    for name in candidates:
        if name in record_set._fields:
            return name
    return None


class ResUsersAccessRecorder(models.Model):
    """Records membership changes made from the user side."""

    _inherit = 'res.users'

    def _access_groups_field_name(self):
        return _field_name(self, _USER_GROUPS_FIELDS)

    def _access_membership_snapshot(self):
        """{user_id: frozenset(group_ids)} for this recordset.

        `sudo()` because the recorder must see the whole truth regardless of
        who is acting — a user who cannot read `res.groups` would otherwise
        produce a diff that says groups were removed when they were only
        invisible, which is a fabricated removal in an append-only record.
        """
        field = self._access_groups_field_name()
        if not field:
            return {}
        snapshot = {}
        for user in self.sudo():
            snapshot[user.id] = frozenset(user[field].ids)
        return snapshot

    def _access_record_diff(self, before, after, source):
        """Turn two snapshots into rows. The only place events are decided."""
        if self.env.context.get(ACCESS_CHANGE_SKIP_KEY):
            return
        rows = []
        Users = self.env['res.users'].sudo()
        Groups = self.env['res.groups'].sudo()
        for user_id, after_groups in after.items():
            before_groups = before.get(user_id, frozenset())
            granted = after_groups - before_groups
            removed = before_groups - after_groups
            if not granted and not removed:
                continue
            user = Users.browse(user_id).exists()
            for group in Groups.browse(sorted(granted)).exists():
                rows.append({'event': ACCESS_EVENT_GRANTED, 'user': user,
                             'group': group, 'source': source})
            for group in Groups.browse(sorted(removed)).exists():
                rows.append({'event': ACCESS_EVENT_REMOVED, 'user': user,
                             'group': group, 'source': source})
        # A user that vanished between the two snapshots — the unlink case —
        # is handled by its own hook, which snapshots identity before the row
        # is gone. Nothing to do here.
        if rows:
            self.env['myservice.api.access.change']._record_many(rows)

    @api.model_create_multi
    def create(self, vals_list):
        """Records the groups a new account lands in.

        Read from the created records rather than from `vals`, because
        `_default_groups()` puts every new user in `base.group_user` (plus
        whatever `base.default_user_group` implies) whether or not the create
        mentioned groups at all — and `auth_signup` creates users by `copy()`
        of a template, where the groups are cloned and never appear in `vals`
        either. The vals are not the truth; the resulting membership is.
        """
        users = super().create(vals_list)
        after = users._access_membership_snapshot()
        # Everything is new, so `before` is empty for every one of them and
        # the diff is the whole membership.
        users._access_record_diff({}, after, 'user_create')
        return users

    def write(self, vals):
        """Records a membership change made on the user record.

        Guarded on the groups key being present: a write that cannot move
        membership must not pay for two snapshots, and `res.users.write` is on
        the path of every login (`login_date`) and every preference change.
        """
        field = self._access_groups_field_name()
        touches_groups = bool(field and field in vals)
        before = self._access_membership_snapshot() if touches_groups else None
        result = super().write(vals)
        if touches_groups:
            after = self._access_membership_snapshot()
            self._access_record_diff(before, after, 'user_write')
        return result

    def unlink(self):
        """Records the removals a cascade is about to make invisible.

        `res_groups_users_rel` has `ON DELETE CASCADE` on both foreign keys, so
        deleting a user silently erases every membership row they had. Without
        this the record would end mid-sentence: an auditor would see the grants
        and never the fact that the account and all its access went away.

        The identity snapshots (`user_login`, `user_name`) are taken here,
        while the user still exists, which is what makes a deleted account's
        history still legible afterwards.
        """
        before = self._access_membership_snapshot()
        users = {u.id: u for u in self.sudo()}
        rows = []
        Groups = self.env['res.groups'].sudo()
        if not self.env.context.get(ACCESS_CHANGE_SKIP_KEY):
            for user_id, groups in before.items():
                user = users.get(user_id)
                for group in Groups.browse(sorted(groups)).exists():
                    rows.append({'event': ACCESS_EVENT_REMOVED, 'user': user,
                                 'group': group, 'source': 'user_unlink'})
        if rows:
            self.env['myservice.api.access.change']._record_many(rows)
        return super().unlink()


class ResGroupsAccessRecorder(models.Model):
    """Records changes made from the group side — both kinds."""

    _inherit = 'res.groups'

    def _access_users_field_name(self):
        return _field_name(self, _GROUP_USERS_FIELDS)

    def _access_group_snapshot(self):
        """{group_id: (frozenset(user_ids), frozenset(implied_group_ids))}."""
        users_field = self._access_users_field_name()
        snapshot = {}
        for group in self.sudo():
            members = frozenset(group[users_field].ids) if users_field else frozenset()
            implied = frozenset(group.implied_ids.ids) if 'implied_ids' in self._fields else frozenset()
            snapshot[group.id] = (members, implied)
        return snapshot

    def write(self, vals):
        """Records membership and implication changes made on a group.

        Two different facts, deliberately kept apart:

        * `user_ids` is membership, and this is the SAME change as
          `res.users.write` made from the other side. It never passes through
          `res.users.write`, so without this hook `scripts/bootstrap.py` and
          eight security XML files that re-run on every module upgrade would
          all be invisible.

        * `implied_ids` is not membership at all. On Odoo 19
          `res.groups.all_implied_ids` is an unstored compute, so adding an
          implication grants every member of this group the rights of another
          group while writing zero rows to the membership table. It is
          recorded as its own event because an effective-access change that
          leaves no membership row is exactly the hole this record exists to
          close — and because `res.config.settings` group toggles are this
          case rather than the membership one.
        """
        users_field = self._access_users_field_name()
        touches = bool(
            (users_field and users_field in vals) or ('implied_ids' in vals))
        before = self._access_group_snapshot() if touches else None
        result = super().write(vals)
        if touches and not self.env.context.get(ACCESS_CHANGE_SKIP_KEY):
            after = self._access_group_snapshot()
            rows = []
            Users = self.env['res.users'].sudo()
            Groups = self.env['res.groups'].sudo()
            for group_id, (after_users, after_implied) in after.items():
                before_users, before_implied = before.get(
                    group_id, (frozenset(), frozenset()))
                group = Groups.browse(group_id).exists()
                for user in Users.browse(
                        sorted(after_users - before_users)).exists():
                    rows.append({'event': ACCESS_EVENT_GRANTED, 'user': user,
                                 'group': group, 'source': 'group_write'})
                for user in Users.browse(
                        sorted(before_users - after_users)).exists():
                    rows.append({'event': ACCESS_EVENT_REMOVED, 'user': user,
                                 'group': group, 'source': 'group_write'})
                for implied in Groups.browse(
                        sorted(after_implied - before_implied)).exists():
                    rows.append({'event': ACCESS_EVENT_IMPLIED_ADDED,
                                 'group': group, 'implied_group': implied,
                                 'source': 'group_implied'})
                for implied in Groups.browse(
                        sorted(before_implied - after_implied)).exists():
                    rows.append({'event': ACCESS_EVENT_IMPLIED_REMOVED,
                                 'group': group, 'implied_group': implied,
                                 'source': 'group_implied'})
            if rows:
                self.env['myservice.api.access.change']._record_many(rows)
        return result
