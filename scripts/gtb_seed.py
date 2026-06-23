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


def seed_demo_requests(env, target=30):
    """Best-effort: create demo requests so the FM dashboard KPIs aren't zero.

    The create uses ONLY the proven-minimal fields (type_id + request_text) —
    everything else defaults. Location and stage are attached AFTER, in
    separate guarded writes, so a rejected enrichment never loses the record
    (an earlier version put the location in the create() and every record was
    silently rejected → 0 created). Never breaks the seed.
    """
    try:
        Req = env["request.request"]
        rfields = Req.fields_get()
        existing = Req.search_count([])
        if existing >= target:
            print(f"  ✓ Demo requests: {existing} already present — skipping")
            return

        types = env["request.type"].search([])
        if not types:
            print("  ! Demo requests: no request.type found — skipping")
            return

        text_field = next((f for f in ("request_text", "description", "note") if f in rfields), None)
        loc_field = next((f for f in ("request_location_id", "location_id") if f in rfields), None)
        branches = env["generic.location"].search([("latitude", "!=", False)])
        stages = env["request.stage"].search([]) if "request.stage" in env else None

        made, first_err = 0, None
        for i in range(target - existing):
            rtype = types[i % len(types)]
            branch = branches[i % len(branches)] if branches else None
            blurb = _DEMO_REQUESTS[i % len(_DEMO_REQUESTS)]
            vals = {"type_id": rtype.id}
            if text_field:
                vals[text_field] = blurb + (f" — {branch.name}" if branch else "")
            try:
                rec = Req.create(vals)          # proven-minimal create
            except Exception as ex:             # noqa: BLE001 — per-record
                first_err = first_err or str(ex)
                continue
            made += 1
            # Enrichment — guarded; a failure here keeps the (already-created) record.
            if loc_field and branch:
                try:
                    rec.write({loc_field: branch.id})
                except Exception:  # noqa: BLE001
                    pass
            if stages:
                try:
                    rec.write({"stage_id": stages[i % len(stages)].id})
                except Exception:  # noqa: BLE001
                    pass
        env.cr.commit()
        msg = f"  ✓ Demo requests created: {made}"
        if made == 0 and first_err:
            msg += f"  (first error: {first_err[:140]})"
        print(msg)
    except Exception as ex:  # noqa: BLE001 — must never break the seed
        _logger.warning("GTB demo-request seeding skipped: %s", ex)
        print(f"  ! Demo requests skipped: {ex}")


set_company_branding(env)   # noqa: F821  (env injected by bootstrap.py)
seed_demo_requests(env)     # noqa: F821
