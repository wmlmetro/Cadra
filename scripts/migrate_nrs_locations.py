#!/usr/bin/env python3
"""
NRS location bridge for the 15 -> 19 cutover.

The NRS asset CSV pack (docs/seed/NRS_asset_seed) references locations by
Odoo export external IDs of the form `__export__.generic_location_<N>_<hash>`,
where <N> is the SOURCE (staging) generic_location database id. A fresh 19 DB
has neither those locations nor those external IDs, so the asset import can't
resolve `location_id/id`.

This script bridges that gap in two steps against a target 19 DB (via XML-RPC):

  1. Import the real NRS location tree exported from staging
     (scripts/export: nrs_locations_export.csv — columns id=nrs_loc_<N>,
     name, parent_id/id, location_type, zone_code, longitude, latitude,
     active). load() preserves hierarchy via the nrs_loc_<N> external ids.

  2. Rebuild the `__export__.generic_location_<N>_<hash>` external IDs the
     asset CSVs reference, each pointing at the freshly-imported location
     whose external id is nrs_loc_<N>. After this, seed_nrs_assets.py resolves
     location_id/id exactly (~98% of refs; the rest are source ids absent from
     the export and are reported).

Produce the CSV first (run against the SOURCE db):
  psql -d staging -tAc "COPY ( SELECT 'nrs_loc_'||id AS \"id\", name,
     CASE WHEN parent_id IS NOT NULL THEN 'nrs_loc_'||parent_id ELSE '' END
       AS \"parent_id/id\",
     COALESCE(location_type,''), COALESCE(zone_code,''),
     COALESCE(longitude::text,''), COALESCE(latitude::text,''),
     (CASE WHEN active THEN '1' ELSE '0' END)
     FROM generic_location ORDER BY parent_path ) TO STDOUT WITH CSV HEADER" \
     > nrs_locations_export.csv

Then (against the TARGET 19 db):
  python scripts/migrate_nrs_locations.py --url http://localhost:8369 \
     --db nrs19 --user admin --password admin \
     --locations-csv nrs_locations_export.csv \
     --asset-pack docs/seed/NRS_asset_seed
"""
import argparse
import csv
import glob
import os
import re
import sys
import xmlrpc.client

BATCH = 500
REF_RE = re.compile(r"^(__export__)\.(generic_location_(\d+)_[0-9a-f]+)$")


def connect(url, db, user, password):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, password, {})
    if not uid:
        sys.exit(f"Authentication failed for {user}@{db}")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    print(f"Authenticated as uid={uid}")
    return uid, models


def load_locations(models, db, uid, password, csv_path, dry):
    with open(csv_path, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    print(f"generic.location: {len(rows)} rows from {os.path.basename(csv_path)}")
    if dry:
        print(f"  [dry-run] columns: {', '.join(header)}")
        return
    loaded = errors = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        res = models.execute_kw(db, uid, password, "generic.location", "load",
                                [header, chunk])
        ids = [x for x in (res.get("ids") or []) if x]
        loaded += len(ids)
        for msg in res.get("messages", []):
            errors += 1
            if errors <= 10:
                print(f"    ERROR: {msg.get('message')}")
    print(f"  loaded ~{loaded}, errors ~{errors}")


def build_aliases(models, db, uid, password, asset_pack, dry):
    """Create __export__.generic_location_<N>_<hash> -> nrs_loc_<N> aliases."""
    refs = set()
    for f in glob.glob(os.path.join(asset_pack, "0[34]_assets*", "IMPORT_*_nrs_asset.csv")):
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh):
                x = (row.get("location_id/id") or "").strip()
                if x:
                    refs.add(x)
    print(f"asset location refs: {len(refs)} distinct")
    if dry:
        print("  [dry-run] not creating aliases")
        return
    IMD = "ir.model.data"
    # One bulk fetch of every imported location's external id (nrs_loc_<N>) →
    # res_id, and of existing __export__ location aliases. Avoids per-ref
    # round-trips (307×N XML-RPC calls is too slow).
    loc_imd = models.execute_kw(db, uid, password, IMD, "search_read",
                                [[["model", "=", "generic.location"],
                                  ["name", "like", "nrs_loc_%"]]],
                                {"fields": ["name", "res_id"]})
    by_n = {}
    for r in loc_imd:
        mm = re.match(r"nrs_loc_(\d+)$", r["name"])
        if mm:
            by_n[mm.group(1)] = r["res_id"]
    # Drop any existing __export__ location aliases and recreate them all in a
    # single batched create — 300+ per-record XML-RPC writes are too slow.
    old = models.execute_kw(db, uid, password, IMD, "search",
                            [[["model", "=", "generic.location"],
                              ["module", "=", "__export__"]]])
    if old:
        models.execute_kw(db, uid, password, IMD, "unlink", [old])
    vals, missing = [], 0
    for ref in sorted(refs):
        m = REF_RE.match(ref)
        if not m:
            continue
        _module, name, n = m.group(1), m.group(2), m.group(3)
        res_id = by_n.get(n)
        if not res_id:
            missing += 1
            continue
        vals.append({"module": "__export__", "name": name,
                     "model": "generic.location", "res_id": res_id})
    if vals:
        models.execute_kw(db, uid, password, IMD, "create", [vals])
    print(f"  aliases created={len(vals)} (dropped {len(old)}) missing_source={missing}")


def build_categories(models, db, uid, password, asset_pack, dry):
    """Create the nrs.asset.category / .subcategory records the asset CSVs
    reference by NAME (seed_nrs_assets matches them by name; missing ones make
    every asset row fail). Idempotent."""
    cats, subs = set(), {}
    for f in glob.glob(os.path.join(asset_pack, "0[34]_assets*", "IMPORT_*_nrs_asset.csv")):
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh):
                c = (row.get("category_id") or "").strip()
                s = (row.get("subcategory_id") or "").strip()
                if c:
                    cats.add(c)
                if s:
                    subs[s] = c
    print(f"asset taxonomy: {len(cats)} categories, {len(subs)} sub-categories")
    if dry:
        return
    Cat, Sub = "nrs.asset.category", "nrs.asset.subcategory"
    cat_id = {}
    for name in sorted(cats):
        found = models.execute_kw(db, uid, password, Cat, "search", [[["name", "=", name]]], {"limit": 1})
        cat_id[name] = found[0] if found else models.execute_kw(db, uid, password, Cat, "create", [{"name": name}])
    sfields = models.execute_kw(db, uid, password, Sub, "fields_get", [], {"attributes": ["type"]})
    for name, parent in sorted(subs.items()):
        if models.execute_kw(db, uid, password, Sub, "search_count", [[["name", "=", name]]]):
            continue
        vals = {"name": name}
        if "category_id" in sfields and parent in cat_id:
            vals["category_id"] = cat_id[parent]
        models.execute_kw(db, uid, password, Sub, "create", [vals])
    print(f"  categories ensured={len(cat_id)}, sub-categories ensured={len(subs)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("ODOO_URL"))
    ap.add_argument("--db", default=os.getenv("ODOO_DB"))
    ap.add_argument("--user", default=os.getenv("ODOO_USER"))
    ap.add_argument("--password", default=os.getenv("ODOO_PASSWORD"))
    ap.add_argument("--locations-csv", required=True)
    ap.add_argument("--asset-pack", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uid, models = connect(args.url, args.db, args.user, args.password)
    load_locations(models, args.db, uid, args.password, args.locations_csv, args.dry_run)
    build_aliases(models, args.db, uid, args.password, args.asset_pack, args.dry_run)
    build_categories(models, args.db, uid, args.password, args.asset_pack, args.dry_run)
    print("Done.")


main()
