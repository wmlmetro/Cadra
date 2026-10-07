"""Handoff 57 §6.4 — which routes the register filter reaches, measured.

Reads every list / count / report / export route over assets, receives ONE
candidate with the tenant's switch on, reads them all again. A route that
hides candidates does not move; `/candidates` and `?register_state=any` move
by one. The switch is put back as found.

    CADRA_API_BASE=http://test19.localhost:8069 \
        tests/.venv/bin/python docs/handoffs/57-evidence/register_filter_probe.py
"""
import os
import sys
import time
import uuid

import requests

BASE = os.environ["CADRA_API_BASE"].rstrip("/")
DB = BASE.split("//")[1].split(".")[0]
creds = dict(l.strip().split("=", 1) for l in open(
    "docs/api/.creds.%s" % DB) if "=" in l)
tok = requests.post(BASE + "/api/v1/auth/token", json={
    "client_id": creds["CLIENT_ID"], "client_secret": creds["CLIENT_SECRET"],
}).json()["data"]["access_token"]
H = {"Authorization": "Bearer " + tok}


def get(path, **params):
    r = requests.get(BASE + path, headers=H, params=params)
    r.raise_for_status()
    return r.json()


def total(path, **params):
    return get(path, limit=1, **params)["pagination"]["total_estimate"]


def category_count(cid):
    for c in get("/api/v1/asset-categories")["data"]:
        if c["id"] == cid:
            return c.get("asset_count")


PROBES = [
    ("GET /assets (total_estimate)", lambda: total("/api/v1/assets")),
    ("GET /assets?category_id=1", lambda: total("/api/v1/assets",
                                                category_id=1)),
    ("GET /reports/asset-register?as_of=today", lambda: total(
        "/api/v1/reports/asset-register",
        as_of=time.strftime("%Y-%m-%d"))),
    ("GET /dashboard/kpis assets.total", lambda: get(
        "/api/v1/dashboard/kpis")["data"].get("assets", {}).get("total")),
    ("GET /barcode/kpis total_assets", lambda: get(
        "/api/v1/barcode/kpis")["data"].get("total_assets")),
    # The rows are capped at the credential's record cap (100 here), so
    # the row count proves nothing; the export's own `total` is what it
    # would have exported.
    ("GET /assets/export data.total", lambda: get(
        "/api/v1/assets/export")["data"]["total"]),
    ("GET /assets/export.csv X-Cadra-Truncated", lambda: requests.get(
        BASE + "/api/v1/assets/export.csv", headers=H).headers.get(
            "X-Cadra-Truncated")),
    ("GET /asset-categories asset_count (category 1)",
     lambda: category_count(1)),
    ("GET /reports/depreciation totals.asset_count", lambda: get(
        "/api/v1/reports/depreciation")["data"]["totals"]["asset_count"]),
    # These two SHOULD move.
    ("GET /assets?register_state=any", lambda: total(
        "/api/v1/assets", register_state="any")),
    ("GET /candidates", lambda: total("/api/v1/candidates")),
]


def snapshot():
    out = {}
    for name, fn in PROBES:
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001 — a probe that fails says so
            out[name] = "ERROR %s" % e
    return out


def gated():
    return bool(get("/api/v1/settings")["data"].get("receipt_gated"))


def set_gate(on):
    requests.patch(BASE + "/api/v1/settings/receipt-gate", headers=H,
                   json={"enabled": on}).raise_for_status()


was = gated()
try:
    set_gate(True)
    before = snapshot()
    name = "probe57-%d-%s" % (time.time(), uuid.uuid4().hex[:6])
    r = requests.post(BASE + "/api/v1/assets", headers=H, json={
        "name": name, "category_id": 1, "grn_reference": "GRN-PROBE-57"})
    r.raise_for_status()
    created = r.json()["data"]
    after = snapshot()
finally:
    set_gate(was)

print("tenant %s; candidate %s (%s) register_state=%s tag=%s"
      % (DB, created["id"], name, created["register_state"], created["tag"]))
print("%-50s %-14s %-14s %s" % ("route", "before", "after", "verdict"))
moves = {"GET /assets?register_state=any", "GET /candidates"}
bad = 0
for key, _fn in PROBES:
    b, a = before[key], after[key]
    should_move = key in moves
    moved = b != a
    ok = moved == should_move
    bad += not ok
    shown = lambda v: (str(v)[:60] + "…") if len(str(v)) > 60 else str(v)
    print("%-50s %-14s %-14s %s" % (key, shown(b), shown(a),
          ("moved, as it should" if should_move else "unchanged — hides candidates")
          if ok else "WRONG"))
sys.exit(1 if bad else 0)
