#!/usr/bin/env python3
"""
Load Jaiz Bank Plc branch locations into generic.location.

Reads scripts/jaiz_locations.json (39 real Nigerian branches, supplied by the
client with verified/approximate coordinates + addresses). Builds a tree:

    Jaiz Bank Plc — Nigeria   (root)
      └── <State>             (e.g. Lagos, Kano, FCT)   → "zone" tier
            └── <Branch>      with latitude / longitude → "building" (map marker)

The FM/operations dashboards plot every generic.location that has
latitude & longitude set (see myservice_fm_dashboard/controllers/dashboard.py),
so the branch level is what shows up on the map.

Exec'd by scripts/bootstrap.py with `env` in scope (no __main__).
Idempotent: re-running matches existing records by (name, parent).
"""
import json
import os
import logging

_logger = logging.getLogger("cadra.seed.jaiz_locations")

# Resolve the data file against both layouts. NOTE: bootstrap.py exec()s this
# file with only {"env": env} in scope, so __file__ is NOT defined — use
# absolute paths, not os.path.dirname(__file__). scripts/ is bind-mounted at
# /mnt/extra-addons/scripts in dev and copied to /opt/cadra/scripts in k8s.
_CANDIDATES = [
    "/mnt/extra-addons/scripts/jaiz_locations.json",  # dev (compose bind-mount)
    "/opt/cadra/scripts/jaiz_locations.json",         # k8s image
]


def _data_path():
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("jaiz_locations.json not found in: %s" % ", ".join(_CANDIDATES))


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


def load_jaiz_locations(env):
    model = _loc_model(env)
    _logger.info("Jaiz locations → using model %s", model)
    branches = json.load(open(_data_path()))

    root = _get_or_create(env, model, "Jaiz Bank Plc — Nigeria")
    states = {}
    stats = {"states": 0, "branches": 0, "real": 0, "demo": 0}

    for b in branches:
        state_name = (b.get("state") or "Unknown").strip() or "Unknown"
        state = states.get(state_name)
        if state is None:
            # Each state becomes a "zone" tier so the frontend Locations page
            # groups branches by state (the location_type Selection has no
            # "state" key — only building/floor/wing/room/zone).
            state = _get_or_create(env, model, state_name, parent_id=root.id,
                                   vals={"location_type": "zone"})
            states[state_name] = state
            stats["states"] += 1

        # Branches are bank offices → "building" maps to Office in the frontend.
        _get_or_create(
            env, model, b["name"], parent_id=state.id,
            vals={"latitude": b["lat"], "longitude": b["lng"],
                  "location_type": "building"},
        )
        stats["branches"] += 1
        stats["real" if not b.get("demo") else "demo"] += 1

    env.cr.commit()

    # Robust location_type backfill via RAW SQL (ORM writes in this pipeline have
    # been observed to silently roll back, leaving the frontend Locations page
    # blank). In a Jaiz tenant DB every row is a Jaiz location: branches with
    # coords → "building"; their parent state nodes → "zone".
    env.cr.execute("""
        UPDATE generic_location SET location_type = 'building'
        WHERE latitude IS NOT NULL
          AND location_type IS DISTINCT FROM 'building'
    """)
    branch_n = env.cr.rowcount
    env.cr.execute("""
        UPDATE generic_location SET location_type = 'zone'
        WHERE latitude IS NULL AND parent_id IS NOT NULL
          AND location_type IS DISTINCT FROM 'zone'
    """)
    zone_n = env.cr.rowcount
    env.cr.commit()

    _logger.info(
        "\n  ✅ Jaiz branches loaded\n"
        "  ───────────────────────\n"
        "  States   : %(states)d\n"
        "  Branches : %(branches)d  (real=%(real)d)\n",
        stats,
    )
    print(f"  ✓ Jaiz locations: {stats}")
    print(f"  ✓ location_type set via SQL → branches/building={branch_n}, states/zone={zone_n}")


load_jaiz_locations(env)  # noqa: F821  (env injected by bootstrap.py)
