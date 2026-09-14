"""§13.4's fifth standard audit report: who changed what setting, and when.

**The ceiling is low and the report says so on its face.** `ir.config_parameter`
carries `create_uid`, `create_date`, `write_uid` and `write_date` — real audit
columns, unlike the group-membership table in `audit_access.py` — but it is
last-write-wins and it is not tracked. So for a key that changed, exactly
three facts survive:

    the CURRENT value · the LAST writer · the LAST write time

The previous value is gone. How many times it changed is gone. A key deleted
since is gone without a tombstone. Measured across all eight local tenants
when this was built: **22 keys estate-wide were written after they were
created, 12 of them by a named human** and the remaining 10 by `__system__`
— cron, CLI or module upgrade.

**And the settings screen writes to a table that self-destructs.**
`res.config.settings` is a `TransientModel`; its rows are vacuumed, so every
settings-form save leaves nothing behind but the resulting parameter row.
That is the single biggest reason this report is thin, and it is the one an
auditor is least likely to guess.

## Values are redacted, and that is not optional

`ir_config_parameter` is where `myservice_api.jwt_secret` lives — the key
every access token in the tenant is signed with — alongside
`database.secret`, and the relay, webhook and API keys the identity modules
read. A configuration report that published values verbatim would hand the
token-signing secret to every caller holding the read scope, and an audit
credential is exactly the kind of broad, long-lived, widely-shared credential
that would then be carrying it.

So `_redact` decides, and it decides by KEY NAME rather than by a list of
known-secret keys: a deny-list of the six secrets that exist today is a
deny-list that misses the seventh. A redacted row still carries everything
the audit question needs — that the key exists, that it changed, who changed
it and when — and publishes a fingerprint of the value so two deployments
can be compared without either revealing what they hold.

It never writes; `myservice_api/tests/test_audit_configuration_report.py`
fingerprints the tables to prove it.
"""
import hashlib
import re

from odoo import api, fields, models


#: Same three-way distinction the disposal report's `sap_coverage` makes.
CONFIG_COVERAGE_EMPTY = 'empty'
CONFIG_COVERAGE_LAST_WRITE_ONLY = 'last_write_only'

#: Odoo stamps `create_date` and `write_date` in the same transaction, so a
#: parameter that has never been touched since it was seeded still shows the
#: two within microseconds of each other. Two seconds is the tolerance that
#: separates "written again later" from "written once"; without it every key
#: in the database reports as changed.
CONFIG_SAME_TRANSACTION_SECONDS = 2

#: A key whose NAME says its value is a credential. Matched as whole words so
#: that `cadra.brand_primary` is not redacted for containing no such thing,
#: while `myservice_api.jwt_secret`, `database.secret`,
#: `cadra.email_relay_secret`, `myservice_api.turnstile_secret`,
#: `myservice_identity.redhubs_api_key` and
#: `myservice_identity.sap_webhook_secret` all are.
#:
#: Deliberately a NAME rule and not a list of the keys that exist today. The
#: keys that exist today are the ones somebody remembered; the rule has to
#: cover the one added next month by a person who never reads this file.
_SECRET_KEY_RE = re.compile(
    r"(?:^|[._-])(secret|password|passwd|pwd|token|api_?key|private_?key|"
    r"credential|salt|signature|cert|jwt)(?:$|[._-])", re.IGNORECASE)

#: Values that are structurally identifying rather than secret, but which
#: nothing outside the deployment has any business reading.
_OPAQUE_KEYS = frozenset({'database.uuid'})

_REDACTED = '[redacted]'


class IrConfigParameterAuditReport(models.Model):
    _inherit = 'ir.config_parameter'

    # ── redaction ───────────────────────────────────────────────────

    @api.model
    def _is_secret_key(self, key):
        return bool(_SECRET_KEY_RE.search(key or '')) or key in _OPAQUE_KEYS

    @api.model
    def _redact(self, key, value):
        """The value, or a fingerprint of it, never a partial reveal.

        No prefix, no last-four, no length. A truncated secret is still a
        head start, and a published length narrows a brute force; the sha256
        answers the only legitimate question a redacted value has to answer,
        which is *"is this the same value as the one over there"*.
        """
        if not self._is_secret_key(key):
            return value, False
        digest = hashlib.sha256((value or '').encode('utf-8')).hexdigest()
        return '%s sha256:%s' % (_REDACTED, digest[:16]), True

    # ── the boundary ────────────────────────────────────────────────

    @api.model
    def _config_transient_settings_rows(self):
        """`res_config_settings` row count — expected 0, measured anyway.

        If this is ever non-zero the vacuum has stopped running, which is
        both a finding in itself and a source this report would then owe the
        reader an answer about.
        """
        self.env.cr.execute("""
            SELECT count(*) FROM information_schema.tables
             WHERE table_name = 'res_config_settings'""")
        if not self.env.cr.fetchone()[0]:
            return None
        self.env.cr.execute("SELECT count(*) FROM res_config_settings")
        return self.env.cr.fetchone()[0]

    @api.model
    def _config_tracking_rows(self):
        self.env.cr.execute("""
            SELECT count(*) FROM mail_tracking_value tv
              JOIN mail_message m ON m.id = tv.mail_message_id
             WHERE m.model IN ('ir.config_parameter', 'res.config.settings')
        """)
        return self.env.cr.fetchone()[0]

    @api.model
    def configuration_change_fidelity(self):
        """Re-measured each request, for the reason `audit_access.py` gives."""
        transient_rows = self._config_transient_settings_rows()
        tracking_rows = self._config_tracking_rows()
        # `getattr` for the reason `audit_access.py` gives at the same line.
        tracked = any(getattr(f, 'tracking', False)
                      for f in self._fields.values())

        return {
            'recoverable': [
                'key', 'current_value', 'last_written_by', 'last_written_at',
                'created_by', 'created_at', 'value_is_redacted',
            ],
            'not_recoverable': [
                'previous_value', 'number_of_changes', 'intermediate_changes',
                'deleted_keys', 'which_settings_form_was_used',
                'changes_made_through_the_settings_screen',
            ],
            'tracked': tracked,
            'tracking_rows': tracking_rows,
            'transient_settings_rows': transient_rows,
            'notes': {
                'last_write_only': (
                    "`ir.config_parameter` is last-write-wins and carries %s "
                    "on this deployment, so a key changed five times is one "
                    "row showing the fifth. The previous value is not stored "
                    "anywhere and cannot be recovered."
                    % ('tracking' if tracked else 'no tracking')),
                'settings_screen': (
                    "`res.config.settings` is a transient model and its rows "
                    "are vacuumed — %s on this deployment. A change made "
                    "through the Settings screen therefore leaves only the "
                    "resulting parameter row; who opened the form, what else "
                    "they changed in the same save, and what the form showed "
                    "them are all gone."
                    % ('the table does not exist' if transient_rows is None
                       else '%d rows' % transient_rows)),
                'system_actor': (
                    "An actor of `__system__` (uid 1) means the write came "
                    "from a module install or upgrade, a cron, or the "
                    "command line — not from a person. Those are real "
                    "configuration changes and are reported, but they are "
                    "not somebody's decision and should not be read as one."),
                'redaction': (
                    "A value whose KEY names a credential is replaced by "
                    "`%s` plus a truncated sha256 of the value, so two "
                    "deployments can be compared without either revealing "
                    "what it holds. `value_is_redacted` says which rows. The "
                    "rule matches the key name rather than a list of known "
                    "secrets, so a credential added later is covered without "
                    "anybody remembering to add it here."
                    % _REDACTED),
                'deleted_keys': (
                    "A parameter deleted since the requested date leaves no "
                    "tombstone. This report is a LOWER BOUND on the "
                    "configuration the deployment has carried."),
                'scope': (
                    "`ir.config_parameter` only. Views, crons, server "
                    "actions, ACLs and record rules also change what the "
                    "system does; all of them carry a write stamp, and on "
                    "every tenant measured every one of those stamps was "
                    "`__system__` — module upgrade churn, not human edits. "
                    "They are named here rather than reported, because a "
                    "table of 1,634 view rows nobody edited would bury the "
                    "handful of parameters somebody did."),
            },
        }

    # ── the statement above the table ───────────────────────────────

    @api.model
    def _config_change_coverage(self, rows, changed):
        if not rows:
            return CONFIG_COVERAGE_EMPTY, (
                "No configuration parameter was created or written in this "
                "period.")
        if not changed:
            return CONFIG_COVERAGE_LAST_WRITE_ONLY, (
                "%d parameter(s) fall in this period and none of them was "
                "modified after it was created — every row is a parameter "
                "being set for the first time. Cadra stores no previous "
                "values, so had any been modified this report could still "
                "only have shown the most recent write." % len(rows))
        return CONFIG_COVERAGE_LAST_WRITE_ONLY, (
            "%d of %d parameter(s) in this period were modified after they "
            "were created. For each, Cadra holds the CURRENT value, the LAST "
            "writer and the LAST write time, and nothing else: not the "
            "previous value, not how many times it changed, and not what "
            "else changed in the same save. A key modified five times is one "
            "row showing the fifth." % (len(changed), len(rows)))

    # ── the rows ────────────────────────────────────────────────────

    @api.model
    def _config_actor(self, user):
        return {'id': user.id, 'name': user.name} if user else None

    @api.model
    def configuration_change_report(self, date_from, date_to):
        """Parameters created or written in `[date_from, date_to]`, inclusive.

        Returns `{'rows', 'summary', 'fidelity'}`.
        """
        fidelity = self.configuration_change_fidelity()
        start = fields.Datetime.to_datetime(date_from)
        end = fields.Datetime.to_datetime(date_to).replace(
            hour=23, minute=59, second=59)

        params = self.sudo().search([], order='key')
        rows = []
        changed = []
        for param in params:
            touched_at = param.write_date or param.create_date
            if not touched_at or not (start <= touched_at <= end):
                continue
            was_changed = bool(
                param.write_date and param.create_date
                and (param.write_date - param.create_date).total_seconds()
                > CONFIG_SAME_TRANSACTION_SECONDS)
            value, redacted = self._redact(param.key, param.value)
            row = {
                'key': param.key,
                'current_value': value,
                'value_is_redacted': redacted,
                'changed_after_create': was_changed,
                'created_at': param.create_date,
                'created_by': self._config_actor(param.create_uid),
                'last_written_at': param.write_date,
                'last_written_by': self._config_actor(param.write_uid),
                'evidence': 'ir_config_parameter.write_date / write_uid',
                'precision': 'last_write_only',
            }
            rows.append(row)
            if was_changed:
                changed.append(row)

        coverage, statement = self._config_change_coverage(rows, changed)
        by_human = [r for r in changed
                    if r['last_written_by']
                    and r['last_written_by']['id'] != self.env.ref(
                        'base.user_root').id]
        return {
            'rows': rows,
            'summary': {
                'parameters_in_period': len(rows),
                'modified_after_create': len(changed),
                'modified_by_a_named_user': len(by_human),
                'modified_by_system': len(changed) - len(by_human),
                'redacted_values': sum(1 for r in rows
                                       if r['value_is_redacted']),
                'coverage': coverage,
                'statement': statement,
            },
            'fidelity': fidelity,
        }
