"""The last two of §13.4's five audit reports, and the approval route.

`GET /api/v1/reports/access-changes?from=&to=`      — `access:read`
`GET /api/v1/reports/configuration-changes?from=&to=` — `settings:read`
`POST /api/v1/assets/<id>/approve-disposal`         — `approvals:write`

Four things this suite is built around, and only the first is obvious from
the routes:

**One of these three is reachable with the suite's own credential and two
are not.** `docs/api/.creds.<tenant>` holds `access:read` (via the `admin`
wildcard where the credential is admin-scoped; `identity:read` opened this
report until handoff 47 split the scope) and does NOT
hold `settings:read` or `approvals:write`. That is not a gap to be papered
over with an openapi-only assertion: a scope the token lacks is a scope the
suite can prove is ENFORCED, which is the stronger test. So the access
report is exercised in full, and the other two are asserted as real,
asserted **403s naming the exact scope** — plus the published contract, so a
consumer can learn the shape without a 200.

**The fixture has to make its own subject exist.** `approve-disposal` needs
an asset in `state = disposed`, and there are none on any tenant; the access
report needs a period that genuinely contains events, which is why the
period fixture asserts it found some rather than passing vacuously against
an empty table. A report test that does not make the data exist takes the
early-return branch on every assertion and passes having checked nothing.

**The access report is read-only and that is asserted, not assumed.** A
report that writes while it reads cannot honestly report what it found: the
second run reports a state it created. It is run twice and the events, the
summary and every roster write stamp are compared.

**The boundary is the payload.** `data` is an OBJECT on the access report on
purpose — the events sit inside it at `data.events` so it is not possible to
receive them without `data.fidelity` and `data.summary.statement`. Asserting
that the three arrive together is asserting the design, not the plumbing.

This suite writes ONE permanent artefact into whichever tenant it is pointed
at: a disposed asset named `pytest-approval-<epoch>`, created by the
`disposal_awaiting_approval` fixture. Nothing else here writes, and the
access report's read-only test would fail if it did.
"""
import base64
import datetime
import json
import re
import time

import pytest

from . import gates
from .conftest import (assert_envelope_ok, assert_envelope_err,
                       assert_fields_refused, lagos_today)

ACCESS = "/api/v1/reports/access-changes"
CONFIG = "/api/v1/reports/configuration-changes"
APPROVE = "/api/v1/assets/{id}/approve-disposal"
APPROVE_SPEC_PATH = "/api/v1/assets/{id}/approve-disposal"

# The published `summary.coverage` enum (`myservice_api/models/audit_access.py`,
# ACCESS_COVERAGE_*). Enums are published API surface (rule 4) and a consumer
# is told to branch on this value rather than on the English beside it, so the
# set is asserted explicitly rather than merely read.
#
# `recorded` was added in handoff 24 with the forward record that makes it
# reachable: the three values are a statement about where the requested period
# sits relative to the instant this tenant's access record BEGAN — `recorded`
# for a period wholly inside it (the changes listed are complete), `partial`
# for one that straddles it (the count is a lower bound), `none` for one that
# ended before it or for a tenant that has recorded nothing yet.
#
# There is deliberately NO `empty` — a quiet period and an unrecorded one must
# not look alike, which is exactly what `coverage` exists to distinguish. An
# earlier draft declared `empty` in the model, returned it nowhere, and
# published the distinction as contract in three places; this set contained it
# and asserted only membership, so it passed on the broken contract. The
# `test_no_unreachable_coverage_value_is_published` below is what stops that
# recurring: a value in this set that the report can never return now fails —
# and, in the other direction, a value the model can return that is missing
# from this set fails too, which is what carries `recorded` here.
_COVERAGE = {"none", "partial", "recorded"}

# Every key `access_change_fidelity()` promises. A boundary declaration with a
# key missing is a boundary a consumer reads past. `record_starts_at` and
# `record_rows` are handoff 24's, and `record_starts_at` is the load-bearing
# one: it is the instant the whole coverage verdict is computed against, it is
# `null` until this tenant records its first change, and it is measured from
# the earliest row held rather than from any migration date.
_FIDELITY_KEYS = ("groups_field", "groups_field_tracked",
                  "membership_audit_columns", "tracking_rows",
                  "logging_rows", "notes", "recoverable", "not_recoverable",
                  "record_starts_at", "record_rows",
                  # Handoff 45: the account-state half's own boundary.
                  "account_state_record_starts_at",
                  "account_state_record_rows")

# The four facts the forward record makes answerable, and only from the instant
# it begins. `access_change_fidelity` moves them between `recoverable` and
# `not_recoverable` by MEASUREMENT, so the assertions below pin the RULE and
# never the list — a suite that pinned either list would be asserting which
# tenant it last ran against.
_RECORDED_FACTS = {"group_granted", "group_removed", "group_change_actor",
                   "group_change_timestamp"}

# The same rule for an account switched off or on (handoff 45), against the
# account-state record's OWN start — that half began later than the group half.
_ACCOUNT_STATE_FACTS = {"account_deactivated", "account_reactivated",
                        "account_state_change_actor",
                        "account_state_change_timestamp"}

# A key name that would mean a credential travelled in the roster. Matched on
# the NAME, the same rule `audit_configuration._SECRET_KEY_RE` applies to
# parameter keys, and for the same reason: a deny-list of the fields that
# exist today misses the one added next month.
_CREDENTIALISH = re.compile(
    r"secret|password|passwd|pwd|token|api_?key|private_?key|credential"
    r"|salt|signature|totp|hash|cookie|session", re.IGNORECASE)

# Every spelling `_APPROVER_CLAIM_FIELDS` in `v1_assets.py` knows about. The
# approve-disposal route refuses a body carrying any of them; PATCH must not
# write any of them either, under any spelling.
_APPROVER_SPELLINGS = ("disposal_approved_by", "disposal_approved_date",
                       "disposal_approved_at", "approved_by", "approved_date",
                       "approved_at", "approver", "approver_id",
                       "approved_by_id", "approver_name", "user_id", "uid")


def _today():
    # The LAGOS day, not the machine's: both reports here bound Lagos days
    # (configuration since 63b, access since 65), and so does a disposal's
    # date. CI's clock is UTC, where `date.today()` is yesterday in Lagos
    # from 23:00 to 24:00 and a row made a moment ago falls outside it.
    return lagos_today()


def _iso(d):
    return d.isoformat()


# ─── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def history(client):
    """A period wide enough to contain events, and the report for it.

    Returns `{'from', 'to', 'body', 'data'}`. Every account on the tenant was
    created at some point after 2000, so a period from then to today contains
    at least one `account_created` event by construction — but it is ASSERTED
    rather than assumed, because every assertion below about events, coverage
    and statements is vacuous against an empty report, and a suite that
    passes on an empty report is worse than one that fails.
    """
    date_from, date_to = "2000-01-01", _iso(_today())
    r = client.get(ACCESS, params={"from": date_from, "to": date_to})
    body = assert_envelope_ok(r)
    # The WHOLE report, every page: `roster` and `events` page together by
    # account (default 50), and `summary` counts the whole period. Until
    # handoff 44 this read one page, which was the whole report only while
    # the tenant held fewer than 51 accounts — `test19` crossed that with
    # handoff 43's fixtures (61), and the count test below failed 198 vs 170
    # on a report that was right. `body` stays the first page.
    data = dict(body["data"],
                events=list(body["data"]["events"]),
                roster=list(body["data"]["roster"]))
    cursor, pages = body["pagination"]["next_cursor"], 1
    # An API credential sees at most the external record cap of accounts
    # (`utils.EXTERNAL_TOTAL_CAP`), announced in the top-level `_warnings`.
    # `test19` crossed 100 accounts on 2026-10-02; from then on the walk ends
    # at the cap BY DESIGN and the tests below assert the announcement
    # instead of a total this credential is not shown.
    truncated = (body.get("_warnings") or {}).get("truncated")
    while cursor:
        page = assert_envelope_ok(client.get(ACCESS, params={
            "from": date_from, "to": date_to, "cursor": cursor}))
        truncated = truncated or (page.get("_warnings") or {}).get("truncated")
        data["events"] += page["data"]["events"]
        data["roster"] += page["data"]["roster"]
        cursor = page["pagination"]["next_cursor"]
        pages += 1
        assert pages <= 1000, "the access report did not stop paging"
    assert data["events"], (
        "the whole-history period returned no access events at all. Every "
        "assertion in this suite about events, coverage and the statement "
        "would be vacuous, so this fails loudly rather than passing having "
        "checked nothing.")
    assert data["roster"], "the tenant reports no accounts at all"
    return {"from": date_from, "to": date_to, "body": body, "data": data,
            "truncated": truncated}


def token_scopes(token):
    """The scopes this suite's own credential actually holds.

    **The scopes are a property of the TENANT, not of this suite**, and three
    tests in this file learned that the expensive way. They asserted a `403`
    on the reasoning that "this suite's credential does not hold
    `settings:read`" — true of `jaizbankplc`, where they were written and
    where they passed, and false in CI, whose `scripts/bootstrap.py` grants
    its client `_all_scopes()` on purpose. CI answered `200` three times.

    That is CLAUDE.md's own warning one level along: *a per-tenant number is
    a fact about a demo, not about an estate.* It is just as true of a
    per-tenant scope list.

    So the tests below branch on what the credential really holds and assert
    something real either way — the refusal where the scope is absent, the
    contract where it is present. Deliberately NOT a skip: a skip is a guard
    that passes, and the scope-gated routes are the ones where that matters
    most.

    Read without verifying: the signature is the server's business, and this
    is reading the caller's own token to decide what to assert about it.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return set(scopes)



def token_grants(token, scope):
    """Does this credential reach `scope` — including via the `admin` wildcard?

    `admin` is a wildcard in `require_jwt`
    (`myservice_api/controllers/utils.py:236` says so in as many words), so a
    credential holding `admin` reaches every scope-gated route without ever
    listing the specific scope. Asking `scope in token_scopes(token)` is
    therefore not the same question the server answers, and the difference is
    invisible on any tenant whose credential happens to hold the named scope.

    Handoff 25 found it the way `token_scopes` itself was found: by pointing
    the suite at a different tenant. `test19`'s client holds `admin` but NOT
    `settings:read`, so the configuration report answered 200 while the test
    was still expecting the 403 branch — a tenant behaving correctly and a
    test asserting the wrong half.

    Same lesson one level along again: a scope list is a fact about a tenant,
    and so is the wildcard that shortcuts it.
    """
    scopes = token_scopes(token)
    return scope in scopes or "admin" in scopes

def _make_disposed_asset(client, test_location):
    """A disposed asset with no approver, freshly created every call.

    **Function-scoped on purpose.** This was one module-scoped fixture, and
    on a tenant whose credential holds `approvals:write` the approval test
    approved it — after which the PATCH test, which needs a pristine
    subject, found `approved_by` already set and failed on a state its own
    assertions had not created. A fixture that one test mutates and another
    depends on is an ordering coupling, and it reads as a real defect in the
    code the second time somebody hits it.
    """
    body = {
        "name": f"pytest-approval-{int(time.time() * 1000)}",
        "category_id": 1,
        "condition": "poor",
        "state": "disposed",
        "location_id": test_location["id"],
        "disposal_date": _iso(_today()),
        "disposal_reason": "pytest — approve-disposal fixture",
    }
    if gates.receipt_gated(client):
        # Handoff 58, P5: a receipt cannot arrive disposed; the unit is
        # walked onto the register and disposed there (`tests/gates.py`). A
        # disposal is approved on a register asset either way.
        data = gates.disposed_on_the_register(client, **body)
    else:
        r = client.post("/api/v1/assets",
                        json=gates.receipt_body(client, **body))
        if r.status_code != 201:
            pytest.skip(
                "could not create a disposed asset on this tenant "
                f"(HTTP {r.status_code}): {r.text[:200]}. The approval "
                "assertions would have nothing to act on.")
        data = r.json()["data"]
    assert data["disposal"]["approved_by"] is None, (
        "a freshly created disposal already carries an approver — the create "
        "path wrote one, which is the control this whole route exists to "
        "keep")
    return data


@pytest.fixture
def disposal_awaiting_approval(client, test_location):
    """One disposed asset with no approver — approve-disposal's own subject."""
    return _make_disposed_asset(client, test_location)


def _credential_keys(value, path=""):
    """Every key anywhere in `value` whose NAME says it carries a secret."""
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            here = f"{path}.{k}" if path else k
            if _CREDENTIALISH.search(str(k)):
                found.append(here)
            found.extend(_credential_keys(v, here))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found.extend(_credential_keys(v, f"{path}[{i}]"))
    return found


# ─── the access report · the statement above the table ───────────────

def test_the_statement_is_present_and_its_coverage_is_one_we_publish(
        client, history, capture):
    """*"Read `summary.statement` before `data.events`."*

    The statement is the report's answer to the question as asked — that
    Cadra holds no record of group grants at all — and `coverage` is the
    machine-readable half of it. A consumer is told to branch on the enum
    and never on the English, so the enum is asserted against the published
    set: a sixth value appearing here is a breaking change for anybody who
    wrote that branch.
    """
    r = client.get(ACCESS, params={"from": history["from"],
                                   "to": history["to"]})
    capture("reports/access_changes", r)
    summary = assert_envelope_ok(r)["data"]["summary"]

    assert summary["statement"], "the report published no statement"
    assert summary["statement"].strip(), "the statement is whitespace"
    assert summary["coverage"] in _COVERAGE, (
        f"`coverage` is {summary['coverage']!r}, which is not one of "
        f"{sorted(_COVERAGE)}. This enum is published API surface and a "
        "consumer branches on it.")
    # The counts an auditor reads off the statement must be the counts in the
    # payload beside it — or, when the record cap bit, the payload must SAY
    # how much of it this credential was shown.
    truncated = history["truncated"]
    if truncated:
        assert truncated["total"] == summary["accounts"], (truncated, summary)
        assert len(history["data"]["roster"]) == truncated["cap"], (
            "the walk returned %d accounts under a cap of %d"
            % (len(history["data"]["roster"]), truncated["cap"]))
        assert summary["events_in_period"] >= len(history["data"]["events"])
    else:
        assert summary["events_in_period"] == len(history["data"]["events"])
        assert summary["accounts"] == len(history["data"]["roster"])


def test_no_unreachable_coverage_value_is_published(client):
    """A published enum value the code cannot return is a contract with a
    hole in it, and asserting only membership passes straight over it.

    The access report shipped declaring `empty`, returning it nowhere, and
    documenting the `empty` / `none` distinction in the changelog, the
    OpenAPI description and INT-10 §2.10. A consumer branching on `coverage`
    would have written a dead arm and, worse, would have read a quiet period
    as `empty` when the report was about to call it `none`.

    So this reads the MODEL's declared constants and requires every one of
    them to be reachable from `_access_change_coverage`, which is the only
    place the value is decided. It is a source-level check because the wire
    can only ever show the branch this tenant's data happens to take.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    source = (root / "myservice_api" / "models" / "audit_access.py").read_text()
    tree = ast.parse(source)

    declared = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("ACCESS_COVERAGE_")
        and isinstance(node.value, ast.Constant)
    }
    assert declared, "no ACCESS_COVERAGE_* constants found — did they move?"

    returned = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id.startswith("ACCESS_COVERAGE_")
    } - set(declared)  # the assignment targets themselves are not returns
    used = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        and n.id.startswith("ACCESS_COVERAGE_")
    }

    unreachable = sorted(set(declared) - used)
    assert not unreachable, (
        "these coverage values are declared and never returned: %s. A "
        "published enum value the report cannot produce is a dead arm in "
        "every consumer that branches on it — delete the constant, or make "
        "it reachable." % unreachable)

    assert set(declared.values()) == _COVERAGE, (
        "the model declares %s and this suite publishes %s; the two must "
        "agree or one of them is describing a contract that does not exist"
        % (sorted(declared.values()), sorted(_COVERAGE)))


def test_group_changes_in_period_is_present_and_measured(client, history):
    """PRESENT always; `0` only where the record cannot answer.

    The key is in the payload precisely so a consumer reading counts SEES
    the absence rather than inferring it from a missing key — the same
    argument `omitted_asset_ids` makes on the register snapshot. A missing
    key is indistinguishable from a consumer's own typo. That half is
    unchanged.

    What changed in handoff 24 is the zero. This asserted `== 0` on the
    reasoning that nothing in the database could produce a group change;
    there is now a forward record that can, so the old assertion would fail
    the day a tenant recorded its first grant — and the "fix" somebody would
    reach for is deleting the test.

    **It has to stay honest in both states, because every tenant is in the
    first one today and will be in the second one tomorrow.** So the rule is
    asserted rather than the number: with no record there can be no count and
    `coverage` must not claim one; with a record the count is a real
    measurement that cannot be smaller than the group events published
    beside it. `coverage` is what tells a zero-because-nothing-happened from
    a zero-because-the-record-does-not-reach-this-period, which is the
    distinction the count alone cannot carry.
    """
    summary = history["data"]["summary"]
    fidelity = history["data"]["fidelity"]

    assert "group_changes_in_period" in summary, (
        "`group_changes_in_period` is absent. A count that is not in the "
        "payload is not a statement about the record — it is a key a "
        "consumer will read as its own mistake.")
    assert "implication_changes_in_period" in summary, (
        "`implication_changes_in_period` is absent. On Odoo 19 a group "
        "implication moves effective access while writing no membership row "
        "at all, so a consumer that only ever sees membership counts is "
        "blind to the access change that leaves the least trace.")
    count = summary["group_changes_in_period"]
    assert isinstance(count, int) and not isinstance(count, bool)
    assert count >= 0

    if fidelity["record_starts_at"] is None:
        assert count == 0, (
            f"the report counted {count} group changes on a tenant whose "
            "access record has not begun — `fidelity.record_starts_at` is "
            "null, so there are no rows to have counted and this is a "
            "synthesised history.")
        assert summary["implication_changes_in_period"] == 0
        assert summary["coverage"] != "recorded", (
            "`coverage` is `recorded` on a tenant holding no access-change "
            "rows. `recorded` means the listed changes are COMPLETE for the "
            "period; with no record it is a claim of coverage that does not "
            "exist.")
        return

    # The record has begun. The period runs from 2000-01-01 to today and the
    # record cannot have begun before this code was written, so it begins
    # part-way through: a lower bound, and the statement has to say so.
    assert summary["coverage"] == "partial", (
        f"a period from 2000 to today, on a tenant whose record began at "
        f"{fidelity['record_starts_at']}, was answered "
        f"{summary['coverage']!r}. It straddles the start of the record, so "
        "the count is a lower bound and `partial` is the only honest answer.")
    recorded_events = [e for e in history["data"]["events"]
                       if e["event"] in ("granted", "removed")]
    assert count >= len(recorded_events), (
        f"the summary counts {count} group changes and {len(recorded_events)} "
        "are published as events. The count covers the whole period and the "
        "events are the page, so the count can be larger — never smaller.")


def test_the_fidelity_block_publishes_every_key_it_promises(client, history):
    """The boundary is only a boundary if every part of it arrives.

    `fidelity` is re-MEASURED on each request rather than carried as a
    constant, so that the day this deployment grows an access history the
    report says so. That only works if the measurements are all published.
    """
    fidelity = history["data"]["fidelity"]
    for key in _FIDELITY_KEYS:
        assert key in fidelity, (
            f"`data.fidelity.{key}` is absent — the report measured "
            "something it did not publish")
    assert isinstance(fidelity["notes"], dict) and fidelity["notes"], (
        "`fidelity.notes` is empty; the English behind each measurement is "
        "the part an auditor reads")
    assert fidelity["recoverable"], "`recoverable` names nothing"
    assert fidelity["not_recoverable"], (
        "`not_recoverable` names nothing, on a report whose entire purpose "
        "is to say what it cannot answer")
    # The two halves must not overlap — a fact claimed as both recoverable
    # and not recoverable is a boundary that says nothing.
    assert not (set(fidelity["recoverable"])
                & set(fidelity["not_recoverable"]))
    assert isinstance(fidelity["record_rows"], int)
    assert fidelity["record_rows"] >= 0
    # One measurement seen twice: `changed_at` is required on the model, so a
    # tenant holding rows has an earliest one and a tenant holding none has no
    # start. If these disagree, one of them has stopped being measured.
    assert (fidelity["record_starts_at"] is None) == \
        (fidelity["record_rows"] == 0), (
            f"`record_starts_at` is {fidelity['record_starts_at']!r} while "
            f"`record_rows` is {fidelity['record_rows']} — a row cannot exist "
            "without a `changed_at`, so one of these is a constant rather "
            "than a measurement")
    assert "record_start" in fidelity["notes"], (
        "the fidelity block measures when the access record begins and "
        "publishes no English for it; the note is the half an auditor reads")


def test_the_group_facts_move_with_the_record_not_with_the_code(
        client, history):
    """`recoverable` and `not_recoverable` are DYNAMIC, and this is the rule.

    Group grants and removals were flatly not recoverable until handoff 24.
    They are now recoverable **from the instant this tenant's record begins**
    and not before — which is a property of the tenant, not of the deployed
    code. A build that moved the four facts into `recoverable` because the
    recorder is installed would be claiming coverage of every period in the
    past, on a report whose entire value is that it does not do that.

    Asserted as the rule so it holds in both states: every tenant holds zero
    rows today, and the first grant on any of them flips this over without
    anything else changing.
    """
    fidelity = history["data"]["fidelity"]
    recoverable = set(fidelity["recoverable"])
    not_recoverable = set(fidelity["not_recoverable"])

    if fidelity["record_starts_at"]:
        assert _RECORDED_FACTS <= recoverable, (
            f"this tenant's record began at {fidelity['record_starts_at']} "
            f"and {sorted(_RECORDED_FACTS - recoverable)} are still not "
            "published as recoverable — the report is understating a record "
            "it holds")
        assert not (_RECORDED_FACTS & not_recoverable)
    else:
        assert _RECORDED_FACTS <= not_recoverable, (
            f"this tenant holds no access-change rows and "
            f"{sorted(_RECORDED_FACTS - not_recoverable)} are not named as "
            "unrecoverable. Nothing can be answered about a grant here, and "
            "a boundary that omits the four facts the whole report is about "
            "is worse than no boundary.")
        assert not (_RECORDED_FACTS & recoverable)


def test_the_account_state_half_has_its_own_count_and_boundary(
        client, history):
    """Deactivations and reactivations (handoff 45): present at zero, counted
    apart from the group and implication counts, bounded by their own start,
    and published as events that name no group.

    Asserted as the rule, in whatever state the tenant is in: a tenant that
    has never switched an account off since the recorder shipped has no
    account-state start and must say `none` for it, however healthy its
    group record is."""
    summary = history["data"]["summary"]
    fidelity = history["data"]["fidelity"]
    for key in ("account_state_changes_in_period",
                "account_state_changes_not_shown", "account_state_coverage"):
        assert key in summary, f"`summary.{key}` is absent"
    count = summary["account_state_changes_in_period"]
    assert isinstance(count, int) and not isinstance(count, bool) and count >= 0
    assert summary["account_state_coverage"] in _COVERAGE
    assert "account_state" in fidelity["notes"]

    recoverable = set(fidelity["recoverable"])
    not_recoverable = set(fidelity["not_recoverable"])
    assert (fidelity["account_state_record_starts_at"] is None) == \
        (fidelity["account_state_record_rows"] == 0), fidelity
    if fidelity["account_state_record_starts_at"] is None:
        assert count == 0, (
            f"{count} deactivations/reactivations counted on a tenant that "
            "holds none")
        assert summary["account_state_coverage"] == "none"
        assert _ACCOUNT_STATE_FACTS <= not_recoverable
        assert not (_ACCOUNT_STATE_FACTS & recoverable)
    else:
        # From 2000 to today straddles any start this code can have.
        assert summary["account_state_coverage"] == "partial"
        assert _ACCOUNT_STATE_FACTS <= recoverable
        assert not (_ACCOUNT_STATE_FACTS & not_recoverable)

    state_events = [e for e in history["data"]["events"]
                    if e["event"] in ("deactivated", "reactivated")]
    assert count >= len(state_events), (
        f"the summary counts {count} account-state changes and "
        f"{len(state_events)} are published as events")
    for e in state_events:
        assert e["group"] is None, e
        assert e["precision"] == "exact", e
        assert "attributable" in e, e


def test_the_finding_itself_is_asserted_from_the_api(client, history):
    """The finding, read off the wire rather than off the docstring.

    `res_groups_users_rel` is `(gid, uid)` and nothing else, and
    `res.users.group_ids` carries no tracking. Those are the two schema facts
    that make a RECONSTRUCTED grant history impossible, and this asserts the
    report MEASURED them rather than asserting them itself.

    Handoff 24 did not change either fact and was not able to: the forward
    record is a separate append-only table written as membership moves, which
    is why it can only ever answer forwards. The past is still gone. That is
    the distinction this test keeps visible — a reader who sees group changes
    in the payload must still be able to check that they did not come from
    the membership table, because nothing can come from the membership table.

    If this test ever fails because the values changed, the report is right
    and the test is out of date — somebody added tracking or an audit
    module, and `coverage` should now be reading `partial` on that account.
    """
    fidelity = history["data"]["fidelity"]
    assert fidelity["membership_audit_columns"] == [], (
        "the membership table now carries audit columns "
        f"({fidelity['membership_audit_columns']}) — the report's stated "
        "limitation has stopped being true and `coverage` should say so")
    assert fidelity["groups_field_tracked"] is False, (
        "the groups field now carries tracking; there IS a chatter history "
        "to read and this report is no longer reading everything it could")
    assert fidelity["groups_field"] in ("group_ids", "groups_id"), (
        "the report could not find the groups field at all, which means the "
        "membership measurement above was taken against nothing")


def test_the_events_cannot_be_received_without_the_boundary(client, history):
    """Why `data` is an OBJECT and not an array of events.

    There is nowhere honest to hang a boundary declaration off an array, and
    a boundary a consumer can miss by reading the obvious key is not a
    boundary. So the events sit INSIDE the declaration: one response
    carries the events, the fidelity block and the statement, or it carries
    none of them.
    """
    r = client.get(ACCESS, params={"from": history["from"],
                                   "to": history["to"]})
    data = assert_envelope_ok(r)["data"]

    assert isinstance(data, dict), (
        "`data` is an array. The events are then reachable without the "
        "boundary that qualifies them, which is the whole reason this "
        "report's `data` is an object.")
    assert "events" in data and isinstance(data["events"], list)
    assert "fidelity" in data, (
        "events arrived without `fidelity` — a consumer can now read the "
        "rows without ever seeing what the report cannot say")
    assert data["summary"].get("statement"), (
        "events arrived without `summary.statement`")
    assert "roster" in data and "period" in data
    # Spelled exactly as `DisposalReport` spells it. An auditor reading the
    # five §13.4 reports side by side must not meet the same fact under two
    # names; the first draft of this route published `{from, to, bounds}`
    # and it was corrected to match the report that shipped first.
    assert data["period"] == {"date_from": history["from"],
                              "date_to": history["to"],
                              "inclusive": "both"}, (
        "the report did not echo back the period it was asked for, or "
        "stopped declaring its bounds inclusive, or drifted from the "
        "spelling `/reports/disposals` publishes")


def test_no_roster_row_carries_a_credential(client, history):
    """*Who has access now* is a question about identity, not about secrets.

    The roster joins `res.users` to `myservice.api.client`, and that client
    record holds a hashed secret beside the scopes. An audit credential is
    exactly the broad, long-lived, widely-shared credential that must not be
    carrying one — the same argument `audit_configuration._redact` makes
    about `myservice_api.jwt_secret`.
    """
    leaked = _credential_keys(history["data"]["roster"], "roster")
    assert leaked == [], (
        f"the roster published credential-named keys: {leaked}. A read-scoped "
        "audit report must not be a second door onto a secret.")
    # And the same for the events, which carry the same actors.
    assert _credential_keys(history["data"]["events"], "events") == []
    # The rows that ARE expected — enough to prove the check ran against a
    # populated structure rather than an empty list.
    row = history["data"]["roster"][0]
    for key in ("user_id", "login", "name", "active", "groups",
                "is_api_client", "api_scopes"):
        assert key in row, f"roster row is missing `{key}`"


# ─── the access report · the period ──────────────────────────────────

def test_both_period_bounds_are_required(client):
    """A period report with no period is a report of all history under a
    heading that claims a quarter. Neither bound defaults."""
    good = _iso(_today())

    body = assert_envelope_err(client.get(ACCESS, params={"to": good}),
                               400, "invalid_request")
    assert "from" in body["error"]["message"]
    assert "from" in body["error"]["details"]

    body = assert_envelope_err(client.get(ACCESS, params={"from": good}),
                               400, "invalid_request")
    assert "to" in body["error"]["message"]
    assert "to" in body["error"]["details"]

    assert_envelope_err(client.get(ACCESS), 400, "invalid_request")


def test_an_unparseable_date_is_a_400_naming_the_parameter(client, capture):
    """Both parameters separately, and never a silent whole-history report
    under the caller's chosen heading."""
    good = _iso(_today())

    r = client.get(ACCESS, params={"from": "lastish-quarter", "to": good})
    capture("reports/access_changes_bad_from", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "from" in body["error"]["message"]
    assert body["error"]["details"]["from"] == "lastish-quarter", (
        "the 400 did not echo the value it refused, so the caller cannot see "
        "which of its two dates was wrong")

    body = assert_envelope_err(
        client.get(ACCESS, params={"from": good, "to": "2026-13-45"}),
        400, "invalid_request")
    assert "to" in body["error"]["message"]
    assert body["error"]["details"]["to"] == "2026-13-45"


def test_a_period_that_ends_before_it_starts_is_a_400_naming_both(client):
    """`invalid_request`, not `validation_failed`. An integration branching
    on `error.code` must be told its REQUEST was wrong rather than that a
    record failed validation — and it must be told which two dates, because
    either one of them could be the typo."""
    body = assert_envelope_err(
        client.get(ACCESS, params={
            "from": _iso(_today()),
            "to": _iso(_today() - datetime.timedelta(days=30))}),
        400, "invalid_request")
    assert "from" in body["error"]["details"]
    assert "to" in body["error"]["details"]


def test_a_single_day_period_is_a_real_period(client):
    """The upper bound is INCLUSIVE of the whole closing day.

    `from == to` is how an auditor asks about one day, and an exclusive
    upper bound makes that request empty by construction — a 200 reporting
    nothing, which is indistinguishable from a quiet day. It must answer,
    and it must answer for a period whose two bounds are the same date.
    """
    today = _iso(_today())
    body = assert_envelope_ok(client.get(ACCESS, params={"from": today,
                                                         "to": today}))
    data = body["data"]
    assert data["period"] == {"date_from": today, "date_to": today,
                              "inclusive": "both"}
    assert data["summary"]["coverage"] in _COVERAGE
    assert isinstance(data["events"], list)
    # The roster is present-tense and does not depend on the period at all —
    # a one-day window must not silently narrow "who has access now".
    assert data["roster"], (
        "a single-day period returned an empty roster. The roster is CURRENT "
        "access and is not a function of the period.")


# ─── the access report · read-only ───────────────────────────────────

def test_the_access_report_does_not_repair_what_it_finds(client, history):
    """*"A report that quietly fixes what it finds can never honestly report
    zero"* — the second run reports a state it created itself.

    Asserted from the API alone, and the strongest available signal is the
    roster's own write stamps: this report reads `res.users`, so a write on
    the read path would move `last_modified_at` on some row and, one run
    later, manufacture an `account_modified` event that nobody caused.
    """
    first = assert_envelope_ok(
        client.get(ACCESS, params={"from": history["from"],
                                   "to": history["to"]}))["data"]
    second = assert_envelope_ok(
        client.get(ACCESS, params={"from": history["from"],
                                   "to": history["to"]}))["data"]

    assert first["events"] == second["events"], (
        "two consecutive runs of the same period reported different events. "
        "Either the report wrote while it read, or something it reads on is "
        "not stable — both make the report unciteable.")
    assert first["summary"] == second["summary"]

    stamps_first = {r["user_id"]: r["last_modified_at"]
                    for r in first["roster"]}
    stamps_second = {r["user_id"]: r["last_modified_at"]
                     for r in second["roster"]}
    assert stamps_first == stamps_second, (
        "running the access report moved a user's write stamp. The report is "
        "read-only; a moved stamp is a write on the read path, and it would "
        "show up in the NEXT run as an `account_modified` event that nobody "
        "caused.")
    assert first["fidelity"] == second["fidelity"], (
        "the measured boundary changed between two runs of the same request")


def test_the_access_report_refuses_a_caller_with_no_token(unauthed_client):
    """The report runs `sudo()` and reads the whole identity register, so the
    token is the only gate between a caller and every login on the tenant."""
    assert_envelope_err(
        unauthed_client.get(ACCESS, params={"from": _iso(_today()),
                                            "to": _iso(_today())}),
        401, "unauthorized")


def test_the_access_report_is_gated_on_access_read(client):
    """`access:read` — its own scope since handoff 47, not `identity:read`.

    The same-data-same-scope ruling put it on `identity:read` first; what
    that missed is that the scope was TWO data sets under one name — the
    employee picker a custodian needs, and the record of who granted whom
    which role. Every Asset User could read the access record, and the
    Auditor (whose job it is) could not find it. Asserted from the published
    contract because the suite holds one credential and cannot narrow it.
    """
    spec = client.get("/api/v1/openapi.json").json()
    assert ACCESS in spec["paths"], f"{ACCESS} is not published"
    op = spec["paths"][ACCESS]["get"]
    assert op["x-cadra-scopes"] == ["access:read"], (
        f"{ACCESS} declares {op['x-cadra-scopes']}; the access record takes "
        "its own scope (handoff 47), granted to the Auditor and covered by "
        "the admin wildcard")
    assert op["security"], "the report publishes no security requirement"
    assert "AccessChangeReport" in \
        spec["components"]["schemas"], "the component schema is not published"


def test_the_report_honours_the_pagination_parameters_it_publishes(
        client, history):
    """Written when it FAILED, kept now that it passes.

    Both reports declared `limit` and `cursor` in `query_params` and neither
    handler read either one, so `openapi.json` published two parameters that
    did nothing: `?limit=1` returned every event and every roster row,
    `?limit=abc` answered **200** where the disposal report answers `400`,
    and there was no `pagination` block at all — a caller walking
    `pagination.next_cursor` read `None` on page one and stopped, correctly
    by accident. That is rule 3 exactly: *anything that silently degrades is
    a defect even when it returns 200.* The roster was also unbounded, which
    on a tenant with a large `res.users` is the uncapped-response shape the
    external record cap exists to prevent, reachable with a read-only scope.

    **A page here is a window of ACCOUNTS, not of events**, and that is why
    the route spells out its own `limit` description instead of taking the
    shared one. `roster` is the window; `events` is every event belonging to
    it, so one account carrying two events answers `limit=1` with two events
    and that is correct. Paging the two lists independently would let a
    caller hold an event for an account whose roster row is three pages
    away.
    """
    params = {"from": history["from"], "to": history["to"], "limit": 1}
    body = assert_envelope_ok(client.get(ACCESS, params=params))

    assert "pagination" in body, (
        "the report publishes `limit` and `cursor` and returns no "
        "`pagination` block — a caller has no way to know whether it "
        "received the whole report")
    roster = body["data"]["roster"]
    assert len(roster) == 1, (
        "`limit=1` returned %d roster rows. A page is a window of accounts "
        "and the parameter bounds it." % len(roster))

    # The two lists describe the SAME accounts. This is the invariant that
    # makes one cursor honest for both.
    on_page = {r["user_id"] for r in roster}
    stray = [e["user_id"] for e in body["data"]["events"]
             if e["user_id"] not in on_page]
    assert not stray, (
        "events arrived for accounts that are not on this page: %s. The "
        "roster and the events must describe one window." % sorted(set(stray)))

    # `summary` is the whole period on every page — the statement above the
    # table must not change under a reader who has paged.
    assert body["data"]["summary"]["accounts"] == \
        body["pagination"]["total_estimate"], (
            "`total_estimate` disagrees with `summary.accounts`; they must "
            "come from one count of the period")
    assert body["data"]["summary"]["accounts"] > 1, (
        "this tenant has one account, so the paging assertions above proved "
        "nothing")


def test_the_published_event_order_is_ascending_account_id(client, history):
    """The order a CONSUMER sees, which is not the order the model produces.

    The model sorts `(at, user_id, event)`; the route re-sorts by ascending
    account id before publishing, because the cursor walks ascending ids and
    a chronological list cannot be paged honestly with the cursor this API
    issues — the trade `/reports/disposals` documents. Nothing asserted the
    published order at all until the verification pass noticed that the
    model's own test claimed chronological under a title about what an
    auditor reads.

    Every event carries `at`, so a caller that has walked the whole period
    can re-sort it; that is what makes the trade acceptable rather than a
    loss.
    """
    body = assert_envelope_ok(client.get(ACCESS, params={
        "from": history["from"], "to": history["to"], "limit": 100}))
    events = body["data"]["events"]
    assert len(events) > 1, "too few events to prove anything about order"
    ids = [e["user_id"] for e in events]
    assert ids == sorted(ids), (
        "the published events are not in ascending account id, which is the "
        "order the cursor walks: %s" % ids)
    assert all("at" in e for e in events), (
        "an event has no `at`, so a caller cannot re-sort chronologically "
        "and the ordering trade is a straight loss")


def test_an_unreadable_limit_or_cursor_is_refused_not_ignored(client, history):
    """The other half: the parameters are parsed, not merely consumed.

    `parse_limit` and `decode_cursor` are the same two functions every list
    route in this API uses, so `?limit=all` and a cursor this API did not
    issue get the same answer here as everywhere else — a 400 rather than a
    silently unfiltered or silently restarted read. Handoff 21 refused the
    first and handoff 22 the second; a report added afterwards must not
    reopen either.
    """
    for bad in ({"limit": "abc"}, {"limit": "all"}, {"cursor": "garbage"}):
        params = {"from": history["from"], "to": history["to"], **bad}
        r = client.get(ACCESS, params=params)
        assert r.status_code == 400, (
            "%s answered %d, not 400 — the parameter is published and "
            "not parsed" % (bad, r.status_code))


def test_the_cursor_walks_the_whole_report_without_repeating(client, history):
    """A cursor that drops or repeats an account is a report with a hole.

    Walked at `limit=1`, the smallest page the route accepts, so the walk
    takes more than one page on ANY register holding at least two accounts.
    It used to walk at `limit=3` and assert that more than one page came
    back, which made the proof a function of how many users the tenant
    happened to have — it failed on the marked test tenant handoff 25 moved
    the suite onto, where the whole roster fits in three rows. The property
    under test is the cursor, not the size of the register.
    Asserts ascending order, no duplicate, and that the walk totals exactly
    what `pagination.total_estimate` promised — the same three properties
    `test_the_snapshot_pages_forwards_without_repeating` asserts.
    """
    seen, cursor, pages = [], None, 0
    total = None
    # The budget is the report's own promise plus slack, not a constant: a
    # fixed 60 was the size of `test19` in handoff 25, and it had 61 accounts
    # by handoff 44. A walk that needs more pages than `total_estimate` is
    # still caught — that is the repeat this test exists for.
    budget = len(history["data"]["roster"]) + 5
    while pages < budget:
        params = {"from": history["from"], "to": history["to"], "limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(ACCESS, params=params))
        total = body["pagination"]["total_estimate"]
        seen += [r["user_id"] for r in body["data"]["roster"]]
        cursor = body["pagination"]["next_cursor"]
        pages += 1
        if not cursor:
            break
    assert cursor is None, (
        "the walk did not terminate in %d pages for %d accounts"
        % (budget, len(history["data"]["roster"])))
    assert pages > 1, (
        "the whole report fitted on one page, so this proved nothing about "
        "the cursor")
    assert seen == sorted(seen), "the walk was not in ascending account id"
    assert len(seen) == len(set(seen)), (
        "the walk returned the same account twice: %s"
        % sorted({u for u in seen if seen.count(u) > 1}))
    expected = (history["truncated"]["cap"] if history["truncated"] else total)
    assert len(seen) == expected, (
        "the walk returned %d accounts; `total_estimate` is %d and the record "
        "cap, when it bit, is %r" % (len(seen), total, history["truncated"]))


# ─── the configuration report · the scope that is not held ───────────

def test_the_configuration_report_answers_according_to_the_scope_held(
        client, token, capture):
    """Enforced where the scope is absent; correct where it is present.

    **Both branches assert, and neither skips.** This began as a one-sided
    `403` test on the reasoning that "this suite's credential does not hold
    `settings:read`" — true of `jaizbankplc` and false in CI, where
    `scripts/bootstrap.py` grants its client every scope deliberately. It
    answered `200` and the test failed on a tenant that was behaving
    correctly. See `token_scopes`.

    The report reads `ir_config_parameter` — the table holding
    `myservice_api.jwt_secret` — so where the scope is missing the gate has
    to be real, and where it is held the REDACTION has to be real. The two
    branches are the two halves of the same control.
    """
    r = client.get(CONFIG, params={"from": "2000-01-01", "to": _iso(_today())})
    capture("reports/configuration_changes_by_scope", r)

    if not token_grants(token, "settings:read"):
        body = assert_envelope_err(r, 403, "forbidden")
        details = body["error"]["details"]
        assert details["required_scopes"] == ["settings:read"], (
            f"the 403 names {details.get('required_scopes')} as required; "
            "this report is gated on `settings:read` and the error must say "
            "which scope to ask for")
        assert "settings:read" in body["error"]["message"], (
            "the message does not name the missing scope, so an integrator "
            "has to read the details block to learn what to request")
        assert "granted_scopes" in details, (
            "the 403 does not say what the caller DOES hold — the caller "
            "then cannot tell a missing scope from a broken token")
        return

    # The credential holds it, so prove the thing the scope protects.
    data = assert_envelope_ok(r)["data"]
    assert data["summary"]["coverage"] in {"empty", "no_modifications",
                                           "last_write_only", "partial"}
    assert data["summary"]["statement"]

    secrets = [row for row in data["parameters"] if row["value_is_redacted"]]
    assert len(secrets) == data["summary"]["redacted_values"]
    for row in secrets:
        assert row["current_value"].startswith("[redacted] sha256:"), (
            f"{row['key']} is marked redacted and its value is not: "
            f"{row['current_value'][:40]!r}")

    # The one that matters: no key naming a credential is published in the
    # clear, whatever the rule thinks. Asserted from the wire, not from the
    # regex — the regex is the thing under test.
    for row in data["parameters"]:
        if _CREDENTIALISH.search(row["key"]):
            assert row["value_is_redacted"], (
                f"{row['key']} names a credential and its value is "
                "published in the clear")


def test_the_configuration_report_is_gated_on_settings_read(client):
    """`settings:read`, not `settings:write`.

    An auditor whose only way to READ what the settings are is to hold the
    right to CHANGE them is an auditor the control has been handed to.
    """
    spec = client.get("/api/v1/openapi.json").json()
    assert CONFIG in spec["paths"], f"{CONFIG} is not published in openapi"
    op = spec["paths"][CONFIG]["get"]
    assert op["x-cadra-scopes"] == ["settings:read"], (
        f"{CONFIG} declares {op['x-cadra-scopes']}")
    assert op["security"], "the report publishes no security requirement"
    names = {p["name"] for p in op.get("parameters", [])}
    assert {"from", "to"} <= names, (
        "the period parameters are not published, so an integrator cannot "
        "discover that they are required")
    assert "403" in op["responses"], (
        "the operation does not publish a 403, which is the only answer a "
        "credential without `settings:read` will ever get from it")


def test_the_redaction_contract_is_documented_in_the_published_schema(client):
    """A consumer must be able to learn that values are redacted WITHOUT
    ever receiving a 200.

    `_redact` replaces a value whose KEY names a credential with a truncated
    sha256 — so `current_value` is sometimes the value and sometimes a
    fingerprint. A consumer that diffs two deployments without knowing that
    will read every redacted row as a difference. If the only place that is
    said is a Python docstring, the only way to learn it is to already have
    the scope.
    """
    schemas = client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    assert "ConfigurationChangeReport" in schemas, (
        "the component schema is not published, so the response has no "
        "documented shape at all")
    description = schemas["ConfigurationChangeReport"].get("description") or ""
    lowered = description.lower()
    assert "redact" in lowered, (
        "the published schema never mentions redaction. A caller reading "
        "`current_value` has no way to know some values are fingerprints.")
    assert "value_is_redacted" in description, (
        "the schema documents redaction but not the per-row flag that says "
        "WHICH rows it happened to")
    for promised in ("period", "summary", "fidelity", "parameters"):
        assert promised in schemas["ConfigurationChangeReport"]["properties"], (
            f"the schema does not declare `{promised}`")


# ─── approve-disposal · the scope that is not held ───────────────────

def test_approve_disposal_answers_according_to_the_scope_held(
        client, token, disposal_awaiting_approval, capture):
    """Refused where the scope is absent; records the CALLER where it is held.

    **Both branches assert.** `approvals:write` gates nothing else
    asset-related, precisely so that granting it is a deliberate act rather
    than something a broad credential already carries — so on a narrow
    credential the refusal is the proof, and on a broad one the recorded
    approver is.

    The in-registry `myservice_api/tests/test_approve_disposal_route.py` is
    the thorough version of the second branch: it provisions its own client,
    holds exactly `assets:read approvals:write`, and reads the approver back
    through the ORM. This is the wire-level companion, and it exists because
    whichever branch a given tenant takes, one of them runs.
    """
    asset_id = disposal_awaiting_approval["id"]
    r = client.post(APPROVE.format(id=asset_id), json={})
    capture("assets/approve_disposal_by_scope", r)

    if not token_grants(token, "approvals:write"):
        body = assert_envelope_err(r, 403, "forbidden")
        details = body["error"]["details"]
        assert details["required_scopes"] == ["approvals:write"], (
            f"the 403 names {details.get('required_scopes')}")
        assert "approvals:write" in body["error"]["message"]
        assert "granted_scopes" in details
        assert "assets:write" in details["granted_scopes"], (
            "this token does not hold `assets:write` either, so the refusal "
            "does not prove that a broad ASSET credential cannot approve")

        after = assert_envelope_ok(
            client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
        assert after["approved_by"] is None
        assert after["approved_at"] is None
        return

    # The credential holds it: the approver must be the CALLER, and the
    # identity is read back from a fresh GET rather than from the response
    # under test.
    approved = assert_envelope_ok(r)["data"]["disposal"]
    assert approved["approved_by"], "a 200 recorded no approver at all"
    assert approved["approved_at"]

    whoami = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    # `data.id` — asserted present rather than fetched with a default. The
    # first version of this line read `data.user.id` with a fallback and got
    # `None`, so the comparison below was skipped and the test passed while
    # checking the one thing it exists to check. A missing key here is a
    # failure, not a reason to stop asserting.
    assert "id" in whoami, (
        f"/auth/whoami no longer publishes `data.id`: {sorted(whoami)}. "
        "This test cannot identify the caller, so it cannot prove the "
        "approver is the caller.")
    assert approved["approved_by"]["id"] == whoami["id"], (
        f"the disposal names user {approved['approved_by']} and the call was "
        f"made by user {whoami['id']}. The approver must come from the "
        "credential, never from anywhere else.")

    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert after["approved_by"] == approved["approved_by"], (
        "the response and a fresh read disagree about who approved it")

    # A second approval is a one-time act refused 409, not a quiet success.
    again = client.post(APPROVE.format(id=asset_id), json={})
    assert_envelope_err(again, 409, "conflict")


def test_a_body_naming_an_approver_is_refused_by_the_route(
        client, token, disposal_awaiting_approval):
    """The 400 branch, reachable only with the scope.

    Refused rather than ignored: dropping the field would answer `200` to a
    caller that believes it appointed somebody, and the approver in the
    register would then disagree with the approver in that caller's own
    logs. Where the credential cannot reach the route at all, the scope gate
    is asserted instead — there is nothing weaker about that, it is simply
    the other door.
    """
    asset_id = disposal_awaiting_approval["id"]
    r = client.post(APPROVE.format(id=asset_id),
                    json={"disposal_approved_by": 2, "approver": "someone"})

    if not token_grants(token, "approvals:write"):
        assert_envelope_err(r, 403, "forbidden")
        return

    body = assert_envelope_err(r, 400, "invalid_request")
    rejected = body["error"]["details"]["rejected_fields"]
    assert "disposal_approved_by" in rejected and "approver" in rejected, (
        f"the 400 does not name the fields it refused: {rejected}")

    # And the refusal wrote nothing — proved by the record still being
    # approvable afterwards.
    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert after["approved_by"] is None, (
        "the refused call recorded an approver anyway")


def test_approve_disposal_publishes_its_whole_contract(client):
    """Scope, conflict, idempotency, and an empty request schema.

    All four are the design rather than decoration:

    * `approvals:write` alone gates it.
    * `409` is a published answer — an approval is a one-time act, and a
      second caller is told who holds it rather than quietly succeeding.
    * `X-Idempotency-Key` is declared, so a replay returns the original
      response rather than a 409 the caller cannot distinguish from a race.
    * The request schema declares NO approver property, because the approver
      is the user behind the bearer token. A schema that named one would
      invite exactly the body the route refuses.
    """
    spec = client.get("/api/v1/openapi.json").json()
    assert APPROVE_SPEC_PATH in spec["paths"], (
        f"{APPROVE_SPEC_PATH} is not published in openapi.json")
    op = spec["paths"][APPROVE_SPEC_PATH]["post"]

    assert op["x-cadra-scopes"] == ["approvals:write"], (
        f"the route declares {op['x-cadra-scopes']}; `approvals:write` is "
        "the scope that must gate it and nothing else asset-related takes")
    assert "409" in op["responses"], (
        "409 is not a published response. A second approval is a conflict "
        "and an integration has to be able to branch on it.")
    names = {p["name"] for p in op.get("parameters", [])}
    assert "X-Idempotency-Key" in names, (
        "the route is declared idempotent but does not publish the header "
        "that makes a replay safe")

    schema = op["requestBody"]["content"]["application/json"]["schema"]
    properties = schema.get("properties") or {}
    offending = [k for k in properties if k in _APPROVER_SPELLINGS]
    assert offending == [], (
        f"the request schema declares {offending}. The approver is taken "
        "from the credential, never from the body; publishing the property "
        "invites the request the route refuses with a 400.")
    assert (schema.get("description") or ""), (
        "the request schema says nothing, so a caller has no published "
        "reason why a body naming an approver is refused")


def test_patch_cannot_name_the_approver_under_any_spelling(
        client, disposal_awaiting_approval):
    """Complementary to `test_audit_reports.py::
    test_a_client_cannot_assert_its_own_disposal_approval`, NOT a duplicate.

    That test already asserts the three READ-ONLY MODEL FIELDS —
    `disposal_approved_by`, `disposal_approved_date`,
    `disposal_date_reconstructed` — are refused on PATCH and write nothing.
    It is the canonical assertion for those three and is deliberately not
    repeated here.

    What handoff 23 adds is `_APPROVER_CLAIM_FIELDS`: twelve SPELLINGS a
    caller might reach for when it thinks it can name the approver, which
    the approve-disposal route refuses outright with a 400. That set is
    wider than the model's field names — `approved_by`, `approver_id`,
    `user_id`, `uid` — and it exists because the route reasoned about what a
    confused integration would actually send.

    So the complementary question is the one that set raises about the OTHER
    door: PATCH must not write an approver under any of those spellings
    either, and must not silently drop them. If one of them were ever added
    to `_WRITABLE_FIELDS` — `user_id` is the plausible one, it is a real
    column on plenty of Odoo models — the approve-disposal route would be
    refusing a body that PATCH accepts one request later.

    Since handoff 31 the two doors give the SAME answer, a 400 naming the
    field, where PATCH used to answer 200 with the spellings listed in
    `data._warnings.rejected_fields`.
    """
    asset_id = disposal_awaiting_approval["id"]
    before = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert before["approved_by"] is None

    # Named one by one by the helper: a spelling missing from the list is
    # one PATCH accepted — or dropped silently — and that is the same control
    # failing at the other door (rules 2 and 3).
    assert_fields_refused(
        client.patch(f"/api/v1/assets/{asset_id}",
                     json={name: 1 for name in _APPROVER_SPELLINGS}),
        *_APPROVER_SPELLINGS)

    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert after["approved_by"] is None, (
        "PATCH wrote an approver. A client can now manufacture the "
        "authorisation the disposal report exists to look for.")
    assert after["approved_at"] is None
    assert after["date_reconstructed"] is False
