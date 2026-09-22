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

from .conftest import assert_envelope_ok, assert_fields_refused

_SOURCES = {"api_transfer", "api_write", "transfer", "direct",
            "tracking_backfill", "test", "approval"}

# `approval` joined the set in handoff 35: when a tenant requires a second
# person, the link is written by `action_approve` and declares that as its
# source. It is what a real client's chain will be full of, so a reader of
# this suite should see it named here even on a tenant where the credential
# relabels it (see `_TEST_SOURCE` below).

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


def _build_a_chain(client, second_person, asset_id, links_wanted=3):
    """Move the custodian back and forth until the chain is long enough.

    Without this, a freshly created session asset has one link or none, and
    every pagination assertion below takes its early-return branch and tests
    nothing — a green run that checked nothing, which is worse than a red
    one. Returns the number of links now on the chain.

    **Handoff 35 made this exact failure happen.** When `/transfer-custody`
    started answering 400 *"`approver_id` is required"*, this loop's tolerant
    `if r.status_code not in (200, 400, 404)` swallowed every call, no chain
    was ever built, and three tests in this file went from passing to
    SKIPPING — with the message "tenant has no two employees", which was not
    true and was not the reason. The suite reported 11 skips instead of 8 and
    nothing else changed colour. That is the shape report 23 §3 warned about:
    a skip is a guard that passes. It is why the helper now goes through
    `second_person`, which fails loudly when the tenant needs a second person
    and there is nobody to be one.
    """
    pair = _two_employees(client)
    if not pair:
        return len(_whole_chain(client, asset_id))
    held = None
    chain = _whole_chain(client, asset_id)
    if chain:
        held = (chain[-1]["to_custodian"] or {}).get("id")
    for i in range(links_wanted):
        target = pair[i % 2]
        if target == held:
            # The route refuses a transfer to the custodian already holding
            # it, and rightly — but a refusal here writes no link, so the
            # loop would run its full count and build a shorter chain than it
            # reports. Alternate around it instead.
            target = pair[(i + 1) % 2]
        if target == held:
            break
        second_person.transfer_custody(
            asset_id, target, reason="test_custody._build_a_chain")
        held = target
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


def test_the_total_counts_the_chain_not_the_page(client, test_asset,
                                                 second_person):
    """handoff 12's honesty, inherited rather than reimplemented.

    A one-record page of an N-link chain must still report N. This is the
    defect that made `total_estimate` a false statement about the register
    on every list endpoint until handoff 12; a route added afterwards gets
    it for free ONLY if it goes through `paginate()`, which is what this
    checks.
    """
    _build_a_chain(client, second_person, test_asset["id"])
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


def test_the_chain_pages_forwards(client, test_asset, second_person):
    """Oldest first, and the cursor walks it without repeating a link."""
    _build_a_chain(client, second_person, test_asset["id"])
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


def test_include_custody_is_not_capped(client, test_asset,
                                       second_person):
    """The embed carries the WHOLE chain, and matches the route."""
    _build_a_chain(client, second_person, test_asset["id"])
    r = client.get(f"/api/v1/assets/{test_asset['id']}",
                   params={"include": "custody"})
    body = assert_envelope_ok(r)
    embedded = body["data"]["custody"]
    listed = _whole_chain(client, test_asset["id"])
    assert [link["id"] for link in embedded] == [link["id"] for link in listed]


def test_a_transfer_appends_exactly_one_link(client, test_asset,
                                             second_person, capture):
    """One physical act, one link — however many people it took to agree.

    The old body tolerated a 400 and returned, on the grounds that "already
    assigned to employee 1" says nothing about the chain. Handoff 35 turned
    that tolerance into a hole: the 400 it started swallowing was *"`approver_id`
    is required"*, and this test passed for the wrong reason while asserting
    nothing at all. The target is now chosen so that it cannot be the
    custodian already held, which removes the only refusal the branch existed
    for — and the call goes through `second_person`, which asserts its own
    2xx and fails rather than shrugging.

    **The link is written on APPROVAL and never on the request.** That is
    handoff 35 §B's first non-negotiable and it is what this test's counting
    now also proves: one link for one act, not one for the asking and another
    for the agreeing.
    """
    before = _whole_chain(client, test_asset["id"])
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    held = (before[-1]["to_custodian"] or {}).get("id") if before else None
    target = pair[1] if held == pair[0] else pair[0]
    if target == held:
        pytest.skip("the asset already holds the only employee available")
    moved = second_person.transfer_custody(
        test_asset["id"], target, reason="test_custody.append_one")
    capture("assets/custody_transfer", moved["decision"] or moved["raised"])
    link_id = moved["custody_id"]
    assert link_id
    after = _whole_chain(client, test_asset["id"])
    assert len(after) == len(before) + 1
    appended = after[-1]
    assert appended["id"] == link_id
    # `api_transfer` is what the route declares. A credential flagged
    # `is_test_credential` overrides it to `test` on the way in, deliberately
    # — these links are permanent artefacts and saying so matters more to a
    # reader than which route they arrived by. Both are correct answers here;
    # anything else means the route stopped declaring a source.
    assert appended["source"] in ("api_transfer", "test")
    assert appended["reason"] == "test_custody.append_one"
    assert appended["to_custodian"]["id"] == target
    # The acting user, recorded. A chain that cannot say who moved the asset
    # answers half the auditor's question.
    assert appended["changed_by"] is not None


def test_a_patch_of_the_custodian_also_appends(client, test_asset,
                                               second_person):
    """`custodian_id` is in `_WRITABLE_FIELDS`, so PATCH moved custody too.

    The handoff that built the chain scoped the recorder to the transfer
    route on the grounds that it was the only writer. It was not — and a
    chain missing this one would have a gap that reads as a period of no
    movement.

    **Handoff 35 shut this door where a second person is required.** PATCH
    now refuses a body that CHANGES `custodian_id`, whole, 400, naming
    `/transfer-custody` in `details.use_instead`. So there are two properties
    and this asserts whichever one is true of the tenant:

      * door open  — the PATCH appends exactly one link, as it always did;
      * door shut  — the PATCH appends NOTHING, and the chain is unchanged.

    The second is the more important of the two to assert, because a refusal
    is a response and not a rollback (CLAUDE.md): a route that refused after
    writing would leave a permanent, unalterable link recording a change of
    custodian that the caller was told had not happened.

    The old body returned early on any non-200 and on any unchanged chain,
    which on an approval tenant made it a test that ran and checked nothing.
    """
    before = _whole_chain(client, test_asset["id"])
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    held = (before[-1]["to_custodian"] or {}).get("id") if before else None
    target = pair[1] if held == pair[0] else pair[0]
    if target == held:
        pytest.skip("the asset already holds the only employee available")

    r = client.patch(f"/api/v1/assets/{test_asset['id']}",
                     json={"custodian_id": target})

    if second_person.required:
        details = assert_fields_refused(r, "custodian_id")
        assert details["approval_required"] is True
        assert "/transfer-custody" in details["use_instead"]["custodian_id"]
        assert _whole_chain(client, test_asset["id"]) == before, (
            "a refused PATCH appended a link to an append-only chain — the "
            "one kind of record nobody can go back and remove")
        return

    assert_envelope_ok(r)
    after = _whole_chain(client, test_asset["id"])
    assert len(after) == len(before) + 1
    # See the transfer test above: `test` is the same link relabelled by the
    # credential, not a different source.
    assert after[-1]["source"] in ("api_write", "test")


def test_the_chain_has_no_write_endpoint(client, test_asset):
    """Append-only means there is nothing to POST to.

    The links are a side effect of a custodian change, never a payload. A
    route that accepted one would be a way to write history directly.
    """
    r = client.post(f"/api/v1/assets/{test_asset['id']}/custody",
                    json={"to_custodian_id": 1})
    assert r.status_code in (404, 405)


def test_a_link_this_suite_wrote_says_so(client, test_asset,
                                         second_person):
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
    _build_a_chain(client, second_person, test_asset["id"])
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
