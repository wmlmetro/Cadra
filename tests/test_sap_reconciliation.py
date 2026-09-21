"""The SAP legs of the register — INT-06/07 and the dual-code control.

The September Integration Flow names one completeness control:

    "An asset is complete only when both the Cadra Asset Code and the SAP
     asset code are linked on the register."

Half of it landed in handoff 02, when `asset_code` became unique and NOT
NULL. This file pins the other half: the `data.sap` block that publishes what
finance knows, the filters an auditor uses to ask which assets are
incomplete, and the fact that none of it is writable by the caller.

Two of the assertions here are the same bug wearing different hats. A filter
that answers `200 []` on a typo tells an auditor there are no findings; a
filter that silently drops itself and answers with the whole register tells
them everything is fine. Both are the silent degradation rule 3 forbids, and
the second is the more dangerous one — an empty list reads as "no matches",
but a full list reads as an ANSWER.
"""
import time
import uuid

from .conftest import (assert_envelope_ok, assert_envelope_err,
                       assert_fields_refused, ids_matching)


# The keys `_serialize_sap` publishes. Named here rather than derived from
# the response so that a key quietly disappearing is a failure, not a
# tautology.
SAP_KEYS = (
    "asset_number", "asset_subnumber", "company_code", "asset_class",
    "capitalisation_date", "capitalised_amount", "net_book_value",
    "accumulated_depreciation", "code_source", "posting_state",
    "reconciliation_state", "synced_at",
)

RECONCILIATION_STATES = ["not_tagged", "pending", "reconciled", "exception"]


def _uniq():
    """Unique across concurrent runs, not just within one."""
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _new_asset(client, name=None, **extra):
    name = name or f"pytest-sap-{_uniq()}"
    r = client.post("/api/v1/assets",
                    json={"name": name, "category_id": 1, **extra})
    return assert_envelope_ok(r, expected_status=201)["data"]


# ─── the block is published at all ───────────────────────────────────


def test_sap_block_present_on_every_asset(client, test_asset, capture):
    """Unconditional, so an integration can always branch on it.

    Same contract as `provenance` and `tagging`: the block is there whether
    or not SAP has ever answered for the asset. A consumer that has to check
    for the key's existence before reading it will eventually get it wrong.
    """
    r = client.get(f"/api/v1/assets/{test_asset['id']}")
    capture("sap/get_asset_sap_block", r)
    body = assert_envelope_ok(r)
    assert "sap" in body["data"], "`data.sap` missing from the asset envelope"
    sap = body["data"]["sap"]
    for field in SAP_KEYS:
        assert field in sap, f"`{field}` missing from the sap block"
    assert len(sap) == len(SAP_KEYS), (
        f"the sap block published keys the contract does not name: "
        f"{sorted(set(sap) - set(SAP_KEYS))}"
    )


def test_a_new_asset_is_not_tagged_and_not_posted(client):
    """The honest opening state, and the one that is NOT a finding.

    INT-06 fires on tagging confirmed, so an asset nobody has tagged has no
    SAP code because it is not yet due one. Colouring that as an exception
    would bury the real findings in eleven thousand false ones, and an
    exception report nobody can read is the same as no exception report.
    """
    sap = _new_asset(client)["sap"]

    assert sap["asset_number"] is None
    assert sap["code_source"] is None
    assert sap["synced_at"] is None
    assert sap["posting_state"] == "none"
    assert sap["reconciliation_state"] == "not_tagged", (
        f"a freshly created, untagged asset must read as `not_tagged`, got "
        f"{sap['reconciliation_state']!r}"
    )


# ─── the dual-code filter is an enum, not free text ──────────────────


def test_reconciliation_state_rejects_a_value_outside_the_enum(client, capture):
    """`?sap_reconciliation_state=bogus` must 400, not answer `200 []`.

    This filter's entire audience is an auditor asking to be shown the
    incomplete assets. `exceptions` — the plural, the natural typo —
    answering with an empty list tells them there are none, which is the
    single most reassuring wrong answer this API can give.
    """
    r = client.get("/api/v1/assets",
                   params={"sap_reconciliation_state": "bogus", "limit": 5})
    capture("sap/reconciliation_state_bogus", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["allowed_values"] == RECONCILIATION_STATES, (
        "the error must name the values the caller may use — the allowed set "
        f"came back as {body['error']['details'].get('allowed_values')!r}"
    )


def test_the_plural_typo_is_rejected_rather_than_answered_empty(client):
    """The specific typo, spelled out because it is the realistic one."""
    r = client.get("/api/v1/assets",
                   params={"sap_reconciliation_state": "exceptions"})
    assert r.status_code == 400, (
        f"?sap_reconciliation_state=exceptions returned {r.status_code}; an "
        "empty 200 reads as 'there are no findings'"
    )
    assert r.json()["error"]["code"] == "invalid_request"


def test_the_literal_string_null_is_rejected_on_the_enum(client, capture):
    """`"null"` is not a "no filter" sentinel where the filter is an enum.

    A JS caller stringifying an unset value sends the literal "null". Reading
    it as "no filter" hands back every asset in the register while the caller
    believes they are looking at one reconciliation state — a standing ruling
    in this repo, first made for `tag_label_state`.
    """
    r = client.get("/api/v1/assets",
                   params={"sap_reconciliation_state": "null"})
    capture("sap/reconciliation_state_null", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["allowed_values"] == RECONCILIATION_STATES


def test_an_empty_reconciliation_state_is_no_filter_at_all(client):
    """`?sap_reconciliation_state=` is a form that submitted its empty default.

    "No filter" has to mean the same rows as omitting the parameter, not zero
    rows — otherwise every UI that serialises unset filters gets a 400 or an
    empty screen.
    """
    def ids(**params):
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"limit": 5, **params}))
        return [a["id"] for a in body["data"]]

    unfiltered = ids()
    assert unfiltered, (
        "the register is empty, so this test cannot tell a working filter "
        "from one that drops everything"
    )
    assert ids(sap_reconciliation_state="") == unfiltered


def test_every_state_in_the_enum_is_accepted_and_actually_filters(client):
    """The validation must not have closed the filter it is guarding.

    And each value has to narrow: asserting only the 200 would pass on a
    filter that was never applied to the domain at all.
    """
    for state in RECONCILIATION_STATES:
        body = assert_envelope_ok(client.get(
            "/api/v1/assets",
            params={"sap_reconciliation_state": state, "limit": 50}))
        mismatched = [a["id"] for a in body["data"]
                      if a["sap"]["reconciliation_state"] != state]
        assert not mismatched, (
            f"?sap_reconciliation_state={state} returned assets in a "
            f"different state: {mismatched}"
        )


def test_the_exception_filter_returns_only_findings(client, capture):
    """The auditor's query. Empty is a legitimate answer; wrong rows are not.

    `exception` is the one value in the enum that is a finding — the asset is
    tagged, so it demonstrably exists, and finance has not booked it. A row
    in this result that is not in that state is a false positive in an audit
    report, which is worse than a missing one because somebody will chase it.
    """
    r = client.get("/api/v1/assets",
                   params={"sap_reconciliation_state": "exception",
                           "limit": 50})
    capture("sap/reconciliation_state_exception", r)
    body = assert_envelope_ok(r)
    for asset in body["data"]:
        assert asset["sap"]["reconciliation_state"] == "exception", (
            f"asset {asset['id']} came back from the exception filter in "
            f"state {asset['sap']['reconciliation_state']!r}"
        )


# ─── has_sap_code: the boolean that must never drop itself ───────────


def test_has_sap_code_rejects_a_value_it_cannot_interpret(client, capture):
    """`?has_sap_code=1` must 400, not return the unfiltered register.

    This is the dangerous half of the query-validation backlog. An empty list
    reads as "no matches"; a full list reads as an answer, and a caller
    cannot tell it from one. `?has_sap_code=false` is literally the question
    "which assets has finance not booked" — answering it with every asset in
    the register, or with every asset that IS booked, is not a degraded
    answer, it is a wrong one.
    """
    r = client.get("/api/v1/assets", params={"has_sap_code": "1", "limit": 5})
    capture("sap/has_sap_code_bogus", r)
    assert_envelope_err(r, 400, "invalid_request")

    for bogus in ("yes", "null", "0", "TRUE!"):
        r = client.get("/api/v1/assets",
                       params={"has_sap_code": bogus, "limit": 5})
        assert r.status_code == 400, (
            f"has_sap_code={bogus!r} returned {r.status_code}, not 400"
        )
        assert r.json()["error"]["code"] == "invalid_request"


def test_has_sap_code_true_and_false_are_complements(client):
    """Both values work, they partition, and neither is the whole register.

    Scoped to assets this test made, because the two halves are asserted as
    an exact partition and the register is shared with every other run.
    """
    marker = f"pytest-sapcode-{_uniq()}"
    made = {_new_asset(client, name=f"{marker}-{n}")["id"] for n in (1, 2)}

    def ids(**params):
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"q": marker, "limit": 100, **params}))
        return {a["id"] for a in body["data"]}

    unfiltered = ids()
    assert unfiltered == made, f"the marker scope is not ours: {unfiltered}"

    with_code = ids(has_sap_code="true")
    without_code = ids(has_sap_code="false")

    assert not (with_code & without_code), (
        f"an asset came back from both halves of the filter: "
        f"{with_code & without_code}"
    )
    assert with_code | without_code == unfiltered, (
        "true and false together must account for every asset in scope; got "
        f"{with_code | without_code} against {unfiltered}"
    )
    # `sap_asset_number` is not writable over the API, so nothing this suite
    # can create carries one — the assets it just made must all be in the
    # `false` half, and the `true` half must be empty of them.
    assert without_code == made, (
        "assets created through the API carry no SAP asset number, so they "
        f"must all read as has_sap_code=false; got {without_code}"
    )
    assert not with_code


def test_has_sap_code_agrees_with_the_serialised_block(client):
    """The filter and the serialiser must answer the same question.

    A filter matching on one column while the block reports another is how a
    reconciliation report and the record it cites come to disagree.
    """
    for value, expect_number in (("true", True), ("false", False)):
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"has_sap_code": value, "limit": 25}))
        wrong = [a["id"] for a in body["data"]
                 if bool(a["sap"]["asset_number"]) is not expect_number]
        assert not wrong, (
            f"?has_sap_code={value} returned assets whose "
            f"`sap.asset_number` disagrees: {wrong}"
        )


def test_an_empty_has_sap_code_is_no_filter_at_all(client):
    """`?has_sap_code=` must behave as if the parameter were omitted."""
    def ids(**params):
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"limit": 5, **params}))
        return [a["id"] for a in body["data"]]

    unfiltered = ids()
    assert unfiltered, "the register is empty; this test proves nothing"
    assert ids(has_sap_code="") == unfiltered


# ─── the exact-match lookup ──────────────────────────────────────────


def test_sap_asset_number_that_matches_nothing_is_an_empty_200(client, capture):
    """An exact-match filter that matches nothing is legitimately empty.

    The distinction from the enum cases above: there is no typo to detect.
    Any string is a syntactically valid SAP asset number, so "no asset is
    booked under this number" is a real answer and the only one available.
    """
    r = client.get("/api/v1/assets",
                   params={"sap_asset_number": f"NO-SUCH-SAP-{_uniq()}",
                           "limit": 5})
    capture("sap/asset_number_no_match", r)
    body = assert_envelope_ok(r)
    assert body["data"] == [], (
        "an unmatched SAP asset number returned rows — the filter is not "
        f"being applied: {[a['id'] for a in body['data']]}"
    )


def test_sap_asset_number_is_exact_not_a_substring_search(client):
    """A reconciliation that over-matches is not a reconciliation.

    Asserted against whatever the register holds: every row returned for a
    number must carry exactly that number, never one containing it.
    """
    body = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"has_sap_code": "true", "limit": 5}))
    rows = body["data"]
    if not rows:
        import pytest
        pytest.skip("no asset on this tenant carries a SAP asset number yet")
    number = rows[0]["sap"]["asset_number"]
    body = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"sap_asset_number": number, "limit": 25}))
    wrong = [a["id"] for a in body["data"]
             if a["sap"]["asset_number"] != number]
    assert not wrong, f"?sap_asset_number={number!r} over-matched: {wrong}"


# ─── none of it is writable ──────────────────────────────────────────


def test_sap_fields_are_not_writable_on_create(client, capture):
    """A client that can set `sap_asset_number` can fake a reconciliation.

    The dual-code control is an audit control: `reconciled` is supposed to
    mean finance booked the asset. A caller able to POST the number would
    reach that state without SAP having booked anything, and a caller able to
    POST the state would reach it without even the pretence of a code. Both
    are REFUSED — rule 3, and since handoff 31 with a 400 rather than a 201
    and a warning: until then the asset was created WITHOUT the number, which
    is what Vendra dead-lettered after the fact, under an idempotency key
    that replayed the same incomplete 201 on every retry.

    So this asserts two records: the refused body created NONE, and the same
    asset sent without the four fields is created with an empty SAP block.
    """
    name = f"pytest-sapwrite-{_uniq()}"
    r = client.post("/api/v1/assets", json={
        "name": name,
        "category_id": 1,
        "sap_asset_number": "100000001234",
        "sap_reconciliation_state": "reconciled",
        "sap_code_source": "integration",
        "sap_synced_at": "2026-09-06T10:00:00",
    })
    capture("sap/create_rejects_sap_fields", r)
    assert_fields_refused(r, "sap_asset_number", "sap_reconciliation_state",
                          "sap_code_source", "sap_synced_at")
    assert ids_matching(client, "/api/v1/assets", name) == [], (
        "the SAP fields were refused with a 400 and the asset was created "
        "anyway")

    data = _new_asset(client, name=name)
    assert ids_matching(client, "/api/v1/assets", name) == [data["id"]]
    assert data["sap"]["asset_number"] is None, (
        "the client's SAP asset number reached the record"
    )
    assert data["sap"]["code_source"] is None
    assert data["sap"]["synced_at"] is None
    assert data["sap"]["reconciliation_state"] == "not_tagged", (
        "the client set the dual-code state to "
        f"{data['sap']['reconciliation_state']!r} without SAP having booked "
        "anything"
    )


def test_sap_fields_are_not_writable_on_patch(client):
    """Same control on the update path, which is the easier one to forget."""
    asset = _new_asset(client)
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "sap_asset_number": "100000009999",
        "sap_reconciliation_state": "reconciled",
    })
    assert_fields_refused(r, "sap_asset_number", "sap_reconciliation_state")

    after = assert_envelope_ok(client.get(f"/api/v1/assets/{asset['id']}"))
    assert after["data"]["sap"]["asset_number"] is None
    assert after["data"]["sap"]["reconciliation_state"] == "not_tagged"


def test_the_serialised_alias_names_are_not_writable_either(client):
    """The block's own key names must not be a second way in.

    `data.sap.asset_number` is the published name, and a caller who never
    reads the model would reasonably try to PATCH it. It is not a model field
    either, so it is refused — by name, so that the caller who tried the
    published spelling is told that is not how the number arrives.
    """
    asset = _new_asset(client)
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"sap": {"asset_number": "100000004321"},
                           "asset_number": "100000004321"})
    assert_fields_refused(r, "sap", "asset_number")
    after = assert_envelope_ok(client.get(f"/api/v1/assets/{asset['id']}"))
    assert after["data"]["sap"]["asset_number"] is None


# ─── the published contract describes it ─────────────────────────────


def test_the_openapi_document_describes_the_sap_block(client):
    """An integrator reading the spec must be able to see `data.sap`.

    Rule 2: the model, the allow-list, the OpenAPI annotation and the test
    move together. This is the assertion that keeps the fourth one honest
    about the third.
    """
    spec = client.get("/api/v1/openapi.json").json()
    schemas = spec["components"]["schemas"]

    assert "AssetSap" in schemas, "the SAP block is not in the published spec"
    assert schemas["Asset"]["properties"]["sap"]["$ref"] == \
        "#/components/schemas/AssetSap"

    sap = schemas["AssetSap"]
    assert sap.get("readOnly") is True, (
        "the SAP block must be published read-only — nothing in it is in the "
        "writable-field allow-list"
    )
    for field in SAP_KEYS:
        assert field in sap["properties"], f"`{field}` undocumented"

    assert sap["properties"]["reconciliation_state"]["enum"] == \
        RECONCILIATION_STATES
    assert sap["properties"]["code_source"]["enum"] == \
        ["integration", "import", "manual"]
    assert sap["properties"]["posting_state"]["enum"] == \
        ["none", "queued", "posted", "failed"]


def test_the_list_endpoint_publishes_its_sap_query_parameters(client):
    """The three filters are annotated, so nobody has to find them by trying."""
    spec = client.get("/api/v1/openapi.json").json()
    params = spec["paths"]["/api/v1/assets"]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}

    for name in ("sap_asset_number", "has_sap_code",
                 "sap_reconciliation_state"):
        assert name in by_name, f"`{name}` is not in the published spec"

    assert by_name["sap_reconciliation_state"]["schema"]["enum"] == \
        RECONCILIATION_STATES
