"""A warranty on an asset, over the API — handoff 34.

The model's rules are proved in `myservice_asset_register/tests/
test_warranty.py`. What is proved HERE is what an integration sees, and in
particular what Vendra is gated on:

  * the five keys are ACCEPTED on `POST /assets` and published in
    `openapi.json` — the sentence in the report that opens Vendra's side;
  * the published block can be sent back as it was read, because a
    read-edit-write round trip being refused is the defect handoff 33 §B2
    is about;
  * the answer AND the working — `basis` says how the expiry was reached;
  * three filter states, not two, and each returns rows that publish it;
  * *expiring soon* is a window of Lagos days that never includes an
    expired warranty;
  * a change is an append-only history event, and a warranty moves nothing
    about the asset's state or condition.
"""
import datetime
import time

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

#: The keys a caller may write, all of them published inside `warranty`
#: under the same names.
WRITABLE = ("warranty_expiry", "warranty_start_date", "warranty_months",
            "warrantor", "warranty_reference")

#: The keys `warranty` carries that are the server's, not the caller's.
DERIVED = ("status", "status_as_of", "basis")


def _lagos_today():
    """The server's day: UTC+1, the definition `snapshot_today` uses."""
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)).date()


def _iso(day):
    return day.isoformat()


def _new(client, name, **extra):
    """An asset ON THE REGISTER whichever way the receipt switch is set
    (handoff 58 §2) — the warranty filters read the register, which with the
    gates on hides a receipt until `tests/gates.py` walks it onto it."""
    body = {"name": name, "category_id": 1}
    body.update(extra)
    return gates.new_registered_asset(client, **body)


def _get(client, asset_id):
    return assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}"))["data"]


def _ids(client, **params):
    params.setdefault("limit", 200)
    body = assert_envelope_ok(client.get("/api/v1/assets", params=params))
    return [row["id"] for row in body["data"]], body


@pytest.fixture(scope="module")
def marker():
    return f"pytest-warranty-{int(time.time())}"


# ─── the gate Vendra opens on ────────────────────────────────────────

def test_openapi_advertises_the_warranty_keys_on_create(client):
    """Vendra decides whether to send warranty fields by reading this, the
    same way it decided for provenance: a Cadra that does not publish them
    would refuse them with a 400 and every receipt would dead-letter."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200, f"openapi.json unavailable: {r.status_code}"
    spec = r.json()
    create = spec["paths"]["/api/v1/assets"]["post"]
    props = (create["requestBody"]["content"]["application/json"]
             ["schema"]["properties"])
    for key in WRITABLE:
        assert key in props, f"`{key}` is not advertised on POST /assets"
    schemas = spec["components"]["schemas"]
    assert "warranty" in schemas["Asset"]["properties"]
    assert set(schemas["AssetWarranty"]["properties"]) == \
        set(WRITABLE) | set(DERIVED)


# ─── the answer and the working ──────────────────────────────────────

def test_a_duration_and_a_start_derive_the_expiry(client, marker):
    asset = _new(client, f"{marker}-derived",
                 warranty_start_date="2026-03-12", warranty_months=24,
                 warrantor="Dell Nigeria Ltd",
                 warranty_reference="DL-WC-55120")
    w = asset["warranty"]
    assert w["warranty_expiry"] == "2028-03-12"
    assert w["warranty_start_date"] == "2026-03-12"
    assert w["warranty_months"] == 24
    assert w["warrantor"] == "Dell Nigeria Ltd"
    assert w["warranty_reference"] == "DL-WC-55120"
    assert w["basis"] == "24 months from 2026-03-12"
    assert w["status_as_of"] == _iso(_lagos_today())
    # The older published spelling reads the same column, unchanged.
    assert asset["dates"]["warranty_expiry"] == "2028-03-12"


def test_no_warranty_is_said_as_none_not_as_expired(client, marker):
    w = _new(client, f"{marker}-none")["warranty"]
    assert w["status"] == "none"
    assert w["basis"] is None
    assert all(w[k] is None for k in WRITABLE)


def test_a_bare_date_says_it_had_no_basis(client, marker):
    w = _new(client, f"{marker}-bare", warranty_expiry="2030-01-31")["warranty"]
    assert w["warranty_expiry"] == "2030-01-31"
    assert w["warranty_months"] is None
    assert w["basis"].startswith("Entered as an expiry date")


def test_a_contradicting_expiry_is_refused_and_nothing_is_written(
        client, marker):
    asset = _new(client, f"{marker}-contradict",
                 warranty_start_date="2026-03-12", warranty_months=24)
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "warranty_months": 36, "warranty_expiry": "2031-01-01"})
    assert_envelope_err(r, 400, "validation_failed")
    after = _get(client, asset["id"])["warranty"]
    assert (after["warranty_months"], after["warranty_expiry"]) == \
        (24, "2028-03-12"), "a refused write changed the record"


@pytest.mark.parametrize("body", [
    {"warranty_months": 24},
    {"warranty_start_date": "2026-03-12"},
    {"warranty_start_date": "2026-03-12", "warranty_months": 0},
    {"warranty_start_date": "2026-03-12", "warranty_months": 601},
    {"warranty_start_date": "2026-03-12", "warranty_months": 24.5},
])
def test_half_a_basis_or_a_bad_duration_is_refused(client, marker, body):
    r = client.post("/api/v1/assets", json=gates.receipt_body(
        client, **dict(body, name=f"{marker}-refused", category_id=1)))
    assert_envelope_err(r, 400, "validation_failed")


def test_the_published_block_can_be_sent_back_as_read(client, marker):
    """GET, edit, PATCH the same keys: nothing refused. The derived three
    are the server's and are left out, as any read-only key is."""
    asset = _new(client, f"{marker}-roundtrip",
                 warranty_start_date="2026-01-01", warranty_months=12,
                 warrantor="HP")
    block = _get(client, asset["id"])["warranty"]
    body = {k: v for k, v in block.items() if k not in DERIVED}
    assert set(body) == set(WRITABLE)
    body["warranty_months"] = 36
    body.pop("warranty_expiry")    # it would contradict the new duration
    w = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json=body))["data"]["warranty"]
    assert w["warranty_expiry"] == "2029-01-01"
    # And the whole block unchanged, expiry included, is accepted as is.
    same = {k: v for k, v in w.items() if k not in DERIVED}
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json=same))


# ─── three states, and the window ────────────────────────────────────

def test_each_status_filter_returns_only_rows_that_publish_it(
        client, marker):
    today = _lagos_today()
    under = _new(client, f"{marker}-f-under",
                 warranty_expiry=_iso(today))
    expired = _new(client, f"{marker}-f-expired",
                   warranty_expiry=_iso(today - datetime.timedelta(days=1)))
    none = _new(client, f"{marker}-f-none")
    expected = {"under_warranty": under["id"], "expired": expired["id"],
                "none": none["id"]}
    for status, mine in expected.items():
        ids, body = _ids(client, warranty_status=status, q=f"{marker}-f-")
        assert ids == [mine], (status, ids)
        # Unnarrowed, every row on the page publishes what it was filtered
        # on — and the count is of that same query.
        _, page = _ids(client, warranty_status=status, limit=50)
        assert {row["warranty"]["status"] for row in page["data"]} <= {status}


def test_expiring_soon_is_a_window_of_days_never_an_expired_one(
        client, marker):
    today = _lagos_today()
    soon = _new(client, f"{marker}-w-soon",
                warranty_expiry=_iso(today + datetime.timedelta(days=10)))
    today_row = _new(client, f"{marker}-w-today", warranty_expiry=_iso(today))
    gone = _new(client, f"{marker}-w-gone",
                warranty_expiry=_iso(today - datetime.timedelta(days=1)))
    ids, _ = _ids(client, warranty_expires_within_days=30, q=f"{marker}-w-")
    assert sorted(ids) == sorted([soon["id"], today_row["id"]])
    ids, _ = _ids(client, warranty_expires_within_days=5, q=f"{marker}-w-")
    assert ids == [today_row["id"]]
    ids, _ = _ids(client, warranty_expires_within_days=3650, q=f"{marker}-w-")
    assert gone["id"] not in ids


@pytest.mark.parametrize("params", [
    {"warranty_status": "Expired"},
    {"warranty_status": "null"},
    {"warranty_expires_within_days": "0"},
    {"warranty_expires_within_days": "3651"},
    {"warranty_expires_within_days": "soon"},
    {"warranty_expires_within_days": "null"},
])
def test_a_bad_warranty_filter_is_a_400_not_the_whole_register(
        client, params):
    assert_envelope_err(client.get("/api/v1/assets", params=params),
                        400, "invalid_request")


# ─── a change is recorded; the asset's health is not touched ─────────

def test_a_warranty_change_is_an_append_only_history_event(client, marker):
    asset = _new(client, f"{marker}-event",
                 warranty_start_date="2026-03-12", warranty_months=24)
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"warranty_months": 36}))
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}/history"))["data"]
    changed = [e for e in history["events"]
               if e["type"] == "warranty_changed"]
    fields = {c["field"]: (c["old"], c["new"])
              for e in changed for c in e["detail"]["changes"]}
    assert fields == {"warranty_months": ("24", "36"),
                      "warranty_expiry": ("2028-03-12", "2029-03-12")}
    assert {e["evidence"] for e in changed} == {"append_only"}


def test_an_expired_warranty_moves_nothing_about_the_asset(client, marker):
    asset = _new(client, f"{marker}-health", condition="good",
                 state="active")
    after = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"warranty_expiry": "2001-01-01"}))["data"]
    assert after["warranty"]["status"] == "expired"
    assert (after["state"], after["condition"], after["is_verified"]) == \
        (asset["state"], asset["condition"], asset["is_verified"])
