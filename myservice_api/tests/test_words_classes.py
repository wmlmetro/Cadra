"""Two classes of string, separated so the words guard can be drawn.

Handoff 50 §5, closing 33 §D3, on report 36 §4's ruling: **an API error
message and a composed sentence shown on a screen are DIFFERENT classes of
string**, and the guard handoff 33 wanted — no field names, no backticks in
anything user-facing — cannot be drawn until the two are separated. This
file is the separation, and it is where the edge is recorded.

**Class 1 — composed statements.** Strings the server WRITES FOR A READER:
keys named `statement`, `meaning`, a fidelity `note`, the snapshot's
`filters.note`, an empty-state sentence. These are shown on a screen to
somebody doing a job, not to a parser, so they must be words: no backticks,
and no payload paths of the `fidelity.` shape. A reader of the disposals
report is an auditor, not a maintainer of this codebase, and a sentence
that leans on a key name is a sentence that outsources its meaning to the
reader's willingness to go and look one up.

**Class 2 — refusals.** The error envelope's `message` and `details`. These
MAY name a field, a key, or a literal shell command, and the guard
deliberately does NOT cover them — this paragraph is the record of that
edge. The reasoning is `database_class.mark_command`'s, restated by
`nrs.asset._approval_needed_message` (the gated-write refusal, which prints
the exact command an administrator runs): *an error naming a remedy the
reader has to go and look up is worse than one naming none.* A refusal's
reader is somebody who just sent the wrong thing and needs the right thing
named exactly — `details.rejected_fields`, `details.writable` and the
verbatim command ARE the design (CLAUDE.md rule 3), and a words guard over
them would forbid precisely what makes them repairable.

**What the class-1 census covers.** The composed statements of the report
surfaces, collected from LIVE calls to the builders the routes delegate to:

  - the asset history's location statement (`nrs.asset.asset_history`) —
    the REST of the history's statements are held by
    `test_asset_history.TestAssetHistoryDoesNotOverclaim.
    test_the_statements_are_words_not_field_names`, which reports cite by
    name and which stays where it is; this file adds the one key it does
    not collect rather than duplicating the eight it does;
  - the register snapshot's fidelity notes (`nrs.asset.snapshot_fidelity`)
    and its `filters.note` (`v1_assets._snapshot_filter_disclosure`);
  - the disposals report's SAP/INT-09 statement
    (`nrs.asset.disposal_report`);
  - the configuration-changes report's statement
    (`ir.config_parameter.configuration_change_report`);
  - the access-changes report's statement
    (`res.users.access_change_report`).

**User-ENTERED content is nobody's composed string** — a verification note,
a reason, a name — and it is excluded STRUCTURALLY: the collectors read
named statement keys off the payloads and never sweep whole payloads, so a
custodian called `` `fidelity.` `` could not fail this test.

**What the census cannot see, said plainly.** A statement with branches is
collected in the branch the fixture produces (the measured-empty period,
1990 — the same one handoff 49 proved empty, because every tenant's
fixtures backdate disposals to exactly 2020-01-01). A branch only a
differently-shaped tenant reaches is checked the day such a tenant runs the
suite, which is the deal every live-response census makes.

**Standing violations.** Four of the snapshot's fidelity notes carry
backticked key paths today (`myservice_asset_register/models/
asset_snapshot.py`, outside handoff 50 §5's files). They are named in
`_STANDING_VIOLATIONS` below — each an entry somebody has to argue with,
not a silence — so the guard is drawn NOW and a NEW violation fails, which
is the point; rewording the four is a wording-only change (their own
docstrings rule: branch on the enum, never the wording) left for the
handoff that owns that file.

Run with:
    odoo -d <db> -u myservice_api --test-enable \\
         --test-tags /myservice_api --stop-after-init
"""
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..controllers.v1_assets import _snapshot_filter_disclosure

#: The measured-empty period (handoff 49): every tenant's disposal fixtures
#: are backdated to exactly 2020-01-01, no configuration parameter and no
#: account predates the product, so every period-bounded report answers its
#: empty or before-the-record branch here, deterministically.
_EMPTY_FROM = "1990-01-01"
_EMPTY_TO = "1990-12-31"

#: Class-1 strings that VIOLATE the rule today, in a file outside this
#: handoff's ownership (`asset_snapshot.py`'s `SNAPSHOT_NOTES`). Keyed by
#: the census key, valued by why it is left rather than fixed here. An
#: entry whose key the census no longer collects fails as stale; a
#: violation NOT named here fails outright.
_STANDING_VIOLATIONS = {
    "snapshot.fidelity.notes.tracked_from":
        "names `tracked_from.since` in backticks; reword in "
        "asset_snapshot.py (wording-only — nothing branches on it)",
    "snapshot.fidelity.notes.custodian_id":
        "names `custodian_id` and `_fidelity.unknown` in backticks; "
        "reword in asset_snapshot.py",
    "snapshot.fidelity.notes.value":
        "names `depreciation_method`, `_fidelity.as_of_today`, "
        "`erp_managed` and `value` in backticks; reword in "
        "asset_snapshot.py. NOTE: on a tenant without the depreciation "
        "module this note is replaced by a clean sentence, so this entry "
        "asserts the KEY is still collected, not that it still violates",
    "snapshot.fidelity.notes.tag_label_state":
        "names `printed`, `affixed`, `is_tagged` and a literal comparison "
        "in backticks; reword in asset_snapshot.py",
}


def _violates_class_one(text):
    """The two mechanical rules of the asset-history test, reused verbatim:
    a backtick, or a payload path of the `fidelity.` shape. Mechanical on
    purpose — a vocabulary judgment would make the guard a reviewer."""
    return "`" in text or "fidelity." in text


@tagged("post_install", "-at_install")
class TestComposedStatementsAreWords(CadraTransactionCase):

    def _collected(self):
        """(census key, text) for every class-1 string the report surfaces
        compose. NAMED KEYS ONLY — never a sweep of a payload, so user-
        entered content cannot enter the census."""
        out = []
        Asset = self.env["nrs.asset"]

        # The register snapshot's fidelity notes, and the filter
        # disclosure's note (a pure function of the querystring — called
        # with none, which is the shape every unfiltered snapshot answers).
        fidelity = Asset.snapshot_fidelity()
        for key, text in sorted(fidelity["notes"].items()):
            out.append(("snapshot.fidelity.notes.%s" % key, text))
        out.append(("snapshot.filters.note",
                    _snapshot_filter_disclosure({})["note"]))

        # The disposals report's INT-09 statement, in the measured-empty
        # period's branch.
        disposals = Asset.disposal_report(_EMPTY_FROM, _EMPTY_TO)
        out.append(("disposals.summary.sap_coverage.statement",
                    disposals["summary"]["sap_coverage"]["statement"]))

        # The two audit reports' statements above their tables.
        config = self.env["ir.config_parameter"].configuration_change_report(
            _EMPTY_FROM, _EMPTY_TO)
        out.append(("configuration.summary.statement",
                    config["summary"]["statement"]))
        access = self.env["res.users"].access_change_report(
            _EMPTY_FROM, _EMPTY_TO)
        out.append(("access.summary.statement",
                    access["summary"]["statement"]))

        # The asset history's location statement — the one composed key
        # `test_asset_history` does not already hold (see the module
        # docstring for the division of labour).
        category = self.env["nrs.asset.category"].create(
            {"name": "Words guard category"})
        asset = Asset.create({"name": "Words guard asset",
                              "category_id": category.id})
        history = asset.asset_history()
        out.append(("history.fidelity.location.statement",
                    history["fidelity"]["location"]["statement"]))
        return out

    def test_every_composed_statement_is_words(self):
        """The guard itself: class 1 must be words, with the standing
        violations named one by one rather than waved through as a class."""
        broken = []
        for key, text in self._collected():
            self.assertTrue(
                isinstance(text, str) and text,
                "%s is not a sentence at all: %r" % (key, text))
            if _violates_class_one(text) and key not in _STANDING_VIOLATIONS:
                broken.append("%s: %r" % (key, text))
        self.assertFalse(
            broken,
            "These composed statements are shown to a reader and lean on "
            "key names or backticks. Write them as words, or — only for a "
            "string outside the files a handoff owns — name them in "
            "`_STANDING_VIOLATIONS` with where the fix belongs:\n  "
            + "\n  ".join(sorted(broken)))

    def test_the_standing_violations_name_only_keys_that_still_exist(self):
        """A waiver that outlives its string says a debt was considered
        when nothing holds it any more — the write-only list's rule. KEY
        existence, not continued violation, because two of the four are
        branch-dependent (the note's text changes with the tenant's
        modules; the key does not)."""
        collected = {key for key, _text in self._collected()}
        stale = sorted(k for k in _STANDING_VIOLATIONS if k not in collected)
        self.assertFalse(
            stale, "`_STANDING_VIOLATIONS` names census keys that are no "
            "longer collected: %s" % (stale,))

    def test_the_refusal_class_still_names_its_remedy(self):
        """The OTHER half of the separation, pinned from the class-2 side:
        the gated-write refusal must go on printing the literal command —
        the day somebody 'cleans it up' into words, the ruling this file
        records has been silently reversed, and this is what fails."""
        from odoo.addons.myservice_nrs_base.database_class import (
            mark_command)
        command = mark_command(self.env.cr.dbname)
        self.assertIn(
            self.env.cr.dbname, command,
            "the remedy must name THIS database, not a placeholder")
        # And the approval refusal composes the set command verbatim — the
        # exact sentence 36 §4 ruled must stay a command, quoted from the
        # source so a reword of the refusal is caught without writing a
        # location or a custodian (which would need a whole fixture here).
        import inspect
        from odoo.addons.myservice_asset_register.models import asset
        source = inspect.getsource(asset)
        self.assertIn(
            "set_command(self.env.cr.dbname)", source,
            "the approval refusal no longer prints the literal command; "
            "if that was ruled, this file's class definitions are what "
            "must change WITH it")
