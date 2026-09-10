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


# Minimal request workflow (matches the field set proven in
# seeds/nrs_seed.build_stages_and_routes). "new" is the start stage; resolved
# and rejected are closed. The FM dashboard counts non-closed requests as open.
_STAGE_TEMPLATE = [
    # name,          code,          sequence, closed
    ("New",          "new",         10, False),
    ("In Progress",  "in_progress", 20, False),
    ("Resolved",     "resolved",    30, True),
    ("Rejected",     "rejected",    40, True),
]
_ROUTE_TEMPLATE = [
    # name,        from_code,     to_code,       close, sequence
    ("Start work", "new",         "in_progress", False, 10),
    ("Resolve",    "in_progress", "resolved",    True,  20),
    ("Reject",     "new",         "rejected",    True,  30),
]


def ensure_request_workflows(env):
    """itsm_structure.py creates request *types* but no stages, so every type
    has no start stage and requests can't be created at all (and the request
    forms wouldn't work). Build a minimal stage workflow + routes for each type
    that's missing one. Returns {type_id: {code: stage_id}}.
    """
    Type = env["request.type"]
    Stage = env["request.stage"]
    Route = env["request.stage.route"] if "request.stage.route" in env else None
    sfields = Stage.fields_get()
    built = 0
    maps = {}
    for rtype in Type.search([]):
        existing = Stage.search([("request_type_id", "=", rtype.id)])
        if getattr(rtype, "start_stage_id", False) and existing:
            maps[rtype.id] = {s.code: s.id for s in existing if "code" in sfields}
            continue
        id_map = {}
        for name, code, seq, closed in _STAGE_TEMPLATE:
            vals = {"name": name, "request_type_id": rtype.id}
            if "code" in sfields:
                vals["code"] = code
            if "sequence" in sfields:
                vals["sequence"] = seq
            if "closed" in sfields:
                vals["closed"] = closed
            id_map[code] = Stage.create(vals).id
        if "start_stage_id" in rtype._fields:
            rtype.write({"start_stage_id": id_map["new"]})
        if Route is not None:
            for rname, fc, tc, close, seq in _ROUTE_TEMPLATE:
                if id_map.get(fc) and id_map.get(tc):
                    Route.create({
                        "name": rname, "stage_from_id": id_map[fc],
                        "stage_to_id": id_map[tc], "close": close,
                        "sequence": seq, "request_type_id": rtype.id,
                    })
        maps[rtype.id] = id_map
        built += 1
    if built:
        env.cr.commit()
        print(f"  ✓ Built request workflow (stages+routes) for {built} types")
    return maps


def seed_demo_requests(env, target=30):
    """Create demo requests across branches + stages so the FM dashboard KPIs
    aren't zero. Builds the stage workflow first (types ship without one), then
    creates with the proven-minimal fields and enriches (location, stage) via
    guarded post-create writes. Never breaks the seed.
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

        stage_maps = ensure_request_workflows(env)

        text_field = next((f for f in ("request_text", "description", "note") if f in rfields), None)
        loc_field = next((f for f in ("request_location_id", "location_id") if f in rfields), None)
        branches = env["generic.location"].search([("latitude", "!=", False)])
        # Spread requests across open stages for dashboard variety.
        open_codes = ["new", "new", "in_progress"]

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
            # catch-all: reported — the first error is kept in `first_err` and
            # printed when nothing was created, and `made` counts only the
            # creates that landed. The gap it leaves: a PARTIAL failure is
            # visible only as a lower count, because first_err is printed only
            # when made == 0.
            except Exception as ex:             # noqa: BLE001 — per-record
                first_err = first_err or str(ex)
                continue
            made += 1
            # Enrichment — guarded; a failure here keeps the created record.
            if loc_field and branch:
                try:
                    rec.write({loc_field: branch.id})
                # catch-all: optional — demo decoration on a demo row. The
                # request already exists and is already counted; a failed
                # location write leaves it unplaced, which is a less pretty
                # demo and not a wrong number. The seed's printed count is
                # unaffected and stays true.
                except Exception:  # noqa: BLE001
                    pass
            code = open_codes[i % len(open_codes)]
            stage_id = (stage_maps.get(rtype.id) or {}).get(code)
            if stage_id:
                try:
                    rec.write({"stage_id": stage_id})
                # catch-all: optional — same as the location write above: the
                # request keeps whatever stage the type gave it. It is worth a
                # look if the FM dashboard's stage columns come out empty, but
                # nothing here reports a number that this could falsify.
                except Exception:  # noqa: BLE001
                    pass
        env.cr.commit()
        msg = f"  ✓ Demo requests created: {made}"
        if made == 0 and first_err:
            msg += f"  (first error: {first_err[:140]})"
        print(msg)
    # catch-all: reported — logs at WARNING and prints "Demo requests skipped"
    # with the exception. Demo activity is best-effort by design and must never
    # break a tenant seed, but a seed that skipped it never claims it ran.
    except Exception as ex:  # noqa: BLE001 — must never break the seed
        _logger.warning("GTB demo-request seeding skipped: %s", ex)
        print(f"  ! Demo requests skipped: {ex}")


set_company_branding(env)   # noqa: F821  (env injected by bootstrap.py)
seed_demo_requests(env)     # noqa: F821
