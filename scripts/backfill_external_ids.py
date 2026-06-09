#!/usr/bin/env python3
"""
backfill_external_ids.py
═══════════════════════════════════════════════════════════════════════════════
Prerequisite for running docs/seed/NRS_asset_seed/seed_nrs_assets.py against
a Cadra DB that was bootstrapped without the seed's External IDs.

The seed CSVs reference rows via External IDs like:
    __export__.hr_employee_<IR>
    __export__.hr_department_<slug>
    __export__.generic_location_<dbid>_<hash>

Our existing hr.department / hr.employee / generic.location rows were created
by other paths (the API endpoint, load_offices, etc.) and have NO such External
IDs. Without them, model.load() would DUPLICATE every row rather than update.

This script writes the missing ir.model.data rows so the seed loader sees the
existing data as the "current" rows for those External IDs:

    hr.department   ─ matched by name
    hr.employee     ─ matched by ir_number  (our native field on hr.employee)
    generic.location ─ matched by name; ambiguous names resolved by the path
                       column in the asset CSV (" / "-delimited)

Idempotent: any External ID that already exists is left alone.

Usage:
    python scripts/backfill_external_ids.py \
        --url https://staging.app.cadra.ng \
        --db odoo --user admin --password '****' [--dry-run]

Environment-variable fallbacks: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD.

Run order:
    1. This script.   (1-2 minutes; writes only ir.model.data rows.)
    2. docs/seed/NRS_asset_seed/seed_nrs_assets.py --ensure-fields
═══════════════════════════════════════════════════════════════════════════════
"""
import argparse
import csv
import os
import re
import sys
import xmlrpc.client

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SEED = os.path.join(REPO, "docs/seed/NRS_asset_seed")

DEPT_CSV     = os.path.join(SEED, "01_references/IMPORT_ref_hr_department.csv")
EMP_CSV      = os.path.join(SEED, "02_employees/IMPORT_employees_hr_employee.csv")
ASSET_CSVS   = [
    os.path.join(SEED, "03_assets_ict/IMPORT_ALL_ICT_nrs_asset.csv"),
    os.path.join(SEED, "04_assets_fleet/IMPORT_fleet_nrs_asset.csv"),
]

XID_PREFIX = "__export__."
PATH_SEP   = " / "


# ─── XML-RPC plumbing ───────────────────────────────────────────────────────

def connect(url, db, user, password):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, password, {})
    if not uid:
        sys.exit("Auth failed — check --url/--db/--user/--password.")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return uid, models


def rpc(models, db, uid, password, model, method, *args, **kwargs):
    return models.execute_kw(db, uid, password, model, method,
                             list(args), kwargs or {})


# ─── helpers ────────────────────────────────────────────────────────────────

def split_xid(xid):
    """`__export__.hr_employee_28414` → ('__export__', 'hr_employee_28414')."""
    if not xid.startswith(XID_PREFIX):
        return None, None
    return "__export__", xid[len(XID_PREFIX):]


def existing_xids(models, db, uid, password, model, names):
    """Return the subset of `names` that already exist as ir.model.data rows
    for the given model under module='__export__'."""
    if not names:
        return set()
    found = rpc(models, db, uid, password, "ir.model.data", "search_read",
                [("module", "=", "__export__"),
                 ("model",  "=", model),
                 ("name",   "in", list(names))],
                ["name"])
    return {r["name"] for r in found}


def upsert_xids(models, db, uid, password, model, mapping, dry_run, label):
    """`mapping` is {short_xid_name -> db_id}. Create ir.model.data rows for
    every short name that doesn't already exist. Returns (created, skipped).

    Uses bulk create — one RPC per BATCH rows instead of one per row. On a
    11k-row backfill against a remote Odoo this is the difference between
    ~20 min (per-row) and ~1 min (bulk). If a batch fails as a whole, we
    fall back to per-row inserts for that batch so one bad row doesn't
    sink the rest.
    """
    already = existing_xids(models, db, uid, password, model, mapping.keys())
    to_create = [(n, rid) for n, rid in mapping.items() if n not in already]
    print(f"  {label}: {len(mapping)} requested, {len(already)} already there, "
          f"{len(to_create)} to create")
    if dry_run or not to_create:
        return 0, len(already)
    created = 0
    BATCH = 500
    for i in range(0, len(to_create), BATCH):
        chunk = to_create[i:i + BATCH]
        vals_list = [{"module": "__export__", "name": name,
                      "model": model, "res_id": rid, "noupdate": False}
                     for name, rid in chunk]
        try:
            rpc(models, db, uid, password, "ir.model.data", "create", vals_list)
            created += len(chunk)
        except Exception as e:
            # Fall back to per-row to localise the bad row(s).
            print(f"    ! bulk batch failed ({e}); falling back row-by-row")
            for vals, (name, rid) in zip(vals_list, chunk):
                try:
                    rpc(models, db, uid, password, "ir.model.data", "create", vals)
                    created += 1
                except Exception as e2:
                    print(f"      ! __export__.{name} → {model} id={rid}: {e2}")
        print(f"    + created {min(i + BATCH, len(to_create))}/{len(to_create)}")
    return created, len(already)


# ─── plans ──────────────────────────────────────────────────────────────────

def plan_departments(models, db, uid, password):
    """{short_xid_name -> hr.department.id} from the seed CSV, by name match."""
    rows = []
    with open(DEPT_CSV) as f:
        for r in csv.DictReader(f):
            xid = r.get("id", "").strip()
            name = r.get("name", "").strip()
            if xid and name:
                _, short = split_xid(xid)
                if short:
                    rows.append((short, name))

    names = sorted({n for _, n in rows})
    found = rpc(models, db, uid, password, "hr.department", "search_read",
                [("name", "in", names)], ["id", "name"])
    by_name = {}
    duplicates = {}
    for rec in found:
        n = rec["name"]
        if n in by_name:
            duplicates.setdefault(n, [by_name[n]]).append(rec["id"])
        else:
            by_name[n] = rec["id"]
    if duplicates:
        print(f"  ! {len(duplicates)} duplicate dept names — using first match "
              f"for each: {list(duplicates)[:3]}{'...' if len(duplicates) > 3 else ''}")

    mapping = {}
    missing = []
    for short, name in rows:
        if name in by_name:
            mapping[short] = by_name[name]
        else:
            missing.append((short, name))
    if missing:
        print(f"  ! {len(missing)} seed depts not found in DB (would be created on load): "
              f"{[n for _, n in missing][:3]}")
    return mapping


def plan_employees(models, db, uid, password):
    """{short_xid_name -> hr.employee.id} from the seed CSV, by ir_number match."""
    irs = []
    with open(EMP_CSV) as f:
        for r in csv.DictReader(f):
            xid = r.get("id", "").strip()
            ir = (r.get("x_ir_number") or r.get("identification_id") or "").strip()
            if xid and ir:
                _, short = split_xid(xid)
                if short:
                    irs.append((short, ir))

    ir_values = sorted({ir for _, ir in irs})
    print(f"  matching {len(ir_values)} unique IRs against hr.employee.ir_number...")
    # Batch the IN clause; XML-RPC can handle large lists but we keep it sane.
    by_ir = {}
    CHUNK = 2000
    for i in range(0, len(ir_values), CHUNK):
        chunk = ir_values[i:i + CHUNK]
        found = rpc(models, db, uid, password, "hr.employee", "search_read",
                    [("ir_number", "in", chunk)], ["id", "ir_number"])
        for rec in found:
            by_ir[rec["ir_number"]] = rec["id"]

    mapping = {}
    missing = 0
    for short, ir in irs:
        if ir in by_ir:
            mapping[short] = by_ir[ir]
        else:
            missing += 1
    if missing:
        print(f"  ! {missing} seed employees not yet in DB — they will be CREATED on load")
    return mapping


def _walk_location_paths(models, db, uid, password):
    """Build {db_id: 'A / B / C'} for every generic.location."""
    rows = rpc(models, db, uid, password, "generic.location", "search_read",
               [], ["id", "name", "parent_id"])
    by_id = {r["id"]: r for r in rows}
    def path(rid):
        parts = []
        cur = by_id.get(rid)
        while cur:
            parts.append(cur["name"])
            pid = cur["parent_id"][0] if cur["parent_id"] else None
            cur = by_id.get(pid) if pid else None
        return PATH_SEP.join(reversed(parts))
    return {rid: path(rid) for rid in by_id}, by_id


def plan_locations(models, db, uid, password):
    """{short_xid_name -> generic.location.id} from asset CSVs.

    Strategy:
      1. Extract (xid, leaf_name, path_string) per row.
      2. For each unique (leaf, path) pair: find generic.location whose
         computed path matches exactly.
      3. If no exact path match: fall back to unique-name match.
      4. Else skip (asset will load with empty location_id).
    """
    refs = {}  # {xid: (leaf_name, path_string)}
    for path in ASSET_CSVS:
        with open(path) as f:
            for r in csv.DictReader(f):
                xid  = r.get("location_id/id", "").strip()
                name = r.get("location_id/name", "").strip()
                pth  = r.get("location_id", "").strip()
                if xid and (name or pth):
                    refs[xid] = (name, pth)

    print(f"  {len(refs)} distinct location external IDs referenced")

    paths_by_id, by_id = _walk_location_paths(models, db, uid, password)
    # Reverse: path -> [ids]
    ids_by_path = {}
    for rid, p in paths_by_id.items():
        ids_by_path.setdefault(p, []).append(rid)
    # Name index
    ids_by_name = {}
    for rid, rec in by_id.items():
        ids_by_name.setdefault(rec["name"], []).append(rid)

    mapping = {}
    by_path = by_name = ambiguous = unresolved = 0
    samples_unresolved = []
    for xid, (leaf, pth) in refs.items():
        _, short = split_xid(xid)
        if not short:
            continue
        # 1) Try exact path
        if pth and pth in ids_by_path and len(ids_by_path[pth]) == 1:
            mapping[short] = ids_by_path[pth][0]
            by_path += 1
            continue
        # 2) Try unique name
        candidates = ids_by_name.get(leaf, [])
        if len(candidates) == 1:
            mapping[short] = candidates[0]
            by_name += 1
            continue
        if len(candidates) > 1:
            ambiguous += 1
        else:
            unresolved += 1
        if len(samples_unresolved) < 5:
            samples_unresolved.append((short, leaf, pth, len(candidates)))

    print(f"  resolved: path={by_path}, unique-name={by_name}")
    print(f"  unresolved: ambiguous={ambiguous}, missing={unresolved}")
    if samples_unresolved:
        print(f"  samples (xid, leaf, path, name-candidates):")
        for s in samples_unresolved:
            print(f"    {s}")
    return mapping


# ─── main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url",      default=os.getenv("ODOO_URL"))
    ap.add_argument("--db",       default=os.getenv("ODOO_DB"))
    ap.add_argument("--user",     default=os.getenv("ODOO_USER"))
    ap.add_argument("--password", default=os.getenv("ODOO_PASSWORD"))
    ap.add_argument("--dry-run",  action="store_true",
                    help="resolve mappings + print stats; create nothing")
    args = ap.parse_args()
    if not all([args.url, args.db, args.user, args.password]):
        sys.exit("Provide --url/--db/--user/--password or ODOO_* env vars.")

    print(f"Connecting to {args.url} (db={args.db}) ...")
    uid, models = connect(args.url, args.db, args.user, args.password)
    print(f"Authenticated as uid={uid}")
    if args.dry_run:
        print("DRY RUN — no writes will be made.\n")

    print("\n── hr.department ──")
    dept_map = plan_departments(models, args.db, uid, args.password)
    upsert_xids(models, args.db, uid, args.password, "hr.department",
                dept_map, args.dry_run, "hr.department")

    print("\n── hr.employee ──")
    emp_map = plan_employees(models, args.db, uid, args.password)
    upsert_xids(models, args.db, uid, args.password, "hr.employee",
                emp_map, args.dry_run, "hr.employee")

    print("\n── generic.location ──")
    loc_map = plan_locations(models, args.db, uid, args.password)
    upsert_xids(models, args.db, uid, args.password, "generic.location",
                loc_map, args.dry_run, "generic.location")

    print("\nDone." + ("  (dry-run — nothing written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
