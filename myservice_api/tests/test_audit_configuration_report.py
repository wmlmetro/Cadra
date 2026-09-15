"""The configuration report tells you a key changed without telling you the key.

Handoff 23, specification §13.4's fifth standard report. Most of what
`myservice_api/models/audit_configuration.py` does is arithmetic over four
audit columns, and the arithmetic is tested here. But the reason this file is
long is the other thing it does:

**`ir_config_parameter` is where `myservice_api.jwt_secret` lives.** That is
the key every access token in the tenant is signed with, sitting in the same
table as the brand colour and the depreciation mode. A configuration report
that published values verbatim would hand token-signing authority to every
caller holding `settings:read` — and an audit credential is exactly the
broad, long-lived, widely-shared credential that would then be carrying it. A
leak here is not a degraded report; it is a full compromise of the tenant,
delivered through the endpoint an auditor was given precisely because it was
supposed to be safe to hand out.

So the redaction tests are the point of this file, and they are written to
fail in the three ways a redaction actually fails in practice:

1. **It covers the keys that exist and misses the one added next month.**
   `_is_secret_key` is a NAME rule, not a deny-list, and the test drives a
   key that does not exist anywhere in this codebase to prove the rule is
   doing the work rather than the list.
2. **The value leaks somewhere other than the field that was redacted** — a
   note, a statement, a summary. So the regression net is
   `json.dumps(report)` over the WHOLE payload and not an assertion about
   one field.
3. **It reveals "just a bit"** — a prefix, a suffix, a length. Each of those
   is a head start, and a published length narrows a brute force. Asserted
   directly.

Everything else here — coverage, the two-second rule, period filtering, the
summary identities — is the ordinary regression net.

**Scoping.** `configuration_change_report` takes no domain argument and
reports the WHOLE parameter table, so nothing here asserts an absolute count.
Every row assertion is looked up by a key carrying a per-test uuid marker,
and the two summary assertions are IDENTITIES that hold for any tenant. In CI
`pytest tests/` runs before this suite and commits fixtures of its own; an
absolute count would be an assertion about that debris.

Run with:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --test-enable \\
      --test-tags /myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098
"""
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.myservice_api.models.audit_configuration import (
    CONFIG_COVERAGE_EMPTY,
    CONFIG_COVERAGE_LAST_WRITE_ONLY,
    CONFIG_COVERAGE_NO_MODIFICATIONS,
    CONFIG_COVERAGE_PARTIAL,
    CONFIG_SAME_TRANSACTION_SECONDS,
    _OPAQUE_KEYS,
    _REDACTED,
)

WIDE_FROM = date(2000, 1, 1)
WIDE_TO = date(2099, 12, 31)

#: A period that exists only to hold rows this test deliberately dated into
#: it. Far enough back that no real parameter has ever been written there.
DEAD_FROM = date(2001, 1, 1)
DEAD_TO = date(2001, 12, 31)

#: Keys whose value must never be published. Every one of these except the
#: last is a key that really exists in this estate; the last one does not
#: exist anywhere and is the point — the rule has to cover the credential
#: added by somebody who never reads `audit_configuration.py`.
SECRET_KEYS = (
    "myservice_api.jwt_secret",
    "database.secret",
    "database.uuid",
    "cadra.email_relay_secret",
    "myservice_api.turnstile_secret",
    "myservice_identity.redhubs_api_key",
    "myservice_identity.sap_webhook_secret",
    "cadra.something_private_key",
)

#: Keys whose value is the answer an auditor came for. Redacting these would
#: make the report useless in the opposite direction, and a redaction that
#: fires on everything is indistinguishable from no report at all.
PUBLIC_KEYS = (
    "cadra.brand_primary",
    "web.base.url",
    "cadra.depreciation.mode",
    "nrs_asset.tag_label_size",
)


class ConfigReportCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Param = self.env["ir.config_parameter"]
        self.marker = uuid.uuid4().hex[:10]
        self._seq = 0

    # ── fixtures ────────────────────────────────────────────────────

    def _key(self, suffix=""):
        """A key nothing else in the estate can collide with.

        Carries `audit_test` on its face so a row left behind by an aborted
        run is self-identifying rather than looking like configuration.
        """
        self._seq += 1
        return "cadra.audit_test_%s_%d%s" % (self.marker, self._seq, suffix)

    def _param(self, key=None, value="a plain value"):
        return self.Param.create({"key": key or self._key(), "value": value})

    # ── plumbing ────────────────────────────────────────────────────

    def _flush_tracking(self):
        """See `test_audit_access_report.py` — tracking values reach
        `mail_tracking_value` at COMMIT, and a TransactionCase never commits,
        so a fingerprint without this is blind to the writes it exists to
        catch."""
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.flush_all()

    def _backdate(self, records, column, moment):
        """Move an audit stamp in SQL, because the ORM will not.

        `cr.now()` is cached for the whole transaction, so every row a
        TransactionCase creates carries the SAME `create_date` and
        `write_date` to the microsecond. Testing the two-second rule or a
        period boundary therefore has to go under the ORM.
        """
        self.assertIn(column, ("create_date", "write_date"))
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE %s SET %s = %%s WHERE id IN %%s" % (records._table, column),
            (moment, tuple(records.ids)))
        self.env.invalidate_all()

    def _report(self, date_from=WIDE_FROM, date_to=WIDE_TO):
        return self.Param.configuration_change_report(date_from, date_to)

    def _today_period(self):
        today = fields.Datetime.now().date()
        return today - timedelta(days=1), today + timedelta(days=1)

    def _row_for(self, report, key):
        for row in report["rows"]:
            if row["key"] == key:
                return row
        return None


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheReportWritesNothing(ConfigReportCase):
    """Fingerprinted, for the reason the disposal report was.

    Sharper here than elsewhere: `ir.config_parameter` is the one model in
    this repository where a stray `set_param` in a read path would change how
    the SYSTEM BEHAVES rather than merely dirtying a row — a rewritten
    `myservice_api.jwt_secret` invalidates every live token in the tenant. A
    report over this table earns its fingerprint.
    """

    FINGERPRINTED = {
        "ir_config_parameter": "t.id",
        "res_users": "t.id",
        "res_groups_users_rel": "t.gid, t.uid",
        "mail_message": "t.id",
        "mail_tracking_value": "t.id",
    }

    def test_the_fingerprint_notices_a_write(self):
        """The NEGATIVE CONTROL — see the same test in the access report.

        Without it, a `FINGERPRINTED` dict pointed at the wrong tables gives
        an identical before and after on every run and reads exactly like a
        proof that the report writes nothing.
        """
        before = self._fingerprint()
        self.env["ir.config_parameter"].sudo().set_param(
            "cadra.fingerprint_probe_%s" % self.marker, "1")
        self._flush_tracking()
        self.assertNotEqual(
            before["ir_config_parameter"],
            self._fingerprint()["ir_config_parameter"],
            "a parameter write did not move the `ir_config_parameter` "
            "fingerprint, so this fingerprint cannot detect a write and "
            "every read-only claim resting on it is unproven")

    def _fingerprint(self):
        self._flush_tracking()
        self.env.invalidate_all()
        marks = {}
        for table, order in self.FINGERPRINTED.items():
            self.env.cr.execute(
                "SELECT count(*), md5(coalesce(string_agg(t::text, '|' "
                "ORDER BY %s), '')) FROM %s t" % (order, table))
            marks[table] = self.env.cr.fetchone()
        return marks

    def test_the_report_changes_nothing(self):
        key = self._key()
        self._param(key)
        self._param(self._key("_secret"), value="not published")
        self._flush_tracking()

        before = self._fingerprint()
        report = self._report(*self._today_period())
        after = self._fingerprint()

        self.assertIsNotNone(
            self._row_for(report, key),
            "the fixture produced no row, so this test proved nothing about "
            "a report that ran over parameters")
        self.assertEqual(
            before, after,
            "configuration_change_report modified the database. It reads the "
            "table that holds the tenant's signing secret: a write here does "
            "not dirty a row, it changes how the system behaves.")

    def test_the_fidelity_block_changes_nothing(self):
        """Measured separately: this is the half that runs raw SQL against
        `information_schema` and `res_config_settings`."""
        self._param()
        self._flush_tracking()
        before = self._fingerprint()
        fidelity = self.Param.configuration_change_fidelity()
        after = self._fingerprint()
        self.assertTrue(fidelity["notes"], "fidelity came back empty")
        self.assertEqual(before, after,
                         "configuration_change_fidelity modified the database")

    def test_running_it_twice_gives_the_same_answer(self):
        self._param()
        self._flush_tracking()
        period = self._today_period()
        self.assertEqual(
            self._report(*period), self._report(*period),
            "two consecutive runs disagreed, which means the first changed "
            "something the second read")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestWhichKeysAreSecret(ConfigReportCase):
    """`_is_secret_key` decides by NAME, and the name rule is the contract.

    A deny-list of the six secrets that exist today is a deny-list that
    misses the seventh, and the seventh is added by somebody who has never
    opened this file. So the last entry in `SECRET_KEYS` is deliberately a
    key that exists NOWHERE in this codebase: if the implementation is ever
    "simplified" into a list of real keys, that one assertion is what fails.

    The other direction matters just as much. A redaction that fires on
    everything publishes nothing, and the auditor who asked what the
    depreciation mode is set to gets a sha256 back.
    """

    def test_the_real_credentials_are_all_matched(self):
        for key in SECRET_KEYS:
            self.assertTrue(
                self.Param._is_secret_key(key),
                "`%s` is not recognised as a credential, so its VALUE would "
                "be published verbatim to every caller holding settings:read"
                % key)

    def test_a_credential_nobody_has_added_yet_is_matched(self):
        """The whole argument for a name rule, isolated so it fails alone.

        `cadra.something_private_key` does not exist in this estate and is
        not named anywhere in `audit_configuration.py`. It is matched because
        the RULE matches it, which is the property that covers next month's
        key.
        """
        self.assertTrue(
            self.Param._is_secret_key("cadra.something_private_key"),
            "the secret rule has been narrowed to keys that exist today; a "
            "credential added later will be published verbatim and nobody "
            "will notice until it is in somebody's audit export")
        for invented in ("vendra.int03_shared_token",
                         "cadra.reporting_password",
                         "sap.client_credential",
                         "nrs.payload_signature"):
            self.assertTrue(
                self.Param._is_secret_key(invented),
                "`%s` names a credential and is not matched" % invented)

    def test_ordinary_configuration_is_not_redacted(self):
        for key in PUBLIC_KEYS:
            self.assertFalse(
                self.Param._is_secret_key(key),
                "`%s` is ordinary configuration and is being redacted. A "
                "redaction that fires on everything is indistinguishable "
                "from no report: the auditor asked what this is SET to."
                % key)

    def test_database_uuid_is_covered_by_the_opaque_list_not_the_regex(self):
        """`uuid` is not a credential word and never will be, so this one is
        carried by `_OPAQUE_KEYS`. Asserted through both doors so that
        deleting either is a visible failure rather than a silent one."""
        self.assertIn("database.uuid", _OPAQUE_KEYS)
        self.assertTrue(self.Param._is_secret_key("database.uuid"))

    def test_a_missing_key_does_not_raise(self):
        """`key` arrives from a database row; a report that 500s on a NULL is
        a report that stops existing the day somebody inserts one."""
        self.assertFalse(self.Param._is_secret_key(None))
        self.assertFalse(self.Param._is_secret_key(""))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheValueNeverReachesThePayload(ConfigReportCase):
    """The regression net that actually matters.

    Not "is `current_value` redacted" — that is the assertion a leak routes
    around. The value is searched for across `json.dumps` of the ENTIRE
    report, because the realistic leak is somewhere nobody was looking: a
    fidelity note that quotes an example, a coverage statement that names the
    offending key and its value, a debugging field somebody added to a row.
    """

    #: Distinctive enough that finding it anywhere in a JSON blob is proof,
    #: and deliberately NOT derived from the test's key marker — a value that
    #: shared a substring with the key would be "found" in the payload by the
    #: key alone and the test would fail for the wrong reason.
    def _secret_value(self):
        return "SENTINEL-%s-DO-NOT-PUBLISH" % uuid.uuid4().hex

    def test_a_secret_value_appears_nowhere_in_the_report(self):
        key = self._key("_secret")
        value = self._secret_value()
        self._param(key, value=value)
        self._flush_tracking()

        report = self._report(*self._today_period())
        row = self._row_for(report, key)
        self.assertIsNotNone(
            row, "the parameter this test created is not in the report, so "
                 "the redaction was never exercised")
        self.assertIs(
            row["value_is_redacted"], True,
            "a key ending in `_secret` was published unredacted")

        blob = json.dumps(report, default=str)
        self.assertNotIn(
            value, blob,
            "the raw value of a credential key appears somewhere in the "
            "configuration report payload. `ir_config_parameter` holds "
            "myservice_api.jwt_secret; a leak on this endpoint hands token-"
            "signing authority to every holder of settings:read.")

    def test_the_key_itself_is_still_published(self):
        """Redaction hides the value, not the fact. An auditor's question —
        did this credential change, when, and who changed it — is answerable
        without the value, and a row that vanished entirely would answer
        nothing while looking like a clean sheet."""
        key = self._key("_secret")
        self._param(key, value=self._secret_value())
        self._flush_tracking()
        row = self._row_for(self._report(*self._today_period()), key)
        self.assertIsNotNone(row)
        self.assertEqual(row["key"], key)
        self.assertIsNotNone(row["last_written_at"])
        self.assertIsNotNone(row["last_written_by"])
        self.assertEqual(row["precision"], "last_write_only")

    def test_an_ordinary_value_is_published_intact(self):
        """The control. If this fails alongside the test above, the report is
        redacting everything and proving nothing."""
        key = self._key()
        self._param(key, value="quarterly")
        self._flush_tracking()
        row = self._row_for(self._report(*self._today_period()), key)
        self.assertEqual(row["current_value"], "quarterly")
        self.assertIs(row["value_is_redacted"], False)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThereIsNoPartialReveal(ConfigReportCase):
    """No prefix, no suffix, no length.

    Each of those is the compromise that feels harmless. A first-four is a
    head start on a targeted guess and often identifies the issuer outright;
    a last-four is how card numbers are matched, which is exactly the point;
    and a published length turns an unbounded search into a bounded one. The
    sha256 answers the only legitimate question a redacted value has — *is
    this the same value as the one over there* — and answers nothing else.
    """

    SHORT = "ab"
    LONG = "correct-horse-battery-staple-0123456789-abcdefghijklmnop"

    def test_neither_end_of_the_value_survives(self):
        value = "ABCDwxyzMNOPqrst"
        redacted, was = self.Param._redact("cadra.x_secret", value)
        self.assertTrue(was)
        self.assertNotIn(
            value[:4], redacted,
            "the first four characters of the secret survive redaction")
        self.assertNotIn(
            value[-4:], redacted,
            "the last four characters of the secret survive redaction")
        self.assertNotIn(value, redacted)

    def test_the_length_of_the_value_is_not_published(self):
        """Asserted as a property rather than by hunting for a number: two
        values 54 characters apart must redact to strings of the SAME length,
        which is the only formulation a sha256 cannot accidentally satisfy."""
        short, _ = self.Param._redact("cadra.x_secret", self.SHORT)
        long_, _ = self.Param._redact("cadra.x_secret", self.LONG)
        self.assertEqual(
            len(short), len(long_),
            "the redacted form varies in length with the secret, so the "
            "report publishes the length of every credential it holds and a "
            "brute force against it is bounded rather than open-ended")

    def test_the_redacted_form_is_the_marker_plus_a_truncated_digest(self):
        """Pinned, because the shape is what a consumer renders and compares.
        A change here is a breaking API change for anyone diffing two
        deployments."""
        value = "a value"
        redacted, _ = self.Param._redact("cadra.x_secret", value)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        self.assertEqual(redacted, "%s sha256:%s" % (_REDACTED, digest[:16]))
        self.assertTrue(redacted.startswith(_REDACTED))

    def test_an_empty_secret_still_redacts(self):
        """A parameter whose value is NULL must not fall through to
        `None` in the payload and reveal, by its emptiness, that the
        credential is unset — and `None.encode()` would be a 500."""
        redacted, was = self.Param._redact("cadra.x_secret", None)
        self.assertTrue(was)
        self.assertTrue(redacted.startswith(_REDACTED))
        self.assertNotIn("None", redacted)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheFingerprintIsComparable(ConfigReportCase):
    """The one property redaction promises to PRESERVE.

    The stated purpose of publishing a digest rather than nothing at all is
    that two deployments can be compared without either revealing what it
    holds — *"is staging still signing with the same key as production?"*. If
    equal values produced different fingerprints the digest would be
    decoration, and if different values produced equal ones it would be a
    lie.
    """

    def test_the_same_value_fingerprints_the_same_under_different_keys(self):
        """Keyed on the VALUE only. Two deployments do not necessarily store
        the same credential under the same parameter name, and a fingerprint
        salted by the key would answer a question nobody asked."""
        a, _ = self.Param._redact("myservice_api.jwt_secret", "shared-value")
        b, _ = self.Param._redact("cadra.email_relay_secret", "shared-value")
        self.assertEqual(
            a, b,
            "the same secret value fingerprints differently depending on the "
            "key it sits under, so the comparison the redaction exists to "
            "support does not work")

    def test_a_different_value_fingerprints_differently(self):
        a, _ = self.Param._redact("cadra.x_secret", "value-one")
        b, _ = self.Param._redact("cadra.x_secret", "value-two")
        self.assertNotEqual(
            a, b,
            "two different secrets produce the same published fingerprint, "
            "so the report would show a rotated key as unchanged")

    def test_a_one_character_difference_is_visible(self):
        a, _ = self.Param._redact("cadra.x_secret", "value-one")
        b, _ = self.Param._redact("cadra.x_secret", "value-onE")
        self.assertNotEqual(a, b)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheTwoSecondRule(ConfigReportCase):
    """`changed_after_create` separates "set once" from "changed since".

    Odoo stamps `create_date` and `write_date` in the same transaction — and
    `cr.now()` is cached, so on a fresh row they are identical to the
    microsecond. Without the tolerance every key in the database reports as
    changed, and `modified_after_create` — the number the whole report is
    read for — becomes the row count.
    """

    def test_a_freshly_created_parameter_is_not_reported_as_changed(self):
        key = self._key()
        self._param(key)
        self._flush_tracking()
        row = self._row_for(self._report(*self._today_period()), key)
        self.assertIs(
            row["changed_after_create"], False,
            "a parameter created and never touched again is reported as "
            "modified. `write_date` equals `create_date` on a fresh row, so "
            "the %d-second tolerance is not being applied and every key in "
            "the tenant now reports as changed."
            % CONFIG_SAME_TRANSACTION_SECONDS)

    def test_a_parameter_written_later_is_reported_as_changed(self):
        """The tolerance must not swallow a real change either. `create_date`
        is pushed an hour back in SQL because the ORM cannot separate the two
        stamps inside one transaction."""
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        self._backdate(param, "create_date",
                       fields.Datetime.now() - timedelta(hours=1))

        row = self._row_for(self._report(*self._today_period()), key)
        self.assertIs(
            row["changed_after_create"], True,
            "a parameter written an hour after it was created is reported as "
            "untouched, so the tolerance is swallowing real changes and the "
            "report's headline number is always zero")
        self.assertEqual(row["precision"], "last_write_only")

    def test_the_tolerance_is_the_published_constant(self):
        """A gap just inside the tolerance is still "set once"; the boundary
        is `CONFIG_SAME_TRANSACTION_SECONDS` and not a number retyped in the
        comparison."""
        self.assertEqual(CONFIG_SAME_TRANSACTION_SECONDS, 2)
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        self._backdate(
            param, "create_date",
            fields.Datetime.now()
            - timedelta(seconds=CONFIG_SAME_TRANSACTION_SECONDS - 1))
        row = self._row_for(self._report(*self._today_period()), key)
        self.assertIs(
            row["changed_after_create"], False,
            "a gap inside the tolerance is being reported as a change")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheCoverageEnum(ConfigReportCase):
    """All three branches, driven directly.

    Driven directly because two of them cannot be produced on demand from a
    live tenant without waiting for the right quarter, and because the
    branch that matters — a period holding rows, none of them modified — is
    the one whose sentence is easiest to get subtly wrong.

    Worth stating plainly: only TWO enum values exist, so the second and
    third branches are indistinguishable by `coverage` alone. That is the
    model's deliberate shape — both really are last-write-only — and a
    consumer separates them with `summary.modified_after_create`. The tests
    therefore assert the enum AND the distinct wording, and the wording is
    load-bearing here in a way it is not in the access report.
    """

    def _row(self, key="k", changed=False):
        return {"key": key, "changed_after_create": changed}

    def test_an_empty_period_says_nothing_was_written(self):
        coverage, statement = self.Param._config_change_coverage([], [])
        self.assertEqual(coverage, CONFIG_COVERAGE_EMPTY)
        self.assertEqual(
            statement,
            "No configuration parameter was created or written in this "
            "period.")

    def test_rows_with_none_modified_is_its_own_coverage_value(self):
        """Both counts of interest are zero and the two mean different
        things: nothing was written at all, versus three parameters were set
        for the first time. Collapsing them would let a quarter of new
        configuration render as a quarter of no configuration.

        This case had `last_write_only` — the same value as "some were
        modified" — so a consumer obeying the published rule *branch on
        `coverage`, never on `statement`* could not separate them and had to
        fall back to reading `summary.modified_after_create`. That is the
        failure `sap_coverage` was written to prevent, and it got its own
        value rather than a note telling consumers to read the counts.
        """
        rows = [self._row("a"), self._row("b"), self._row("c")]
        coverage, statement = self.Param._config_change_coverage(rows, [])
        self.assertEqual(coverage, CONFIG_COVERAGE_NO_MODIFICATIONS)
        self.assertNotEqual(
            coverage, CONFIG_COVERAGE_LAST_WRITE_ONLY,
            "'none modified' and 'some modified' must not share a value")
        self.assertIn("3 parameter(s) fall in this period", statement)
        self.assertIn("none of them was modified", statement)
        self.assertNotIn("No configuration parameter was created", statement)

    def test_partial_is_reachable_the_day_a_value_history_appears(self):
        """The branch that exists so this report cannot go stale silently.

        Unreachable on every deployment today, and that is exactly why it
        needs a test: `audit_access.py`'s whole future-proofing argument is
        that a deployment which grows a history is DESCRIBED rather than
        misreported, and this file's first version had no way to say so —
        it would have published `last_write_only` for ever while the
        database held more. Driven directly, because the only way to reach
        it for real is to add tracking to `ir.config_parameter`.
        """
        rows = [self._row("a", True)]
        for fidelity in ({"tracked": True, "tracking_rows": 0},
                         {"tracked": False, "tracking_rows": 12}):
            with self.subTest(fidelity=fidelity):
                coverage, statement = self.Param._config_change_coverage(
                    rows, rows, fidelity)
                self.assertEqual(coverage, CONFIG_COVERAGE_PARTIAL)
                self.assertIn("understates what the database holds", statement)

    def test_rows_with_some_modified_counts_both_numbers(self):
        changed = [self._row("a", True)]
        rows = changed + [self._row("b"), self._row("c")]
        coverage, statement = self.Param._config_change_coverage(rows, changed)
        self.assertEqual(coverage, CONFIG_COVERAGE_LAST_WRITE_ONLY)
        self.assertIn(
            "1 of 3 parameter(s)", statement,
            "the statement does not carry both numbers, so a reader cannot "
            "tell one changed key in three from three in three")
        self.assertIn("not the previous value", statement)

    def test_the_statement_does_not_move_with_the_language(self):
        """A published payload string an integration stores and diffs. See
        the fuller argument in `test_audit_access_report.py`."""
        rows = [self._row("a")]
        english = self.Param._config_change_coverage(rows, [])
        other = self.env["ir.config_parameter"].with_context(
            lang="fr_FR")._config_change_coverage(rows, [])
        self.assertEqual(english, other)
        self.assertIs(type(english[1]), str)

    def test_the_report_publishes_that_same_statement(self):
        report = self._report(*self._today_period())
        expected = self.Param._config_change_coverage(
            report["rows"],
            [r for r in report["rows"] if r["changed_after_create"]])
        self.assertEqual(report["summary"]["coverage"], expected[0])
        self.assertEqual(report["summary"]["statement"], expected[1])


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheSummaryArithmetic(ConfigReportCase):
    """The identities, asserted as identities.

    Deliberately not "the tenant has 7 modified parameters". The report has
    no domain argument, so every count it publishes is register-wide, and in
    CI `pytest tests/` commits fixtures before this suite runs. What is
    testable without lying is that the numbers ADD UP — which is what a
    reader actually relies on when they quote two of them in the same
    sentence.
    """

    def test_named_and_system_writers_partition_the_modified_rows(self):
        """A modification is either somebody's decision or it is not, and
        every one of them is one or the other. A row falling through both —
        a `write_uid` of NULL, say — would make two published numbers fail to
        reconcile with a third, in a report an auditor is quoting."""
        self._param(self._key())
        self._flush_tracking()
        summary = self._report()["summary"]
        self.assertEqual(
            summary["modified_by_a_named_user"] + summary["modified_by_system"],
            summary["modified_after_create"],
            "modified_by_a_named_user + modified_by_system does not equal "
            "modified_after_create; a modified row is being counted twice or "
            "not at all")
        for key in ("modified_by_a_named_user", "modified_by_system",
                    "modified_after_create", "parameters_in_period",
                    "redacted_values"):
            self.assertGreaterEqual(summary[key], 0, "%s is negative" % key)

    def test_modified_rows_never_outnumber_the_rows_they_came_from(self):
        summary = self._report()["summary"]
        self.assertEqual(summary["parameters_in_period"],
                         len(self._report()["rows"]))
        self.assertLessEqual(summary["modified_after_create"],
                             summary["parameters_in_period"])

    def test_redacted_values_counts_the_rows_that_say_they_are_redacted(self):
        """The two must agree or the summary is telling an auditor a
        different story from the table beneath it. Made non-trivial by
        putting a real redacted row in the period."""
        self._param(self._key("_secret"), value="SENTINEL-%s" % self.marker)
        self._flush_tracking()
        report = self._report(*self._today_period())
        self.assertEqual(
            report["summary"]["redacted_values"],
            sum(1 for r in report["rows"] if r["value_is_redacted"]),
            "summary.redacted_values disagrees with the rows it is counting")
        self.assertGreaterEqual(
            report["summary"]["redacted_values"], 1,
            "the fixture's redacted row was not counted, so this test "
            "proved nothing")

    def test_the_fidelity_block_is_measured_rather_than_asserted(self):
        """Both numbers are counted on every request, for the reason
        `audit_access.py` gives: a limitation published as a constant goes
        stale silently."""
        fidelity = self.Param.configuration_change_fidelity()
        self.assertIsInstance(fidelity["tracked"], bool)
        self.assertIsInstance(fidelity["tracking_rows"], int)
        self.assertIn("recoverable", fidelity)
        self.assertIn("not_recoverable", fidelity)
        self.assertIn(
            "previous_value", fidelity["not_recoverable"],
            "the report no longer declares that the previous value is "
            "unrecoverable, which is its single most important limitation")
        self.assertIn(_REDACTED, fidelity["notes"]["redaction"])
        rows = fidelity["transient_settings_rows"]
        self.assertTrue(rows is None or isinstance(rows, int))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThePeriodFiltering(ConfigReportCase):
    """A parameter outside the period is absent, and the closing day is whole.

    The failure this guards against is a report that ignores its arguments:
    one that returns the whole table for every period passes every assertion
    about a row being PRESENT, and is wrong in the only direction an auditor
    would not catch.
    """

    def test_a_parameter_outside_the_period_is_absent(self):
        key = self._key()
        self._param(key)
        self._flush_tracking()
        report = self._report(DEAD_FROM, DEAD_TO)
        self.assertIsNone(
            self._row_for(report, key),
            "a parameter written today appears in a report for 2001, so "
            "configuration_change_report is not filtering on its period")

    def test_that_same_parameter_is_present_once_it_is_dated_into_it(self):
        """The other direction, on the same row, so the test above cannot
        pass because the row was simply never reportable."""
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        moment = datetime(2001, 6, 15, 12, 0, 0)
        self._backdate(param, "create_date", moment)
        self._backdate(param, "write_date", moment)

        row = self._row_for(self._report(DEAD_FROM, DEAD_TO), key)
        self.assertIsNotNone(row, "a parameter dated into the period is "
                                  "still absent from it")
        self.assertIs(
            row["changed_after_create"], False,
            "create and write stamps are identical, so this is a parameter "
            "set once")

    def test_a_write_at_2330_on_the_closing_day_is_included(self):
        """A period given as two dates that silently drops everything after
        midnight on the closing date is the quietest way for a report to be
        wrong: right for most rows, and the ones it loses are the ones
        nobody counted."""
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        moment = datetime(2001, 6, 30, 23, 30, 0)
        self._backdate(param, "create_date", moment)
        self._backdate(param, "write_date", moment)

        row = self._row_for(
            self._report(date(2001, 6, 1), date(2001, 6, 30)), key)
        self.assertIsNotNone(
            row,
            "a parameter written at 23:30 on the closing date of the period "
            "was dropped; the bound is documented as inclusive of the whole "
            "closing day")

    def test_a_write_the_next_day_is_excluded(self):
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        moment = datetime(2001, 7, 1, 0, 30, 0)
        self._backdate(param, "create_date", moment)
        self._backdate(param, "write_date", moment)

        self.assertIsNone(
            self._row_for(
                self._report(date(2001, 6, 1), date(2001, 6, 30)), key),
            "a parameter written after midnight on the day AFTER the closing "
            "date is inside the period, so the upper bound is not bounding")

    def test_the_row_is_keyed_on_the_last_write_not_the_creation(self):
        """`touched_at` is `write_date or create_date`. A key created years
        ago and changed last week belongs in last week's report — reporting
        it by its creation date would hide exactly the change an auditor is
        looking for."""
        key = self._key()
        param = self._param(key)
        self._flush_tracking()
        self._backdate(param, "create_date", datetime(2001, 3, 1, 9, 0, 0))

        self.assertIsNone(
            self._row_for(self._report(DEAD_FROM, DEAD_TO), key),
            "the row is placed in the period of its CREATION; a parameter "
            "created in 2001 and rewritten today is being reported as a 2001 "
            "change")
        row = self._row_for(self._report(*self._today_period()), key)
        self.assertIsNotNone(
            row, "the row is absent from the period of its last write")
        self.assertIs(row["changed_after_create"], True)
