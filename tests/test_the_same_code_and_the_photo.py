"""Handoff 61 over HTTP — everything that is not the reprint, the photos or
the room codes (those have their own files).

* §0b ruling 1 — IAD's evidence is read by IAD, the Register Maker and
  Checker and the Auditor (`evidence:read`); the Store Officer is told the
  count and refused the file. Driven as each persona. (Vendra's own secret
  is not on this machine; a credential with Vendra's exact scopes is driven
  in-registry, `myservice_api/tests/test_the_same_code_and_the_photo.py`.)
* §0b ruling 5 — *Submit selected* and *Request tagging for selected*: N
  single fires, a refused unit rolling back nothing, `dry_run` a rollback,
  receipts mixed.
* §2 (R10) — a candidate is refused verify, mark-missing, mark-found and
  condemn with `not_on_the_register`, and PATCH cannot give it a status or a
  verification date; nothing is written.
* §3 (R9) — a chair with no brand is received with the gates on.
* §6 — `updated_since`: refused when unreadable, composed with
  `location_id` and `register_state=any`, and a sync across two pages with
  a row changed between them.

Every test that turns the receipt switch puts it back (`gated`).
"""
import time
import uuid

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

SETTINGS_GATE = "/api/v1/settings/receipt-gate"
READERS = ("iad_officer", "iad_approver", "register_maker",
           "register_checker", "auditor")


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def gated(client, admin_scope):
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": True}))
    try:
        yield
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


@pytest.fixture
def ungated(client, admin_scope):
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": False}))
    try:
        yield
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


def _raw(client, key, path):
    """GET as a persona, the raw response (a file route is not JSON)."""
    return requests.get(
        f"{client.base}/api/v1{path}", timeout=60,
        headers={"Authorization": f"Bearer {gates._token(client, key)}"})


# ── §0b ruling 1 — who reads IAD's evidence ──────────────────────────

def test_iads_evidence_is_read_by_its_five_readers_and_counted_for_the_rest(
        client, gated):
    unit = gates._walk(client, gates.receive(client, name=_uniq("pytest-61")), "vfm_verified")
    path = f"/assets/{unit['id']}/evidence"

    # The Store Officer: the count, in words, and nothing that opens a file.
    r = gates._as(client, "storekeeper", "GET", path)
    data = assert_envelope_ok(r)["data"]
    assert data["readable"] is False
    assert data["count"] == 1
    assert data["summary"] == "IAD evidence: 1 item"
    assert data["verifications"] == []
    assert data["requires_scope"] == "evidence:read"

    file_id = None
    for key in READERS:
        data = assert_envelope_ok(gates._as(client, key, "GET", path))["data"]
        assert data["readable"] is True, key
        assert data["count"] == 1, key
        files = data["verifications"][0]["files"]
        assert [f["name"] for f in files] == ["sighted.txt"], key
        file_id = files[0]["id"]
        got = _raw(client, key, f"{path}/{file_id}")
        assert got.status_code == 200, (key, got.status_code, got.text[:300])
        assert got.content == b"sighted", key

    refused = _raw(client, "storekeeper", f"{path}/{file_id}")
    assert refused.status_code == 403, refused.text[:300]
    assert "evidence:read" in refused.text

    # The history keeps what was attested and drops the papers' ids.
    hist = assert_envelope_ok(gates._as(
        client, "storekeeper", "GET", f"/assets/{unit['id']}/history"))
    verify = [e for e in hist["data"]["events"]
              if (e.get("detail") or {}).get("action") == "verify"]
    assert verify, hist["data"]["events"][:3]
    # The same answer as `/evidence`: the count and nothing more.
    assert verify[0]["detail"]["evidence"] == {"attachments": {
        "readable": False, "count": 1, "summary": "IAD evidence: 1 item",
        "requires_scope": "evidence:read"}}


# ── §0b ruling 5 — the two batches ───────────────────────────────────

def _batch(client, key, action, ids, **body):
    return gates._as(client, key, "POST", f"/candidates/gates/{action}",
                     dict(asset_ids=ids, **body))


def _state(client, asset_id):
    r = client.get(f"/api/v1/assets/{asset_id}")
    return assert_envelope_ok(r)["data"]["register_state"]


def test_submit_selected_is_n_single_fires_across_receipts(client, gated):
    a = gates.receive(client, name=_uniq("pytest-61"), grn_reference=_uniq("GRN61A"))
    b = gates.receive(client, name=_uniq("pytest-61"), grn_reference=_uniq("GRN61B"))
    c = gates.receive(client, name=_uniq("pytest-61"), grn_reference=_uniq("GRN61C"))
    gates._fire(client, c, "submit", "storekeeper", "vfm_pending")
    ids = [a["id"], b["id"], c["id"]]

    preview = assert_envelope_ok(_batch(client, "storekeeper", "submit", ids,
                                        dry_run=True))["data"]
    assert preview["dry_run"] is True
    assert [l["outcome"] for l in preview["results"]] == [
        "would_fire", "would_fire", "refused"]
    assert {_state(client, i) for i in ids[:2]} == {"captured"}

    answer = assert_envelope_ok(_batch(client, "storekeeper", "submit",
                                       ids))["data"]
    assert (answer["total"], answer["fired"], answer["refused"]) == (3, 2, 1)
    refused = answer["results"][2]
    # The single route's own answer, from inside the batch.
    single = gates._as(client, "storekeeper", "POST",
                       f"/assets/{c['id']}/gates/submit", {})
    assert refused["status"] == single.status_code == 409
    assert refused["message"] == single.json()["error"]["message"]
    assert [_state(client, i) for i in ids] == ["vfm_pending"] * 3

    # One event per unit, each its own.
    for i in ids[:2]:
        hist = assert_envelope_ok(client.get(f"/api/v1/assets/{i}/history"))
        submits = [e for e in hist["data"]["events"]
                   if (e.get("detail") or {}).get("action") == "submit"]
        assert len(submits) == 1, i


def test_request_tagging_for_selected_is_the_controllers_act(client, gated):
    units = [gates._walk(client, gates.receive(
        client, name=_uniq("pytest-61"), grn_reference=_uniq(f"GRN61T{i}")), "vfm_approved")
        for i in range(2)]
    early = gates.receive(client, name=_uniq("pytest-61"))                 # still captured
    ids = [u["id"] for u in units] + [early["id"]]

    # Not the storekeeper's scope: the whole batch is refused at the door.
    refused = _batch(client, "storekeeper", "request-tagging", ids)
    assert_envelope_err(refused, 403, "forbidden")

    preview = assert_envelope_ok(_batch(
        client, "asset_controller", "request-tagging", ids,
        dry_run=True))["data"]
    assert preview["fired"] == 2 and preview["refused"] == 1
    assert {_state(client, u["id"]) for u in units} == {"vfm_approved"}

    answer = assert_envelope_ok(_batch(
        client, "asset_controller", "request-tagging", ids))["data"]
    assert (answer["fired"], answer["refused"]) == (2, 1)
    assert answer["results"][2]["status"] == 409
    for u in units:
        got = assert_envelope_ok(client.get(f"/api/v1/assets/{u['id']}"))
        got = got["data"]
        assert got["register_state"] == "tag_issued"
        # Each unit's label, under its own asset code (ruling 4.3).
        assert got["tagging"]["tag_number"] == got["asset_code"]


# ── §2 (R10) — not on the register, so not missing from it ───────────

ROUTES_ON_A_CANDIDATE = (
    ("verify", {}),
    ("mark-missing", {"reason": "not on the bay"}),
    ("mark-found", {"reason": "found on the bay"}),
    ("condemn", {"reason": "dropped off the truck"}),
)


def test_a_candidate_is_refused_every_status_route(client, gated):
    unit = gates.receive(client, name=_uniq("pytest-61"))
    assert unit["register_state"] == "captured"
    for route, body in ROUTES_ON_A_CANDIDATE:
        r = client.post(f"/api/v1/assets/{unit['id']}/{route}", json=body)
        err = assert_envelope_err(r, 409, "conflict")["error"]
        assert err["details"]["reason"] == "not_on_the_register", route
        assert "not on the register yet" in err["message"], route
    for patch in ({"state": "missing"}, {"state": "in_repair"},
                  {"last_verified_date": time.strftime("%Y-%m-%d")}):
        r = client.patch(f"/api/v1/assets/{unit['id']}", json=patch)
        err = assert_envelope_err(r, 409, "conflict")["error"]
        assert err["details"]["reason"] == "not_on_the_register", patch
    after = assert_envelope_ok(client.get(f"/api/v1/assets/{unit['id']}"))
    after = after["data"]
    assert after["state"] == "active"
    assert after["register_state"] == "captured"
    assert not (after.get("dates") or {}).get("last_verified_date")


def test_a_registered_asset_is_still_verified_and_marked(client):
    asset = gates.new_registered_asset(client, name=_uniq("pytest-61"))
    assert_envelope_ok(client.post(f"/api/v1/assets/{asset['id']}/verify",
                                   json={}))
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/mark-missing",
        json={"reason": "not at its desk"}))


# ── §3 (R9) — a chair with no brand ──────────────────────────────────

def _tag_id_class(client):
    rows = assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]
    for row in rows:
        if row["identification_mode"] == "tag_id" and \
                row["class_attributes_schema"]["mandatory"] == [
                    "name", "colour", "material", "dimensions"]:
            return row
    pytest.fail("no tag_id class on the default schema on this tenant: "
                f"{[(r['name'], r['identification_mode']) for r in rows if r['identification_mode'] == 'tag_id']}")


def test_the_default_tag_id_schema_has_no_make_or_model(client):
    row = _tag_id_class(client)
    assert "make" not in row["class_attributes_schema"]["mandatory"]
    assert "model_name" not in row["class_attributes_schema"]["mandatory"]


def test_a_chair_with_no_brand_is_received_with_the_gates_on(client, gated):
    row = _tag_id_class(client)
    r = client.post("/api/v1/assets", json={
        "name": _uniq("pytest-61-chair"), "category_id": row["id"],
        "colour": "Grey", "material": "Fabric",
        "dimensions": "55x55x90 cm"})
    data = assert_envelope_ok(r, 201)["data"]
    assert data["register_state"] == "captured"
    assert data["identification_mode"] == "tag_id"
    assert not data.get("make")


# ── §6 — the sync filter ─────────────────────────────────────────────

def test_updated_since_refuses_what_it_cannot_read(client):
    for raw in ("yesterday", "2026-13-01", "15/10/2026", "null"):
        r = client.get("/api/v1/assets", params={"updated_since": raw})
        err = assert_envelope_err(r, 400, "invalid_request")["error"]
        assert err["details"]["updated_since"] == raw
        assert "ISO-8601" in err["message"]


def test_updated_since_in_the_future_is_empty_not_everything(client):
    r = client.get("/api/v1/assets",
                   params={"updated_since": "2999-01-01T00:00:00Z"})
    body = assert_envelope_ok(r)
    assert body["data"] == []
    assert body["pagination"]["total_estimate"] == 0


def _server_now(client):
    return assert_envelope_ok(client.get("/api/v1/assets",
                                         params={"limit": 1}))["meta"][
        "timestamp"]


def _sync(client, since, location_id, between=None):
    """One sync pass, two rows a page, as a client pages it. `between` runs
    once, after the first page. Returns (ids in order, pages, the first
    page's `meta.timestamp`)."""
    params = {"updated_since": since, "location_id": location_id, "limit": 2}
    ids, pages, started = [], 0, None
    while True:
        body = assert_envelope_ok(client.get("/api/v1/assets", params=params))
        started = started or body["meta"]["timestamp"]
        ids += [a["id"] for a in body["data"]]
        pages += 1
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            return ids, pages, started
        params["cursor"] = cursor
        if between and pages == 1:
            between()


def test_a_sync_across_two_pages_catches_a_row_changed_mid_sync(
        client, ungated, test_location):
    t0 = _server_now(client)
    made = [assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq(f"pytest-61-sync-{i}"), "category_id": 1,
        "location_id": test_location["id"]}), 201)["data"]["id"]
        for i in range(3)]
    first = made[0]

    # Mid-sync, between page 1 and page 2, the FIRST row — already behind
    # the cursor — changes.
    ids, pages, started = _sync(
        client, t0, test_location["id"],
        between=lambda: assert_envelope_ok(client.patch(
            f"/api/v1/assets/{first}", json={"notes": "changed mid-sync"})))
    assert pages >= 2
    assert ids == sorted(ids), "a sync pages by id"
    assert [i for i in ids if i in made] == made
    # This pass saw the first row BEFORE its change; the change itself is
    # behind the cursor and was not re-read in this pass.

    # The next sync starts from the FIRST page's `meta.timestamp` (not from
    # the largest `updated_at` seen): it re-reads the row that changed while
    # the last pass was running — and exactly the rows whose own record
    # changed since the pass began. (A new asset's record can be written
    # again a moment after creation by the system itself — an outbound
    # message's delivery state — and that is a change too.)
    again, _, _ = _sync(client, started, test_location["id"])
    assert first in again
    for i in made:
        stamp = assert_envelope_ok(client.get(f"/api/v1/assets/{i}"))[
            "data"]["updated_at"]
        assert (i in again) == (stamp >= started), (i, stamp, started)


def test_updated_since_composes_with_register_state_any(client, gated,
                                                         test_location):
    t0 = _server_now(client)
    unit = gates.receive(client, name=_uniq("pytest-61"))
    plain = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"updated_since": t0, "limit": 100}))
    assert unit["id"] not in [a["id"] for a in plain["data"]]
    anyst = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"updated_since": t0, "limit": 100,
                                  "register_state": "any"}))
    assert unit["id"] in [a["id"] for a in anyst["data"]]
