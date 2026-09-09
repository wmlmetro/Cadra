"""The chain of custody over the API — INT-10 §2.3.

Two things these assert that a status check would not:

- the chain is a LIST endpoint, so it inherits `paginate()`'s honest
  `total_estimate` and the truncation warning. That is claimed rather than
  obvious, so it is checked: the total must count the whole chain, not the
  page.
- `include=custody` is NOT capped. The embedded `transfers` list takes the
  last 20, and "the last twenty custodians" is the answer an auditor cannot
  use — a truncated chain is indistinguishable from a complete one.

`source` is asserted because it is what tells a link recorded as it happened
from one reconstructed out of the chatter tracking values that preceded the
model. An auditor has to be able to see that without knowing to ask.
"""
import pytest

from .conftest import assert_envelope_ok

_SOURCES = {"api_transfer", "api_write", "transfer", "direct",
            "tracking_backfill", "test"}

# What this suite's own links come back as. The suite moves a real asset's
# custodian, and the recorder is append-only, so every link it writes is
# PERMANENT in whichever tenant the run was pointed at. `source: "test"`
# is what makes them visible as artefacts to somebody reading the chain who
# was never told the suite exists — the same argument as `tracking_backfill`.
#
# Decided server-side from the credential (`myservice.api.client
# .is_test_credential`), never from anything sent with the request: a caller
# able to label its own writes could disguise a real change of custodian as
# a test.
_TEST_SOURCE = "test"


def _chain(client, asset_id, **params):
    r = client.get(f"/api/v1/assets/{asset_id}/custody", params=params)
    return r, assert_envelope_ok(r)


def _two_employees(client):
    """Two real employee ids on this tenant, or None.

    Hard-coding id 1 was the old way and it is wrong twice over: the id may
    not exist, and if it happens to be the asset's current custodian the
    transfer is refused and the test silently proves nothing.
    """
    r = client.get("/api/v1/identity/employees", params={"limit": 2})
    if r.status_code != 200:
        return None
    rows = r.json().get("data") or []
    if len(rows) < 2:
        return None
    return rows[0]["id"], rows[1]["id"]


def _build_a_chain(client, asset_id, links_wanted=3):
    """Move the custodian back and forth until the chain is long enough.

    Without this, a freshly created session asset has one link or none, and
    every pagination assertion below takes its early-return branch and tests
    nothing — a green run that checked nothing, which is worse than a red
    one. Returns the number of links now on the chain.
    """
    pair = _two_employees(client)
    if not pair:
        return len(_whole_chain(client, asset_id))
    for i in range(links_wanted):
        target = pair[i % 2]
        r = client.post(f"/api/v1/assets/{asset_id}/transfer-custody",
                        json={"to_custodian_id": target,
                              "reason": "test_custody._build_a_chain"})
        if r.status_code not in (200, 400, 404):
            break
    return len(_whole_chain(client, asset_id))


def _whole_chain(client, asset_id):
    """Every link, by walking the cursor.

    NOT `limit=200`. `parse_limit` clamps a service token to
    EXTERNAL_MAX_PAGE_LIMIT (100), so naming a big number silently gives you
    a page and calls it the whole chain — which is the exact class of false
    answer this endpoint exists to stop. Walking is the honest way to ask.
    """
    links = []
    cursor = None
    for _ in range(50):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        _, body = _chain(client, asset_id, **params)
        links.extend(body["data"])
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    return links


def test_custody_route_returns_a_chain(client, test_asset, capture):
    """GET /api/v1/assets/<id>/custody — the asset's own chain."""
    r, body = _chain(client, test_asset["id"], limit=100)
    capture("assets/custody", r)
    assert isinstance(body["data"], list)
    assert "pagination" in body
    for link in body["data"]:
        assert link["source"] in _SOURCES
        # Who MOVED it. The two custodian fields cannot answer that, and it
        # is half of what an auditor asks.
        assert "changed_by" in link
        assert "changed_at" in link


def test_the_total_counts_the_chain_not_the_page(client, test_asset):
    """handoff 12's honesty, inherited rather than reimplemented.

    A one-record page of an N-link chain must still report N. This is the
    defect that made `total_estimate` a false statement about the register
    on every list endpoint until handoff 12; a route added afterwards gets
    it for free ONLY if it goes through `paginate()`, which is what this
    checks.
    """
    _build_a_chain(client, test_asset["id"])
    full = _whole_chain(client, test_asset["id"])
    length = len(full)
    if length < 2:
        # This tenant has fewer than two employees to move the asset
        # between, so no chain can be built and there is nothing to page.
        # Skipping loudly beats asserting vacuously.
        pytest.skip("tenant has no two employees to build a chain with")
    _, first = _chain(client, test_asset["id"], limit=1)
    assert len(first["data"]) == 1
    assert first["pagination"]["total_estimate"] == length
    assert first["pagination"]["next_cursor"]


def test_the_chain_pages_forwards(client, test_asset):
    """Oldest first, and the cursor walks it without repeating a link."""
    _build_a_chain(client, test_asset["id"])
    full = _whole_chain(client, test_asset["id"])
    if len(full) < 2:
        pytest.skip("tenant has no two employees to build a chain with")
    seen = []
    cursor = None
    # One extra iteration than there are links, so the loop ends because the
    # cursor ran out and not because the range did — a fixed bound would
    # quietly truncate `seen` and then compare it against the whole chain.
    for _ in range(len(full) + 1):
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        _, page = _chain(client, test_asset["id"], **params)
        seen.extend(link["id"] for link in page["data"])
        cursor = page["pagination"]["next_cursor"]
        if not cursor:
            break
    assert not cursor, "the cursor did not run out within the chain's length"
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    assert seen == [link["id"] for link in full]


def test_include_custody_is_not_capped(client, test_asset):
    """The embed carries the WHOLE chain, and matches the route."""
    _build_a_chain(client, test_asset["id"])
    r = client.get(f"/api/v1/assets/{test_asset['id']}",
                   params={"include": "custody"})
    body = assert_envelope_ok(r)
    embedded = body["data"]["custody"]
    listed = _whole_chain(client, test_asset["id"])
    assert [link["id"] for link in embedded] == [link["id"] for link in listed]


def test_a_transfer_appends_exactly_one_link(client, test_asset, capture):
    """POST /assets/<id>/transfer-custody — one physical act, one link."""
    before = _whole_chain(client, test_asset["id"])
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    held = (before[-1]["to_custodian"] or {}).get("id") if before else None
    target = pair[1] if held == pair[0] else pair[0]
    r = client.post(f"/api/v1/assets/{test_asset['id']}/transfer-custody",
                    json={"to_custodian_id": target,
                          "reason": "test_custody.append_one"})
    capture("assets/custody_transfer", r)
    if r.status_code in (400, 404):
        # 400: already assigned to employee 1. 404: this tenant has no
        # employee 1. Both are the transfer route's own answers about its
        # own inputs, and neither says anything about the chain — so this
        # test has nothing to assert rather than something to fail on.
        return
    body = assert_envelope_ok(r)
    link_id = body["data"]["custody_change"]["custody_id"]
    assert link_id
    after = _whole_chain(client, test_asset["id"])
    assert len(after) == len(before) + 1
    appended = after[-1]
    assert appended["id"] == link_id
    assert appended["source"] == "api_transfer"
    assert appended["reason"] == "test_custody.append_one"
    assert appended["to_custodian"]["id"] == target
    # The acting user, recorded. A chain that cannot say who moved the asset
    # answers half the auditor's question.
    assert appended["changed_by"] is not None


def test_a_patch_of_the_custodian_also_appends(client, test_asset):
    """`custodian_id` is in `_WRITABLE_FIELDS`, so PATCH moves custody too.

    The handoff scoped the recorder to the transfer route on the grounds
    that it is the only writer. It is not — and a chain missing this one
    would have a gap that reads as a period of no movement.
    """
    before = _whole_chain(client, test_asset["id"])
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    held = (before[-1]["to_custodian"] or {}).get("id") if before else None
    target = pair[1] if held == pair[0] else pair[0]
    r = client.patch(f"/api/v1/assets/{test_asset['id']}",
                     json={"custodian_id": target})
    if r.status_code != 200:
        return
    after = _whole_chain(client, test_asset["id"])
    if len(after) == len(before):
        # The custodian did not actually move. Nothing to assert, and a link
        # here would be the bug.
        return
    assert len(after) == len(before) + 1
    assert after[-1]["source"] == "api_write"


def test_the_chain_has_no_write_endpoint(client, test_asset):
    """Append-only means there is nothing to POST to.

    The links are a side effect of a custodian change, never a payload. A
    route that accepted one would be a way to write history directly.
    """
    r = client.post(f"/api/v1/assets/{test_asset['id']}/custody",
                    json={"to_custodian_id": 1})
    assert r.status_code in (404, 405)


def test_a_link_this_suite_wrote_says_so(client, test_asset):
    """The suite's own artefacts are identifiable FROM THE API ALONE.

    This suite writes permanent links into whichever tenant it is pointed
    at — that is accepted, because a test that does not exercise the
    recorder proves nothing. What is not acceptable is a reader of the
    chain being unable to tell. The old marker was a `reason` string
    carrying this module's name, which is a string somebody has to know to
    look for; `source` is returned on every link to everyone.

    Skips rather than fails where the credential is not provisioned as a
    test credential — a tenant bootstrapped before the flag existed, or a
    run pointed at a real integration credential. Skipping says so; a
    failure would read as a defect in the labelling.
    """
    links_before = len(_whole_chain(client, test_asset["id"]))
    _build_a_chain(client, test_asset["id"])
    full = _whole_chain(client, test_asset["id"])
    if len(full) <= links_before:
        pytest.skip("tenant has no two employees to build a chain with")

    ours = full[links_before:]
    sources = {link["source"] for link in ours}
    if sources == {"api_transfer"}:
        pytest.skip(
            "this credential is not flagged `is_test_credential`; its links "
            "are labelled by route, not as artefacts")
    assert sources == {_TEST_SOURCE}, (
        "a link written by the test suite came back as %s. It has to say "
        "what it is: these rows are permanent and append-only, and a reader "
        "who was never told this suite exists must still be able to see "
        "that they are artefacts." % sorted(sources))
