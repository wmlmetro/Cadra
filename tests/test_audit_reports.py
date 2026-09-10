"""The two audit reports — specification §13.4, handoff 16 §B.

`GET /api/v1/reports/asset-register?as_of=` and
`GET /api/v1/reports/disposals?from=&to=`.

Three things this suite is built around, and none of them is obvious from
the routes:

**The fixture has to make the data exist first.** There are ZERO disposed
assets on every tenant — 17,795 assets estate-wide, none disposed, none
missing, and `state` has no tracking rows anywhere. A disposal test that
does not create a disposal takes its early-return branch on every assertion
and passes having checked nothing, which is worse than failing. So
`disposed_assets` builds the population it then reports on, exactly as
`test_custody._build_a_chain` does and for the same reason.

**The pages are walked, never asked for in one big number.** `parse_limit`
clamps a service token to EXTERNAL_MAX_PAGE_LIMIT (100), so `limit=5000`
silently returns a page and lets the caller call it the whole report — the
precise class of false answer these endpoints exist to remove. Every "the
whole thing" here is a cursor walk.

**Both reports are read-only and that is asserted, not assumed.** A report
that quietly repairs what it finds can never honestly report zero: the
second run reports a cleanliness it created itself. The suite runs each
report twice and asserts the findings and the write stamps are unchanged.

This suite writes permanent artefacts into whichever tenant it is pointed
at — disposed assets named `pytest-disposal-*`. That is accepted for the
same reason the custody suite's links are: a disposal report tested against
no disposals proves nothing. The names say what they are.
"""
import datetime
import time

import pytest

from .conftest import assert_envelope_ok, assert_envelope_err

SNAPSHOT = "/api/v1/reports/asset-register"
DISPOSALS = "/api/v1/reports/disposals"

# The published disposal-method enum (`nrs.asset.disposal_method`). Asserted
# rather than merely used: enums are published API surface (rule 4), and a
# value that stops being accepted is a breaking change for Vendra.
_METHODS = {"sale", "auction", "transfer", "donation", "trade_in",
            "scrapped", "write_off", "other"}

# The published finding strings. A finding nobody can branch on is a
# sentence, not a finding.
#
# `no_sap_asset_number` was here and was RETIRED in handoff 17 E1 — it fired
# on close to every row, and a finding present on every row is one a reader
# learns to skip. It is deliberately absent from this set rather than merely
# unasserted, so that
# `test_every_finding_and_enum_is_one_we_publish` FAILS if any row starts
# emitting it again. The fact it carried did not go anywhere: it is on each
# row as `sap_asset_number`, and stated once for the period in
# `summary.sap_coverage`.
_FINDINGS = {"no_authorising_reference", "no_approver", "no_approval_date",
             "no_disposal_method", "no_disposal_date", "no_disposal_reason",
             "no_proceeds_recorded", "disposal_date_reconstructed"}

_RETIRED_FINDINGS = {"no_sap_asset_number"}

# The four verdicts `summary.sap_coverage.coverage` can carry. Published API
# surface (rule 4) like every other enum in this file.
_SAP_COVERAGE = {"empty", "none", "partial", "complete"}

# The sentence that is true ONLY when no disposal in the period carried a SAP
# number. Asserted as a forbidden substring everywhere else, because printing
# it over a table where three rows DO carry one is the single way this
# replacement can be worse than the finding it replaced.
_ABSOLUTE_SAP_SENTENCE = "No disposal in this period carried a SAP asset number"

_DATE_SOURCES = {"recorded", "reconstructed", "state_transition", "none"}

# Fields the API must never let a client write. Each of these records an
# AUTHORISATION or a DISCLOSURE, and a client able to assert its own
# approval turns `no_approver` — the finding the whole report exists to
# surface — into a clean row with one PATCH.
_READ_ONLY_DISPOSAL_FIELDS = ("disposal_approved_by",
                              "disposal_approved_date",
                              "disposal_date_reconstructed")


def _today():
    return datetime.date.today()


def _iso(d):
    return d.isoformat()


# ─── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def disposed_assets(client, test_location):
    """Three disposed assets: one bare, one documented, one part-documented.

    Without this every disposal assertion below runs against an empty report
    and passes vacuously. The tenants hold no disposed assets at all, so the
    report's whole subject matter has to be created before it can be read.

    All three share a name prefix so the register snapshot can be filtered
    down to them with `q=` instead of paging 11,942 rows.

    Returns {'prefix': str, 'bare': {...}, 'documented': {...},
             'partial': {...}, 'date': 'YYYY-MM-DD'}.
    """
    prefix = f"pytest-disposal-{int(time.time())}"
    # Yesterday, so a period test can put a boundary either side of it and a
    # "created after the snapshot date" test has a date to sit before.
    disposal_date = _iso(_today() - datetime.timedelta(days=1))

    def _make(suffix, extra):
        body = {
            "name": f"{prefix}-{suffix}",
            "category_id": 1,
            "condition": "poor",
            "state": "disposed",
            "location_id": test_location["id"],
            "disposal_date": disposal_date,
        }
        body.update(extra)
        r = client.post("/api/v1/assets", json=body)
        if r.status_code != 201:
            pytest.skip(
                "could not create a disposed asset on this tenant "
                f"(HTTP {r.status_code}): {r.text[:200]}. Every disposal "
                "assertion below would be vacuous, so this skips loudly "
                "rather than passing having checked nothing.")
        return r.json()["data"]

    return {
        "prefix": prefix,
        "date": disposal_date,
        # The finding itself: disposed, and no paper behind it.
        "bare": _make("bare", {}),
        # Everything a client is allowed to say about a disposal.
        "documented": _make("documented", {
            "disposal_method": "sale",
            "disposal_reference": "BOS/2026/PYTEST-001",
            "disposal_proceeds": 125000.0,
            "disposal_reason": "Sold at board of survey — pytest fixture",
        }),
        # A method that expects proceeds, with none — the narrower finding.
        "partial": _make("partial", {
            "disposal_method": "auction",
            "disposal_reference": "BOS/2026/PYTEST-002",
            "disposal_reason": "Auctioned — pytest fixture",
        }),
    }


# ─── walkers ─────────────────────────────────────────────────────────

def _walk_disposals(client, date_from, date_to, **params):
    """Every row in the period, by walking the cursor.

    Returns (rows, first_body). The first body is kept because `summary`,
    `period` and `pagination.total_estimate` describe the whole period and
    are identical on every page — asserting against page one is asserting
    against the report.
    """
    rows = []
    first = None
    cursor = None
    for _ in range(100):
        q = {"from": date_from, "to": date_to, "limit": 100}
        q.update(params)
        if cursor:
            q["cursor"] = cursor
        r = client.get(DISPOSALS, params=q)
        body = assert_envelope_ok(r)
        if first is None:
            first = body
        rows.extend(body["data"]["rows"])
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    assert not cursor, "the disposal cursor did not run out within 100 pages"
    return rows, first


def _walk_snapshot(client, as_of, **params):
    """Every row of a snapshot, by walking the cursor. Returns (rows, first)."""
    rows = []
    first = None
    cursor = None
    for _ in range(100):
        q = {"as_of": as_of, "limit": 100}
        q.update(params)
        if cursor:
            q["cursor"] = cursor
        r = client.get(SNAPSHOT, params=q)
        body = assert_envelope_ok(r)
        if first is None:
            first = body
        rows.extend(body["data"]["assets"])
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    assert not cursor, "the snapshot cursor did not run out within 100 pages"
    return rows, first


# ─── B1 · the register snapshot ──────────────────────────────────────

def test_the_snapshot_states_which_fields_are_as_of_today(client, capture):
    """The acceptance criterion, and the reason `data` is an object.

    *"A snapshot that silently mixes the two is worse than no snapshot,
    because an auditor will reconcile it against a figure and the
    discrepancy will be ours."* So the declaration is not a warning hanging
    off the envelope where a consumer reading `body["data"]` never sees it —
    the rows live INSIDE it, and it is not possible to receive them without
    it.
    """
    r = client.get(SNAPSHOT, params={"as_of": _iso(_today()), "limit": 5})
    capture("reports/asset_register_snapshot", r)
    body = assert_envelope_ok(r)
    data = body["data"]

    assert isinstance(data, dict), (
        "`data` must be an OBJECT on this route. An array has nowhere "
        "honest to carry the fidelity declaration — which is exactly why "
        "handoff 12 moved the truncation warning to envelope level — and a "
        "boundary a consumer can miss by reading the obvious key is not a "
        "boundary.")
    assert isinstance(data.get("assets"), list)

    fidelity = data["fidelity"]
    for key in ("rolled_back", "as_of_today", "not_recoverable"):
        assert isinstance(fidelity[key], list), f"fidelity.{key} must be a list"
        assert all(isinstance(f, str) for f in fidelity[key])
    assert isinstance(fidelity["notes"], dict)

    # The whole point: the as-of-today list must NAME the fields, not merely
    # exist. An empty list here would be a claim that the entire register
    # rolls back, which is false on every tenant.
    assert fidelity["as_of_today"], (
        "`fidelity.as_of_today` is empty — that asserts the snapshot rolled "
        "back every published field, which no tenant's history supports.")
    assert fidelity["rolled_back"], "`fidelity.rolled_back` is empty"

    # A field cannot be in two classes at once; that would make the
    # declaration unreadable.
    overlap = set(fidelity["rolled_back"]) & set(fidelity["as_of_today"])
    assert not overlap, f"fields declared both rolled back and as-of-today: {overlap}"


def test_the_snapshot_publishes_the_cutoff_instant(client):
    """"As at 31 March" in UTC and in UTC+1 are different questions.

    An auditor reconciling to the hour is entitled to know which one was
    answered, so the exact instant the rollback cut at is published rather
    than left implicit in the date.
    """
    as_of = _iso(_today() - datetime.timedelta(days=30))
    r = client.get(SNAPSHOT, params={"as_of": as_of, "limit": 1})
    body = assert_envelope_ok(r)
    data = body["data"]
    assert data["as_of"] == as_of
    assert data["cutoff"], "no cutoff instant published"
    assert data["cutoff_timezone"] == "UTC"
    # Naive ISO 8601, no offset — the terms Cadra stores every datetime in.
    parsed = datetime.datetime.fromisoformat(data["cutoff"])
    assert parsed.tzinfo is None, (
        "the cutoff carries an offset. Cadra stores naive UTC and the cutoff "
        "is published in the same terms; an offset here would claim a "
        "precision the tracking rows do not have.")

    # `cutoff_timezone` describes the VALUE. WHICH DAY BOUNDARY was taken is
    # a different question and it must be answered too: the snapshot cuts at
    # the end of the requested day in West Africa Time, so a change made at
    # 23:30 UTC on 31 March is 00:30 on 1 April in Lagos and is NOT in the 31
    # March snapshot. An auditor reconciling to the hour cannot work that out
    # from a bare "UTC".
    assert data["fidelity"]["notes"].get("cutoff"), (
        "`fidelity.notes.cutoff` does not say which day boundary the "
        "snapshot cut at. `cutoff_timezone: \"UTC\"` describes the value's "
        "format, not the question that was asked.")


def test_the_snapshot_says_its_filters_were_evaluated_today(client):
    """The second half of the boundary, and the easy one to miss.

    The rows are rolled back; the SELECTION is not. `?as_of=2026-03-31&
    state=active` means "assets active TODAY, reported as they stood on 31
    March", which reconciles to a different number from "assets active on 31
    March". The report says so rather than implying it did the other thing.
    """
    r = client.get(SNAPSHOT, params={"as_of": _iso(_today()),
                                     "state": "active", "limit": 1})
    body = assert_envelope_ok(r)
    filters = body["data"]["filters"]
    assert filters["evaluated_as_of"] == "today"
    assert "state" in filters["query_parameters_supplied"]
    # `as_of`, `limit` and `cursor` are the report's own parameters, not
    # filters, and listing them as filters would misdescribe the query.
    assert "as_of" not in filters["query_parameters_supplied"]
    assert "limit" not in filters["query_parameters_supplied"]
    assert filters["note"]


def test_a_bad_as_of_is_a_400_naming_the_parameter(client, capture):
    """Never a silent unfiltered result, and never a snapshot dated today.

    CLAUDE.md's backlog records five boolean query parameters API-wide that
    silently drop their filter and return the UNFILTERED list. The
    equivalent failure here answers 200 with a figure an auditor would put
    in a file.
    """
    r = client.get(SNAPSHOT, params={"as_of": "the-first-of-never"})
    capture("reports/asset_register_bad_as_of", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "as_of" in body["error"]["message"]
    assert "as_of" in body["error"]["details"]


def test_as_of_is_required(client):
    """No default. A snapshot that quietly means "today" is
    GET /api/v1/assets wearing a report's name, and every fidelity claim in
    it would be vacuous."""
    r = client.get(SNAPSHOT, params={"limit": 1})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "as_of" in body["error"]["message"]


def test_a_future_as_of_is_refused(client):
    """The register has no value at a date that has not happened. Answering
    200 would put a date in an audit file the data cannot support."""
    future = _iso(_today() + datetime.timedelta(days=7))
    r = client.get(SNAPSHOT, params={"as_of": future})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "as_of" in body["error"]["details"]


def test_an_unparseable_filter_is_still_a_400(client):
    """The snapshot inherits `_list_domain`'s validation rather than
    re-implementing it — an enum typo must not answer `200 []`, which is the
    single most reassuring wrong answer this API can give."""
    r = client.get(SNAPSHOT, params={"as_of": _iso(_today()),
                                     "sap_reconciliation_state": "bogus"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"].get("allowed_values")


def test_the_snapshot_excludes_an_asset_created_after_the_date(
        client, disposed_assets):
    """Existence — the first of the auditor's six questions.

    The fixture assets were created during this session. A snapshot dated
    before that must not contain them, and one dated today must.
    """
    prefix = disposed_assets["prefix"]
    yesterday = _iso(_today() - datetime.timedelta(days=1))

    before, _ = _walk_snapshot(client, yesterday, q=prefix)
    assert before == [], (
        "a snapshot dated before these assets were created returned "
        f"{len(before)} of them. Existence is the first thing an auditor "
        "tests and the register cannot report an asset it did not hold.")

    now, _ = _walk_snapshot(client, _iso(_today()), q=prefix)
    ids = {row["id"] for row in now}
    for key in ("bare", "documented", "partial"):
        assert disposed_assets[key]["id"] in ids, (
            f"the {key} fixture asset is missing from today's snapshot")


def test_a_snapshot_row_declares_its_own_degradation(client, disposed_assets):
    """`_fidelity` is per row and present ONLY when non-empty.

    The report-wide declaration says what the SNAPSHOT can answer; this says
    what it could answer for THIS asset. A consumer that ignores it is
    reading today's value as history.
    """
    rows, _ = _walk_snapshot(client, _iso(_today()), q=disposed_assets["prefix"])
    assert rows, "no snapshot rows to inspect"
    for row in rows:
        assert "id" in row
        assert "value" in row, (
            "every row carries the point-in-time `value` block — it is one "
            "of the auditor's six questions")
        fid = row.get("_fidelity")
        if fid is not None:
            assert fid, ("`_fidelity` is present but empty. It is published "
                         "only when non-empty; an empty one reads as a "
                         "degradation that is not there.")
            assert set(fid) <= {"as_of_today", "unknown"}
        changed = row.get("_changed_since")
        if changed is not None:
            assert changed, "`_changed_since` is present but empty"


def test_the_snapshot_total_is_the_true_count(client, disposed_assets):
    """handoff 12's honesty, inherited rather than reimplemented.

    A one-row page of an N-row report must still report N. A report added
    after handoff 12 gets that for free ONLY if it goes through
    `paginate()`, which is what this checks.
    """
    prefix = disposed_assets["prefix"]
    full, _ = _walk_snapshot(client, _iso(_today()), q=prefix)
    assert len(full) >= 2, "fixture did not create enough assets to page"

    r = client.get(SNAPSHOT, params={"as_of": _iso(_today()), "q": prefix,
                                     "limit": 1})
    body = assert_envelope_ok(r)
    assert len(body["data"]["assets"]) == 1
    assert body["pagination"]["total_estimate"] == len(full), (
        "`total_estimate` reported the page rather than the query. That is "
        "the false statement about the register handoff 12 exists to stop.")
    assert body["pagination"]["next_cursor"]


def test_the_snapshot_pages_forwards_without_repeating(client, disposed_assets):
    """Ascending id, one row at a time, no repeats and no holes."""
    prefix = disposed_assets["prefix"]
    full, _ = _walk_snapshot(client, _iso(_today()), q=prefix)
    if len(full) < 2:
        pytest.skip("fewer than two snapshot rows to page")
    seen = []
    cursor = None
    # One more iteration than there are rows, so the loop ends because the
    # cursor ran out and not because the range did.
    for _ in range(len(full) + 1):
        params = {"as_of": _iso(_today()), "q": prefix, "limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(SNAPSHOT, params=params))
        seen.extend(row["id"] for row in body["data"]["assets"])
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    assert not cursor, "the cursor did not run out within the report's length"
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    assert seen == [row["id"] for row in full]


def test_the_snapshot_never_drops_a_row_silently(client, disposed_assets):
    """`omitted_asset_ids` is ALWAYS present and normally empty.

    A row quietly missing from a page reads to an auditor as an asset that
    did not exist on the date — the one failure mode a snapshot cannot
    recover from, because there is no sign it happened.
    """
    _, first = _walk_snapshot(client, _iso(_today()),
                              q=disposed_assets["prefix"])
    assert "omitted_asset_ids" in first["data"], (
        "the key is absent. A key that appears only when something went "
        "wrong is a key nobody checks.")
    assert first["data"]["omitted_asset_ids"] == []


# ─── B2 · the disposal report ────────────────────────────────────────

def test_a_disposal_with_no_reference_is_present_with_its_finding(
        client, disposed_assets, capture):
    """The acceptance criterion: *"a disposal with no authorising reference
    appears in the report as a finding, not filtered out."*

    A report that showed only the well-documented disposals would be a
    report of the paperwork rather than of the estate.
    """
    date = disposed_assets["date"]
    rows, first = _walk_disposals(client, date, date)
    capture("reports/disposals", first_response_of(client, date))

    by_id = {row["asset_id"]: row for row in rows}
    bare_id = disposed_assets["bare"]["id"]
    assert bare_id in by_id, (
        "the undocumented disposal is ABSENT from the report. That is the "
        "defect this endpoint exists to remove: a disposal with no "
        "authorising reference is itself the finding.")
    bare = by_id[bare_id]
    assert "no_authorising_reference" in bare["findings"]
    assert "no_approver" in bare["findings"]
    assert "no_disposal_method" in bare["findings"]
    assert bare["disposal_reference"] is None

    documented_id = disposed_assets["documented"]["id"]
    assert documented_id in by_id
    documented = by_id[documented_id]
    assert documented["disposal_reference"] == "BOS/2026/PYTEST-001"
    assert "no_authorising_reference" not in documented["findings"]
    assert documented["disposal_method"] == "sale"
    # `sale` maps onto SAP's `disposal`, not `retirement` — something
    # changed hands (INT-06/07/09 §4.2).
    assert documented["sap_disposal_type"] == "disposal"

    # `no_proceeds_recorded` fires only where the route means money should
    # have come in. The auctioned one has none; the sold one does.
    partial = by_id[disposed_assets["partial"]["id"]]
    assert "no_proceeds_recorded" in partial["findings"]
    assert "no_proceeds_recorded" not in documented["findings"]


def first_response_of(client, date):
    """One un-walked response, for the capture. Kept separate so the capture
    records what a caller actually receives rather than a synthesised page."""
    return client.get(DISPOSALS, params={"from": date, "to": date, "limit": 5})


def test_every_finding_and_enum_is_one_we_publish(client, disposed_assets):
    """Enums are published API surface (rule 4). A finding string or a
    method value outside the documented set is a value no integration can
    branch on and a breaking change waiting to happen."""
    date = disposed_assets["date"]
    rows, first = _walk_disposals(client, date, date)
    for row in rows + first["data"]["unplaceable"]:
        assert set(row["findings"]) <= _FINDINGS, (
            f"undocumented finding(s): {set(row['findings']) - _FINDINGS}")
        assert row["date_source"] in _DATE_SOURCES
        if row["disposal_method"] is not None:
            assert row["disposal_method"] in _METHODS
        assert row["sap_disposal_type"] in ("disposal", "retirement")


def test_the_summary_counts_match_the_rows(client, disposed_assets, capture):
    """*"N of M carry no authorising reference"* must be readable from page
    one, without walking.

    So the summary describes the WHOLE PERIOD on every page while `rows`
    pages — and it is recomputed here from the walked rows to prove the two
    agree. A summary taken over the page would shrink as the reader paged,
    which is a number that changes meaning depending on where you are.
    """
    date = disposed_assets["date"]
    rows, first = _walk_disposals(client, date, date)
    capture("reports/disposals_summary", first_response_of(client, date))

    if first.get("_warnings", {}).get("truncated"):
        pytest.skip(
            "this credential's record cap bit on the disposal schedule, so "
            "the walked rows are a window and cannot be compared with a "
            "summary that describes the period. The cap is honest — "
            "`_warnings.truncated` said so — but the comparison is not "
            "available.")

    summary = first["data"]["summary"]
    assert summary["total"] == len(rows), (
        "`summary.total` and the walked schedule disagree. They come out of "
        "one call to the model precisely so they cannot.")
    assert first["pagination"]["total_estimate"] == summary["total"], (
        "there must be exactly ONE count of the period in this response")

    expected = {}
    for row in rows:
        for finding in row["findings"]:
            expected[finding] = expected.get(finding, 0) + 1
    assert summary["findings"] == expected

    assert summary["clean"] == sum(1 for row in rows if not row["findings"])

    # The single number the handoff asked for by name.
    assert summary["findings"].get("no_authorising_reference", 0) >= 1, (
        "the fixture created an undocumented disposal in this period and the "
        "summary counted none")

    # Every page carries the identical summary — otherwise "read page one"
    # is not advice anybody can follow.
    later = assert_envelope_ok(
        client.get(DISPOSALS, params={"from": date, "to": date, "limit": 1}))
    assert later["data"]["summary"] == summary


def test_the_sap_position_is_a_statement_and_not_a_per_row_finding(
        client, disposed_assets):
    """Handoff 17 E1, stated as the acceptance criterion it is.

    `no_sap_asset_number` fired on essentially every row of this report on
    every tenant, and a control that fires on 100% of rows is one a reader
    learns to skip — taking `no_approver` and `no_authorising_reference`,
    sitting in the same column, down with it. It is now said ONCE for the
    period, where it reads as a fact about INT-09 rather than as a defect
    repeated on each row.

    Removing it would have hidden something true, so the FACT is asserted in
    both places it survives: `sap_asset_number` on the row, and the counts in
    `summary.sap_coverage`.
    """
    date = disposed_assets["date"]
    rows, first = _walk_disposals(client, date, date)
    summary = first["data"]["summary"]

    for row in rows + first["data"]["unplaceable"]:
        assert not (set(row["findings"]) & _RETIRED_FINDINGS), (
            f"row {row['asset_id']} carries a retired finding: "
            f"{set(row['findings']) & _RETIRED_FINDINGS}. It moved to "
            "`summary.sap_coverage` and must appear once, not per row.")
        # The fact itself is still published per row. Only the label went.
        assert "sap_asset_number" in row

    assert "no_sap_asset_number" not in summary["findings"], (
        "the findings TALLY still counts it, so it is still being emitted "
        "somewhere")

    coverage = summary["sap_coverage"]
    assert coverage["coverage"] in _SAP_COVERAGE
    assert coverage["total"] == summary["total"], (
        "`sap_coverage` is counted over a different population from "
        "`summary.total` — two numbers in one response that cannot both be "
        "about the same period")
    assert (coverage["with_sap_asset_number"]
            + coverage["without_sap_asset_number"]) == coverage["total"]

    # The fixture creates its disposals through the API, and
    # `sap_asset_number` is not writable there — deliberately, and asserted
    # elsewhere in this file. So the bare/documented/partial trio contribute
    # three rows with no SAP number, and the period cannot be `empty` or
    # `complete`.
    assert coverage["coverage"] in ("none", "partial")
    assert coverage["without_sap_asset_number"] >= 3, (
        "the fixture put three disposals with no SAP number in this period "
        "and the coverage block counted fewer than three")


def test_the_sap_statement_is_never_the_absolute_one_when_it_is_untrue(
        client, disposed_assets):
    """The one way this replacement can be worse than the finding it
    replaced.

    *"No disposal in this period carried a SAP asset number"* is the sentence
    the ruling asked for and it is true only when the count is ALL of them.
    Printed over a table where three rows DO carry one it is a false
    statement in an audit report — which is worse than a noisy findings
    column. The verdict is therefore not left to the renderer: `coverage`
    decides, once, in the model.

    Asserted in BOTH directions, because an implementation that never emits
    the absolute sentence at all would pass a one-directional test while
    failing the ruling.
    """
    date = disposed_assets["date"]
    rows, first = _walk_disposals(client, date, date)
    if first.get("_warnings", {}).get("truncated"):
        pytest.skip(
            "this credential's record cap bit on the disposal schedule, so "
            "the walked rows are a window and cannot be compared with a "
            "coverage block that describes the period.")
    coverage = first["data"]["summary"]["sap_coverage"]

    with_number = sum(1 for row in rows if row["sap_asset_number"])
    assert coverage["with_sap_asset_number"] == with_number, (
        "the coverage count and the rows disagree about how many disposals "
        "reached SAP")

    if with_number:
        assert coverage["coverage"] == "partial"
        assert _ABSOLUTE_SAP_SENTENCE not in coverage["statement"], (
            f"{with_number} disposal(s) in this period carry a SAP asset "
            "number and the report states that none does. A period-scoped "
            "absolute is a false statement in an audit report.")
        assert str(with_number) in coverage["statement"]
    else:
        assert coverage["coverage"] == "none"
        assert _ABSOLUTE_SAP_SENTENCE in coverage["statement"], (
            "no disposal in this period reached SAP and the report does not "
            "say so. The fact was moved out of the findings column, not "
            "deleted.")

    # `statement` is prose for a human; `coverage` is the thing to branch on.
    # A caller told to branch on the enum needs the enum to be there.
    assert isinstance(coverage["statement"], str) and coverage["statement"]

    # And it is identical on every page, like the rest of the summary — the
    # statement sits ABOVE the table, so a reader on page two must not see a
    # different one.
    later = assert_envelope_ok(
        client.get(DISPOSALS, params={"from": date, "to": date, "limit": 1}))
    assert later["data"]["summary"]["sap_coverage"] == coverage


def test_the_period_bounds_are_both_inclusive(client, disposed_assets):
    """An auditor asks for a quarter by naming its first and last day. An
    exclusive upper bound silently loses everything disposed of on 31
    March."""
    date = disposed_assets["date"]
    bare_id = disposed_assets["bare"]["id"]

    # A single-day period whose only day IS the disposal date.
    rows, _ = _walk_disposals(client, date, date)
    assert bare_id in {row["asset_id"] for row in rows}, (
        "a one-day period containing the disposal date did not contain the "
        "disposal — one of the two bounds is exclusive")

    # A period that ends the day before must not contain it.
    day_before = _iso(datetime.date.fromisoformat(date)
                      - datetime.timedelta(days=1))
    outside, _ = _walk_disposals(client, day_before, day_before)
    assert bare_id not in {row["asset_id"] for row in outside}


def test_a_bad_date_is_a_400_naming_the_parameter(client, capture):
    """Both parameters, separately, and never a silent whole-history
    report."""
    good = _iso(_today())
    r = client.get(DISPOSALS, params={"from": "yesterdayish", "to": good})
    capture("reports/disposals_bad_from", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "from" in body["error"]["message"]
    assert "from" in body["error"]["details"]

    r = client.get(DISPOSALS, params={"from": good, "to": "2026-13-45"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "to" in body["error"]["message"]


def test_both_period_bounds_are_required(client):
    """A period report with no period is a report of all history under a
    heading that claims a quarter."""
    good = _iso(_today())
    assert_envelope_err(client.get(DISPOSALS, params={"to": good}),
                        400, "invalid_request")
    assert_envelope_err(client.get(DISPOSALS, params={"from": good}),
                        400, "invalid_request")
    assert_envelope_err(client.get(DISPOSALS), 400, "invalid_request")


def test_a_period_that_ends_before_it_starts_is_a_400(client):
    """`invalid_request`, not `validation_failed`. An integration branching
    on `error.code` should be told its REQUEST was wrong, not that a record
    failed validation."""
    body = assert_envelope_err(
        client.get(DISPOSALS, params={"from": _iso(_today()),
                                      "to": _iso(_today()
                                                 - datetime.timedelta(days=5))}),
        400, "invalid_request")
    assert "from" in body["error"]["details"]
    assert "to" in body["error"]["details"]


def test_unplaceable_disposals_are_returned_in_full(client, disposed_assets):
    """A disposal with no date and no tracked state change belongs to no
    period. Dropping it makes it invisible in every report ever run;
    folding it into the period double-counts it next quarter. So it gets its
    own key, its own count, and appears on every page."""
    date = disposed_assets["date"]
    _, first = _walk_disposals(client, date, date)
    data = first["data"]
    assert isinstance(data["unplaceable"], list)
    assert data["summary"]["unplaceable"] == len(data["unplaceable"])
    # None of them may also be in the period rows — that would double-count.
    period_ids = {row["asset_id"] for row in data["rows"]}
    for row in data["unplaceable"]:
        assert row["asset_id"] not in period_ids
        assert row["disposal_date"] is None
        assert row["date_source"] == "none"


def test_the_disposal_report_pages_forwards(client, disposed_assets):
    """Ascending asset id, no repeats, no holes — and the cursor runs out."""
    date = disposed_assets["date"]
    full, _ = _walk_disposals(client, date, date)
    if len(full) < 2:
        pytest.skip("fewer than two disposals in the fixture period")
    seen = []
    cursor = None
    for _ in range(len(full) + 1):
        params = {"from": date, "to": date, "limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(DISPOSALS, params=params))
        seen.extend(row["asset_id"] for row in body["data"]["rows"])
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    assert not cursor, "the cursor did not run out within the report's length"
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    assert seen == [row["asset_id"] for row in full]


# ─── read-only ───────────────────────────────────────────────────────

def test_neither_report_repairs_what_it_finds(client, disposed_assets):
    """*"A report that quietly fixes what it finds can never honestly report
    zero"* — the second run reports a cleanliness it created itself.

    Asserted from the API alone: the findings on a known-bad disposal must
    be byte-identical across two runs, and the asset's `updated_at` must not
    move. A repair would show up as either.
    """
    date = disposed_assets["date"]
    bare_id = disposed_assets["bare"]["id"]

    before = assert_envelope_ok(
        client.get(f"/api/v1/assets/{bare_id}"))["data"]

    first_rows, _ = _walk_disposals(client, date, date)
    snap_before, _ = _walk_snapshot(client, _iso(_today()),
                                    q=disposed_assets["prefix"])
    second_rows, _ = _walk_disposals(client, date, date)

    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{bare_id}"))["data"]

    assert after["updated_at"] == before["updated_at"], (
        "running the reports moved the asset's write stamp. Both reports "
        "are read-only; a stamped field means something on the read path "
        "wrote.")
    assert after["disposal"] == before["disposal"]

    first_bare = next(r for r in first_rows if r["asset_id"] == bare_id)
    second_bare = next(r for r in second_rows if r["asset_id"] == bare_id)
    assert first_bare == second_bare, (
        "the same disposal reported differently on two consecutive runs — "
        "the report changed what it was reporting on")
    assert "no_authorising_reference" in second_bare["findings"]
    assert snap_before, "the snapshot returned nothing to compare"


# ─── rule 2 · the allow-list is the gate ─────────────────────────────

def test_the_writable_disposal_fields_round_trip(client, test_location):
    """`disposal_method`, `disposal_reference` and `disposal_proceeds` are in
    `_WRITABLE_FIELDS`, so they must be settable and readable back under
    `data.disposal`. A field on the allow-list that does not round-trip is
    an allow-list entry that does nothing."""
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-disposal-writable-{int(time.time())}",
        "category_id": 1,
        "state": "disposed",
        "location_id": test_location["id"],
        "disposal_date": _iso(_today()),
        "disposal_method": "scrapped",
        "disposal_reference": "BOS/2026/PYTEST-WRITE",
        "disposal_proceeds": 0.0,
        "disposal_reason": "pytest — writable round trip",
    })
    if r.status_code != 201:
        pytest.skip(f"could not create the asset: HTTP {r.status_code} "
                    f"{r.text[:200]}")
    data = r.json()["data"]
    rejected = data.get("_warnings", {}).get("rejected_fields") or []
    for field in ("disposal_method", "disposal_reference", "disposal_reason"):
        assert field not in rejected, (
            f"`{field}` is on the writable allow-list but the create "
            f"rejected it")
    disposal = data["disposal"]
    assert disposal["method"] == "scrapped"
    assert disposal["reference"] == "BOS/2026/PYTEST-WRITE"
    assert disposal["reason"] == "pytest — writable round trip"
    # Nothing wrote an approver. `action_approve_disposal` is the only thing
    # that may, and it was not called.
    assert disposal["approved_by"] is None
    assert disposal["approved_at"] is None
    assert disposal["date_reconstructed"] is False

    # And PATCH corrects a mis-keyed reference — the reason these are
    # writable at all.
    patched = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{data['id']}",
        json={"disposal_reference": "BOS/2026/PYTEST-WRITE-CORRECTED"}))
    assert patched["data"]["disposal"]["reference"] == \
        "BOS/2026/PYTEST-WRITE-CORRECTED"


def test_a_client_cannot_assert_its_own_disposal_approval(
        client, disposed_assets):
    """The highest-value omission from `_WRITABLE_FIELDS` in this change.

    `no_approver` is one of the disposal report's findings. A client able to
    PATCH `disposal_approved_by` could create a disposal and name its own
    approver in the same request, turning that finding into a clean row
    without anybody having authorised anything — the same shape as the
    `asset_tag` and `sap_asset_number` omissions this file already
    documents.

    And it must not degrade SILENTLY: the rejection is reported in
    `data._warnings.rejected_fields` (rule 3).
    """
    asset_id = disposed_assets["bare"]["id"]
    before = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert before["approved_by"] is None

    r = client.patch(f"/api/v1/assets/{asset_id}", json={
        "disposal_approved_by": 1,
        "disposal_approved_date": "2020-01-01 00:00:00",
        "disposal_date_reconstructed": False,
    })
    body = assert_envelope_ok(r)
    rejected = set(body["data"].get("_warnings", {})
                   .get("rejected_fields") or [])
    for field in _READ_ONLY_DISPOSAL_FIELDS:
        assert field in rejected, (
            f"`{field}` was accepted or dropped without a warning. It "
            "records an authorisation or a disclosure; a client able to "
            "write it can manufacture the evidence the audit report exists "
            "to look for — and a field dropped without a warning is a "
            "defect even at 200 (rule 3).")

    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]["disposal"]
    assert after["approved_by"] is None
    assert after["approved_at"] is None
    assert after["date_reconstructed"] is False


# ─── the gate ────────────────────────────────────────────────────────

def test_both_reports_refuse_a_caller_with_no_token(client, unauthed_client):
    """Every list endpoint in this API runs `sudo()`, so the scope is the
    ONLY gate between a caller and the register. Both reports are views of
    the register and neither may answer without one."""
    for path, params in ((SNAPSHOT, {"as_of": _iso(_today())}),
                         (DISPOSALS, {"from": _iso(_today()),
                                      "to": _iso(_today())})):
        r = unauthed_client.get(path, params=params)
        assert_envelope_err(r, 401, "unauthorized")


def test_both_reports_are_gated_on_assets_read(client):
    """The scope each report declares, asserted from the published contract.

    `assets:read`, NOT the `dashboards:read` that `/reports/depreciation`
    takes: that route returns aggregates, these return ROWS OF THE
    REGISTER. Gating them on `dashboards:read` would give a credential that
    cannot call `GET /api/v1/assets` a second, weaker door onto the same
    data.

    Asserted against `/openapi.json` rather than by minting a scoped-down
    token, because this suite holds ONE credential and cannot narrow it —
    `POST /auth/token` returns the client record's own scopes. What can be
    checked from the API alone is that the published contract names the
    right scope, and it is checked here rather than left to a code review.
    """
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200, f"openapi.json unavailable: {r.status_code}"
    paths = r.json()["paths"]
    for path in (SNAPSHOT, DISPOSALS):
        assert path in paths, f"{path} is not published in openapi.json"
        op = paths[path]["get"]
        assert op["x-cadra-scopes"] == ["assets:read"], (
            f"{path} declares {op['x-cadra-scopes']}; these reports return "
            "rows of the register and take the register's scope")
        assert op["security"], f"{path} publishes no security requirement"
        # Every documented parameter is a parameter, not prose.
        names = {p["name"] for p in op.get("parameters", [])}
        assert "limit" in names and "cursor" in names, (
            f"{path} does not publish its pagination parameters")


def test_the_snapshot_publishes_its_own_contract(client):
    """`response_schema` and the component schemas exist. An endpoint an
    integration cannot read the shape of is an endpoint it will guess at."""
    spec = client.get("/api/v1/openapi.json").json()
    schemas = spec["components"]["schemas"]
    for name in ("AssetRegisterSnapshot", "AssetSnapshotRow",
                 "AssetSnapshotFidelity", "DisposalReport",
                 "DisposalReportRow", "AssetDisposal"):
        assert name in schemas, f"component schema {name} is not published"
    # The disposal block on the asset itself, so a consumer reading one
    # asset gets the same disclosure as one reading the schedule.
    assert "disposal" in schemas["Asset"]["properties"]
    fid = schemas["AssetRegisterSnapshot"]["properties"]["fidelity"]
    assert fid["$ref"].endswith("AssetSnapshotFidelity")
