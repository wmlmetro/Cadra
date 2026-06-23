#!/usr/bin/env python3
"""
Load Guaranty Trust Bank (GTB) branch locations into generic.location.

Reads seeds/gtb_locations.json (122 Nigerian branches: 41 real, sourced from
OpenStreetMap, + 81 demo-fill across the remaining states — each tagged with a
`demo` flag and `source`). Builds a tree:

    Guaranty Trust Bank — Nigeria   (root)
      └── <State>                   (e.g. Lagos, Rivers, FCT)
            └── <Branch>            with latitude / longitude  → map markers

The FM/operations dashboards plot every generic.location that has
latitude & longitude set (see myservice_fm_dashboard/controllers/dashboard.py),
so the branch level is what shows up on the map.

Exec'd by scripts/bootstrap.py with `env` in scope (no __main__).
Idempotent: re-running matches existing records by (name, parent).
"""
import json
import os
import logging

_logger = logging.getLogger("cadra.seed.gtb_locations")

# Resolve the data file against both layouts. NOTE: bootstrap.py exec()s this
# file with only {"env": env} in scope, so __file__ is NOT defined — use
# absolute paths, not os.path.dirname(__file__). scripts/ is bind-mounted at
# /mnt/extra-addons/scripts in dev and copied to /opt/cadra/scripts in k8s.
_CANDIDATES = [
    "/mnt/extra-addons/scripts/gtb_locations.json",  # dev (compose bind-mount)
    "/opt/cadra/scripts/gtb_locations.json",         # k8s image
]


def _data_path():
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("gtb_locations.json not found in: %s" % ", ".join(_CANDIDATES))


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
    create_vals = dict(vals or {})
    create_vals["name"] = name
    fields = Loc.fields_get()
    if parent_id and "parent_id" in fields:
        create_vals["parent_id"] = parent_id
    # Drop any coord fields the model doesn't actually have.
    for f in ("latitude", "longitude"):
        if f in create_vals and f not in fields:
            create_vals.pop(f)
    if rec:
        # Backfill coordinates on an existing record if missing.
        patch = {f: create_vals[f] for f in ("latitude", "longitude")
                 if f in create_vals and not rec[f]}
        if patch:
            rec.write(patch)
        return rec
    return Loc.create(create_vals)


def load_gtb_locations(env):
    model = _loc_model(env)
    _logger.info("GTB locations → using model %s", model)
    branches = json.load(open(_data_path()))

    root = _get_or_create(env, model, "Guaranty Trust Bank — Nigeria")
    states = {}
    stats = {"states": 0, "branches": 0, "real": 0, "demo": 0}

    for b in branches:
        state_name = (b.get("state") or "Unknown").strip() or "Unknown"
        state = states.get(state_name)
        if state is None:
            state = _get_or_create(env, model, state_name, parent_id=root.id)
            states[state_name] = state
            stats["states"] += 1

        _get_or_create(
            env, model, b["name"], parent_id=state.id,
            vals={"latitude": b["lat"], "longitude": b["lng"]},
        )
        stats["branches"] += 1
        stats["real" if not b.get("demo") else "demo"] += 1

    env.cr.commit()
    _logger.info(
        "\n  ✅ GTB branches loaded\n"
        "  ──────────────────────\n"
        "  States   : %(states)d\n"
        "  Branches : %(branches)d  (real=%(real)d, demo-fill=%(demo)d)\n",
        stats,
    )
    print("  ✓ GTB locations:", stats)


load_gtb_locations(env)  # noqa: F821  (env injected by bootstrap.py)
