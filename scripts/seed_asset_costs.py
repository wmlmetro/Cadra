#!/usr/bin/env python3
"""
seed_asset_costs.py
═══════════════════════════════════════════════════════════════════════════════
Seeds DEMO acquisition costs and dates onto assets that have none, so the
depreciation feature has something to compute from.

WHY THIS EXISTS
───────────────
The asset register was imported without financial data: the NRS CSVs carry an
`acquisition_cost` column on all 11,878 rows but every value is 0.0, and there
is no acquisition-date column at all. The same is true of the gtb / jaiz / lasg
seeds. Depreciation therefore computes correctly and reports zero everywhere,
which demonstrates nothing.

This fills that gap for demo and evaluation tenants.

⚠️  THE NUMBERS THIS WRITES ARE INVENTED.
They are plausible per asset class, not real procurement figures. Never run this
against a tenant whose register is the real book of record. NRS's financial data
belongs to SAP FICO, and their spec (§6.2) puts them on `erp_managed` where
Cadra must not compute at all.

It therefore refuses any database that does not say, in its own
`cadra.database_class` parameter, that it is a test database — absent included.
See THE GUARD below, and note the consequence: the demo tenants in the usage
line are marked `client` and now require an explicit, announced override.

WHAT IT DOES
────────────
For every asset with no acquisition cost:
  * picks a cost from a per-category range (ATMs cost more than chairs)
  * picks an acquisition date, weighted so the fleet spans early-life to
    near-end-of-life and the report shows a realistic spread
  * recomputes depreciation for the assets it touched

Assets that already have a cost are left completely alone, so this is safe to
re-run and safe to run after real data starts arriving.

Deterministic: the RNG is seeded per asset id, so a re-run produces the same
figures rather than reshuffling everyone's book value.

Usage
─────
    # dry run (default) — reports what it would write, changes nothing
    odoo shell -d test19 ... < scripts/seed_asset_costs.py

    # apply
    SEED_APPLY=1 odoo shell -d test19 ... < scripts/seed_asset_costs.py

    # a DEMO tenant (gtb / jaiz / lasg) is marked `client` and is refused by
    # default. Overriding is a deliberate act and the run announces it.
    SEED_APPLY=1 SEED_FORCE_PROTECTED=1 odoo shell -d gtb ... < ...
"""
import os
import random
from datetime import date, timedelta

# Imported, not re-implemented. `nrs.asset` only exists in
# myservice_asset_register, whose manifest depends on `myservice_nrs_base` —
# so by the time this script can do anything at all, the module holding the
# guard is installed and on the addons path. (scripts/bootstrap.py duplicates
# these two constants instead, for the opposite reason: it runs against
# databases where no Cadra addon is installed yet.)
from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    TEST, database_class, mark_command,
)

env = env  # noqa: F821 — injected by `odoo shell`

APPLY = os.environ.get("SEED_APPLY") == "1"
FORCE_PROTECTED = os.environ.get("SEED_FORCE_PROTECTED") == "1"
#: Overwrite costs this script wrote before. Off by default so a re-run never
#: restates a register — but needed when re-seeding to differentiate tenants.
RESEED = os.environ.get("SEED_RESEED") == "1"
BATCH = 500

#: Reproducible across runs — a re-run must not reshuffle book values.
RANDOM_SEED = 20260811

# (min_cost, max_cost) in NGN, by keyword in the category name. First match wins,
# so the more specific keywords come first.
COST_RANGES = [
    # Health sector first, for the same reasons as the policy keywords:
    # "cold chain" must not fall through to "cooling".
    (("cold chain", "vaccine", "freezer"),         (   400_000,  4_000_000)),
    (("laborator", "pathology", "diagnostic"),     (   300_000,  8_000_000)),
    (("medical", "imaging", "x-ray", "ultrasound",
      "theatre", "clinical"),                      (   500_000, 15_000_000)),
    (("ward", "hospital bed", "trolley", "stretcher"), (  80_000,    800_000)),
    (("lift", "elevator", "escalator"),            (15_000_000, 40_000_000)),
    (("vehicle", "fleet", "transport"),            (12_000_000, 35_000_000)),
    (("atm",),                                     ( 8_000_000, 15_000_000)),
    (("generator", "power generation", "genset"),  ( 5_000_000, 25_000_000)),
    (("chiller", "hvac plant"),                    ( 4_000_000, 18_000_000)),
    (("water treatment",),                         ( 3_000_000, 12_000_000)),
    (("server", "network", "switch", "router"),    ( 3_000_000, 12_000_000)),
    (("compressor",),                              ( 1_500_000,  6_000_000)),
    (("banking equipment", "teller", "cash"),      (   500_000,  3_000_000)),
    (("cooling", "hvac", "air cond", "split"),     (   400_000,  3_000_000)),
    (("ups", "battery", "inverter"),               (   300_000,  2_500_000)),
    (("cctv", "surveillance", "security"),         (   250_000,  2_000_000)),
    (("access control", "elv", "intercom"),        (   250_000,  2_000_000)),
    (("printer", "photocopier", "scanner"),        (   200_000,  1_500_000)),
    (("laptop", "desktop", "computer", "it equip"),(   350_000,  1_200_000)),
    (("plumbing", "pump", "borehole"),             (   150_000,  1_200_000)),
    (("electrical", "distribution board", "panel"),(   200_000,  2_500_000)),
    (("tank",),                                    (   300_000,  2_000_000)),
    (("fire extinguisher",),                       (    25_000,    120_000)),
    (("fire",),                                    (   100_000,    800_000)),
    (("furniture", "fitting", "desking"),          (    50_000,    400_000)),
    (("plant", "machinery"),                       ( 1_000_000, 10_000_000)),
]
DEFAULT_RANGE = (200_000, 1_500_000)

#: Acquisition dates span this window. Deliberately wide so the register shows a
#: realistic mix of nearly-new, mid-life and fully-depreciated assets.
ACQ_START = date(2017, 1, 1)
ACQ_END = date(2025, 6, 30)

Asset = env["nrs.asset"]
db_name = env.cr.dbname

print("=" * 78)
print("  CADRA — DEMO ASSET COST SEED")
print(f"  database : {db_name}")
print(f"  mode     : {'APPLY' if APPLY else 'DRY RUN (set SEED_APPLY=1 to write)'}")
print("=" * 78)
print("\n  The costs and dates written here are INVENTED demo figures, not real")
print("  procurement data. They exist so depreciation has something to compute.")

# ─── THE GUARD ───────────────────────────────────────────────────────────────
#
# This used to be a DATABASE-NAME allowlist: `PROTECTED_DBS = {"staging",
# "nrs", "nrs19"}`. It did not contain `jaizbankplc`, which is a register
# derived from a live client's data (see the header of
# scripts/mark_test_fixtures.py) — so the one control standing between
# invented money and a customer's book of record was a list that omitted the
# tenant most at risk, and nobody could tell by reading it.
#
# The repo has since ruled against name-based gating outright (docs/
# DECISIONS.md, 2026-09-15, handoff 25 A): a name is wrong the day somebody
# restores a client dump into `test19`. Safety is a property of the DATABASE,
# recorded IN the database — `cadra.database_class`, set deliberately by a
# person, read with SQL and never through `get_param`, which is @ormcached per
# worker and has already served a guard a value the database no longer held.
#
# So the question asked here is no longer "is this one of three names somebody
# remembered in August" but "does this database say it is a test database".
# **Absent refuses exactly as `production` does**: a database nobody has
# classified is a database nobody has thought about.
#
# The name list is DELETED rather than kept alongside. It cannot catch
# anything the class check misses — `nrs` is marked `client` and `nrs19`
# carries no mark at all, so both were already refused by class — and a second,
# weaker gate beside the real one only invites the next reader to argue about
# which of them is doing the work.
#
# WHY `SEED_FORCE_PROTECTED` SURVIVES, against handoff 25's "no bypass flag":
#   * The demo tenants this script was written for — gtb, jaiz, lasg — are
#     marked `client`, so the class guard now refuses every one of them.
#     Deleting the flag would not make the script safer; it would make it
#     unrunnable for its stated purpose.
#   * It is already wired end to end as a human decision:
#     .github/workflows/depreciation.yml exposes `force_protected` as a
#     workflow_dispatch input and k8s/dev/52-depreciation-job.yaml passes it in
#     as SEED_FORCE_PROTECTED. Dropping the read here would leave a control
#     that still looks like a control and does nothing — which is the defect
#     this handoff closes, not a fix for it.
# Handoff 25's rule governs a suite that runs unattended on every push. This is
# one person setting one variable, and a forced run now says so on its face.
found_class = database_class(env)
if found_class != TEST:
    if not FORCE_PROTECTED:
        print(f"\n  REFUSING: '{db_name}' is not marked as a test database.")
        print(f"    cadra.database_class = {found_class or 'not set'}")
        print("\n  This script writes INVENTED acquisition costs and dates. On a")
        print("  register somebody reads, that is fabricated money on screen.")
        print("  NRS financial data is owned by SAP FICO (NRS spec §6.2) and that")
        print("  tenant runs in erp_managed mode, where Cadra must not compute at all.")
        print("\n  If this database really is a throwaway, mark it once:\n")
        print(mark_command(db_name))
        print("\n  If you meant a different database, change the target rather than")
        print("  the mark. To seed a demo tenant that is legitimately marked")
        print("  'client', set SEED_FORCE_PROTECTED=1 — the run will announce it.")
        print("=" * 78)
        env.cr.rollback()
        # Exit 1, not 0. The previous version exited 0 on a refusal, so the
        # k8s Job in k8s/dev/52-depreciation-job.yaml reported Succeeded for a
        # run that had done nothing at all — the same shape of lie this guard
        # is here to stop.
        raise SystemExit(1)

    print("\n  " + "!" * 74)
    print("  !!  SEED_FORCE_PROTECTED=1 — the class guard is being OVERRIDDEN.")
    print(f"  !!  '{db_name}' is marked '{found_class or 'not set'}' and is about to")
    print("  !!  receive invented financial figures anyway.")
    print("  " + "!" * 74)


def cost_range_for(name):
    low = (name or "").lower()
    for keywords, rng in COST_RANGES:
        if any(k in low for k in keywords):
            return rng
    return DEFAULT_RANGE


def money(v):
    return f"{v:,.2f}"


if RESEED:
    print("\n  SEED_RESEED=1 — existing costs will be OVERWRITTEN.")
    targets = Asset.search([])
else:
    targets = Asset.search([
        "|", ("acquisition_cost", "=", False), ("acquisition_cost", "<=", 0),
    ])
total = Asset.search_count([])
print(f"\n  assets in register        : {total:,}")
print(f"  assets with no cost       : {len(targets):,}")
print(f"  assets already priced     : {total - len(targets):,} (left untouched)")

if not targets:
    # A LEGITIMATE ZERO, stated deliberately rather than by omission. Every
    # asset already carrying a cost is the normal outcome of a second run —
    # the header above has just printed the register total and the priced
    # count, so the reader can see the zero is a full register and not a
    # search that matched nothing. Exit 0 is correct here, unlike the refusal
    # above, because the script was asked to do something and there was
    # genuinely nothing left to do.
    print("\n  Nothing to do — every asset already has a cost.")
    print("=" * 78)
    env.cr.rollback()
    raise SystemExit(0)

span_days = (ACQ_END - ACQ_START).days
by_category = {}
written = 0

for i in range(0, len(targets), BATCH):
    for asset in targets[i:i + BATCH]:
        # Seeded per (database, record id). Including the database name matters:
        # tenants seeded from the same script share asset ids and category
        # names, so an id-only seed gives two different customers byte-identical
        # book values — which reads as a copy-paste bug in a demo.
        rng = random.Random(f"{RANDOM_SEED}:{db_name}:{asset.id}")
        cat_name = asset.category_id.name or ""
        low, high = cost_range_for(cat_name)
        # Round to the nearest 1,000 — real invoices are not to the kobo.
        cost = round(rng.uniform(low, high), -3)
        acq = ACQ_START + timedelta(days=rng.randint(0, span_days))

        bucket = by_category.setdefault(cat_name or "(uncategorised)",
                                        {"n": 0, "total": 0.0})
        bucket["n"] += 1
        bucket["total"] += cost

        if APPLY:
            asset.write({"acquisition_cost": cost, "acquisition_date": acq})
        written += 1

    if APPLY:
        env.cr.commit()
        print(f"    seeded {min(i + BATCH, len(targets)):,}/{len(targets):,}")

print("\n  BY CATEGORY")
for name, b in sorted(by_category.items(), key=lambda kv: -kv[1]["total"]):
    print(f"    {name[:40]:<40} {b['n']:>6,} assets  {money(b['total']):>20}")

grand = sum(b["total"] for b in by_category.values())
print(f"    {'TOTAL':<40} {written:>6,} assets  {money(grand):>20}")

# Recompute so book values reflect the new costs immediately.
if APPLY:
    print("\n  recomputing depreciation for the seeded assets...")
    for i in range(0, len(targets), BATCH):
        targets[i:i + BATCH]._apply_depreciation()
        env.cr.commit()
    print("    done")

    report = Asset.get_depreciation_report()
    t = report["totals"]
    print("\n" + "=" * 78)
    print("  RESULT")
    print("=" * 78)
    print(f"  depreciable cost          : {money(t['depreciable_cost'])}")
    print(f"  accumulated depreciation  : {money(t['accumulated_depreciation'])}")
    print(f"  net book value            : {money(t['current_book_value'])}")
    print(f"  by state                  : {report['by_state']}")
    print(f"  needs a real start date   : {report['needs_start_date']:,}")
    print(f"  method but no cost        : {report['missing_cost']:,}")
    env.cr.commit()
    print("\n  Committed.")
else:
    env.cr.rollback()
    print("\n  DRY RUN — nothing written. Re-run with SEED_APPLY=1 to apply.")
print("=" * 78)
