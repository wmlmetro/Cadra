"""§13.4's fourth standard audit report: access changes for any user, per period.

**Read the boundary before the rows.** Cadra does not hold a change log of
who was granted or removed from what. That is not a gap in this report — it
is a gap in the record this report reads, and the honest thing to do with it
is publish it on the report's own face rather than in a document nobody
opens beside the answer.

What the record physically cannot support, measured on this deployment
rather than asserted:

* **A group grant leaves no trace at all.** `res_groups_users_rel` is two
  integer columns, `(gid, uid)`, and that is the whole table — no
  `create_date`, no `create_uid`, no `write_date`, no `write_uid`. Odoo
  models group membership as pure present tense. Even a willingness to
  accept "current state plus timestamps" instead of a history gets nothing,
  because the row itself records neither when the grant happened nor who
  made it.
* **The field carries no tracking.** `res.users.group_ids` is declared in
  Odoo core with no `tracking=`, so nothing reaches `mail.tracking.value`,
  so there is no chatter history to roll back the way the asset snapshot
  rolls back `custodian_id`.
* **`ir_logging` is empty** on every tenant, because `log_db` is not set in
  `config/odoo.19.conf` and never has been.
* **No audit module is installed or vendored** — `oca-19/` carries one
  module and it is `web_responsive`; none of the 23 modules in `crnd-19/`
  is an audit log.

So the report does NOT invent a history. It reports the access events it can
actually evidence — an account created, an account last modified — each one
carrying what it is evidence OF and how precise it is, and it states in
words that group grants are not among them.

**Every one of those four claims is re-measured on each request** rather
than hard-coded, by `access_change_fidelity()`. If somebody adds
`tracking=True` to the groups field next year, or installs an audit module,
this report notices and says so instead of continuing to publish a
limitation that has stopped being true. A boundary that is a constant is a
boundary that goes stale silently, which is the defect the whole INT-10
document exists to argue against.

It never writes. That is an acceptance criterion, not an aspiration:
`myservice_api/tests/test_audit_access_report.py` fingerprints before and
after.
"""
from odoo import api, fields, models


#: How much of the requested period this report can speak for, as one value a
#: renderer can branch on. `none` is the honest answer on every deployment
#: today and `partial` exists so that the day somebody adds tracking, the
#: report can say so without a code change to the consumer.
#:
#: `empty` and `none` are different and the distinction is the same one the
#: disposal report makes: `empty` means the period holds no events, `none`
#: means the record cannot hold them at all. Collapsing the two would let a
#: quiet quarter be rendered as "Cadra keeps no access log", and a deployment
#: with no access log be rendered as "nothing happened".
ACCESS_COVERAGE_EMPTY = 'empty'
ACCESS_COVERAGE_NONE = 'none'
ACCESS_COVERAGE_PARTIAL = 'partial'

#: An access event this report can evidence, and what the evidence IS.
#: `precision` is the part an auditor needs: `exact` means the timestamp and
#: the actor are the event's own, `last_write_only` means the row carries one
#: stamp covering every change ever made to it and this is the most recent.
ACCESS_EVENT_CREATED = 'account_created'
ACCESS_EVENT_MODIFIED = 'account_modified'

#: Users that are not people and not integrations. Excluded from the roster
#: by default because an auditor asking "who has access" is not asking about
#: the ORM's own uid 1, and four rows of framework plumbing at the top of
#: every answer is how a report teaches its reader to skim.
_STRUCTURAL_LOGINS = ('__system__', 'public', 'portaltemplate', 'default')


class ResUsersAccessReport(models.Model):
    _inherit = 'res.users'

    # ── the boundary ────────────────────────────────────────────────

    @api.model
    def _access_groups_field(self):
        """`group_ids` on Odoo 19, `groups_id` before it. Neither assumed."""
        for name in ('group_ids', 'groups_id'):
            if name in self._fields:
                return name
        return None

    @api.model
    def _access_membership_table_columns(self):
        """What the membership table can physically record. Measured.

        This is the finding, and it is a schema fact rather than an opinion:
        if the answer is `{'gid', 'uid'}` then no amount of querying will
        produce a grant history, because the grant does not write anything
        that outlives it.
        """
        field = self._access_groups_field()
        if not field:
            return set()
        relation = self._fields[field].relation
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s", (relation,))
        return {row[0] for row in self.env.cr.fetchall()}

    @api.model
    def _access_tracking_rows(self):
        """How many chatter tracking rows exist on users and on groups.

        Zero on every tenant today. Counted rather than assumed, because a
        report whose stated limitation is a constant cannot notice the day
        the limitation is lifted.
        """
        self.env.cr.execute("""
            SELECT count(*) FROM mail_tracking_value tv
              JOIN mail_message m ON m.id = tv.mail_message_id
             WHERE m.model IN ('res.users', 'res.groups')
        """)
        return self.env.cr.fetchone()[0]

    @api.model
    def _access_logging_rows(self):
        """`ir_logging`, which is empty unless `log_db` is configured."""
        self.env.cr.execute("SELECT count(*) FROM ir_logging")
        return self.env.cr.fetchone()[0]

    @api.model
    def access_change_fidelity(self):
        """What this report can and cannot say, re-measured every request."""
        field = self._access_groups_field()
        columns = self._access_membership_table_columns()
        audit_columns = sorted(
            columns & {'create_date', 'create_uid', 'write_date', 'write_uid'})
        # `getattr`, not attribute access: `tracking` is contributed by the
        # `mail` module to the field types that support it, and a plain
        # Many2many in Odoo 19 does not carry the attribute at all. Reading
        # it directly is an AttributeError, which is a 500 on a report whose
        # entire job is to state a limitation accurately.
        tracked = bool(field and getattr(self._fields[field], 'tracking', False))
        tracking_rows = self._access_tracking_rows()
        logging_rows = self._access_logging_rows()

        recoverable = [
            'account_created', 'account_created_by', 'account_modified_at',
            'account_modified_by', 'account_active', 'current_group_membership',
            'current_api_scopes',
        ]
        not_recoverable = [
            'group_granted', 'group_removed', 'group_change_actor',
            'group_change_timestamp', 'which_field_a_modification_changed',
            'previous_values', 'deleted_accounts', 'password_changes',
            'login_history',
        ]

        notes = {
            'membership': (
                "Group membership is stored in `%s`, whose columns on this "
                "deployment are: %s. It carries no timestamp and no actor, so "
                "a grant or a removal writes nothing that outlives it. This "
                "is the reason the report lists no group changes, and it is a "
                "property of the schema rather than of the query."
                % (field and self._fields[field].relation or 'unknown',
                   ", ".join(sorted(columns)) or 'none')),
            'tracking': (
                "`res.users.%s` carries %s on this deployment, and there are "
                "%d chatter tracking rows across `res.users` and `res.groups` "
                "combined. Without tracking there is no history to roll back "
                "the way the asset register snapshot rolls back a custodian."
                % (field or 'the groups field',
                   'tracking=True' if tracked else 'NO tracking',
                   tracking_rows)),
            'logging': (
                "`ir_logging` holds %d rows. Odoo writes to it only when "
                "`log_db` is set in the server configuration; it is not set "
                "in `config/odoo.19.conf`, so this table has always been "
                "empty and will stay empty until that changes."
                % logging_rows),
            'account_modified': (
                "An `account_modified` event says only that SOMETHING on the "
                "user record changed at that moment, by that actor. The row "
                "carries one write stamp covering every change ever made to "
                "it, so this is the MOST RECENT change and not a list of "
                "them, and it does not say which field moved. A timezone "
                "edit and a group grant are indistinguishable here."),
            'structural_users': (
                "Odoo's own non-human accounts (%s) are excluded from the "
                "roster and from the events."
                % ", ".join(_STRUCTURAL_LOGINS)),
            'deleted_accounts': (
                "A user deleted since the requested date cannot be "
                "reconstructed and leaves no tombstone. The roster is "
                "therefore a LOWER BOUND on who held access during the "
                "period."),
        }

        return {
            'recoverable': recoverable,
            'not_recoverable': not_recoverable,
            'groups_field': field,
            'groups_field_tracked': tracked,
            'membership_audit_columns': audit_columns,
            'tracking_rows': tracking_rows,
            'logging_rows': logging_rows,
            'notes': notes,
        }

    # ── the statement above the table ───────────────────────────────

    @api.model
    def _access_change_coverage(self, events, fidelity):
        """One enum plus the English for it, correct in all three cases.

        Branch on `coverage`, never on `statement` — the wording may be
        improved, the enum may not. Deliberately NOT run through `_()`: this
        is a published API payload, and a value that changes with the acting
        user's language is not something a consumer can store, diff or
        reconcile against last quarter's run.
        """
        has_history = bool(
            fidelity['groups_field_tracked']
            or fidelity['membership_audit_columns']
            or fidelity['tracking_rows'])

        if has_history:
            return ACCESS_COVERAGE_PARTIAL, (
                "This deployment has grown an access history since this "
                "report was written — see `fidelity` for which of the three "
                "sources is now populated. The events below still come from "
                "account create and write stamps only; the new source is NOT "
                "yet read, and until it is, this report understates what the "
                "database holds.")
        if not events:
            return ACCESS_COVERAGE_NONE, (
                "Cadra holds no record of access changes, and no account was "
                "created or modified in this period either. Group grants and "
                "removals are not recorded anywhere in this system: the "
                "membership table stores no timestamp and no actor, and the "
                "groups field carries no tracking. This report can speak for "
                "NO period, and the empty table below is a statement about "
                "the record rather than about the estate.")
        return ACCESS_COVERAGE_NONE, (
            "Cadra holds no record of group grants or removals — the "
            "membership table stores no timestamp and no actor, and the "
            "groups field carries no tracking, so no query against this "
            "database can produce them. The %d event(s) below are the access "
            "events that ARE evidenced: accounts created, and accounts whose "
            "record was last modified, in the requested period. An "
            "`account_modified` row does not say which field changed."
            % len(events))

    # ── the rows ────────────────────────────────────────────────────

    @api.model
    def _access_report_domain(self):
        """Real accounts only, active or not — a deactivated account that
        held access during the period is exactly what an auditor is asking
        about, so `active_test` is off rather than filtered."""
        return [('login', 'not in', list(_STRUCTURAL_LOGINS))]

    @api.model
    def _access_actor(self, user):
        return {'id': user.id, 'name': user.name} if user else None

    @api.model
    def access_change_report(self, date_from, date_to):
        """Access events in `[date_from, date_to]`, both bounds inclusive.

        Returns `{'events', 'roster', 'summary', 'fidelity'}`. Reads only;
        `test_audit_access_report.py` fingerprints the tables to prove it.
        """
        fidelity = self.access_change_fidelity()
        users = self.sudo().with_context(active_test=False).search(
            self._access_report_domain(), order='id')

        # Inclusive of the whole closing day: a period given as dates must
        # not silently exclude everything that happened on its last one.
        start = fields.Datetime.to_datetime(date_from)
        end = fields.Datetime.to_datetime(date_to).replace(
            hour=23, minute=59, second=59)

        groups_field = fidelity['groups_field']
        events = []
        roster = []
        for user in users:
            member_of = sorted(
                (user[groups_field] if groups_field else user.browse()
                 ).mapped('full_name' if 'full_name' in
                          self.env['res.groups']._fields else 'name'))
            client = self.env['myservice.api.client'].sudo().search(
                [('user_id', '=', user.id)], limit=1)
            roster.append({
                'user_id': user.id,
                'login': user.login,
                'name': user.name,
                'active': user.active,
                'is_api_client': bool(client),
                'api_scopes': (client.scopes or '').split() if client else [],
                'groups': member_of,
                'created_at': user.create_date,
                'created_by': self._access_actor(user.create_uid),
                'last_modified_at': user.write_date,
                'last_modified_by': self._access_actor(user.write_uid),
            })

            if user.create_date and start <= user.create_date <= end:
                events.append({
                    'event': ACCESS_EVENT_CREATED,
                    'precision': 'exact',
                    'at': user.create_date,
                    'actor': self._access_actor(user.create_uid),
                    'user_id': user.id,
                    'login': user.login,
                    'evidence': 'res_users.create_date / create_uid',
                    'groups_now': member_of,
                })
            # Only when it is a genuinely later write: Odoo stamps both
            # columns in the creating transaction, so an untouched account
            # would otherwise report a modification it never had.
            if (user.write_date and user.create_date
                    and (user.write_date - user.create_date).total_seconds() > 2
                    and start <= user.write_date <= end):
                events.append({
                    'event': ACCESS_EVENT_MODIFIED,
                    'precision': 'last_write_only',
                    'at': user.write_date,
                    'actor': self._access_actor(user.write_uid),
                    'user_id': user.id,
                    'login': user.login,
                    'evidence': 'res_users.write_date / write_uid',
                    'groups_now': member_of,
                })

        events.sort(key=lambda e: (e['at'], e['user_id'], e['event']))
        coverage, statement = self._access_change_coverage(events, fidelity)
        return {
            'events': events,
            'roster': roster,
            'summary': {
                'accounts': len(roster),
                'accounts_active': sum(1 for r in roster if r['active']),
                'events_in_period': len(events),
                'group_changes_in_period': 0,
                'coverage': coverage,
                'statement': statement,
            },
            'fidelity': fidelity,
        }
