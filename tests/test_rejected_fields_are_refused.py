"""A field a write route does not accept is a 400 — on all ten of them, and
NOTHING is written. Handoff 31 §B.

Until then the answer was a 2xx. The route wrote what it could, dropped the
rest, and named the dropped keys in `data._warnings.rejected_fields`, which
for most of this API's life nothing read. Rule 3 of `CLAUDE.md` had called
that a defect from the start. What settled it was reading the consumer:
Vendra ALREADY treats a rejected field as terminal and dead-letters the
receipt — after Cadra has created the asset, incomplete, under an idempotency
key that replays the same 201 on every retry. And this suite's own
`test_request` fixture had been sending a location that was never once saved,
and found out from the 400.

**BREAKING, and announced.** The shape is one shape on every route:

    400 invalid_request
    details.rejected_fields   the keys refused, as sent
    details.writable          what the route DOES accept, sorted — so a
                              caller can repair itself from the response
    details.hint              on PATCH /requests, and only when `stage_id`
                              is among the refused

What each file that used to assert the 2xx now asserts is that ITS field is
refused. What is asserted HERE is what none of them can see from inside one
route: that the ten agree, that a refusal is for the WHOLE body, and that a
refusal does not burn an idempotency key — which is the property Vendra
needs, because the repair is to fix the mapper and deliver again under the
same key.

**"Nothing was written" is asserted by reading, every time.** For a PATCH
the record is read back and compared whole. For a create there is no record
to read, so the list is searched for a name unique to the test before and
after — with a CONTROL, the same name created without the refused key, or an
`?q=` that had stopped matching would make every such assertion pass alone.
"""
import time
import uuid

import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused, ids_matching)

# A key no model defines and no allow-list will ever grow. Deliberately not a
# real field: the property is the route's answer to a key it does not accept,
# and a real-but-protected field (`asset_tag`, `sap_asset_number`) has a test
# of its own in the file that owns the reason it is protected.
_KEY = "not_a_field_on_anything"


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def me(client):
    data = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    scopes = data.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return {"id": data["id"], "scopes": set(scopes)}


def _holds(me, scope):
    """The question `require_jwt` asks: `admin` and `*` grant everything."""
    return bool({scope, "admin", "*"} & me["scopes"])


def _need(me, scope):
    if not _holds(me, scope):
        pytest.skip(f"this credential does not hold `{scope}`, so the route "
                    "answers 403 before it reads the body")


# ─── the records the PATCH rows act on ───────────────────────────────

@pytest.fixture(scope="module")
def an_asset(client, test_location):
    return assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-refused-asset"), "category_id": 1,
        "location_id": test_location["id"]}), 201)["data"]


@pytest.fixture(scope="module")
def a_disposal_awaiting_approval(client, test_location):
    """Created as already disposed, with a date, and NOT condemned: an
    approval is a one-time act, so this asset must reach the table
    unapproved and leave it unapproved."""
    data = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-refused-disposal"), "category_id": 1,
        "state": "disposed", "disposal_date": "2026-01-31",
        "location_id": test_location["id"]}), 201)["data"]
    assert data["disposal"]["approved_by"] is None
    return data


@pytest.fixture(scope="module")
def a_location(client):
    return assert_envelope_ok(client.post("/api/v1/locations", json={
        "name": _uniq("pytest-refused-location")}), 201)["data"]


@pytest.fixture(scope="module")
def a_request(client, test_asset):
    return assert_envelope_ok(client.post("/api/v1/requests", json={
        "type_id": 1, "category_id": 5, "priority": "2",
        "request_text": f"<p>{_uniq('pytest-refused-request')}</p>",
        "nrs_asset_id": test_asset["id"]}), 201)["data"]


@pytest.fixture(scope="module")
def a_category(client, me):
    """This module's OWN category. A category's policy is pushed down to
    every asset that follows it, so the mixed-body test below must not be
    pointed at one the tenant's assets use."""
    _need(me, "settings:write")
    return assert_envelope_ok(client.post("/api/v1/asset-categories", json={
        "name": _uniq("pytest-refused-category"),
        "description": "as created"}), 201)["data"]


def _category(client, category_id):
    rows = assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]
    return next(row for row in rows if row["id"] == category_id)


def _depreciation_settings(client):
    """Without `data_quality`: those are counts over the register, which
    every other module in this session moves. `last_recompute` stays — a
    write to these settings recomputes, so it is the one field a write that
    "changed nothing" would still move."""
    data = assert_envelope_ok(
        client.get("/api/v1/settings/depreciation"))["data"]
    return {k: v for k, v in data.items() if k != "data_quality"}


# ─── the table ───────────────────────────────────────────────────────
#
# One row per route. `build(request)` returns what the row needs:
#
#   send(extra)   make the request, with `extra` merged into the smallest
#                 body the route would otherwise ACCEPT — so that the refused
#                 key is the only reason for the 400
#   read()        everything the request could have written, in one
#                 comparable value
#   good          for a PATCH: a writable field and a value it does not hold
#                 now, for the mixed-body test. None for a create, whose
#                 required fields already make every body a mixed one.

def _post_asset(request):
    client = request.getfixturevalue("client")
    location = request.getfixturevalue("test_location")
    name = _uniq("pytest-refused-post-asset")
    return {
        "send": lambda extra: client.post("/api/v1/assets", json={
            "name": name, "category_id": 1, "location_id": location["id"],
            **extra}),
        "read": lambda: ids_matching(client, "/api/v1/assets", name),
        "good": None, "created_status": 201,
    }


def _post_category(request):
    """The ELEVENTH route, and the one report 30's count missed.

    That count was made by searching for routes that REPORTED a dropped field
    in `_warnings`. This one dropped fields and reported nothing, so the
    search could not see it: `{"name": …, "method": "straight_line"}`
    answered 201 and set no depreciation policy — the bug that justified the
    ruling, at the one door the ruling's own count left open. `ids_matching`
    cannot be used here (the category list takes no `?q=`), so the read is
    the list filtered by the unique name.
    """
    client = request.getfixturevalue("client")
    _need(request.getfixturevalue("me"), "settings:write")
    name = _uniq("pytest-refused-post-category")

    def read():
        rows = assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]
        return [row["id"] for row in rows if row["name"] == name]

    return {
        "send": lambda extra: client.post(
            "/api/v1/asset-categories", json={"name": name, **extra}),
        "read": read, "good": None, "created_status": 201,
    }


def _patch_asset(request):
    client = request.getfixturevalue("client")
    asset = request.getfixturevalue("an_asset")
    path = f"/api/v1/assets/{asset['id']}"
    return {
        "send": lambda extra: client.patch(path, json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": ("notes", _uniq("SHOULD-NOT-BE-WRITTEN")),
    }


def _approve_disposal(request):
    client = request.getfixturevalue("client")
    _need(request.getfixturevalue("me"), "approvals:write")
    asset = request.getfixturevalue("a_disposal_awaiting_approval")
    path = f"/api/v1/assets/{asset['id']}"
    return {
        "send": lambda extra: client.post(f"{path}/approve-disposal",
                                          json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": None, "reads_no_body": True,
    }


def _post_location(request):
    client = request.getfixturevalue("client")
    name = _uniq("pytest-refused-post-location")
    return {
        "send": lambda extra: client.post("/api/v1/locations",
                                          json={"name": name, **extra}),
        "read": lambda: ids_matching(client, "/api/v1/locations", name),
        "good": None, "created_status": 201,
    }


def _patch_location(request):
    client = request.getfixturevalue("client")
    location = request.getfixturevalue("a_location")
    path = f"/api/v1/locations/{location['id']}"
    return {
        "send": lambda extra: client.patch(path, json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": ("description", _uniq("SHOULD-NOT-BE-WRITTEN")),
    }


def _post_request(request):
    client = request.getfixturevalue("client")
    asset = request.getfixturevalue("test_asset")
    marker = _uniq("pytest-refused-post-request")
    return {
        "send": lambda extra: client.post("/api/v1/requests", json={
            "type_id": 1, "category_id": 5,
            "request_text": f"<p>{marker}</p>",
            "nrs_asset_id": asset["id"], **extra}),
        "read": lambda: ids_matching(client, "/api/v1/requests", marker),
        "good": None, "created_status": 201,
    }


def _patch_request(request):
    client = request.getfixturevalue("client")
    req = request.getfixturevalue("a_request")
    path = f"/api/v1/requests/{req['id']}"
    return {
        "send": lambda extra: client.patch(path, json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": ("priority", "4"),
    }


def _patch_category(request):
    client = request.getfixturevalue("client")
    category = request.getfixturevalue("a_category")
    return {
        "send": lambda extra: client.patch(
            f"/api/v1/asset-categories/{category['id']}", json=extra),
        "read": lambda: _category(client, category["id"]),
        "good": ("description", _uniq("SHOULD-NOT-BE-WRITTEN")),
    }


def _patch_branding(request):
    client = request.getfixturevalue("client")
    _need(request.getfixturevalue("me"), "settings:write")
    return {
        "send": lambda extra: client.patch("/api/v1/settings/branding",
                                           json=extra),
        "read": lambda: assert_envelope_ok(
            client.get("/api/v1/settings/branding"))["data"],
        "good": ("short_name", "NOT-WRITTEN"),
        # What every user of this tenant sees. If the route is ever broken
        # enough to write it, the test fails AND puts it back.
        "restore": lambda before: client.patch(
            "/api/v1/settings/branding",
            json={"short_name": before["short_name"]}),
    }


def _patch_depreciation(request):
    client = request.getfixturevalue("client")
    _need(request.getfixturevalue("me"), "settings:write")
    now = _depreciation_settings(client)
    flipped = not now["declining_switches_to_straight_line"]
    return {
        "send": lambda extra: client.patch("/api/v1/settings/depreciation",
                                           json=extra),
        "read": lambda: _depreciation_settings(client),
        "good": ("declining_switches_to_straight_line", flipped),
        # Restates book values across the register, so as for branding.
        "restore": lambda before: client.patch(
            "/api/v1/settings/depreciation",
            json={"declining_switches_to_straight_line":
                  before["declining_switches_to_straight_line"]}),
    }


def _a_pending_request(request, raised_by_the_suite):
    """A brand-new asset with ONE pending approval request against it.

    Its own asset every time, because there is a partial unique index
    allowing one pending request per asset: reusing a fixture asset across
    the three rows below would make the second and third 409 rather than
    reach the body-checking they are here to test.

    `raised_by_the_suite` decides which credential asks, and it is not a
    detail. Approve and reject are decisions on SOMEBODY ELSE's request —
    self-approval is refused 403 in the model — so those two must be raised
    by the second person. Withdraw is the opposite: only the requester may
    take their own request back, so it must be raised by the suite.
    """
    client = request.getfixturevalue("client")
    second_person = request.getfixturevalue("second_person")
    if not second_person.required:
        pytest.skip("this tenant does not require approval, so `/move` "
                    "changes the asset and there is no request to decide")
    location = request.getfixturevalue("test_location")
    elsewhere = request.getfixturevalue("a_location")
    asset = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-refused-approval-asset"), "category_id": 1,
        "location_id": location["id"]}), 201)["data"]

    if raised_by_the_suite:
        raiser, approver_id = client, second_person.other["id"]
    else:
        raiser, approver_id = second_person.requester, second_person.approver_id
    raised = assert_envelope_ok(raiser.post(
        f"/api/v1/assets/{asset['id']}/move",
        json={"to_location_id": elsewhere["id"], "approver_id": approver_id,
              "reason": "test_rejected_fields_are_refused"}))["data"]
    assert raised["pending_approval"] is True
    return raised["request"]["id"]


def _approve(request):
    _need(request.getfixturevalue("me"), "approvals:write")
    client = request.getfixturevalue("client")
    request_id = _a_pending_request(request, raised_by_the_suite=False)
    path = f"/api/v1/approvals/{request_id}"
    return {
        "send": lambda extra: client.post(f"{path}/approve", json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": None,
    }


def _reject(request):
    """The one row whose smallest acceptable body is not empty.

    `reason` is REQUIRED on a rejection — the person who asked sees it — so
    the refused key rides beside a real one here, which is the create-shaped
    case rather than the PATCH-shaped one.
    """
    _need(request.getfixturevalue("me"), "approvals:write")
    client = request.getfixturevalue("client")
    request_id = _a_pending_request(request, raised_by_the_suite=False)
    path = f"/api/v1/approvals/{request_id}"
    return {
        "send": lambda extra: client.post(
            f"{path}/reject",
            json={"reason": "test_rejected_fields_are_refused", **extra}),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": None,
    }


def _withdraw(request):
    client = request.getfixturevalue("client")
    request_id = _a_pending_request(request, raised_by_the_suite=True)
    path = f"/api/v1/approvals/{request_id}"
    return {
        "send": lambda extra: client.post(f"{path}/withdraw", json=extra),
        "read": lambda: assert_envelope_ok(client.get(path))["data"],
        "good": None,
    }


_ROUTES = [
    ("POST /assets", _post_asset),
    ("PATCH /assets/<id>", _patch_asset),
    ("POST /assets/<id>/approve-disposal", _approve_disposal),
    ("POST /locations", _post_location),
    ("PATCH /locations/<id>", _patch_location),
    ("POST /requests", _post_request),
    ("PATCH /requests/<id>", _patch_request),
    ("POST /asset-categories", _post_category),
    ("PATCH /asset-categories/<id>", _patch_category),
    ("PATCH /settings/branding", _patch_branding),
    ("PATCH /settings/depreciation", _patch_depreciation),
    # Handoff 35 — the three decisions on an approval request. They take a
    # body of exactly one field (`reason`), which is the smallest a route can
    # have and still have an allow-list, and that is precisely why they
    # belong here: a route whose `writable` is one name is the easiest one to
    # write with no refusal at all.
    ("POST /approvals/<id>/approve", _approve),
    ("POST /approvals/<id>/reject", _reject),
    ("POST /approvals/<id>/withdraw", _withdraw),
]
_PATCH_ROUTES = [row for row in _ROUTES if row[0].startswith("PATCH ")]
_CREATE_ROUTES = [row for row in _ROUTES
                  if row[0] in ("POST /assets", "POST /locations",
                                "POST /requests", "POST /asset-categories")]


def test_the_table_is_the_fourteen_routes():
    """Non-vacuity for the parametrisation below: fourteen rows, none twice.

    The ruling named ten. The eleventh is `POST /asset-categories` — see
    `_post_category` for how a count made by searching for `_warnings`
    could not have found a route that never wrote one. Twelve, thirteen and
    fourteen are handoff 35's three decisions on an approval request, added
    when they were added rather than after somebody noticed.

    **This is the number of routes that take a body of FIELDS and are
    reached the same way.** Handoff 32 closed two more doors of a different
    shape — `POST /home/quick-submit`, whose refusal comes back through a
    delegate written to answer a browser, and `POST /integrations/sap/
    employee-sync`, an action endpoint answering 200 with no record to read
    back — so the per-route properties below (a good field to send beside
    the bad one, a record to GET afterwards) have no meaning for them. They
    are in `tests/test_the_twelfth_door.py`, held to the same shared
    `assert_fields_refused` contract. **The complete census of routes that
    take a body is `myservice_api/tests/test_published_names_resolve.py`,
    which is the one that fails when a new route appears.** This number is
    not it, and it has never been it.
    """
    assert len(_ROUTES) == 14
    assert len({label for label, _ in _ROUTES}) == 14
    assert len(_PATCH_ROUTES) == 6 and len(_CREATE_ROUTES) == 4


@pytest.mark.parametrize("label,build", _ROUTES,
                         ids=[label for label, _ in _ROUTES])
def test_a_field_the_route_does_not_accept_is_refused_and_nothing_is_written(
        request, label, build):
    """One answer on all ten, and the answer is for the whole request.

    For a PATCH the refused key is sent ALONE, which is also the case that
    used to be the quietest defect of the lot: a PATCH whose every field was
    refused passed the empty-body check, wrote nothing, and answered 200 —
    typed, saved, unchanged, no message.

    For a create the refused key rides beside the fields the route requires,
    so the body is one the route would otherwise accept; "nothing written"
    is then that no record of that name exists.

    `approve-disposal` reads no body at all, so ANY key is refused and
    `writable` is the empty list: the repair is to send nothing.
    """
    row = build(request)
    before = row["read"]()

    details = assert_fields_refused(row["send"]({_KEY: 1}), _KEY)

    assert details["rejected_fields"] == [_KEY]
    if row.get("reads_no_body"):
        assert details["writable"] == [], (
            "this route reads no body; a non-empty `writable` tells the "
            "caller there is something it could have sent")
    else:
        assert details["writable"], (
            "`details.writable` is empty, so the caller is told what it got "
            "wrong and not what would be right")
        assert all(isinstance(k, str) and k for k in details["writable"])
    assert "hint" not in details, (
        "`hint` is advice about `stage_id` on PATCH /requests; it rode on "
        f"{label} for {_KEY!r}: {details['hint']!r}")

    assert row["read"]() == before, (
        f"{label} answered 400 and still changed what it was pointed at")


@pytest.mark.parametrize("label,build", _CREATE_ROUTES,
                         ids=[label for label, _ in _CREATE_ROUTES])
def test_the_same_create_without_the_refused_key_creates_exactly_one(
        request, label, build):
    """The CONTROL for every "created nothing" above.

    `ids_matching` proves a refused create left no record only if it WOULD
    have found one. So the same body, same unique name, is sent twice: with
    the refused key it must leave nothing to find, and without it must leave
    exactly one — found by the same search.
    """
    row = build(request)
    assert row["read"]() == []
    assert_fields_refused(row["send"]({_KEY: 1}), _KEY)
    assert row["read"]() == []
    created = assert_envelope_ok(row["send"]({}), row["created_status"])
    assert row["read"]() == [created["data"]["id"]]


@pytest.mark.parametrize("label,build", _PATCH_ROUTES,
                         ids=[label for label, _ in _PATCH_ROUTES])
def test_a_body_that_mixes_a_good_field_and_a_refused_one_writes_neither(
        request, label, build):
    """Refused WHOLE — the half of the change that is easiest to get wrong.

    Handoff 30 had it the other way on purpose: *refused, not rejected
    whole*, so the writable field beside a refused one still landed. It was
    reversed because of what the caller does next. Told 400, it fixes the
    body and sends ALL of it again; told 200, it never learns that half of
    what it sent was dropped. And `err()` is a response, not a rollback
    (CLAUDE.md) — so this is only true if the route refuses BEFORE it
    writes, which is what is proved here by reading.

    The good half is proved good: sent ALONE, afterwards, it lands. Without
    that, a `good` value the route would have refused anyway makes the first
    half pass for the wrong reason. The two settings rows put back what that
    second call changed.
    """
    row = build(request)
    field, value = row["good"]
    before = row["read"]()
    assert before.get(field) != value, (
        f"the fixture already holds {value!r} in `{field}`, so an unwanted "
        "write would be invisible")
    try:
        assert_fields_refused(row["send"]({field: value, _KEY: 1}), _KEY)
        after = row["read"]()
        assert after == before, (
            f"{label} refused the request and wrote `{field}` anyway: "
            f"{before.get(field)!r} → {after.get(field)!r}")

        assert_envelope_ok(row["send"]({field: value}))
        assert row["read"]()[field] == value, (
            f"`{field}` sent alone did not land either, so the comparison "
            "above proved nothing about the refusal")
    finally:
        if "restore" in row:
            assert_envelope_ok(row["restore"](before))


def test_a_patch_whose_every_field_is_refused_names_them_all_in_order(
        client, an_asset):
    """Two refused keys and nothing else — the body that used to be a 200.

    `rejected_fields` is every key, in the order sent: a caller mapping its
    own schema onto ours repairs all of them from one response, rather than
    being told about one per round trip.
    """
    path = f"/api/v1/assets/{an_asset['id']}"
    before = assert_envelope_ok(client.get(path))["data"]
    r = client.patch(path, json={"building_id": 1, _KEY: "x"})
    details = assert_fields_refused(r, "building_id", _KEY)
    assert details["rejected_fields"] == ["building_id", _KEY]
    assert assert_envelope_ok(client.get(path))["data"] == before


def test_an_empty_patch_is_still_its_own_refusal(client, an_asset):
    """Not the same 400. Nothing was refused, because nothing was sent — and
    a `rejected_fields: []` would tell a caller to go looking for a bad key
    in a body that has none."""
    r = client.patch(f"/api/v1/assets/{an_asset['id']}", json={})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "rejected_fields" not in (body["error"].get("details") or {})


# ─── the hint ────────────────────────────────────────────────────────

def test_the_stage_hint_is_given_for_stage_id_and_for_nothing_else(
        client, a_request):
    """`details.hint` is advice about ONE field.

    Before handoff 31 it rode on every rejection PATCH /requests made,
    whatever was rejected — so a caller that misspelt `priority` was told to
    use the transition route. Present when `stage_id` is among the refused,
    alone or not; absent otherwise.
    """
    path = f"/api/v1/requests/{a_request['id']}"
    before = assert_envelope_ok(client.get(path))["data"]

    alone = assert_fields_refused(
        client.patch(path, json={"stage_id": 99}), "stage_id")
    assert "/transition" in alone["hint"]
    assert "stage_id" not in alone["writable"]

    among = assert_fields_refused(
        client.patch(path, json={_KEY: 1, "stage_id": 99}), _KEY, "stage_id")
    assert "/transition" in among["hint"]

    other = assert_fields_refused(client.patch(path, json={_KEY: 1}), _KEY)
    assert "hint" not in other, (
        f"a caller that sent {_KEY!r} was given advice about `stage_id`: "
        f"{other['hint']!r}")

    assert assert_envelope_ok(client.get(path))["data"] == before


def test_what_a_request_says_it_accepts_is_published_and_is_accepted(
        client, a_request):
    """`details.writable` is a promise, so it is checked from both sides.

    Every key in it is in the published request schema — POST's or PATCH's;
    one allow-list serves both routes — so the list cannot name something a
    reader of the contract has never heard of. And it is TRUE: the scalar
    keys among them are sent back, one PATCH, and none is refused. Foreign
    keys are left out of the second half only because a valid id is a fact
    about the tenant, not about the route.
    """
    path = f"/api/v1/requests/{a_request['id']}"
    writable = assert_fields_refused(
        client.patch(path, json={_KEY: 1}), _KEY)["writable"]

    spec = client.get("/api/v1/openapi.json").json()
    published = set()
    for route, method in (("/api/v1/requests", "post"),
                          ("/api/v1/requests/{id}", "patch")):
        schema = (spec["paths"][route][method]["requestBody"]["content"]
                  ["application/json"]["schema"])
        published |= set(schema.get("properties") or {})
    unpublished = sorted(set(writable) - published)
    assert not unpublished, (
        f"`details.writable` names {unpublished}, which neither request "
        "schema in openapi.json publishes")

    scalars = {"priority": "3", "impact": "1", "urgency": "1",
               "kanban_state": "normal",
               "response_text": "<p>test_rejected_fields_are_refused</p>",
               "deadline_date": "2030-01-31"}
    sendable = {k: v for k, v in scalars.items() if k in writable}
    assert len(sendable) >= 3, (
        f"only {sorted(sendable)} of the scalar keys are listed as writable; "
        "the second half of this test would prove almost nothing")
    r = client.patch(path, json=sendable)
    if r.status_code == 400:
        refused = (r.json()["error"].get("details") or {}).get(
            "rejected_fields")
        assert not refused, (
            f"{refused} listed in `details.writable` and refused when sent")
    assert_envelope_ok(r)


# ─── a refusal does not burn the key ─────────────────────────────────

def test_a_refused_create_does_not_burn_its_idempotency_key(
        client, test_location):
    """The sequence Vendra needs: fix the mapper, deliver again under the
    SAME key, and it lands.

    Only a SUCCESS is stored under an `X-Idempotency-Key`. So a refused
    request is evaluated afresh each time — the second 400 is a new answer
    with a new `request_id`, not a replay — and the corrected body under the
    same key is processed, creates the asset, and from then on IS replayed.

    This is the defect §B was ruled to close, from the other side. When the
    lenient answer was a 201, the key pinned it: every retry replayed the
    same incomplete asset, and the only repair was by hand.
    """
    key = _uniq("pytest-refused-idem")
    name = _uniq("pytest-refused-idem-asset")
    good = {"name": name, "category_id": 1,
            "location_id": test_location["id"]}
    headers = {"X-Idempotency-Key": key}

    first = client.post("/api/v1/assets", json={**good, _KEY: 1},
                        headers=headers)
    assert_fields_refused(first, _KEY)
    second = client.post("/api/v1/assets", json={**good, _KEY: 1},
                         headers=headers)
    assert_fields_refused(second, _KEY)
    assert (second.json()["error"]["request_id"]
            != first.json()["error"]["request_id"]), (
        "the second 400 is a replay of the first, so a refusal IS stored "
        "under the key — and the corrected body below will be answered "
        "with it")
    assert ids_matching(client, "/api/v1/assets", name) == []

    landed = assert_envelope_ok(
        client.post("/api/v1/assets", json=good, headers=headers), 201)
    replay = assert_envelope_ok(
        client.post("/api/v1/assets", json=good, headers=headers), 201)
    assert replay["data"]["id"] == landed["data"]["id"]
    assert replay["meta"]["request_id"] == landed["meta"]["request_id"], (
        "the fourth call was processed rather than replayed")
    assert ids_matching(client, "/api/v1/assets", name) == [
        landed["data"]["id"]], "one key, one asset"


# ─── the old shape is gone ───────────────────────────────────────────

def test_a_clean_write_carries_no_warnings_block(client, test_location):
    """`data._warnings.rejected_fields` no longer exists — not even empty.

    An empty block on every success would keep alive the idea that a success
    might carry refusals, and a consumer written against the old contract
    would go on checking it and go on finding nothing. `_warnings.truncated`
    on lists and `_warnings.discarded_fields` on the workflow callback are
    other things and are untouched.
    """
    created = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-refused-clean"), "category_id": 1,
        "location_id": test_location["id"]}), 201)["data"]
    assert "_warnings" not in created
    patched = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{created['id']}", json={"notes": "clean"}))["data"]
    assert "_warnings" not in patched
