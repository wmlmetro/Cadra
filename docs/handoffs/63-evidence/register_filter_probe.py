"""Handoff 63 §4 / §5.6 — the register-filter probe, with the SAP mirror loaded.

Handoff 57's probe (`57-evidence/register_filter_probe.py`) read eleven list,
count, report and export routes over assets before and after receiving one
candidate. This reads the same eleven before and after an IMPORT of SAP's
export: the mirror is not the register, so NONE of them may move — not even
the two that moved for a candidate (`?register_state=any`, `/candidates`),
because no row of the mirror is an asset. `GET /sap-assets` is read beside
them as the witness that the import did land.

    # before the import, and again after it:
    CADRA_API_BASE=http://nrs19.localhost:8069 CADRA_LOGIN=admin \\
    CADRA_PASSWORD=... tests/.venv/bin/python \\
        docs/handoffs/63-evidence/register_filter_probe.py snapshot before.json
    ... compare before.json after.json

Reads only. Signs in with `/auth/login` as the login given (`nrs19` has no
admin API credential on this machine).
"""
import json
import os
import sys
import time

import requests

BASE = os.environ["CADRA_API_BASE"].rstrip("/")


def _token():
    r = requests.post(BASE + "/api/v1/auth/login", json={
        "login": os.environ["CADRA_LOGIN"],
        "password": os.environ["CADRA_PASSWORD"]}, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["access_token"]


H = {"Authorization": "Bearer " + _token()}


def get(path, **params):
    r = requests.get(BASE + path, headers=H, params=params, timeout=300)
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
        "/api/v1/reports/asset-register", as_of=time.strftime("%Y-%m-%d"))),
    ("GET /dashboard/kpis assets.total", lambda: get(
        "/api/v1/dashboard/kpis")["data"].get("assets", {}).get("total")),
    ("GET /barcode/kpis total_assets", lambda: get(
        "/api/v1/barcode/kpis")["data"].get("total_assets")),
    ("GET /assets/export data.total", lambda: get(
        "/api/v1/assets/export")["data"]["total"]),
    ("GET /assets/export.csv X-Cadra-Truncated", lambda: requests.get(
        BASE + "/api/v1/assets/export.csv", headers=H, timeout=300).headers.get(
            "X-Cadra-Truncated")),
    ("GET /asset-categories asset_count (category 1)",
     lambda: category_count(1)),
    ("GET /reports/depreciation totals.asset_count", lambda: get(
        "/api/v1/reports/depreciation")["data"]["totals"]["asset_count"]),
    ("GET /assets?register_state=any", lambda: total(
        "/api/v1/assets", register_state="any")),
    ("GET /candidates", lambda: total("/api/v1/candidates")),
]
WITNESS = ("GET /sap-assets (total_estimate) — the witness",
           lambda: total("/api/v1/sap-assets"))


def snapshot():
    out = {}
    for name, fn in PROBES + [WITNESS]:
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001 — a probe that fails says so
            out[name] = "ERROR %s" % e
    return out


if sys.argv[1] == "snapshot":
    json.dump(snapshot(), open(sys.argv[2], "w"), indent=1)
    print("written", sys.argv[2])
    sys.exit(0)

before, after = (json.load(open(p)) for p in sys.argv[2:4])
print("tenant %s" % BASE.split("//")[1].split(".")[0])
print("%-52s %-14s %-14s %s" % ("route", "before", "after", "verdict"))
bad = 0
for key, _fn in PROBES:
    b, a = before[key], after[key]
    ok = b == a and not str(b).startswith("ERROR")
    bad += not ok
    print("%-52s %-14s %-14s %s" % (key, b, a,
          "unchanged — the mirror is not the register" if ok else "WRONG"))
key = WITNESS[0]
print("%-52s %-14s %-14s %s" % (key, before[key], after[key],
      "moved: the import landed" if before[key] != after[key]
      else "did not move — the import did not land"))
sys.exit(1 if bad else 0)
