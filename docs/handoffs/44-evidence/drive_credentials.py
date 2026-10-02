"""Handoff 44 §1 — drive each credential of a tenant over HTTP and log every call.

    tests/.venv/bin/python docs/handoffs/44-evidence/drive_credentials.py \
        http://test19.localhost:8069 docs/api/.creds.test19 > transcript.txt

Reads CLIENT_*, TAGGING_CLIENT_* and VENDRA_CLIENT_* from the creds file;
a pair that is absent is skipped and SAID. Every call is printed as one line:
status, method, path, and the first 200 characters of the body. A call is
flagged `!!` when it answers 5xx, or 4xx with a sentence that names an Odoo
access refusal — the shape a missing group takes — so a diff of two runs
(with and without `base.group_system`) reads as the list the handoff asks for.

The legs, per credential:
  admin smoke (CLIENT_*) — diagnostics, the nine dashboard/station reads,
      employee sync (INT-type inbound), users/roles, the five audit reports,
      the approvals queue, settings reads, reconciliation reads, and an asset
      created and read. (No move request: deciding and withdrawing are
      proved by the HTTP suite, which has the second person they need —
      `tests/test_approvals.py`.)
  Vendra (VENDRA_*)      — INT-03: an idempotent create, its replay, a read,
      the reconciliation filter.
  Tag-Issuing Unit (TAGGING_*) — INT-05: the affix confirmation on the
      asset Vendra (or, absent Vendra, the smoke client) created.
"""
import sys
import time
import uuid

import requests

BASE, CREDS = sys.argv[1].rstrip("/"), sys.argv[2]
creds = {}
for line in open(CREDS):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        creds[k] = v

ACCESS_WORDS = ("not allowed to access", "AccessError", "access rights",
                "You are not allowed", "Access Denied")
flagged = []


def call(sess, label, method, path, **kw):
    r = sess.request(method, BASE + path, timeout=120, **kw)
    text = r.text.replace("\n", " ")
    bad = r.status_code >= 500 or (
        r.status_code in (400, 403) and any(w in text for w in ACCESS_WORDS))
    mark = "!!" if bad else "  "
    print("%s %-8s %3d %-6s %s | %s" % (mark, label, r.status_code, method,
                                       path, text[:200]))
    if bad:
        flagged.append((label, method, path, r.status_code, text[:400]))
    return r


def session(prefix):
    cid, sec = creds.get(prefix + "ID"), creds.get(prefix + "SECRET")
    if not cid or not sec or sec.startswith("<"):
        print("-- %s: no usable credential in %s; skipped" % (prefix, CREDS))
        return None
    s = requests.Session()
    r = s.post(BASE + "/api/v1/auth/token",
               json={"client_id": cid, "client_secret": sec}, timeout=60)
    print("   %-8s %3d POST   /api/v1/auth/token (%s)" % (prefix[:8], r.status_code, cid))
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["data"]["access_token"]
    return s


uniq = "%d-%s" % (time.time(), uuid.uuid4().hex[:6])
print("== %s · %s" % (BASE, time.strftime("%Y-%m-%d %H:%M:%S %Z")))

admin = session("CLIENT_")
vendra = session("VENDRA_CLIENT_")
tagger = session("TAGGING_CLIENT_")

creator = vendra or admin
category = None
if admin:
    cats = call(admin, "admin", "GET", "/api/v1/asset-categories?limit=1").json()
    category = (cats.get("data") or [{}])[0].get("id")

asset = None
if creator:
    label = "vendra" if vendra else "admin"
    key = "h44-" + uniq
    body = {"name": "pytest-h44-%s" % uniq}
    if category:
        body["category_id"] = category
    r1 = call(creator, label, "POST", "/api/v1/assets", json=body,
              headers={"X-Idempotency-Key": key})
    r2 = call(creator, label, "POST", "/api/v1/assets", json=body,
              headers={"X-Idempotency-Key": key})
    if r1.status_code == 201:
        asset = r1.json()["data"]
        same = r2.status_code == r1.status_code and \
            r2.json().get("data", {}).get("id") == asset["id"]
        print("   %-8s replay of %s: %s" % (label, key,
              "same asset, same status" if same else "DIFFERENT — %s" % r2.text[:200]))
    if asset:
        call(creator, label, "GET", "/api/v1/assets/%d" % asset["id"])
    call(creator, label, "GET", "/api/v1/assets?sap_reconciliation_state=reconciled&limit=5")
    call(creator, label, "GET", "/api/v1/assets?limit=5")

if tagger and asset:
    call(tagger, "tagger", "POST", "/api/v1/assets/%d/tag-affixed" % asset["id"],
         json={"tag_number": asset["tag"], "affixed_by_name": "H44 Drive"})
elif admin and asset and not tagger:
    call(admin, "admin", "POST", "/api/v1/assets/%d/tag-affixed" % asset["id"],
         json={"tag_number": asset["tag"], "affixed_by_name": "H44 Drive"})

if admin:
    for p in ("/api/v1/meta/diagnostics", "/api/v1/meta/enums", "/api/v1/brand",
              "/api/v1/dashboard/kpis", "/api/v1/dashboard/map",
              "/api/v1/dashboard/fleet-command", "/api/v1/security/kpis",
              "/api/v1/fleet/dashboard", "/api/v1/fm/dashboard",
              "/api/v1/barcode/kpis", "/api/v1/barcode/recent-tags",
              "/api/v1/barcode/untagged", "/api/v1/tags/pending-replacements",
              "/api/v1/users?limit=5", "/api/v1/roles",
              "/api/v1/approvals?limit=5", "/api/v1/approvals/approvers",
              "/api/v1/settings/approvals", "/api/v1/settings/branding",
              "/api/v1/settings/depreciation",
              "/api/v1/reports/asset-register?as_of=2026-10-02&limit=5",
              "/api/v1/reports/access-changes?from=2026-09-01&to=2026-10-31",
              "/api/v1/reports/configuration-changes?from=2026-09-01&to=2026-10-31",
              "/api/v1/reports/disposals?from=2026-01-01&to=2026-12-31",
              "/api/v1/reports/depreciation?limit=5",
              "/api/v1/identity/employees?limit=5", "/api/v1/locations?limit=5",
              "/api/v1/requests?limit=5"):
        call(admin, "admin", "GET", p)
    call(admin, "admin", "POST", "/api/v1/integrations/sap/employee-sync", json={
        "ir_number": "PYTEST-H44-%s" % uniq[-6:],
        "userId": "pytest.h44.%s@example.com" % uniq[-6:],
        "firstName": "Py", "lastName": "H44", "department": "Pytest",
        "jobTitle": "Drive", "employmentStatus": "active"})

print("== %d call(s) flagged" % len(flagged))
for f in flagged:
    print("!! %s %s %s -> %d: %s" % f)
