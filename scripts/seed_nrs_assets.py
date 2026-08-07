#!/usr/bin/env python3
"""
NRS Asset Register — seed / import script
=========================================
Loads the reference data, employees, and assets into Odoo in dependency order,
via the standard external XML-RPC API using each model's `load()` method (the
same path Odoo's CSV import uses, so external IDs and relational `/id` columns
resolve automatically and re-running UPDATES rather than duplicates).

Load order (enforced):
    1. hr.department      01_references/IMPORT_ref_hr_department.csv
    2. hr.job             01_references/IMPORT_ref_hr_job.csv
    3. hr.employee        02_employees/IMPORT_employees_hr_employee.csv
    4. nrs.asset (ICT)    03_assets_ict/IMPORT_ALL_ICT_nrs_asset.csv
    5. nrs.asset (fleet)  04_assets_fleet/IMPORT_fleet_nrs_asset.csv

generic.location already exists in the target DB and is referenced by
`location_id/id`, so it is NOT loaded here.

Usage:
    python seed_nrs_assets.py \
        --url https://erp.example.gov.ng --db nrs_prod \
        --user admin --password '****' [--ensure-fields] [--dry-run]

Environment variables (alternative to flags):
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD

Notes:
  * --ensure-fields creates the custom x_* fields (see CUSTOM_FIELDS) if absent.
    Run once with an admin account before the first load, or pre-create the
    fields in Studio. Without these fields the x_* columns are ignored on load.
  * --dry-run validates connectivity and file/column presence without writing.
  * The script batches rows to keep payloads reasonable.
"""
import argparse, csv, os, sys, xmlrpc.client

HERE = os.path.dirname(os.path.abspath(__file__))

# Default location of the NRS_asset_seed CSV pack. Override with --seed-dir
# when the pack lives elsewhere (e.g. when running from a different repo
# checkout or a downloaded share). The pack is gitignored — never committed.
DEFAULT_SEED_DIR = os.path.normpath(
    os.path.join(HERE, "..", "docs", "seed", "NRS_asset_seed"))

# (model, relative path) in dependency order
LOAD_PLAN = [
    ("hr.department", "01_references/IMPORT_ref_hr_department.csv"),
    ("hr.job",        "01_references/IMPORT_ref_hr_job.csv"),
    ("hr.employee",   "02_employees/IMPORT_employees_hr_employee.csv"),
    ("nrs.asset",     "03_assets_ict/IMPORT_ALL_ICT_nrs_asset.csv"),
    ("nrs.asset",     "04_assets_fleet/IMPORT_fleet_nrs_asset.csv"),
]

# Custom fields the package relies on (created when --ensure-fields is passed).
# type: char unless noted. These hold the IR key, drill-downs, and review/audit data.
CUSTOM_FIELDS = {
    "hr.employee": [
        ("x_ir_number", "IR Number (NRS/contractor)", "char"),
    ],
    "nrs.asset": [
        ("x_asset_type",            "Asset Type",            "char"),
        ("x_model",                 "Model",                 "char"),
        ("x_model_series",          "Model Series",          "char"),
        ("x_registration_no",       "Registration No",       "char"),
        ("x_engine_no",             "Engine No",             "char"),
        ("x_custodian_score",       "Custodian Match Score", "char"),
        ("x_custodian_decision",    "Custodian Decision",    "char"),
        ("x_match_confidence",      "Location Match Conf.",  "char"),
        ("x_approval_status",       "Approval Status",       "char"),
        ("x_import_review_status",  "Import Review Status",  "char"),
        ("x_review_flags",          "Review Flags",          "text"),
        ("x_possible_duplicate_of", "Possible Duplicate Of", "char"),
    ],
}

BATCH = 500

# Per-model value normalizations applied to specific CSV columns at load time.
# Use when the source data uses a label that doesn't match our Selection options
# and the difference is small enough that a redirect is preferable to a model
# change. Mappings are case-sensitive and applied before model.load().
VALUE_MAPS = {
    "nrs.asset": {
        # Our condition Selection: new / good / fair / poor / decommissioned.
        # The CSV uses 'Faulty' (~274 rows) which has no exact equivalent —
        # fold to Poor as the closest match; revisit if Faulty deserves its
        # own option.
        "condition": {"Faulty": "Poor"},
    },
}


import http.client as _http_client
import socket as _socket
import time as _time

# Transient network errors worth retrying — a single-worker Odoo recycles under
# the import load (limit_memory_hard) and briefly refuses connections. NOT
# xmlrpc.client.Fault (that's a real application/validation error).
_RETRY_ERRORS = (ConnectionError, _socket.timeout, _socket.gaierror,
                 _http_client.HTTPException, xmlrpc.client.ProtocolError, OSError)


class _RetryProxy:
    """Wraps the /object ServerProxy so execute_kw retries transient network
    errors with backoff, recreating the (possibly dead) socket each attempt."""

    def __init__(self, url, retries=10, backoff=3.0):
        self._url, self._retries, self._backoff = url, retries, backoff
        self._proxy = xmlrpc.client.ServerProxy(url)

    def execute_kw(self, *args):
        last = None
        for attempt in range(self._retries):
            try:
                return self._proxy.execute_kw(*args)
            except _RETRY_ERRORS as e:
                last = e
                self._proxy = xmlrpc.client.ServerProxy(self._url)
                _time.sleep(self._backoff * (attempt + 1))
        raise last if last is not None else RuntimeError("execute_kw: retries exhausted")


def connect(url, db, user, password):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, password, {})
    if not uid:
        sys.exit("Authentication failed — check --url/--db/--user/--password.")
    models = _RetryProxy(f"{url}/xmlrpc/2/object")
    return uid, models


def call(models, db, uid, password, model, method, *args):
    return models.execute_kw(db, uid, password, model, method, list(args))


def ensure_fields(models, db, uid, password):
    for model, fields in CUSTOM_FIELDS.items():
        model_ids = call(models, db, uid, password, "ir.model", "search",
                         [["model", "=", model]])
        if not model_ids:
            print(f"  ! model {model} not found; skipping its custom fields")
            continue
        mid = model_ids[0]
        for name, label, ftype in fields:
            exists = call(models, db, uid, password, "ir.model.fields", "search",
                          [["model", "=", model], ["name", "=", name]])
            if exists:
                print(f"  = {model}.{name} exists")
                continue
            call(models, db, uid, password, "ir.model.fields", "create",
                 {"model_id": mid, "model": model, "name": name,
                  "field_description": label, "ttype": ftype, "state": "manual"})
            print(f"  + created {model}.{name} ({ftype})")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def load_file(models, db, uid, password, model, path, dry_run):
    header, data = read_csv(path)
    if not header:
        print(f"  ! {path} empty; skipped")
        return

    # Header preprocessing for Odoo's load() to match what our schema accepts:
    #   1. Drop CSV-export artifacts (`<col>.1`, `.2`, … = pandas duplicate-header).
    #   2. For each relational field <x>_id, prefer External ID lookup if available:
    #        if `<x>_id/id` is present → keep ONLY that one, drop bare and /name
    #        else if `<x>_id/name` is present → keep that, drop bare
    #        else if bare `<x>_id` is present → rename to `<x>_id/name`
    #      This avoids "Can not create Many-To-One records indirectly" errors
    #      that fire when multiple variants disagree or a bare value implies
    #      a create.
    #   3. Drop columns we know clash with our schema (model-specific).
    drop_idx = {i for i, h in enumerate(header)
                if "." in h and h.split(".")[-1].isdigit()}

    # nrs.asset.domain is a Selection (FM Domain) on our model; the seed CSV
    # repurposes it as a free-text System Domain Name → drop to avoid
    # "value not found in selection field" rejections on every row.
    if model == "nrs.asset":
        drop_idx |= {i for i, h in enumerate(header) if h == "domain"}

    # Drop columns that are blank in every row — Odoo's load() still processes
    # the header and a relational column with no values can still trigger
    # "Can not create Many-To-One records indirectly" errors.
    for i, h in enumerate(header):
        if i in drop_idx or h == "id":  # keep `id` (the External ID anchor)
            continue
        if all(not (row[i] if i < len(row) else "").strip() for row in data):
            drop_idx.add(i)

    # Group relational variants by base name.
    #   - When `<x>_id/id` (External ID) is present, drop the other two — the
    #     External ID lookup is unambiguous and bare/`/name` would conflict
    #     ("Can not create Many-To-One records indirectly").
    #   - When only `<x>_id/name` exists alongside a bare, drop the bare.
    #   - When only the bare `<x>_id` is present, KEEP IT — Odoo's load()
    #     interprets bare M2O columns as a display_name lookup; the explicit
    #     `<x>_id/name` syntax wrongly insists on indirect-create semantics.
    bases = {}
    for i, h in enumerate(header):
        if h.endswith("/id"):       bases.setdefault(h[:-3], {})["id"]   = i
        elif h.endswith("/name"):   bases.setdefault(h[:-5], {})["name"] = i
        elif h.endswith("_id") and "/" not in h:
                                    bases.setdefault(h, {})["bare"] = i

    rename = {}
    for base, variants in bases.items():
        if "id" in variants:
            for k in ("bare", "name"):
                if k in variants:
                    drop_idx.add(variants[k])
        elif "name" in variants and "bare" in variants:
            drop_idx.add(variants["bare"])

    if drop_idx or rename:
        if drop_idx:
            print(f"    (dropped: {', '.join(header[i] for i in sorted(drop_idx))})")
        if rename:
            print(f"    (renamed: {', '.join(f'{header[i]}→{v}' for i, v in rename.items())})")
        keep = [i for i in range(len(header)) if i not in drop_idx]
        header = [(rename[i] if i in rename else header[i]) for i in keep]
        data   = [[row[i] for i in keep] for row in data]

    # Value normalisation per (model, column) — see VALUE_MAPS docstring.
    vmap = VALUE_MAPS.get(model, {})
    if vmap:
        col_to_idx = {h: i for i, h in enumerate(header)}
        applied = {}
        for col, mapping in vmap.items():
            ci = col_to_idx.get(col)
            if ci is None:
                continue
            for row in data:
                v = row[ci]
                if v in mapping:
                    row[ci] = mapping[v]
                    applied[col] = applied.get(col, 0) + 1
        if applied:
            for col, n in applied.items():
                print(f"    (normalised {n} row(s) in {col} via VALUE_MAPS)")

    print(f"  {model}: {len(data)} rows from {os.path.basename(path)}")
    if dry_run:
        print(f"    [dry-run] columns: {', '.join(header)}")
        return
    ok = err = 0
    for i in range(0, len(data), BATCH):
        chunk = data[i:i + BATCH]
        res = call(models, db, uid, password, model, "load", header, chunk)
        msgs = res.get("messages") or []
        if msgs:
            err += len(chunk)
            for m in msgs[:5]:
                print(f"    ERROR row~{i}: {m.get('message')}")
        else:
            ok += len(res.get("ids") or chunk)
    print(f"    loaded ~{ok}, errors ~{err}")


def main():
    ap = argparse.ArgumentParser(description="Seed NRS asset register into Odoo")
    ap.add_argument("--url", default=os.getenv("ODOO_URL"))
    ap.add_argument("--db", default=os.getenv("ODOO_DB"))
    ap.add_argument("--user", default=os.getenv("ODOO_USER"))
    ap.add_argument("--password", default=os.getenv("ODOO_PASSWORD"))
    ap.add_argument("--ensure-fields", action="store_true",
                    help="create x_* custom fields if missing (admin required)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate without writing")
    ap.add_argument("--seed-dir", default=os.getenv("CADRA_SEED_DIR", DEFAULT_SEED_DIR),
                    help=f"directory containing the seed pack "
                         f"(default: {DEFAULT_SEED_DIR})")
    args = ap.parse_args()
    if not all([args.url, args.db, args.user, args.password]):
        sys.exit("Provide --url/--db/--user/--password (or ODOO_* env vars).")

    print(f"Connecting to {args.url} (db={args.db}) ...")
    uid, models = connect(args.url, args.db, args.user, args.password)
    print(f"Authenticated as uid={uid}")

    if args.ensure_fields:
        print("Ensuring custom fields ...")
        ensure_fields(models, args.db, uid, args.password)

    if not os.path.isdir(args.seed_dir):
        sys.exit(f"--seed-dir not found: {args.seed_dir}")

    print(f"Loading data in dependency order from {args.seed_dir} ...")
    for model, rel in LOAD_PLAN:
        path = os.path.join(args.seed_dir, rel)
        if not os.path.exists(path):
            print(f"  ! missing {rel}; skipped")
            continue
        load_file(models, args.db, uid, args.password, model, path, args.dry_run)

    print("Done." + ("  (dry-run — nothing written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
