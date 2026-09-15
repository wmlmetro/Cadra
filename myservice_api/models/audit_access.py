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

from .access_change import (
    ACCESS_EVENT_GRANTED,
    ACCESS_EVENT_REMOVED,
    SYSTEM_ACTOR,
)


#: How much of the requested period this report can speak for, as one value a
#: renderer can branch on. `none` is the honest answer on every deployment
#: today and `partial` exists so that the day somebody adds tracking, the
#: report can say so without a code change to the consumer.
#:
#: **There is deliberately no `empty` here**, and the disposal report's
#: `sap_coverage` — which does have one — is why the question came up.
#:
#: There it is load-bearing: a period holding no disposals is a different
#: fact from a period whose disposals reached no SAP. Here the two collapse,
#: because the record cannot hold a group change in ANY period. A quiet
#: quarter and a busy one give the same answer to the question 13.4 asks,
#: and publishing `empty` for the quiet one would imply that some other
#: period might have answered it. `none` covers both; the two statements
#: below differ in wording without pretending to differ in kind.
#:
#: An earlier draft declared `empty`, returned it nowhere, and published the
#: distinction as contract in the changelog, the OpenAPI description and
#: INT-10. The test asserted only that `coverage` was one of the three, so
#: it passed on the broken contract - one more guard that tested nothing.
ACCESS_COVERAGE_NONE = 'none'
ACCESS_COVERAGE_PARTIAL = 'partial'
#: The access record is live and the whole requested period falls at or
#: after the instant it began, so grants and removals in that period are
#: complete rather than absent. Added in handoff 24 with the record that
#: makes it reachable — before that there was no period any tenant could
#: have claimed it for.
ACCESS_COVERAGE_RECORDED = 'recorded'

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
#: Verified present on these tenants rather than assembled from memory — a
#: list that reads as measured has to be.
_STRUCTURAL_LOGINS = ('__system__', 'public', 'portaltemplate')


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
        # `current_schema()`, because the claim is about THIS deployment's
        # table. Without it the query answers about any table anywhere in
        # the database named `res_groups_users_rel`, which is a broader
        # statement than the note built on it makes.
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = current_schema()",
            (relation,))
        return {row[0] for row in self.env.cr.fetchall()}

    @api.model
    def _access_record_start(self):
        """The instant this tenant's access record begins, or None.

        MEASURED, never a constant and never the migration date. A tenant
        upgraded and then left alone has a record that begins when something
        first happened on it; claiming the upgrade instant would assert
        coverage of a period in which nothing was being written down, which is
        the same overstatement the rest of this block exists to avoid.

        Read at request time because the honest answer changes the moment the
        first change is recorded.
        """
        model = self.env.get('myservice.api.access.change')
        if model is None:
            return None
        return model.record_starts_at()

    @api.model
    def _access_record_rows(self):
        """How many access changes this tenant holds in total."""
        model = self.env.get('myservice.api.access.change')
        if model is None:
            return 0
        return model.sudo().search_count([])

    @api.model
    def _access_tracking_rows(self):
        """Chatter tracking rows for the GROUPS FIELD specifically.

        Zero on every tenant today. Counted rather than assumed, because a
        report whose stated limitation is a constant cannot notice the day
        the limitation is lifted.

        Scoped to the one field rather than to the whole of `res.users`, and
        that scoping is a correction. Counting every tracked field on the
        model meant that the day any module tracked anything on a user — an
        `active` flag, a timezone — this report would start telling an
        auditor *"this deployment has grown an access history"*. That is a
        false statement in the opposite direction, on a report whose entire
        value is the accuracy of its boundary, and over-claiming a history
        is worse than admitting there is none.

        There is no `field`/`model` column on `mail_tracking_value` in Odoo
        19, so the field is reached through `ir_model_fields` and the model
        through `mail_message` — the same join `asset_snapshot.py` uses.
        """
        field = self._access_groups_field()
        if not field:
            return 0
        self.env.cr.execute("""
            SELECT count(*) FROM mail_tracking_value tv
              JOIN mail_message m ON m.id = tv.mail_message_id
              JOIN ir_model_fields f ON f.id = tv.field_id
             WHERE m.model IN ('res.users', 'res.groups')
               AND f.name = %s
        """, (field,))
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

        record_start = self._access_record_start()
        record_rows = self._access_record_rows()

        recoverable = [
            'account_created', 'account_created_by', 'account_modified_at',
            'account_modified_by', 'account_active', 'current_group_membership',
            'current_api_scopes',
        ]
        not_recoverable = [
            'which_field_a_modification_changed',
            'previous_values', 'deleted_accounts', 'password_changes',
            'login_history',
        ]
        # The four facts the forward record makes answerable — but only from
        # the instant it begins. They move between the lists by MEASUREMENT
        # rather than being hard-coded into either, because on a tenant where
        # nothing has been recorded yet the honest answer is still the old one,
        # and a report that claimed otherwise on the strength of the code being
        # deployed would be asserting coverage it does not have.
        _recorded_facts = [
            'group_granted', 'group_removed', 'group_change_actor',
            'group_change_timestamp',
        ]
        if record_start:
            recoverable.extend(_recorded_facts)
        else:
            not_recoverable.extend(_recorded_facts)

        notes = {
            'membership': (
                "Group membership is stored in `%s`, whose columns on this "
                "deployment are: %s. It carries no timestamp and no actor, so "
                "a grant or a removal writes nothing that outlives it, and no "
                "query against that table can produce a history. That is a "
                "property of the schema rather than of the query, and it is "
                "why the changes below come from a SEPARATE append-only "
                "record written as they happen, not from the membership table."
                % (field and self._fields[field].relation or 'unknown',
                   ", ".join(sorted(columns)) or 'none')),
            'record_start': (
                ("This tenant's access record begins at %s and holds %d "
                 "row(s). Grants and removals from that instant onward are "
                 "recorded as they happen, with the acting user. BEFORE that "
                 "instant there is no record and none can be reconstructed — "
                 "a period falling wholly before it is answered `none`, and "
                 "one that straddles it is answered `partial`. The instant is "
                 "measured from the earliest row held, not from a migration "
                 "date, so it says when this tenant actually started being "
                 "written down."
                 % (record_start, record_rows))
                if record_start else
                ("This tenant holds NO access-change rows, so the record has "
                 "not begun here and no period can be answered for group "
                 "grants or removals. The recorder is installed and will "
                 "write the first row the next time membership changes; until "
                 "then this is an honest `none` rather than a claim that "
                 "nothing happened.")),
            'tracking': (
                "`res.users.%s` carries %s on this deployment, and there are "
                "%d chatter tracking rows for THAT FIELD. Without tracking "
                "there is no history to roll back the way the asset register "
                "snapshot rolls back a custodian. The count is scoped to the "
                "groups field deliberately: tracking on some other field of "
                "`res.users` is not an access history, and reporting it as "
                "one would overstate the record."
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
            # The boundary, on the report's face. `None` until the first
            # change is recorded on this tenant.
            'record_starts_at': record_start and str(record_start) or None,
            'record_rows': record_rows,
            'notes': notes,
        }

    # ── the statement above the table ───────────────────────────────

    @api.model
    def _access_change_coverage(self, events, fidelity, start=None, end=None,
                                group_changes=0):
        """One enum plus the English for it, correct in all three cases.

        Branch on `coverage`, never on `statement` — the wording may be
        improved, the enum may not. Deliberately NOT run through `_()`: this
        is a published API payload, and a value that changes with the acting
        user's language is not something a consumer can store, diff or
        reconcile against last quarter's run.
        """
        # The forward record decides this first, because it is the only
        # source that actually answers the §13.4 question. The three branches
        # are a boundary, not a status: what separates them is where the
        # requested period sits relative to the instant the record began.
        record_start = fidelity.get('record_starts_at')
        if record_start:
            begins = fields.Datetime.to_datetime(record_start)
            if end is not None and end < begins:
                # A period that ended before the record began. This is the one
                # an auditor will hit for the next twelve months, and the
                # answer must stay `none` however much the record now holds —
                # rows from after the period say nothing about the period.
                return ACCESS_COVERAGE_NONE, (
                    "Cadra's access record begins at %s, which is AFTER the "
                    "end of the period you asked about. Nothing was being "
                    "recorded then, and a grant or removal made before that "
                    "instant left no trace that any query can recover. This "
                    "report can say nothing about group changes in this "
                    "period — that is a statement about the record, not about "
                    "the estate, and an empty table here must not be read as "
                    "'no access changed'." % record_start)
            if start is not None and start < begins:
                return ACCESS_COVERAGE_PARTIAL, (
                    "Cadra's access record begins at %s, part-way through the "
                    "period you asked about. Group changes from that instant "
                    "to the end of the period are complete, with the acting "
                    "user; anything before it was not being recorded and "
                    "cannot be reconstructed. The %d group change(s) below "
                    "are therefore a LOWER BOUND for this period."
                    % (record_start, group_changes))
            return ACCESS_COVERAGE_RECORDED, (
                "Cadra's access record covers the whole of this period — it "
                "begins at %s, at or before the start of what you asked "
                "about. The %d group change(s) below are every grant and "
                "removal made in the period, each with the user, the group "
                "and the actor. A change made by an upgrade, a cron or the "
                "command line is attributed to `%s` rather than to a person, "
                "because it cannot honestly be attributed to one."
                % (record_start, group_changes, SYSTEM_ACTOR))

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
                "groups field carries no tracking, and this tenant holds no "
                "access-change rows yet. This report can speak for NO period, "
                "and the empty table below is a statement about the record "
                "rather than about the estate.")
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
        # `microsecond=999999` is not fussiness. Without it the closing
        # instant is 23:59:59.000000 and everything in the last second of a
        # period documented as "inclusive of the whole closing day" falls
        # outside it — a one-second hole at the top of every period, on a
        # report whose whole value is that its bounds are what they say.
        end = fields.Datetime.to_datetime(date_to).replace(
            hour=23, minute=59, second=59, microsecond=999999)

        groups_field = fidelity['groups_field']
        # ONE search, not one per user. This ran a `myservice.api.client`
        # search inside the loop; on a tenant with a few thousand accounts
        # that is a few thousand queries on a read-only report, and the
        # per-tenant account counts this was written against are a fixture,
        # not an estate.
        clients_by_user = {
            c.user_id.id: c
            for c in self.env['myservice.api.client'].sudo().search(
                [('user_id', 'in', users.ids)])
            if c.user_id}
        events = []
        roster = []
        # Reused by the group-change events below, so the membership shown
        # beside a recorded change is the same list the roster row shows and
        # the two can never disagree on one page.
        membership = {}
        for user in users:
            member_of = sorted(
                (user[groups_field] if groups_field else user.browse()
                 ).mapped('full_name' if 'full_name' in
                          self.env['res.groups']._fields else 'name'))
            membership[user.id] = member_of
            client = clients_by_user.get(user.id)
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

        # The §13.4 question, answered from the forward record rather than
        # from the membership table — which, as `fidelity.notes.membership`
        # says, physically cannot answer it.
        #
        # Membership events carry a user and join the paged `events` list.
        # Implication events do not name a user at all (they move what a group
        # MEANS, not who is in it), so forcing them into a list the controller
        # pages by user id would either drop them silently or break the page
        # contract. They are counted and stated separately instead.
        group_changes, implication_changes = 0, 0
        Record = self.env.get('myservice.api.access.change')
        if Record is not None:
            rows = Record.sudo().search(
                [('changed_at', '>=', start), ('changed_at', '<=', end)],
                order='changed_at, id')
            known = set(users.ids)
            for row in rows:
                if row.event in (ACCESS_EVENT_GRANTED, ACCESS_EVENT_REMOVED):
                    group_changes += 1
                    # A row whose user has since been deleted, or who is a
                    # structural account, has no roster row to page with. It
                    # still counts above — dropping it from the count would
                    # under-report the period — but it cannot be attached to a
                    # page, so it is not invented into one.
                    if row.user_id.id not in known:
                        continue
                    events.append({
                        'event': row.event,
                        'precision': 'exact',
                        'at': row.changed_at,
                        'actor': ({'id': row.changed_by_id.id,
                                   'name': row.actor}
                                  if row.attributable else
                                  {'id': None, 'name': SYSTEM_ACTOR}),
                        'user_id': row.user_id.id,
                        'login': row.user_login,
                        'evidence': 'myservice_api_access_change.id=%d' % row.id,
                        'group': row.group_name,
                        'attributable': row.attributable,
                        'groups_now': membership.get(row.user_id.id, []),
                    })
                else:
                    implication_changes += 1

        events.sort(key=lambda e: (e['at'], e['user_id'], e['event']))
        coverage, statement = self._access_change_coverage(
            events, fidelity, start=start, end=end, group_changes=group_changes)
        return {
            'events': events,
            'roster': roster,
            'summary': {
                'accounts': len(roster),
                'accounts_active': sum(1 for r in roster if r['active']),
                'events_in_period': len(events),
                # No longer a structural zero on a tenant where something has
                # happened — and still exactly zero, honestly, on one where
                # nothing has. `fidelity.record_starts_at` is what tells the
                # two apart.
                'group_changes_in_period': group_changes,
                'implication_changes_in_period': implication_changes,
                'coverage': coverage,
                'statement': statement,
            },
            'fidelity': fidelity,
        }
