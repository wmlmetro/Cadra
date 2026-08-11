#!/usr/bin/env python3
"""
backfill_depreciation.py
═══════════════════════════════════════════════════════════════════════════════
Brings an EXISTING tenant database up to date after myservice_asset_depreciation
is installed. New installs get everything from the module's data files; existing
ones do not, because both data/asset_categories.xml and
data/depreciation_policy_defaults.xml are `noupdate="1"` and Odoo skips noupdate
records on upgrade. (That flag is deliberate — without it every upgrade would
silently overwrite policies a tenant had tuned by hand.)

What it does, in order:

  1. Applies the shipped straight-line / declining-balance policy defaults to
     any category that still has no method set. Categories a tenant has already
     configured are left completely alone.
  2. Pushes category policy down onto assets that follow their category
     (use_category_policy = True). Per-asset overrides are untouched.
  3. Resolves each asset's depreciation start date through the fallback chain
     acquisition_date -> purchase_date -> create_date, recording WHICH source
     won in depreciation_start_source. Anything that lands on `created` is an
     inferred date, not a real capitalisation date, and is reported at the end
     as a backfill queue.
  4. Recomputes accumulated depreciation and net book value.

ERP-managed assets are skipped throughout — SAP FICO owns those figures
(NRS spec §6.2) and Cadra must not compute over them.

Idempotent: safe to re-run after correcting data.

Usage
─────
    # dry run (default) — reports what would change, writes nothing
    odoo shell -d <db> ... < scripts/backfill_depreciation.py

    # apply
    BACKFILL_APPLY=1 odoo shell -d <db> ... < scripts/backfill_depreciation.py

    # also set every asset to ERP-managed (use for the NRS tenant, whose
    # spec §6.2 makes SAP FICO authoritative)
    BACKFILL_APPLY=1 BACKFILL_ERP_MANAGED=1 odoo shell -d <db> ... < ...

    # only apply policy to categories matching a shipped CODE; skip the
    # name-based guessing entirely
    BACKFILL_NO_NAME_MATCH=1 odoo shell -d <db> ... < ...
"""
import os

env = env  # noqa: F821 — injected by `odoo shell`

APPLY = os.environ.get("BACKFILL_APPLY") == "1"
ERP_MANAGED = os.environ.get("BACKFILL_ERP_MANAGED") == "1"
NO_NAME_MATCH = os.environ.get("BACKFILL_NO_NAME_MATCH") == "1"
BATCH = 2000

Asset = env["nrs.asset"]
Category = env["nrs.asset.category"]

# Same values as data/depreciation_policy_defaults.xml, keyed by category code
# so this works even where the XML IDs were never created.
#: Keyword -> policy-code mapping for tenant-specific categories.
#
# Every tenant names its own categories ("IT Equipment", "Power Generation",
# "ATM"), so matching on the shipped codes alone reaches almost nothing: on NRS
# that left all 11,878 assets unpolicied, on GTB 150 of 156. This maps a
# category NAME onto the nearest shipped policy.
#
# Be clear about what this is: a guess at a tenant's accounting treatment made
# from a label. It gets useful numbers on the board quickly, but it is not a
# substitute for someone confirming the useful lives. Every name-matched
# category is reported separately below so the guesses can be reviewed, and
# BACKFILL_NO_NAME_MATCH=1 turns the whole thing off.
#
# First match wins, so order matters — the more specific keywords come first.
NAME_KEYWORDS = [
    (("server", "network", "switch", "router"), "SRV"),
    (("laptop", "desktop", "computer", "it equipment", "ict"), "PC"),
    (("printer", "photocopier", "scanner"), "PRT"),
    (("atm", "banking equipment", "teller", "cash"), "ATM"),
    (("fleet", "vehicle", "transport"), "VEH"),
    (("furniture", "fitting", "desking"), "FURN"),
    (("generator", "power generation", "genset"), "GEN"),
    (("ups", "battery", "inverter"), "UPS"),
    (("lift", "elevator", "escalator"), "LIFT"),
    (("chiller", "hvac plant"), "HVAC-P"),
    (("cooling", "hvac", "air cond", "split unit"), "AC"),
    (("cctv", "surveillance", "security"), "CCTV"),
    (("access control", "elv", "intercom"), "ACS"),
    (("fire extinguisher",), "FEXT"),
    (("fire",), "FIRE"),
    (("plumbing", "pump", "borehole"), "PUMP"),
    (("water treatment",), "WTP"),
    (("tank",), "TANK"),
    (("electrical", "distribution board", "panel"), "ELEC"),
    (("compressor",), "COMP"),
    (("plant", "machinery"), "GEN"),
]

POLICY_BY_CODE = {
    # Not a shipped category, but tenant registers commonly have one and it
    # needs a life to be mapped onto. ATMs conventionally run ~7 years.
    "ATM":    ("straight_line", 84, 0.0, 0.0),
    "GEN":    ("straight_line", 120, 0.0, 10.0),
    "LIFT":   ("straight_line", 180, 0.0, 5.0),
    "HVAC-P": ("straight_line", 120, 0.0, 5.0),
    "COMP":   ("straight_line", 120, 0.0, 5.0),
    "AHU":    ("straight_line", 120, 0.0, 5.0),
    "WTP":    ("straight_line", 180, 0.0, 5.0),
    "UPS":    ("straight_line", 60,  0.0, 0.0),
    "AC":     ("straight_line", 84,  0.0, 0.0),
    "ELEC":   ("straight_line", 180, 0.0, 0.0),
    "FIRE":   ("straight_line", 120, 0.0, 0.0),
    "PUMP":   ("straight_line", 96,  0.0, 0.0),
    "TANK":   ("straight_line", 180, 0.0, 0.0),
    "FEXT":   ("straight_line", 60,  0.0, 0.0),
    "CCTV":   ("straight_line", 60,  0.0, 0.0),
    "ACS":    ("straight_line", 60,  0.0, 0.0),
    "SRV":    ("declining_balance", 60, 30.0, 0.0),
    "PC":     ("declining_balance", 48, 33.3, 0.0),
    "PRT":    ("straight_line", 60,  0.0, 0.0),
    "FURN":   ("straight_line", 120, 0.0, 0.0),
    "VEH":    ("declining_balance", 96, 20.0, 10.0),
}

print("=" * 78)
print("  CADRA — DEPRECIATION BACKFILL")
print(f"  mode: {'APPLY' if APPLY else 'DRY RUN (set BACKFILL_APPLY=1 to write)'}")
if ERP_MANAGED:
    print("  ERP-managed: every asset will be set to erp_managed (Cadra will not compute)")
print("=" * 78)

# ── 1. Category policy defaults ─────────────────────────────────────────────
def match_by_name(name):
    """Nearest shipped policy for a tenant-specific category name."""
    low = (name or "").lower()
    for keywords, code in NAME_KEYWORDS:
        if any(k in low for k in keywords):
            return code, POLICY_BY_CODE.get(code)
    return None, None


print("\n[1/4] Category policy defaults")
touched = 0
already = []
unmatched = []
by_name = []
for cat in Category.search([]):
    matched_via = "code"
    policy = POLICY_BY_CODE.get((cat.code or "").upper())
    if not policy and not NO_NAME_MATCH:
        via_code, policy = match_by_name(cat.name)
        matched_via = f"name~{via_code}"
    if not policy:
        # A tenant-specific category nothing recognises. Leaving it silently
        # unset would read as "done" when it isn't.
        unmatched.append(cat)
        continue
    if cat.depreciation_method and cat.depreciation_method != "none":
        already.append(cat)
        continue  # already configured — never clobber a tenant's own policy
    method, life, rate, salvage = policy
    print(f"  {(cat.code or '—'):<8} {cat.name[:32]:<32} [{matched_via:<10}] -> "
          f"{method} / {life}m / rate {rate}% / salvage {salvage}%")
    if APPLY:
        cat.write({
            "depreciation_method": method,
            "useful_life_months": life,
            "declining_rate": rate,
            "salvage_rate": salvage,
        })
    if matched_via != "code":
        by_name.append(cat)
    touched += 1
print(f"  categories updated: {touched}")
if by_name:
    # These are inferred from a label, not from anyone's accounting policy.
    print(f"\n  NOTE: {len(by_name)} of those were matched on category NAME, not code:")
    for cat in by_name:
        n = Asset.search_count([("category_id", "=", cat.id)])
        print(f"       {cat.name[:44]:<44} {n:>7,} assets")
    print("     These are a best guess at the treatment from the category name.")
    print("     Have someone confirm the useful lives before the figures are")
    print("     shown to the customer. Re-run with BACKFILL_NO_NAME_MATCH=1 to")
    print("     skip name matching entirely.")
if already:
    print(f"  already configured, left alone: {len(already)}")
if unmatched:
    # Loud on purpose: every asset in these categories stays at method `none`
    # and will never appear in a book-value figure.
    asset_counts = [
        (c, Asset.search_count([("category_id", "=", c.id)])) for c in unmatched
    ]
    affected = sum(n for _c, n in asset_counts)
    print(f"\n  !! {len(unmatched)} categories have NO shipped default "
          f"({affected:,} assets) and were left at 'none':")
    for cat, n in sorted(asset_counts, key=lambda x: -x[1]):
        print(f"       {(cat.code or '—'):<8} {cat.name[:38]:<38} {n:>7,} assets")
    print("     These are tenant-specific categories. Set a policy on each in")
    print("     Asset Register > Configuration > Categories, or they will never")
    print("     contribute a book value.")

# ── 2. Push policy down to assets that follow their category ────────────────
print("\n[2/4] Asset policy from category")
following = Asset.search([("use_category_policy", "=", True)])
print(f"  assets following their category: {len(following)}")
overrides = Asset.search_count([("use_category_policy", "=", False)])
print(f"  assets with a per-asset override (left alone): {overrides}")
if APPLY:
    for i in range(0, len(following), BATCH):
        following[i:i + BATCH]._sync_policy_from_category()
        env.cr.commit()
        print(f"    synced {min(i + BATCH, len(following))}/{len(following)}")

# ── 3. Start dates ──────────────────────────────────────────────────────────
print("\n[3/4] Depreciation start dates")
targets = Asset.search([("depreciation_start_source", "!=", "manual")])
print(f"  assets to resolve: {len(targets)}")
if APPLY:
    for i in range(0, len(targets), BATCH):
        targets[i:i + BATCH]._resolve_start_date()
        env.cr.commit()
        print(f"    resolved {min(i + BATCH, len(targets))}/{len(targets)}")

# ── 4. Recompute ────────────────────────────────────────────────────────────
print("\n[4/4] Recompute book values")
if ERP_MANAGED:
    all_assets = Asset.search([])
    print(f"  setting {len(all_assets)} assets to erp_managed")
    if APPLY:
        for i in range(0, len(all_assets), BATCH):
            all_assets[i:i + BATCH].write({
                "use_category_policy": False,
                "depreciation_method": "erp_managed",
            })
            env.cr.commit()
else:
    computed = Asset.search([
        ("depreciation_method", "in", ["straight_line", "declining_balance"])])
    print(f"  assets with a computed method: {len(computed)}")
    if APPLY:
        for i in range(0, len(computed), BATCH):
            computed[i:i + BATCH]._apply_depreciation()
            env.cr.commit()
            print(f"    recomputed {min(i + BATCH, len(computed))}/{len(computed)}")

# ── Report ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
print("  RESULT")
print("=" * 78)
report = Asset.get_depreciation_report()
t = report["totals"]
print(f"  assets                     : {t['asset_count']:,}")
print(f"  depreciable cost           : {t['depreciable_cost']:,.2f}")
print(f"  accumulated depreciation   : {t['accumulated_depreciation']:,.2f}")
print(f"  net book value             : {t['current_book_value']:,.2f}")
print(f"  by state                   : {report['by_state']}")
print(f"  by method                  : {report['by_method']}")

print("\n  DATA QUALITY")
print(f"  assets needing a real start date : {report['needs_start_date']:,}")
print(f"  assets with a method but no cost : {report['missing_cost']:,}")
if report["missing_cost"]:
    print("\n  Depreciation cannot produce a figure without an acquisition cost.")
    print("  The register currently has none for these assets — they need a cost")
    print("  captured (import or data entry) before book values mean anything.")

if not APPLY:
    print("\n  DRY RUN — nothing was written. Re-run with BACKFILL_APPLY=1 to apply.")
    env.cr.rollback()
else:
    env.cr.commit()
    print("\n  Committed.")
print("=" * 78)
