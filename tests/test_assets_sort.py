"""`GET /api/v1/assets?sort=` — the direction, and the cursor that remembers it.

WHY THIS PARAMETER EXISTS
-------------------------
The endpoint has always walked ASCENDING asset id, so the register's newest
asset is on its last page. `nrs.asset._order` was fixed to put the newest
first in Odoo's own views, but this endpoint does not read `_order` at all —
`paginate()` passes `order="id"` explicitly — so the Cadra web register at
`/app/assets/list`, which is an API consumer and not an Odoo view, kept
showing oldest-first. A user who had just received an asset from Vendra could
not find it.

The fix is ADDITIVE on purpose. `sort` is absent by default, the default is
the ascending walk this endpoint has always published, and an ascending
cursor is byte-for-byte what it has always been — so Vendra, which builds
against this contract, sees no change whatsoever. That is what
`test_the_default_is_unchanged_and_an_ascending_cursor_carries_no_direction`
is really guarding, and it is the test to look at first if anyone proposes
flipping the default later.

THE CURSOR IS THE SUBTLE HALF
-----------------------------
A keyset cursor means "everything after the last row I saw", and which SIDE
that is depends on the direction. Replay an ascending cursor against a
descending walk and the comparator pages AWAY from the unseen rows: the
caller receives a short list that looks complete. That is the exact shape
handoff 22 refused to keep for corrupt cursors — an answer that looks like an
answer is worse than a refusal — so the direction is recorded IN the token
and a mismatch is a 400.
"""
import time

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok


def _uniq():
    return str(int(time.time() * 1000))[-9:]


def _ids(body):
    return [a["id"] for a in body["data"]]


@pytest.fixture(scope="module")
def a_fresh_asset(client, test_location):
    """One asset created now, so "newest" has a known right answer.

    ON THE REGISTER whichever way the receipt switch is set (handoff 58
    §2): the list sorts the register, which with the gates on hides a
    receipt until `tests/gates.py` has walked it onto it."""
    ts = _uniq()
    return gates.new_registered_asset(
        client, name=f"pytest-sort-{ts}", category_id=1,
        location_id=test_location["id"])


# ─── the direction ───────────────────────────────────────────────────

def test_sort_newest_puts_the_most_recent_asset_first(client, a_fresh_asset):
    """The whole point: create one, ask for newest, and it is row one."""
    r = client.get("/api/v1/assets", params={"sort": "newest", "limit": 5})
    body = assert_envelope_ok(r)
    assert _ids(body), "the register is empty; this test proves nothing"
    assert body["data"][0]["id"] == a_fresh_asset["id"], (
        "the asset created moments ago must lead `sort=newest`; got id %r"
        % (body["data"][0]["id"],))


def test_sort_newest_is_descending_across_the_whole_page(client):
    r = client.get("/api/v1/assets", params={"sort": "newest", "limit": 25})
    ids = _ids(assert_envelope_ok(r))
    assert len(ids) > 1, "need more than one row to assert an order"
    assert ids == sorted(ids, reverse=True), (
        "`sort=newest` must return strictly descending ids; got %r" % (ids,))


def test_sort_oldest_is_the_default_spelled_out(client):
    """`oldest` is what the endpoint already did — the two must agree exactly."""
    params = {"limit": 25}
    default = _ids(assert_envelope_ok(client.get("/api/v1/assets", params=params)))
    explicit = _ids(assert_envelope_ok(
        client.get("/api/v1/assets", params={**params, "sort": "oldest"})))
    assert default == explicit
    assert default == sorted(default), "the default walk is ascending id"


# ─── the contract that must NOT have moved ───────────────────────────

def test_the_default_is_unchanged_and_an_ascending_cursor_carries_no_direction(client):
    """Vendra's view of this endpoint, asserted rather than assumed.

    An ascending token must decode to exactly `{"last_id": N}`. If a `desc`
    key ever appears here the ascending payload has changed shape, and every
    cursor an integration is holding becomes a token issued by a different
    API than the one it was given.
    """
    import base64
    import json

    r = client.get("/api/v1/assets", params={"limit": 2})
    body = assert_envelope_ok(r)
    cursor = body["pagination"]["next_cursor"]
    if not cursor:
        pytest.skip("register too small to produce a cursor")

    padded = cursor + "=" * (-len(cursor) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    assert set(payload) == {"last_id"}, (
        "an ascending cursor must keep the shape it has always had; got %r"
        % (payload,))


# ─── paging, in both directions ──────────────────────────────────────

def test_a_descending_walk_pages_without_skipping_or_repeating(client):
    """Three small pages, and the ids must be strictly descending throughout.

    A comparator left as `>` would return the SAME rows on every page (or
    none), so this fails loudly rather than subtly if the direction and the
    cursor ever disagree.
    """
    seen = []
    cursor = None
    for _ in range(3):
        params = {"sort": "newest", "limit": 3}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get("/api/v1/assets", params=params))
        page = _ids(body)
        if not page:
            break
        seen.extend(page)
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break

    assert len(seen) == len(set(seen)), (
        "a descending walk repeated rows across pages: %r" % (seen,))
    assert seen == sorted(seen, reverse=True), (
        "a descending walk must stay descending across pages: %r" % (seen,))


# ─── refusals ────────────────────────────────────────────────────────

def test_an_unknown_sort_value_is_a_400_naming_the_set(client):
    r = client.get("/api/v1/assets", params={"sort": "newest_first"})
    body = assert_envelope_err(r, expected_status=400)
    assert body["error"]["code"] == "invalid_request"
    assert set(body["error"]["details"]["allowed_values"]) == {"newest", "oldest"}


def test_an_empty_sort_is_absent_not_invalid(client):
    """`?sort=` is the documented spelling of "no opinion", like every other
    parameter at this door. It must not become a 400."""
    body = assert_envelope_ok(client.get("/api/v1/assets",
                                         params={"sort": "", "limit": 5}))
    assert _ids(body) == sorted(_ids(body))


def test_an_ascending_cursor_replayed_as_descending_is_refused(client):
    """The failure this design exists to prevent, asserted end to end."""
    body = assert_envelope_ok(client.get("/api/v1/assets", params={"limit": 2}))
    cursor = body["pagination"]["next_cursor"]
    if not cursor:
        pytest.skip("register too small to produce a cursor")

    r = client.get("/api/v1/assets",
                   params={"sort": "newest", "limit": 2, "cursor": cursor})
    err = assert_envelope_err(r, expected_status=400)
    assert err["error"]["code"] == "invalid_request"
    details = err["error"]["details"]
    assert details["cursor_direction"] == "ascending"
    assert details["requested_direction"] == "descending"


def test_a_descending_cursor_replayed_as_ascending_is_refused(client):
    """The same guard from the other side — it is not a one-way check."""
    body = assert_envelope_ok(client.get("/api/v1/assets",
                                         params={"sort": "newest", "limit": 2}))
    cursor = body["pagination"]["next_cursor"]
    if not cursor:
        pytest.skip("register too small to produce a cursor")

    r = client.get("/api/v1/assets", params={"limit": 2, "cursor": cursor})
    err = assert_envelope_err(r, expected_status=400)
    assert err["error"]["details"]["cursor_direction"] == "descending"
    assert err["error"]["details"]["requested_direction"] == "ascending"
