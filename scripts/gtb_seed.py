#!/usr/bin/env python3
"""
Guaranty Trust Bank (GTB) tenant seed — company branding + light demo activity.

Runs AFTER itsm_structure.py (request types/stages) and load_gtb_locations.py
(branches) in the `gtb` seed profile. Two parts:

  1. Company branding  — res.company → "Guaranty Trust Bank" + public contact
     details (drives the website footer / report headers via res_company).
  2. Demo service requests — a small, bank-facilities-themed set spread across
     branches and stages, so the FM dashboard KPIs aren't all zero. This part
     is BEST-EFFORT: it adapts to whatever request types exist and skips
     cleanly on any model mismatch — it must never break the seed.

Exec'd by scripts/bootstrap.py with `env` in scope (no __main__).
Idempotent-ish: company write is idempotent; demo requests are created only if
fewer than the target already exist.
"""
import logging
import random

_logger = logging.getLogger("cadra.seed.gtb")
random.seed(2026)


def set_company_branding(env):
    company = env["res.company"].search([], limit=1)
    if not company:
        _logger.warning("GTB seed: no res.company found")
        return
    vals = {
        "name": "Guaranty Trust Bank",
        "email": "info@gtbank.com",
        "phone": "+234 1 448 0000",
        "website": "https://www.gtbank.com",
    }
    # Only write address fields the model has (avoid surprises across versions).
    fields = company.fields_get()
    if "street" in fields:
        vals["street"] = "Plot 635, Akin Adesola Street"
    if "city" in fields:
        vals["city"] = "Victoria Island, Lagos"
    company.write({k: v for k, v in vals.items() if k in fields or k == "name"})
    _logger.info("GTB seed: company → %s", company.name)
    print(f"  ✓ Company branding → {company.name}")


# Bank-facilities-themed request blurbs (subject-ish text).
_DEMO_REQUESTS = [
    "Air-conditioning unit not cooling in the banking hall",
    "Standby generator failed to start during outage",
    "ATM gallery lighting fault",
    "Power inverter / UPS battery replacement due",
    "Leaking roof above the records room",
    "Routine fire-extinguisher inspection overdue",
    "CCTV camera offline at the entrance",
    "Broken glass door at the customer entrance",
    "Plumbing blockage in staff restroom",
    "Signage / branding board damaged by storm",
    "Pest-control servicing request",
    "Network/branch connectivity intermittent",
    "Cleaning contractor escalation",
    "Office furniture repair (cashier station)",
    "Diesel refill for backup generator",
]


def seed_demo_requests(env, target=28):
    """Best-effort: create a handful of demo requests across branches/stages."""
    try:
        if "request.request" not in env:
            return
        Req = env["request.request"]
        rfields = Req.fields_get()
        existing = Req.search_count([])
        if existing >= target:
            print(f"  ✓ Demo requests: {existing} already present — skipping")
            return

        types = env["request.type"].search([]) if "request.type" in env else []
        if not types:
            print("  ! Demo requests: no request.type found — skipping")
            return

        # Branch locations (with coords) to attach as the request's location.
        Loc = env["generic.location"]
        branches = Loc.search([("latitude", "!=", False)]) if "latitude" in Loc.fields_get() else Loc.search([])

        loc_field = next((f for f in ("location_id", "request_location_id") if f in rfields), None)
        text_field = next((f for f in ("request_text", "description", "note") if f in rfields), None)

        made = 0
        for i in range(target - existing):
            rtype = types[i % len(types)]
            vals = {"type_id": rtype.id}
            if "category_id" in rfields and getattr(rtype, "category_id", False):
                vals["category_id"] = rtype.category_id.id
            if text_field:
                blurb = _DEMO_REQUESTS[i % len(_DEMO_REQUESTS)]
                branch = branches[i % len(branches)].name if branches else "branch"
                vals[text_field] = f"{blurb} — {branch}"
            if loc_field and branches:
                vals[loc_field] = branches[i % len(branches)].id
            try:
                Req.create(vals)
                made += 1
            except Exception as ex:  # noqa: BLE001 — defensive per-record
                _logger.info("GTB demo request skipped: %s", ex)
        env.cr.commit()
        print(f"  ✓ Demo requests created: {made}")
    except Exception as ex:  # noqa: BLE001 — must never break the seed
        _logger.warning("GTB demo-request seeding skipped: %s", ex)
        print(f"  ! Demo requests skipped: {ex}")


set_company_branding(env)   # noqa: F821  (env injected by bootstrap.py)
seed_demo_requests(env)     # noqa: F821
