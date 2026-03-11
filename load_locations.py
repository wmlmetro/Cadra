#!/usr/bin/env python3
"""
NRS Facilities Service Manager — Location Tree Loader
======================================================
Loads a Nigeria-wide zone → state → city skeleton into generic.location.
Office-level records (the 400+ sites) are loaded separately via
load_offices.py using NRS's own spreadsheet.

generic.location tree for NRS:
    Zone  (geo-political zone)
    └── State
        └── City / LGA
            └── Office / Site    ← loaded by load_offices.py
                └── Building
                    └── Floor
                        └── Wing / Room / Area

Location access is hierarchical: granting access to a Zone automatically
gives access to all States, Cities, and Offices below it.

Usage:
    exec(open('/opt/odoo/myservice_itsm/data/load_locations.py').read())
"""

import logging
_logger = logging.getLogger(__name__)

# =============================================================================
# NIGERIA ZONE → STATE SKELETON
# =============================================================================
# Extend the cities list per state to match NRS's actual office footprint.
# The loader is idempotent — safe to re-run.

LOCATION_TREE = [
    {
        "name": "North Central",
        "code": "NGA-NC",
        "states": [
            {"name": "Benue",           "code": "BEN", "cities": ["Makurdi", "Gboko", "Otukpo"]},
            {"name": "FCT Abuja",       "code": "FCT", "cities": ["Abuja Municipal", "Gwagwalada", "Kuje", "Bwari", "Abaji", "Kwali"]},
            {"name": "Kogi",            "code": "KOG", "cities": ["Lokoja", "Okene", "Idah"]},
            {"name": "Kwara",           "code": "KWA", "cities": ["Ilorin", "Offa", "Omu-Aran"]},
            {"name": "Nasarawa",        "code": "NAS", "cities": ["Lafia", "Keffi", "Akwanga"]},
            {"name": "Niger",           "code": "NGR", "cities": ["Minna", "Suleja", "Bida"]},
            {"name": "Plateau",         "code": "PLA", "cities": ["Jos", "Bukuru", "Pankshin"]},
        ],
    },
    {
        "name": "North East",
        "code": "NGA-NE",
        "states": [
            {"name": "Adamawa",         "code": "ADA", "cities": ["Yola", "Mubi", "Numan"]},
            {"name": "Bauchi",          "code": "BAU", "cities": ["Bauchi", "Azare", "Misau"]},
            {"name": "Borno",           "code": "BOR", "cities": ["Maiduguri", "Biu", "Konduga"]},
            {"name": "Gombe",           "code": "GOM", "cities": ["Gombe", "Kaltungo", "Billiri"]},
            {"name": "Taraba",          "code": "TAR", "cities": ["Jalingo", "Wukari", "Bali"]},
            {"name": "Yobe",            "code": "YOB", "cities": ["Damaturu", "Gashua", "Potiskum"]},
        ],
    },
    {
        "name": "North West",
        "code": "NGA-NW",
        "states": [
            {"name": "Jigawa",          "code": "JIG", "cities": ["Dutse", "Hadejia", "Gumel"]},
            {"name": "Kaduna",          "code": "KAD", "cities": ["Kaduna", "Zaria", "Kafanchan"]},
            {"name": "Kano",            "code": "KAN", "cities": ["Kano Municipal", "Wudil", "Bichi"]},
            {"name": "Katsina",         "code": "KAT", "cities": ["Katsina", "Daura", "Funtua"]},
            {"name": "Kebbi",           "code": "KEB", "cities": ["Birnin Kebbi", "Argungu", "Yauri"]},
            {"name": "Sokoto",          "code": "SOK", "cities": ["Sokoto", "Tambuwal", "Gwadabawa"]},
            {"name": "Zamfara",         "code": "ZAM", "cities": ["Gusau", "Kaura Namoda", "Talata Mafara"]},
        ],
    },
    {
        "name": "South East",
        "code": "NGA-SE",
        "states": [
            {"name": "Abia",            "code": "ABI", "cities": ["Umuahia", "Aba", "Ohafia"]},
            {"name": "Anambra",         "code": "ANA", "cities": ["Awka", "Onitsha", "Nnewi"]},
            {"name": "Ebonyi",          "code": "EBO", "cities": ["Abakaliki", "Afikpo", "Onueke"]},
            {"name": "Enugu",           "code": "ENU", "cities": ["Enugu", "Nsukka", "Agbani"]},
            {"name": "Imo",             "code": "IMO", "cities": ["Owerri", "Orlu", "Okigwe"]},
        ],
    },
    {
        "name": "South South",
        "code": "NGA-SS",
        "states": [
            {"name": "Akwa Ibom",       "code": "AKW", "cities": ["Uyo", "Ikot Ekpene", "Eket"]},
            {"name": "Bayelsa",         "code": "BAY", "cities": ["Yenagoa", "Ogbia", "Nembe"]},
            {"name": "Cross River",     "code": "CRV", "cities": ["Calabar", "Ikom", "Ogoja"]},
            {"name": "Delta",           "code": "DEL", "cities": ["Asaba", "Warri", "Sapele"]},
            {"name": "Edo",             "code": "EDO", "cities": ["Benin City", "Auchi", "Ekpoma"]},
            {"name": "Rivers",          "code": "RIV", "cities": ["Port Harcourt", "Bonny", "Degema"]},
        ],
    },
    {
        "name": "South West",
        "code": "NGA-SW",
        "states": [
            {"name": "Ekiti",           "code": "EKI", "cities": ["Ado Ekiti", "Ikere", "Ikole"]},
            {"name": "Lagos",           "code": "LAG", "cities": ["Lagos Island", "Lagos Mainland", "Ikeja", "Lekki", "Badagry", "Epe", "Ikorodu"]},
            {"name": "Ogun",            "code": "OGU", "cities": ["Abeokuta", "Sagamu", "Ijebu Ode"]},
            {"name": "Ondo",            "code": "OND", "cities": ["Akure", "Ondo", "Owo"]},
            {"name": "Osun",            "code": "OSU", "cities": ["Osogbo", "Ile-Ife", "Ilesa"]},
            {"name": "Oyo",             "code": "OYO", "cities": ["Ibadan", "Ogbomoso", "Oyo"]},
        ],
    },
]


# =============================================================================
# LOADER
# =============================================================================

def get_or_create_loc(env, LOC_MODEL, name, code, parent_id=None):
    domain = [("name", "=", name)]
    if parent_id:
        domain.append(("parent_id", "=", parent_id))
    record = env[LOC_MODEL].search(domain, limit=1)
    if record:
        _logger.info("EXISTS  location: %s", name)
        return record
    vals = {"name": name}
    loc_fields = env[LOC_MODEL].fields_get()
    if "code" in loc_fields:
        vals["code"] = code
    if parent_id and "parent_id" in loc_fields:
        vals["parent_id"] = parent_id
    record = env[LOC_MODEL].create(vals)
    _logger.info("CREATED location: %s (id=%s)", name, record.id)
    return record


def load_locations(env):
    """
    Load Zone → State → City skeleton into generic.location.
    Office/site level is loaded separately via load_offices.py.
    """
    all_models = env['ir.model'].search([]).mapped('model')
    LOC_MODEL = next((m for m in all_models if 'generic.location' == m), None)

    if not LOC_MODEL:
        # fallback search
        LOC_MODEL = next((m for m in all_models if 'location' in m and 'generic' in m), None)

    if not LOC_MODEL:
        raise RuntimeError(
            "generic.location model not found. "
            "Ensure the generic_location Bureaucrat module is installed.\n"
            "Run: env['ir.model'].search([('model','like','%location%')]).mapped('model')"
        )

    _logger.info("Using location model: %s", LOC_MODEL)
    stats = {"zones": 0, "states": 0, "cities": 0}

    for zone_data in LOCATION_TREE:
        zone = get_or_create_loc(env, LOC_MODEL, zone_data["name"], zone_data["code"])
        stats["zones"] += 1

        for state_data in zone_data["states"]:
            state = get_or_create_loc(
                env, LOC_MODEL,
                state_data["name"],
                state_data["code"],
                parent_id=zone.id,
            )
            stats["states"] += 1

            for city_name in state_data["cities"]:
                city_code = f"{state_data['code']}-{city_name[:3].upper()}"
                get_or_create_loc(
                    env, LOC_MODEL,
                    city_name,
                    city_code,
                    parent_id=state.id,
                )
                stats["cities"] += 1

    _logger.info(
        "\n\n  ✅  NRS Location Skeleton Loaded\n"
        "  ─────────────────────────────────────\n"
        "  Zones  : %d\n"
        "  States : %d\n"
        "  Cities : %d\n"
        "  Next   : run load_offices.py to add 400+ office sites\n",
        stats["zones"], stats["states"], stats["cities"],
    )
    return stats


# =============================================================================
# ENTRY POINT
# =============================================================================

if "env" in dir():
    with env.cr.savepoint():
        result = load_locations(env)
        env.cr.commit()
        print(f"\n✅  Done. {result}")
else:
    print("load_locations.py loaded. Call load_locations(env) from an Odoo shell.")
