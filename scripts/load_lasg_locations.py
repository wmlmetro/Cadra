#!/usr/bin/env python3
"""
Load Lagos State Ministry of Health facility locations into generic.location.

Reads scripts/lasg_locations.json (90 real Lagos State public health facilities
— 60 Primary Health Centres + 30 General/secondary hospitals — geocoded from
the client master list; hospitals have precise addresses, PHCs are geocoded to
ward/area centroids). Builds a tree:

    Lagos State Ministry of Health — Facilities   (root)
      └── <LGA>            (e.g. Ikeja, Alimosho, Ikorodu)   → "zone" tier
            └── <Facility>  with latitude / longitude        → "building" (marker)

The FM/operations dashboards plot every generic.location that has latitude &
longitude set (see myservice_fm_dashboard/controllers/dashboard.py), so the
facility level is what shows up on the map.

Exec'd by scripts/bootstrap.py with `env` in scope (no __main__).
Idempotent: re-running matches existing records by (name, parent).
"""
import json
import os
import logging

_logger = logging.getLogger("cadra.seed.lasg_locations")

# Resolve the data file against both layouts. NOTE: bootstrap.py exec()s this
# file with only {"env": env} in scope, so __file__ is NOT defined — use
# absolute paths, not os.path.dirname(__file__). scripts/ is bind-mounted at
# /mnt/extra-addons/scripts in dev and copied to /opt/cadra/scripts in k8s.
_CANDIDATES = [
    "/mnt/extra-addons/scripts/lasg_locations.json",  # dev (compose bind-mount)
    "/opt/cadra/scripts/lasg_locations.json",         # k8s image
]


def _data_path():
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("lasg_locations.json not found in: %s" % ", ".join(_CANDIDATES))


def _loc_model(env):
    models = env["ir.model"].search([]).mapped("model")
    model = next((m for m in models if m == "generic.location"), None)
    if not model:
        model = next((m for m in models if "location" in m and "generic" in m), None)
    if not model:
        raise RuntimeError(
            "generic.location model not found — is the generic_location module installed?"
        )
    return model


def _get_or_create(env, model, name, parent_id=None, vals=None):
    Loc = env[model]
    domain = [("name", "=", name)]
    if parent_id:
        domain.append(("parent_id", "=", parent_id))
    rec = Loc.search(domain, limit=1)
    fields = Loc.fields_get()
    # Keep only fields the model actually has (drops coords/location_type on
    # models that lack them).
    create_vals = {k: v for k, v in (vals or {}).items() if k in fields}
    create_vals["name"] = name
    if parent_id and "parent_id" in fields:
        create_vals["parent_id"] = parent_id
    if rec:
        # Backfill any provided field that is currently empty.
        patch = {k: v for k, v in create_vals.items()
                 if k not in ("name", "parent_id") and not rec[k]}
        if patch:
            rec.write(patch)
        return rec
    return Loc.create(create_vals)


def load_lasg_locations(env):
    model = _loc_model(env)
    _logger.info("LASG locations → using model %s", model)
    facilities = json.load(open(_data_path()))

    root = _get_or_create(env, model, "Lagos State Ministry of Health — Facilities")
    lgas = {}
    stats = {"lgas": 0, "facilities": 0, "phc": 0, "hospital": 0,
             "geocoded": 0, "approximate": 0}

    for f in facilities:
        lga_name = (f.get("lga") or "Unknown").strip() or "Unknown"
        lga = lgas.get(lga_name)
        if lga is None:
            # Each LGA becomes a "zone" tier so the frontend Locations page
            # groups facilities by Local Government Area (the location_type
            # Selection has no "lga" key — only building/floor/wing/room/zone).
            lga = _get_or_create(env, model, lga_name, parent_id=root.id,
                                 vals={"location_type": "zone"})
            lgas[lga_name] = lga
            stats["lgas"] += 1

        # Facilities (PHCs + hospitals) are buildings → "building" maps to the
        # map marker / Office tier in the frontend.
        _get_or_create(
            env, model, f["name"], parent_id=lga.id,
            vals={"latitude": f["lat"], "longitude": f["lng"],
                  "location_type": "building"},
        )
        stats["facilities"] += 1
        if (f.get("category") or "").lower().startswith("general") or "hospital" in (f.get("category") or "").lower():
            stats["hospital"] += 1
        else:
            stats["phc"] += 1
        stats["geocoded" if f.get("source") == "geocoded" else "approximate"] += 1

    env.cr.commit()

    # Robust location_type backfill via RAW SQL (ORM writes in this pipeline have
    # been observed to silently roll back, leaving the frontend Locations page
    # blank). In a LASG tenant DB every row is a LASG location: facilities with
    # coords → "building"; their parent LGA nodes → "zone".
    env.cr.execute("""
        UPDATE generic_location SET location_type = 'building'
        WHERE latitude IS NOT NULL
          AND location_type IS DISTINCT FROM 'building'
    """)
    building_n = env.cr.rowcount
    env.cr.execute("""
        UPDATE generic_location SET location_type = 'zone'
        WHERE latitude IS NULL AND parent_id IS NOT NULL
          AND location_type IS DISTINCT FROM 'zone'
    """)
    zone_n = env.cr.rowcount
    env.cr.commit()

    _logger.info(
        "\n  ✅ LASG facilities loaded\n"
        "  ───────────────────────\n"
        "  LGAs       : %(lgas)d\n"
        "  Facilities : %(facilities)d  (PHC=%(phc)d, hospital=%(hospital)d)\n"
        "  Geocoding  : geocoded=%(geocoded)d, approximate=%(approximate)d\n",
        stats,
    )
    print(f"  ✓ LASG locations: {stats}")
    print(f"  ✓ location_type set via SQL → facilities/building={building_n}, LGAs/zone={zone_n}")


load_lasg_locations(env)  # noqa: F821  (env injected by bootstrap.py)
