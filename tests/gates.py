"""An asset ON THE REGISTER, whichever way the tenant's switch is set.

Handoff 58 §2 — THE one helper, named in `docs/DECISIONS.md` (2026-10-12).
With the receipt gates on (`cadra.receipt.gated`), `POST /api/v1/assets`
answers a CANDIDATE: `captured`, no label, hidden from every list. A test
that is ABOUT an asset already on the register therefore gets one by
walking it through the seven gates — over HTTP, as seven different people,
because the no-two-gates rule (Addendum A §4) refuses one credential at the
second gate — exactly as a real unit gets there. With the switch off the
same calls are no-ops and every test sees what it always saw.

Three entry points, and only these (plus `receipt_body`, the body
`receive` would send, for a test that must make the call itself):

* `receive(client, **body)` — `POST /assets` as INT-03 makes it. With the
  gates on, a serial-mode class needs a serial and its mandatory attributes
  (Section 12); the helper supplies unique ones when the test did not,
  because a test about something else must not fail at the door. With the
  switch off the body goes as given.
* `on_the_register(client, asset)` — drives the gates from wherever the unit
  is to `registered` and returns the asset as it now stands.
* `ready_to_affix(client, asset)` — drives it to `tag_issued`: the one state
  in which a label is issued and not yet on the unit, which is what a test
  ABOUT affixing needs. Switch off, a new asset is already there.

The seven people are the demo personas (`docs/api/.personas.<tenant>`,
handoff 46 / 57): storekeeper submits, IAD officer verifies, IAD approver
approves, Asset Controller requests the tag, tagger affixes, Register Maker
registers, Register Checker approves. A tenant without the file cannot be
tested with the gates on, and the helper FAILS saying so — never skips: a
skip would turn a switch-on run green by proving nothing.
"""
import pathlib
import time
import uuid

import pytest
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Persona key per gate, in the order the chain fires them.
CREW = (
    ("submit", "storekeeper"),
    ("verify", "iad_officer"),
    ("approve", "iad_approver"),
    ("request-tagging", "asset_controller"),
    ("affix", "tagger"),
    ("register", "register_maker"),
    ("approve-registration", "register_checker"),
)
#: The state each gate moves a unit FROM, so the walk starts where it is.
_FROM = {
    "captured": 0, "vfm_pending": 1, "vfm_verified": 2, "vfm_approved": 3,
    "tag_requested": 4, "tag_issued": 4, "tagged": 5, "reg_submitted": 6,
}

_tokens = {}


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def receipt_gated(client):
    """The tenant's switch, read now — tests turn it on and off."""
    r = client.get("/api/v1/settings")
    assert r.status_code == 200, r.text[:300]
    return bool(r.json()["data"].get("receipt_gated"))


def _class_needs(client, category_id):
    """`(mode, mandatory)` for a category, from the published schema."""
    rows = client.get("/api/v1/asset-categories").json()["data"]
    for row in rows:
        if row["id"] == category_id:
            return (row.get("identification_mode") or "serial",
                    (row.get("class_attributes_schema") or {}).get(
                        "mandatory", []))
    return "serial", []


def receipt_body(client, **body):
    """The body `receive` sends, without sending it.

    For a test that must make the call itself — under an idempotency key, in
    a race, or expecting a REFUSAL. The last is the one that matters: with
    the gates on, a body missing its serial is refused 400
    `validation_failed` at the door, which is the same status and code most
    refusal tests assert — so a refusal test sending a bare body would pass
    for the wrong reason. Filled in, the refusal it gets is the one it is
    about. Switch off: the body as given, plus the default category."""
    body.setdefault("category_id", 1)
    if receipt_gated(client):
        mode, mandatory = _class_needs(client, body["category_id"])
        if mode == "serial":
            body.setdefault("serial_number", _uniq("SN58"))
        for field in mandatory:
            body.setdefault(field, _uniq(field)[:40])
    return body


def receive(client, *, expected_status=201, **body):
    """`POST /api/v1/assets`, filled in for the gates when they are on."""
    body = receipt_body(client, **body)
    r = client.post("/api/v1/assets", json=body)
    assert r.status_code == expected_status, (
        f"POST /assets: HTTP {r.status_code} {r.text[:400]}")
    return r.json()["data"]


def _personas_file(client):
    host = client.base.split("//", 1)[-1].split(":", 1)[0]
    tenant = host.split(".")[0]
    return REPO_ROOT / "docs" / "api" / f".personas.{tenant}"


def _token(client, key):
    cache = (client.base, key)
    if cache in _tokens:
        return _tokens[cache]
    path = _personas_file(client)
    if not path.exists():
        pytest.fail(
            f"The receipt gates are ON on this tenant and {path} does not "
            "exist, so nothing can walk a unit through them: the chain needs "
            "seven different people. Seed the demo personas "
            "(`scripts/demo_personas.sh <db>`) or turn the switch off.")
    for line in path.read_text().splitlines():
        parts = line.split()
        if line.startswith("#") or len(parts) != 3 or parts[0] != key:
            continue
        r = requests.post(f"{client.base}/api/v1/auth/login",
                          json={"login": parts[1], "password": parts[2]},
                          timeout=20)
        assert r.status_code == 200, (
            f"persona {key} could not sign in: {r.status_code} {r.text[:300]}")
        _tokens[cache] = r.json()["data"]["access_token"]
        return _tokens[cache]
    pytest.fail(f"{path} has no `{key}` persona — the gates need one.")


def _as(client, key, method, path, body=None):
    r = requests.request(
        method, f"{client.base}/api/v1{path}", json=body, timeout=60,
        headers={"Authorization": f"Bearer {_token(client, key)}",
                 "Accept": "application/json"})
    return r


def _fire(client, asset, action, key, until):
    asset_id = asset["id"]
    if action == "affix":
        tag = asset["tagging"]["tag_number"]
        body = {"tag_number": tag}
        if asset.get("identification_mode") == "tag_id":
            body["attributes_confirmed"] = True
        elif asset.get("serial_number"):
            body["serial_number"] = asset["serial_number"]
        r = _as(client, key, "POST", f"/assets/{asset_id}/tag-affixed", body)
    else:
        body = {}
        if action == "verify":
            body = {"checklist": {"quantity": True, "specification": True,
                                  "condition": True, "price": True},
                    "attachments": [{"name": "sighted.txt",
                                     "data": "c2lnaHRlZA=="}]}
        elif action == "register":
            # The unit's OWN cost, when it has one: the Register Maker's
            # figure is written onto `acquisition_cost`, and a test that
            # created an asset at a cost (depreciation) must not find the
            # walk has restated it. 1000.0 only for a unit with none.
            own_cost = (asset.get("financial") or {}).get("acquisition_cost")
            body = {"sap_asset_code": _uniq("SAP58")[:30],
                    "cost": own_cost if own_cost and own_cost > 0 else 1000.0,
                    "cost_centre": "CC-58",
                    "capitalisation_date": time.strftime("%Y-%m-%d"),
                    "asset_class": asset["category"]["id"]
                    if isinstance(asset.get("category"), dict)
                    else asset.get("category_id") or 1}
        r = _as(client, key, "POST", f"/assets/{asset_id}/gates/{action}",
                body)
    assert r.status_code == 200, (
        f"gate {action} as {key} on asset {asset_id} (walking to {until}): "
        f"HTTP {r.status_code} {r.text[:400]}")
    got = client.get(f"/api/v1/assets/{asset_id}")
    assert got.status_code == 200, got.text[:300]
    return got.json()["data"]


def _walk(client, asset, until):
    state = asset.get("register_state") or "registered"
    if state == "registered" or state == until:
        return asset
    assert state in _FROM, f"cannot walk a unit at {state!r} to {until}"
    for action, key in CREW[_FROM[state]:]:
        asset = _fire(client, asset, action, key, until)
        if asset["register_state"] == until:
            return asset
    assert asset["register_state"] == until, asset["register_state"]
    return asset


def on_the_register(client, asset):
    """The asset, registered. A no-op for a registered asset."""
    return _walk(client, asset, "registered")


def ready_to_affix(client, asset):
    """The asset with a label issued and not yet affixed. A no-op for a
    registered asset (switch off: its label is issued at creation)."""
    if asset.get("register_state") in (None, "registered"):
        return asset
    return _walk(client, asset, "tag_issued")


def new_registered_asset(client, **body):
    """`receive` then `on_the_register` — the usual fixture."""
    return on_the_register(client, receive(client, **body))


#: What a disposal is made of — the keys a receipt may not carry with the
#: gates on (handoff 58, P5: a unit not on the register cannot be disposed
#: of, at creation included), recorded once the unit is registered instead.
DISPOSAL_KEYS = ("state", "disposal_date", "disposal_reason",
                 "disposal_method", "disposal_reference", "disposal_proceeds",
                 "condition")


def disposed_on_the_register(client, **body):
    """A disposed asset ON THE REGISTER, whichever way the switch is set.

    Switch off: ONE `POST /assets` carrying the disposal, exactly what the
    fixtures always sent. Switch on: received without it, walked through
    the gates, then disposed by `PATCH` — the only order the register now
    allows. Returns the asset as it then stands."""
    if not receipt_gated(client):
        return receive(client, **body)
    disposal = {k: body.pop(k) for k in DISPOSAL_KEYS if k in body}
    asset = new_registered_asset(client, **body)
    r = client.patch(f"/api/v1/assets/{asset['id']}", json=disposal)
    assert r.status_code == 200, (
        f"PATCH /assets/{asset['id']} (the disposal): HTTP {r.status_code} "
        f"{r.text[:400]}")
    return r.json()["data"]
