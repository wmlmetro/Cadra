"""A cursor we did not issue is refused, and the enum sets are published.

TWO HALVES OF ONE ARGUMENT
--------------------------
**The cursor.** `decode_cursor` used to return `{}` for anything it could not
decode, and `{}` means "start at the beginning". So a caller paging with a
corrupted cursor silently restarted at page one *while believing it was on
page three* — walking the same records again, or reading a later page as empty
and concluding the register had ended. That was documented behaviour, and
turning it into a 400 is a BREAKING change (docs/api/CHANGELOG.md, handoff
22). It is the same argument that cleared the twenty-six query parameters in
handoff 21, applied without modification: **an answer that looks like an
answer is worse than a refusal.** A client sending a cursor it did not get
from us has a bug, and a 400 is the only way it finds out.

An absent or empty cursor is a DIFFERENT input and keeps its answer — it
still means "start at the beginning". The tests below assert both halves,
because a change that refused the empty case too would break every first-page
request in the estate.

**The enums.** Until this handoff the only way a client could learn a field's
accepted values was to send a wrong one and read `allowed_values` off the
400 — a refusal doing documentation's job, useless for populating a dropdown
before the user types. `GET /api/v1/meta/enums` publishes them, derived from
the live Odoo Selection rather than from a list written out in a controller.

These are HTTP-level and run against a live tenant, because what is being
asserted is what a caller receives.
"""
import base64
import json
import time

import pytest

from .conftest import assert_envelope_err, assert_envelope_ok


#: Paginated list endpoints. Each is skipped individually if this
#: credential cannot reach it — the suite's token is a CLIENT token and
#: CLAUDE.md documents that it cannot reach every route.
PAGINATED = [
    "/api/v1/assets",
    "/api/v1/locations",
    "/api/v1/requests",
]


def _cursor(payload):
    """Encode a payload the way the API does, for the valid-token cases."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _get(client, path, **params):
    r = client.get(path, params=params)
    if r.status_code in (401, 403):
        pytest.skip("this credential cannot reach %s (%d)" % (path, r.status_code))
    return r


# ─── the cursor refuses ──────────────────────────────────────────────

#: Every one of these used to answer 200-with-page-one.
#:
#: They are not all the same failure underneath, which is the point of
#: listing them separately rather than testing one: `"not-a-cursor"` fails to
#: base64-decode, `_cursor([1, 2])` decodes to valid JSON that is not an
#: object (which reached `"last_id" in cursor_data`, where a list answered
#: False — another silent restart), and `_cursor({"last_id": "abc"})` reached
#: a bare `int()` inside `paginate` and answered **500**. Three different
#: wrong answers, now one right one.
BAD_CURSORS = [
    ("not-a-cursor", "not base64 at all"),
    ("!!!!", "base64-illegal characters"),
    (base64.urlsafe_b64encode(b"not json").decode().rstrip("="), "base64 of non-JSON"),
    (_cursor([1, 2]), "valid JSON, but an array not an object"),
    (_cursor("a string"), "valid JSON, but a bare string"),
    (_cursor(7), "valid JSON, but a bare number"),
    (_cursor({"last_id": "abc"}), "an object whose last_id is not an integer"),
    (_cursor({"last_id": None}), "an object whose last_id is null"),
]


@pytest.mark.parametrize("path", PAGINATED)
@pytest.mark.parametrize("cursor,why", BAD_CURSORS, ids=[w for _, w in BAD_CURSORS])
def test_a_cursor_we_did_not_issue_is_refused(client, path, cursor, why):
    """400, not a silent restart at page one."""
    r = _get(client, path, cursor=cursor, limit=5)
    assert r.status_code != 500, (
        "%s with a cursor that is %s answered 500. A malformed cursor is "
        "caller input and must be a 400 — a 500 tells an integration to "
        "retry a request that can never succeed." % (path, why))
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "cursor" in body["error"]["message"], (
        "the refusal does not name `cursor`, so a caller cannot tell which "
        "part of their request was rejected: %r" % body["error"]["message"])
    assert body["error"]["details"].get("cursor") == cursor, (
        "the refusal does not echo the offending value back")


@pytest.mark.parametrize("path", PAGINATED)
def test_an_absent_cursor_still_starts_at_the_beginning(client, path):
    """The input that always meant "first page" keeps its answer.

    This is the half of the change that must NOT break. Refusing an empty
    cursor as well would have broken every first-page request in the estate,
    and it would have looked like the same fix.
    """
    first = _get(client, path, limit=5)
    assert_envelope_ok(first)

    absent = _get(client, path, limit=5, cursor="")
    assert_envelope_ok(absent)
    assert [row.get("id") for row in absent.json()["data"]] == \
           [row.get("id") for row in first.json()["data"]], (
        "an empty `cursor` returned something other than the first page")


@pytest.mark.parametrize("path", PAGINATED)
def test_a_cursor_we_did_issue_still_pages(client, path):
    """The happy path is untouched: our own `next_cursor` walks forward.

    Without this the refusal above could be satisfied by refusing every
    cursor, which would pass every test in this file and break pagination
    for every caller.
    """
    first = _get(client, path, limit=2)
    assert_envelope_ok(first)
    next_cursor = (first.json().get("pagination") or {}).get("next_cursor")
    if not next_cursor:
        pytest.skip("%s has one page of data on this tenant" % path)

    second = _get(client, path, limit=2, cursor=next_cursor)
    assert_envelope_ok(second)
    first_ids = {row.get("id") for row in first.json()["data"]}
    second_ids = {row.get("id") for row in second.json()["data"]}
    assert not (first_ids & second_ids), (
        "page two repeats rows from page one: %r" % (first_ids & second_ids))


# ─── the enum sets are published ─────────────────────────────────────

#: What `/api/v1/meta/enums` must publish, and the one value in each set whose
#: absence was a live defect. Asserting a specific member rather than only a
#: count is deliberate: a count passes on the wrong set of the right size.
EXPECTED_SETS = {
    # the model's five, in this order — `"2"` is High, which is what the
    # front end got wrong
    "priority": ["0", "1", "2", "3", "4"],
    # `wing` was never offered by the location form, and `state`/`office`
    # were offered but do not exist
    "location_type": ["building", "floor", "wing", "room", "zone"],
    # `group` was missing, so a group-level asset silently demoted
    "asset_level": ["group", "asset", "sub_asset", "component"],
    "domain": ["building", "plant", "plumbing", "fleet", "security", "it",
               "furniture", "other"],
    "condition": ["new", "good", "fair", "poor", "decommissioned"],
    "asset_state": ["active", "in_repair", "disposed", "transferred", "missing"],
    # handoff 34 — three, not two: `none` is not `expired`
    "warranty_status": ["under_warranty", "expired", "none"],
    # nine, rendered as three by the old front end
    "fuel_type": ["diesel", "gasoline", "full_hybrid", "plug_in_hybrid_diesel",
                  "plug_in_hybrid_gasoline", "cng", "lpg", "hydrogen", "electric"],
}


@pytest.fixture(scope="module")
def enum_sets(client):
    r = client.get("/api/v1/meta/enums")
    if r.status_code in (401, 403):
        pytest.skip("this credential cannot reach /api/v1/meta/enums (%d)"
                    % r.status_code)
    assert_envelope_ok(r)
    return r.json()["data"]


@pytest.mark.parametrize("name", sorted(EXPECTED_SETS))
def test_enum_set_is_the_models_own(enum_sets, name):
    """Values and ORDER. Order matters for `priority`, whose keys read as a
    scale — a set that is right as a bag and wrong as a sequence is the bug
    that shipped."""
    assert name in enum_sets, (
        "`%s` is not published by /api/v1/meta/enums; the front end has "
        "nothing to populate that control from" % name)
    values = [o["value"] for o in enum_sets[name]]
    assert values == EXPECTED_SETS[name], (
        "`%s` is %r; the model declares %r" % (name, values, EXPECTED_SETS[name]))


def test_every_option_carries_a_label(enum_sets):
    """A dropdown needs a label. `in_repair` is not something to show a user."""
    bare = [(name, o["value"]) for name, options in enum_sets.items()
            for o in options if not o.get("label")]
    assert not bare, "options published with no label: %r" % bare


def test_priority_labels_are_the_models_not_the_old_front_ends(enum_sets):
    """The specific regression: `"2"` is **High**, not "Normal".

    The SPA published `0=Very low, 1=Low, 2=Normal, 3=High, 4=Urgent` — every
    label one step off — and its blank form defaulted to `"2"`. So a user who
    never touched the dropdown saw "Normal" and the database recorded High.
    If this assertion ever fails, read the model before changing the test.
    """
    labels = {o["value"]: o["label"] for o in enum_sets["priority"]}
    assert labels["2"] == "High", (
        "`priority` `\"2\"` is published as %r. On the model it is High, and "
        "a front end that believes otherwise files every untouched form one "
        "level too high." % labels["2"])
    assert labels["1"] == "Normal"
    assert labels["4"] == "Very Urgent"


def test_the_published_set_is_what_the_filters_accept(client, enum_sets):
    """The endpoint cannot offer a value a filter would then refuse.

    Both read the model through `utils.selection_values`, so this asserts
    they really do agree rather than merely being written to agree. A
    dropdown offering a value the list endpoint rejects is the same class of
    lie, pointed the other way.
    """
    for value in [o["value"] for o in enum_sets["condition"]]:
        r = _get(client, "/api/v1/assets", condition=value, limit=1)
        assert r.status_code == 200, (
            "/api/v1/meta/enums offers `condition=%s` but /api/v1/assets "
            "answered %d for it" % (value, r.status_code))


def test_a_value_outside_the_published_set_is_still_refused(client, enum_sets):
    """`damaged` is the one that cost a screen.

    It has never been on `nrs.asset.condition`, so the register's *Faulty*
    chip always answered empty and the *Damaged* tile always showed `0` —
    reading as "there are no faulty assets". It must not appear here, and it
    must still be refused there.
    """
    assert "damaged" not in [o["value"] for o in enum_sets["condition"]]
    r = _get(client, "/api/v1/assets", condition="damaged", limit=1)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "damaged" in str(body["error"]["details"]), (
        "the refusal does not echo the rejected value")
    assert body["error"]["details"].get("allowed_values"), (
        "the refusal carries no `allowed_values`, so a client still cannot "
        "tell its user what to type instead")


# ─── the partition that summed to everything ─────────────────────────

def _total(client, path, **params):
    """`pagination.total_estimate` — the TRUE count, not the page length.

    This is the whole trick of the tests below. `tests/test_query_params.py`
    counts `len(body["data"])`, which `DEFAULT_PAGE_LIMIT` bounds at 50, so
    its partition assertion is guarded by `if unfiltered < 50` and simply
    does not run on any endpoint with more than fifty rows — silently, with
    nothing skipped and nothing printed. `total_estimate` is documented as
    always being a `search_count` of the caller's own unclamped domain
    (`utils.paginate`), so a partition can be checked over the register
    rather than over a window of it.
    """
    r = _get(client, path, limit=1, **params)
    assert_envelope_ok(r)
    return (r.json().get("pagination") or {}).get("total_estimate")


@pytest.fixture(scope="module")
def both_halves_exist(client):
    """One mapped location and one unmapped one, created if absent.

    The partition assertion below is worth having only if BOTH halves are
    non-empty — a check that passes on an empty half is the thing this test
    exists to prevent. But whether a half is empty is a fact about the
    tenant's data, not about the code: `jaizbankplc` has 130 mapped and 250
    unmapped, while CI's freshly-seeded database has **0 mapped and 480
    unmapped**, because nothing in the seed carries a coordinate.

    Skipping there would have been the easy answer and the wrong one: it
    would mean this regression net never runs in CI, which is precisely the
    "test that does not run" defect this handoff spent its time removing.
    Two rows cost nothing and make the assertion real on any tenant.
    """
    ts = int(time.time())
    created = []
    for suffix, body in (
        ("mapped", {"latitude": 9.0820, "longitude": 8.6753}),
        ("unmapped", {}),
    ):
        r = client.post("/api/v1/locations", json={
            "name": "pytest-coords-%s-%d" % (suffix, ts),
            "description": "Created by tests/test_cursor_and_enums.py — "
                           "guarantees both halves of the has_coordinates "
                           "partition exist. Leave in dev DB.",
            **body,
        })
        if r.status_code in (401, 403):
            pytest.skip("this credential cannot create locations (%d)"
                        % r.status_code)
        assert r.status_code == 201, (
            "could not create the %s fixture location: HTTP %d %s"
            % (suffix, r.status_code, r.text[:300]))
        created.append(r.json()["data"])
    return created


def test_has_coordinates_true_and_false_sum_to_the_whole_register(
        client, both_halves_exist):
    """`?has_coordinates=false` is "which sites has nobody mapped".

    It used to answer **zero** on a tenant where 250 of 380 locations are
    unmapped. `latitude`/`longitude` are declared with no `default=`, so an
    unset coordinate is SQL NULL and never 0.0 — and Odoo renders
    `('latitude', '!=', 0.0)` as `(latitude != 0 OR latitude IS NULL)`, which
    put every unmapped site on the HAS-coordinates side.

    **The old behaviour passed a naive partition check.** true returned 380,
    false returned 0, and 380 + 0 == 380: the two halves summed to the whole
    register while one of them was empty and the other was everything. So
    this asserts the sum AND that neither half is degenerate — a partition
    assertion that cannot pass on an empty half is the entire point, and is
    the lesson report 21 drew about `has_deadline` applied to its own code.
    """
    path = "/api/v1/locations"
    whole = _total(client, path)
    mapped = _total(client, path, has_coordinates="true")
    unmapped = _total(client, path, has_coordinates="false")

    assert None not in (whole, mapped, unmapped), (
        "an endpoint in this test did not report `total_estimate`; the "
        "counts below would be page lengths, not register counts")
    assert mapped + unmapped == whole, (
        "has_coordinates=true (%d) + has_coordinates=false (%d) != the whole "
        "register (%d) — the two branches are not a partition" % (
            mapped, unmapped, whole))
    assert 0 < mapped < whole and 0 < unmapped < whole, (
        "the partition is degenerate: mapped=%d unmapped=%d whole=%d. One "
        "half is empty and the other is everything, which is how this filter "
        "passed for the whole time it was broken.\n"
        "`both_halves_exist` creates one row on each side precisely so this "
        "cannot happen, so a degenerate split here means the FILTER is "
        "wrong, not the fixture — most likely that unset coordinates have "
        "landed on the has-coordinates side again."
        % (mapped, unmapped, whole))
