#!/usr/bin/env python3
"""
NRS Facilities Service Manager — Office / Site Importer
========================================================
Reads NRS's office list from a CSV file and creates Office → Building →
Floor records under the city nodes already loaded by load_locations.py.

Expected CSV columns (case-insensitive, any order):
    office_name     : Display name of the office / site
    office_code     : Short unique code  e.g. ABJ-HQ, LAG-01
    city            : Must match a city name already in generic.location
    state           : Used to disambiguate cities with same name
    address         : Street address (stored in notes/description if field exists)
    buildings       : Comma-separated building names (optional)
                      e.g. "Block A, Block B, Annex"

Minimal CSV (only required columns):
    office_name, office_code, city, state

Usage:
    # Copy your CSV to the server, then in Odoo shell:
    OFFICES_CSV = '/opt/odoo/myservice_itsm/locations/nrs_offices.csv'
    exec(open('/opt/odoo/myservice_itsm/data/load_offices.py').read())

Or pass path at runtime:
    OFFICES_CSV = '/path/to/your/file.csv'
    exec(open('load_offices.py').read())

Template CSV is at: locations/nrs_offices_template.csv
"""

import csv
import logging
import os

_logger = logging.getLogger(__name__)

# Override this path before exec()-ing if needed
OFFICES_CSV = globals().get("OFFICES_CSV", "/opt/odoo/myservice_itsm/locations/nrs_offices.csv")


# =============================================================================
# HELPERS
# =============================================================================

def find_location(env, LOC_MODEL, name, parent_name=None):
    """Find a location by name, optionally scoped to a parent."""
    domain = [("name", "ilike", name)]
    if parent_name:
        parent = env[LOC_MODEL].search([("name", "ilike", parent_name)], limit=1)
        if parent:
            domain.append(("parent_id", "=", parent.id))
    return env[LOC_MODEL].search(domain, limit=1)


def get_or_create_loc(env, LOC_MODEL, name, code, parent_id=None, notes=None):
    domain = [("name", "=", name)]
    if parent_id:
        domain.append(("parent_id", "=", parent_id))
    record = env[LOC_MODEL].search(domain, limit=1)
    if record:
        return record, False
    vals = {"name": name}
    loc_fields = env[LOC_MODEL].fields_get()
    if "code" in loc_fields:
        vals["code"] = code
    if parent_id and "parent_id" in loc_fields:
        vals["parent_id"] = parent_id
    if notes and "description" in loc_fields:
        vals["description"] = notes
    elif notes and "note" in loc_fields:
        vals["note"] = notes
    record = env[LOC_MODEL].create(vals)
    return record, True


# =============================================================================
# MAIN LOADER
# =============================================================================

def load_offices(env, csv_path=None):
    csv_path = csv_path or OFFICES_CSV

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Offices CSV not found: {csv_path}\n"
            "Copy your NRS office list to that path, or set OFFICES_CSV before running.\n"
            "Use locations/nrs_offices_template.csv as your starting template."
        )

    all_models = env['ir.model'].search([]).mapped('model')
    LOC_MODEL = next((m for m in all_models if m == 'generic.location'), None)
    if not LOC_MODEL:
        LOC_MODEL = next((m for m in all_models if 'location' in m and 'generic' in m), None)
    if not LOC_MODEL:
        raise RuntimeError("generic.location model not found. Run load_locations.py first.")

    stats = {"offices": 0, "buildings": 0, "skipped": 0, "errors": []}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # normalise column names to lowercase stripped
        rows = [{k.strip().lower(): v.strip() for k, v in row.items()} for row in reader]

    for i, row in enumerate(rows, start=2):   # row 1 = header
        office_name = row.get("office_name", "").strip()
        office_code = row.get("office_code", "").strip()
        city_name   = row.get("city", "").strip()
        state_name  = row.get("state", "").strip()
        address     = row.get("address", "").strip()
        buildings   = [b.strip() for b in row.get("buildings", "").split(",") if b.strip()]

        if not office_name or not city_name:
            _logger.warning("Row %d: missing office_name or city — skipped", i)
            stats["skipped"] += 1
            continue

        # Locate parent city
        city = find_location(env, LOC_MODEL, city_name, parent_name=state_name or None)
        if not city:
            msg = f"Row {i}: city '{city_name}' not found in location tree — skipped. " \
                  f"Run load_locations.py first or add the city manually."
            _logger.warning(msg)
            stats["errors"].append(msg)
            stats["skipped"] += 1
            continue

        # Create Office node
        office, created = get_or_create_loc(
            env, LOC_MODEL,
            office_name,
            office_code or f"OFF-{i:04d}",
            parent_id=city.id,
            notes=address or None,
        )
        if created:
            stats["offices"] += 1
            _logger.info("CREATED office: %s under %s", office_name, city_name)
        else:
            _logger.info("EXISTS  office: %s", office_name)

        # Create Building sub-nodes
        for bldg_name in buildings:
            bldg_code = f"{office_code}-{bldg_name[:4].upper().replace(' ', '')}"
            _, bldg_created = get_or_create_loc(
                env, LOC_MODEL,
                bldg_name,
                bldg_code,
                parent_id=office.id,
            )
            if bldg_created:
                stats["buildings"] += 1

    if stats["errors"]:
        _logger.warning("\n  ⚠️  %d rows had unresolved cities:\n  %s",
                        len(stats["errors"]), "\n  ".join(stats["errors"]))

    _logger.info(
        "\n\n  ✅  NRS Offices Loaded\n"
        "  ─────────────────────────────────────\n"
        "  Offices created   : %d\n"
        "  Buildings created : %d\n"
        "  Rows skipped      : %d\n",
        stats["offices"], stats["buildings"], stats["skipped"],
    )
    return stats


# =============================================================================
# ENTRY POINT
# =============================================================================

if "env" in dir():
    with env.cr.savepoint():
        result = load_offices(env)
        env.cr.commit()
        print(f"\n✅  Done. {result}")
else:
    print("load_offices.py loaded. Set OFFICES_CSV then call load_offices(env).")
