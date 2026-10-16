"""Handoff 62 §4.2–§4.6 on `test19`, over HTTP — the units the events are
read off afterwards (`outbox.sql`).

Never touches Vendra's staged units (95682–95686, kept `captured` for Vendra
handoff 57's own drives). Every unit here is new, created by the suite's
test credential (so `is_test_fixture`), with `import_source = vendra` and a
GRN Vendra does not hold (`GRN-H62-…`), the way INT-03 sends one. The walks
are `scripts/walk_units.py` itself, run as a subprocess.

    tests/.venv/bin/python docs/handoffs/62-evidence/drive_62.py
"""
import json
import pathlib
import subprocess
import sys
import time

import requests

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tests"))
import gates  # noqa: E402

TENANT = "test19"
BASE = f"http://{TENANT}.localhost:8069"
STAMP = time.strftime("%H%M%S")
GRN = f"GRN-H62-{STAMP}"
LAND = 27703          # `e2e-59 Land (record_only)`, SAP class 6000


class Client:
    def __init__(self):
        creds = dict(line.split("=", 1) for line in (
            REPO / "docs/api/.creds.test19").read_text().split() if "=" in line)
        r = requests.post(f"{BASE}/api/v1/auth/token", timeout=20, json={
            "client_id": creds["CLIENT_ID"],
            "client_secret": creds["CLIENT_SECRET"]})
        r.raise_for_status()
        self.base = BASE
        self.s = requests.Session()
        self.s.headers["Authorization"] = (
            "Bearer " + r.json()["data"]["access_token"])

    def get(self, p, **kw):
        return self.s.get(BASE + p, timeout=60, **kw)

    def post(self, p, **kw):
        return self.s.post(BASE + p, timeout=60, **kw)

    def patch(self, p, **kw):
        return self.s.patch(BASE + p, timeout=60, **kw)


def walk(asset_id, *args):
    cmd = [sys.executable, str(REPO / "scripts/walk_units.py"),
           "--tenant", TENANT, "--asset", str(asset_id), *args]
    print("$ scripts/walk_units.py " + " ".join(cmd[2:]))  # (drive.txt was printed with cmd[3:], dropping --tenant)
    out = subprocess.run(cmd, capture_output=True, text=True)
    print(out.stdout + out.stderr, end="")
    assert out.returncode == 0, out.returncode


def unit(client, source="vendra", **extra):
    a = gates.receive(client, name=f"H62 probe {source}",
                      import_source=source, grn_reference=GRN, **extra)
    print(f"  created asset {a['id']} {a['asset_code']} "
          f"source={source} grn={GRN} state={a['register_state']}")
    return a


def main():
    client = Client()
    assert gates.receipt_gated(client), "the gates must be on to start"
    made = {}

    print("\n## A. one unit through all seven gates, with the script")
    a = unit(client)
    made["seven_gates"] = a["id"]
    walk(a["id"], "--to", "registered")

    print("\n## B. a batch verify of 5 units (+1 unit the batch refuses)")
    batch = [unit(client) for _ in range(5)]
    for b in batch:
        walk(b["id"], "--to", "vfm_pending")
    stray = unit(client)       # still `captured`: verify is refused for it
    ids = [b["id"] for b in batch] + [stray["id"]]
    r = gates._as(client, "iad_officer", "POST", "/candidates/gates/verify",
                  {"asset_ids": ids,
                   "checklist": {"quantity": True, "specification": True,
                                 "condition": True, "price": True},
                   "attachments": [{"name": "sighted.txt",
                                    "data": "c2lnaHRlZA=="}]})
    data = r.json().get("data") or r.json()
    print(f"  POST /candidates/gates/verify ({len(ids)} ids) -> HTTP "
          f"{r.status_code}: fired={data.get('fired')} "
          f"refused={data.get('refused')}")
    for line in data.get("results", []):
        print(f"    {line.get('asset_id')}: {line.get('outcome')}"
              + (f" — {line.get('message')}" if line.get("message") else ""))
    made["batch"] = [b["id"] for b in batch]
    made["batch_refused"] = stray["id"]

    print("\n## C. a query, a reject, and a record_only unit's reg_ready")
    q = unit(client)
    walk(q["id"], "--query", "Which invoice covers this unit?")
    j = unit(client)
    walk(j["id"], "--reject", "Not the model on the purchase order.")
    plot = unit(client, category_id=LAND,
                record_reference=f"PLOT-H62-{STAMP}")
    walk(plot["id"], "--to", "reg_ready")
    made.update(query=q["id"], reject=j["id"], record_only=plot["id"])

    print("\n## D. a unit NOT from Vendra, walked to the register")
    ours = unit(client, source="myservice")
    walk(ours["id"], "--to", "registered")
    made["not_vendra"] = ours["id"]

    print("\n## E. gates OFF: a Vendra unit received and affixed")
    r = client.patch("/api/v1/settings/receipt-gate", json={"enabled": False})
    print(f"  PATCH /settings/receipt-gate enabled=false -> {r.status_code}")
    try:
        off = unit(client)
        tag = off["tagging"]["tag_number"]
        r = gates._as(client, "tagger", "POST",
                      f"/assets/{off['id']}/tag-affixed",
                      {"tag_number": tag,
                       "serial_number": off["serial_number"]})
        print(f"  POST /assets/{off['id']}/tag-affixed (as tagger) -> "
              f"{r.status_code}; is_tagged="
              f"{(r.json().get('data') or {}).get('is_tagged')}")
        made["gates_off"] = off["id"]
    finally:
        r = client.patch("/api/v1/settings/receipt-gate",
                         json={"enabled": True})
        print(f"  PATCH /settings/receipt-gate enabled=true -> {r.status_code}")

    print("\nunits: " + json.dumps(made))
    (pathlib.Path(__file__).parent / "units.json").write_text(
        json.dumps(made, indent=1) + "\n")


if __name__ == "__main__":
    main()
