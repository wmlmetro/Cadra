"""Handoff 63b §3b — time each call of the category policy test, on one tenant.

  tests/.venv/bin/python category_save_timing.py <tenant>
"""
import sys, time, pathlib, requests
tenant = sys.argv[1]
root = pathlib.Path("/Users/macbookprom1/Desktop/WML/myservicenrs")
creds = dict(l.strip().split("=", 1) for l in open(root / f"docs/api/.creds.{tenant}") if "=" in l and not l.startswith("#"))
base = f"http://{tenant}.localhost:8069"
tok = requests.post(f"{base}/api/v1/auth/token", json={"client_id": creds["CLIENT_ID"], "client_secret": creds["CLIENT_SECRET"]}, timeout=10).json()
tok = tok.get("access_token") or tok["data"]["access_token"]
h = {"Authorization": f"Bearer {tok}"}
def t(label, fn):
    t0 = time.monotonic(); r = fn(); dt = time.monotonic() - t0
    print(f"{label:<44} {r.status_code}  {dt:6.1f} s"); return r
cats = t("GET /asset-categories", lambda: requests.get(f"{base}/api/v1/asset-categories", headers=h, timeout=120)).json()["data"]
cat = max((c for c in cats if c["asset_count"] > 0), key=lambda c: c["asset_count"])
orig = cat["depreciation"]["useful_life_months"] or 60
print(f"category {cat['id']} '{cat['name']}': {cat['asset_count']} assets, useful_life_months {orig}")
r = t("PATCH useful_life_months +12 (the save)", lambda: requests.patch(f"{base}/api/v1/asset-categories/{cat['id']}", json={"useful_life_months": orig + 12}, headers=h, timeout=300))
print("  assets_recomputed:", r.json()["data"].get("assets_recomputed"))
t("GET /assets?category_id=…&limit=1", lambda: requests.get(f"{base}/api/v1/assets", params={"category_id": cat["id"], "limit": 1}, headers=h, timeout=120))
r = t("PATCH back (the restore)", lambda: requests.patch(f"{base}/api/v1/asset-categories/{cat['id']}", json={"useful_life_months": orig}, headers=h, timeout=300))
print("  assets_recomputed:", r.json()["data"].get("assets_recomputed"))
