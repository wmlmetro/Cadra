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
against a tenant whose register is the real book of record. It refuses to touch
the `staging` (NRS) database for exactly that reason — NRS's financial data
belongs to SAP FICO, and their spec (§6.2) puts them on `erp_managed` where
Cadra must not compute at all.

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
    odoo shell -d gtb ... < scripts/seed_asset_costs.py

    # apply
    SEED_APPLY=1 odoo shell -d gtb ... < scripts/seed_asset_costs.py

    # override the refusal (do not do this without a very good reason)
    SEED_APPLY=1 SEED_FORCE_PROTECTED=1 odoo shell -d staging ... < ...
"""
import os
import random
from datetime import date, timedelta

env = env  # noqa: F821 — injected by `odoo shell`

APPLY = os.environ.get("SEED_APPLY") == "1"
FORCE_PROTECTED = os.environ.get("SEED_FORCE_PROTECTED") == "1"
BATCH = 500

#: Databases holding a real register that must never receive invented figures.
PROTECTED_DBS = {"staging", "nrs", "nrs19"}

#: Reproducible across runs — a re-run must not reshuffle book values.
RANDOM_SEED = 20260811

# (min_cost, max_cost) in NGN, by keyword in the category name. First match wins,
# so the more specific keywords come first.
COST_RANGES = [
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

if db_name in PROTECTED_DBS and not FORCE_PROTECTED:
    print(f"\n  REFUSING: '{db_name}' holds a real asset register.")
    print("  NRS financial data is owned by SAP FICO (NRS spec §6.2) and that")
    print("  tenant runs in erp_managed mode, where Cadra must not compute at all.")
    print("  Seeding invented costs there would put fabricated money on screen.")
    print("\n  Override with SEED_FORCE_PROTECTED=1 only if you are certain.")
    print("=" * 78)
    env.cr.rollback()
    raise SystemExit(0)


def cost_range_for(name):
    low = (name or "").lower()
    for keywords, rng in COST_RANGES:
        if any(k in low for k in keywords):
            return rng
    return DEFAULT_RANGE


def money(v):
    return f"{v:,.2f}"


targets = Asset.search([
    "|", ("acquisition_cost", "=", False), ("acquisition_cost", "<=", 0),
])
total = Asset.search_count([])
print(f"\n  assets in register        : {total:,}")
print(f"  assets with no cost       : {len(targets):,}")
print(f"  assets already priced     : {total - len(targets):,} (left untouched)")

if not targets:
    print("\n  Nothing to do — every asset already has a cost.")
    print("=" * 78)
    env.cr.rollback()
    raise SystemExit(0)

span_days = (ACQ_END - ACQ_START).days
by_category = {}
written = 0

for i in range(0, len(targets), BATCH):
    for asset in targets[i:i + BATCH]:
        # Seeded per record id: a re-run reproduces the same figure rather than
        # quietly restating the register.
        rng = random.Random(RANDOM_SEED + asset.id)
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
