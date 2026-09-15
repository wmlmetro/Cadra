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


#: How much of the question this report can answer, as one value a renderer
#: can branch on — the same contract `sap_coverage` and the access report's
#: `coverage` publish, and it must carry the same weight.
#:
#: There were three branches and two values here, so a consumer obeying the
#: published rule — *branch on `coverage`, never on `statement`* — could not
#: tell "parameters in the period, none of them modified" from "parameters
#: modified, and we hold only the last write". It had to fall back to reading
#: `summary.modified_after_create`, which is exactly the "a client rendering
#: its own sentence off two raw counts" failure the disposal report's
#: `sap_coverage` docstring exists to prevent. Four values, one per answer.
CONFIG_COVERAGE_EMPTY = 'empty'
CONFIG_COVERAGE_NO_MODIFICATIONS = 'no_modifications'
CONFIG_COVERAGE_LAST_WRITE_ONLY = 'last_write_only'
#: Reachable only if this deployment grows a value history. Unreachable today
#: and deliberately present: the access report's whole future-proofing story
#: is that a deployment which grows a history is DESCRIBED rather than
#: misreported, and a sibling report that can never say so would keep
#: publishing `last_write_only` for ever while the database held more.
CONFIG_COVERAGE_PARTIAL = 'partial'

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
#: Distinctive enough to match ANYWHERE in the key, delimiters or not. This
#: tier exists because the first version required a delimiter on both sides,
#: which quietly failed to redact `database.secretkey`, `cadra.jwtSecret` and
#: `myservice_api.apikey` — and the person who writes `jwtSecret` is exactly
#: the person the rule claims to cover without their having read this file.
#: None of these words appears inside an ordinary English word.
_SECRET_SUBSTRING_RE = re.compile(
    r"secret|password|passwd|api_?key|private_?key|credential|jwt",
    re.IGNORECASE)

#: Common English fragments. `cert` sits inside `concert` and `salt` inside
#: `salted`, so these need a real boundary — a rule that redacts
#: `cadra.concert_hall` is a rule somebody switches off, and then the real
#: secrets go with it. Two shapes, kept separate because they need different
#: case sensitivity:
_SECRET_DELIMITED_RE = re.compile(
    r"(?:^|[._-])(?:pwd|token|salt|signature|cert|key)(?=$|[._-])",
    re.IGNORECASE)

#: ...and the camelCase hump, which must be case-SENSITIVE. Folding case here
#: is what made the first version fire on `concert_hall`: with `re.I` the
#: lowercase `cert` after `con` looks exactly like a hump.
_SECRET_CAMEL_RE = re.compile(
    r"(?<=[a-z0-9])(?:Pwd|Token|Salt|Signature|Cert|Key)(?=$|[A-Za-z._-])")

#: Values that are structurally identifying rather than secret, but which
#: nothing outside the deployment has any business reading.
_OPAQUE_KEYS = frozenset({'database.uuid'})

_REDACTED = '[redacted]'


class IrConfigParameterAuditReport(models.Model):
    _inherit = 'ir.config_parameter'

    # ── redaction ───────────────────────────────────────────────────

    @api.model
    def _is_secret_key(self, key):
        key = key or ''
        return bool(_SECRET_SUBSTRING_RE.search(key)
                    or _SECRET_DELIMITED_RE.search(key)
                    or _SECRET_CAMEL_RE.search(key)) or key in _OPAQUE_KEYS

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
        # The `value` field specifically, not "any field on the model".
        # `any(...)` over every field was true the moment ANOTHER module
        # added a tracked field of its own, and the report would then claim
        # a value history it does not have — a fidelity block that overstates
        # is worse than one that is merely thin. `getattr` because `tracking`
        # is contributed by `mail` only to the field types that support it.
        tracked = bool(getattr(self._fields.get('value'), 'tracking', False))

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
    def _config_change_coverage(self, rows, changed, fidelity=None):
        """One enum plus the English for it, correct in all four cases.

        Branch on the enum, never on the wording. Deliberately NOT run
        through `_()`, for the reason the disposal report gives: a published
        payload string that changes with the acting user's language is not
        something a consumer can store, diff or reconcile.
        """
        if fidelity and (fidelity.get('tracked')
                         or fidelity.get('tracking_rows')):
            return CONFIG_COVERAGE_PARTIAL, (
                "This deployment has grown a configuration history since "
                "this report was written — see `fidelity`. The rows below "
                "still carry the LAST write only; the new source is not yet "
                "read, and until it is this report understates what the "
                "database holds.")
        if not rows:
            return CONFIG_COVERAGE_EMPTY, (
                "No configuration parameter was created or written in this "
                "period.")
        if not changed:
            return CONFIG_COVERAGE_NO_MODIFICATIONS, (
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
        # `microsecond=999999` — see the same line in `audit_access.py`.
        end = fields.Datetime.to_datetime(date_to).replace(
            hour=23, minute=59, second=59, microsecond=999999)

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
                # The cursor walks ascending ids, so the id is published:
                # a report ordered by `key` cannot be paged honestly with
                # the cursor this API issues. Rows still carry `key`, so a
                # caller that has walked the period can sort it however it
                # likes — the trade `/reports/disposals` documents.
                'id': param.id,
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

        coverage, statement = self._config_change_coverage(
            rows, changed, fidelity)
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
