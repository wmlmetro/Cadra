"""Handoff 63 §5.4 — `GET /reports/sap-coverage` on a tenant, every row,
OFFICE CODES MASKED (an office code is an identifier of NRS's register;
59's rule). Offices are printed by rank of active SAP records.

    CADRA_API_BASE=http://nrs19.localhost:8069 CADRA_LOGIN=admin \\
    CADRA_PASSWORD=... tests/.venv/bin/python docs/handoffs/63-evidence/coverage_report.py
"""
import os
import statistics
import time

import requests

BASE = os.environ["CADRA_API_BASE"].rstrip("/")
tok = requests.post(BASE + "/api/v1/auth/login", json={
    "login": os.environ["CADRA_LOGIN"],
    "password": os.environ["CADRA_PASSWORD"]}).json()["data"]["access_token"]
t = time.time()
r = requests.get(BASE + "/api/v1/reports/sap-coverage",
                 headers={"Authorization": "Bearer " + tok}, timeout=600)
print("GET /reports/sap-coverage → %d in %.2f s" % (r.status_code, time.time() - t))
d = r.json()["data"]
print("sentence:", d["sentence"])
print("sap:", d["sap"])
print("totals:", d["totals"])
print("reconcilable_today:", d["reconcilable_today"])
print()
cols = ("sap_active", "linked", "linked_to_a_receipt_candidate", "not_linked",
        "sap_retired", "cadra_assets", "cadra_with_sap_number",
        "cadra_sap_number_not_in_mirror", "cadra_without_sap_number", "held")
print("by_class — " + " | ".join(("class",) + cols))
for row in d["by_class"]:
    print("  " + " | ".join(str(row[c]) for c in ("class",) + cols))
print()
offices = d["by_office"]
named = [o for o in offices if o["office"] is not None]
none = [o for o in offices if o["office"] is None]
print("by_office — %d rows: %d offices and %d row of records with no office"
      % (len(offices), len(named), len(none)))
for o in none:
    print("  no office: sap_active %d, linked %d, not_linked %d"
          % (o["sap_active"], o["linked"], o["not_linked"]))
active = [o["sap_active"] for o in named]
print("  offices: active records per office — mean %.1f, median %s, max %d, "
      "min %d; linked on any office: %d"
      % (statistics.mean(active), statistics.median(active), max(active),
         min(active), sum(o["linked"] for o in named)))
for i, o in enumerate(named[:10], 1):
    print("  office #%d (code masked): sap_active %d, linked %d, held %s"
          % (i, o["sap_active"], o["linked"], o["held"]))
print()
print("definitions:")
for k, v in d["definitions"].items():
    print("  %s — %s" % (k, v))
