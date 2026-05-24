#!/usr/bin/env python3
"""
NRS Facilities Service Manager — ITSM Structure Loader  v2
==========================================================
Bureaucrat ITSM hierarchy:
    Service Group → Service → Category → Type

Design decisions captured here:
  - Types are operational action signals, not vague labels
  - "Incident Report" is a cross-cutting Type across all Security & Safety services,
    with 5 sub-variants in Incident Management (primary home)
  - PTW collapsed to one "Permit to Work" Type; Category carries the work-type detail
  - Location is handled separately via load_locations.py (generic.location tree)

Usage:
    # Odoo shell
    exec(open('/opt/odoo/myservice_itsm/data/itsm_structure.py').read())

    # Shell script
    ./scripts/load_itsm_data.sh
"""

import logging
_logger = logging.getLogger(__name__)

# =============================================================================
# MASTER STRUCTURE
# =============================================================================

STRUCTURE = {
    "groups": [

        # =====================================================================
        # GROUP 1 — FACILITY MANAGEMENT
        # =====================================================================
        {
            "name": "Facility Management",
            "code": "FM",
            "services": [

                # -------------------------------------------------------------
                {
                    "name": "Building Operations",
                    "code": "FM-BLDG",
                    "categories": [
                        {"name": "Electrical"},
                        {"name": "Plumbing"},
                        {"name": "HVAC / Air Conditioning"},
                        {"name": "Civil & Structural"},
                        {"name": "Pest Control"},
                        {"name": "Painting & Decoration"},
                        {"name": "Roofing & Waterproofing"},
                    ],
                    "types": [
                        # What action is needed?
                        {"name": "Fault / Breakdown"},           # reactive — something failed
                        {"name": "Scheduled Maintenance"},       # PPM — calendar-driven
                        {"name": "Emergency — Life Safety"},     # occupant safety, P1
                        {"name": "Inspection Request"},          # survey / condition assessment
                        {"name": "Upgrade / Improvement"},       # enhancement, not fault-driven
                        {"name": "Compliance — Regulatory"},     # statutory deadline or permit
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Cleaning & Janitorial",
                    "code": "FM-CLN",
                    "categories": [
                        {"name": "Routine / Daily Cleaning"},
                        {"name": "Deep Cleaning"},
                        {"name": "Waste & Refuse Management"},
                        {"name": "Consumables Restocking"},
                        {"name": "Sanitation & Hygiene"},
                    ],
                    "types": [
                        {"name": "Routine Service — Daily"},      # standard daily schedule
                        {"name": "Routine Service — Periodic"},   # weekly / monthly deep clean
                        {"name": "Reactive / Ad-hoc Clean"},      # spill, event aftermath
                        {"name": "Quality Complaint"},            # standard not met
                        {"name": "Consumables Restock"},          # below threshold
                        {"name": "Special Event Setup / Cleanup"},
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Lift Services",
                    "code": "FM-LIFT",
                    "categories": [
                        {"name": "Routine Maintenance"},
                        {"name": "Breakdown & Fault"},
                        {"name": "Entrapment / Emergency"},
                        {"name": "Modernisation / Upgrade"},
                        {"name": "Regulatory Inspection"},
                    ],
                    "types": [
                        {"name": "Entrapment — Emergency"},       # person trapped, immediate P1
                        {"name": "Fault / Breakdown"},            # out of service, non-entrapment
                        {"name": "Scheduled Servicing"},          # contracted PPM visit
                        {"name": "Statutory Inspection"},         # LASBCA / regulatory cert
                        {"name": "Modernisation Request"},        # capital upgrade scope
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Generator Services",
                    "code": "FM-GEN",
                    "categories": [
                        {"name": "Routine Servicing"},
                        {"name": "Breakdown & Fault"},
                        {"name": "Fuel Request"},
                        {"name": "Load Testing"},
                        {"name": "Battery & Starter"},
                        {"name": "Change-over / ATS Fault"},
                    ],
                    "types": [
                        {"name": "Fault / No Power"},             # failed to start or tripped
                        {"name": "Scheduled Servicing"},          # routine PPM
                        {"name": "Fuel Replenishment — Urgent"},  # tank critically low
                        {"name": "Fuel Replenishment — Routine"}, # scheduled top-up
                        {"name": "Load Bank Test"},               # planned capacity verification
                        {"name": "Change-over / ATS Fault"},      # automatic transfer switch
                        {"name": "Compliance — Load Certification"},
                    ],
                },
            ],
        },

        # =====================================================================
        # GROUP 2 — SECURITY & SAFETY
        # =====================================================================
        {
            "name": "Security & Safety",
            "code": "SS",
            "services": [

                # -------------------------------------------------------------
                {
                    "name": "Access Control",
                    "code": "SS-ACC",
                    "categories": [
                        {"name": "Access Card / Tag Request"},
                        {"name": "Gate Pass Request"},
                        {"name": "Visitor Management"},
                        {"name": "Access Revocation"},
                        {"name": "Biometric Enrolment"},
                    ],
                    "types": [
                        {"name": "New Access Request"},           # first-time issuance
                        {"name": "Access Modification"},          # change level / area / schedule
                        {"name": "Access Revocation — Routine"},  # planned exit / transfer
                        {"name": "Access Revocation — Urgent"},   # immediate lockout
                        {"name": "Lost / Damaged Card or Tag"},
                        {"name": "Visitor / Contractor Pass"},    # temporary, time-limited
                        {"name": "System Fault"},                 # reader / controller down
                        # cross-cutting incident type:
                        {"name": "Incident Report — Security"},
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Surveillance & Patrol",
                    "code": "SS-SVP",
                    "categories": [
                        {"name": "CCTV Fault / Downtime"},
                        {"name": "Guard Deployment Request"},
                        {"name": "Patrol Schedule Management"},
                        {"name": "DVR / NVR Issue"},
                    ],
                    "types": [
                        {"name": "Camera / Equipment Fault"},     # CCTV / DVR / NVR offline
                        {"name": "Footage Retrieval Request"},    # evidence pull
                        {"name": "Patrol Deployment — Routine"},  # standard guard schedule
                        {"name": "Patrol Deployment — Reinforced"}, # event / threat uplift
                        {"name": "Guard Conduct Complaint"},
                        {"name": "System Upgrade Request"},
                        # cross-cutting incident type:
                        {"name": "Incident Report — Security"},
                    ],
                },

                # -------------------------------------------------------------
                # PRIMARY HOME of all Incident Report sub-types
                {
                    "name": "Incident Management",
                    "code": "SS-INC",
                    "categories": [
                        {"name": "Security Breach / Intrusion"},
                        {"name": "Theft & Loss"},
                        {"name": "Vandalism & Property Damage"},
                        {"name": "Fire & Evacuation"},
                        {"name": "Medical Emergency"},
                        {"name": "Near-Miss"},
                        {"name": "Civil Disturbance"},
                        {"name": "Workplace Violence"},
                    ],
                    "types": [
                        # 5 incident sub-types live here as their primary home:
                        {"name": "Incident Report — Security"},   # breach, intrusion, theft, vandalism
                        {"name": "Incident Report — Medical"},    # injury, collapse, health emergency
                        {"name": "Incident Report — Fire / Evacuation"},
                        {"name": "Incident Report — Near-Miss"},  # no harm but risk materialised
                        {"name": "Incident Report — Civil"},      # disturbance, workplace violence
                        # follow-on types:
                        {"name": "Investigation Request"},        # formal follow-up to a logged incident
                        {"name": "Escalation"},                   # senior / inter-agency involvement
                        {"name": "Post-Incident Review"},         # after-action debrief
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Safety & Compliance",
                    "code": "SS-SFT",
                    "categories": [
                        {"name": "Safety Inspection"},
                        {"name": "Emergency Drill / Evacuation Exercise"},
                        {"name": "Permit to Work"},               # PTW collapsed — Category carries detail
                        {"name": "HSE Audit"},
                        {"name": "PPE Request"},
                        {"name": "Fire Extinguisher / Equipment Check"},
                    ],
                    "types": [
                        {"name": "Permit to Work"},               # single PTW type — category = hot work / confined space etc.
                        {"name": "HSE Inspection — Routine"},     # scheduled safety walk
                        {"name": "HSE Inspection — Triggered"},   # post-incident / complaint-driven
                        {"name": "Emergency Drill — Fire"},
                        {"name": "Emergency Drill — Other"},      # flood / bomb threat / medical
                        {"name": "PPE Request"},
                        {"name": "Regulatory Audit Support"},     # external auditor / authority visit
                        # cross-cutting:
                        {"name": "Incident Report — Security"},
                    ],
                },
            ],
        },

        # =====================================================================
        # GROUP 3 — FLEET MANAGEMENT
        # =====================================================================
        {
            "name": "Fleet Management",
            "code": "FL",
            "services": [

                # -------------------------------------------------------------
                {
                    "name": "Driver Management",
                    "code": "FL-DRV",
                    "categories": [
                        {"name": "Driver Onboarding"},
                        {"name": "Licence & Permit Verification"},
                        {"name": "Conduct & Disciplinary"},
                        {"name": "Driver Availability / Leave"},
                        {"name": "Training & Assessment"},
                    ],
                    "types": [
                        {"name": "New Driver Onboarding"},
                        {"name": "Licence / Document Renewal"},   # expiring credential
                        {"name": "Licence / Document Verification"}, # background / spot-check
                        {"name": "Disciplinary / Conduct"},       # complaint / infraction
                        {"name": "Driver Reassignment"},          # permanent or temporary
                        {"name": "Driver Availability Update"},   # leave / sick / schedule
                        {"name": "Training Enrolment"},           # defensive driving / first aid
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Fuel & Lubricants",
                    "code": "FL-FUEL",
                    "categories": [
                        {"name": "Fuel Request"},
                        {"name": "Lubricant Request"},
                        {"name": "Fuel Card Issue"},
                        {"name": "Mileage Reconciliation"},
                        {"name": "Fuel Consumption Report"},
                    ],
                    "types": [
                        {"name": "Fuel Request — Scheduled"},     # routine top-up
                        {"name": "Fuel Request — Urgent"},        # below minimum threshold
                        {"name": "Lubricant / Fluid Request"},
                        {"name": "Fuel Card — New / Replacement"},
                        {"name": "Fuel Card — Limit Adjustment"},
                        {"name": "Mileage & Consumption Report"}, # periodic reconciliation
                        {"name": "Discrepancy / Dispute"},        # actual vs recorded mismatch
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Insurance & Licensing",
                    "code": "FL-INS",
                    "categories": [
                        {"name": "Insurance Renewal"},
                        {"name": "Road Worthiness Certificate"},
                        {"name": "Vehicle Licence Renewal"},
                        {"name": "Third-Party Claims"},
                        {"name": "Hackney Permit"},
                    ],
                    "types": [
                        {"name": "Insurance Renewal — Due"},       # within notice period
                        {"name": "Insurance Renewal — Lapsed"},    # expired, urgent reinstatement
                        {"name": "Road Worthiness — Scheduled"},
                        {"name": "Road Worthiness — Failed"},      # off-road until cleared
                        {"name": "Vehicle Licence Renewal"},
                        {"name": "Third-Party Claim — Incoming"},  # external party vs govt vehicle
                        {"name": "Third-Party Claim — Outgoing"},  # govt vs third party
                        {"name": "New Vehicle Registration"},
                    ],
                },

                # -------------------------------------------------------------
                # MERGED: Trip Scheduling + Vehicle Request
                {
                    "name": "Fleet Operations",
                    "code": "FL-OPS",
                    "categories": [
                        {"name": "Official Trip Request"},
                        {"name": "Airport Pickup / Drop-off"},
                        {"name": "Inter-state / Long-Distance Trip"},
                        {"name": "Recurring / Standing Schedule"},
                        {"name": "Pool Vehicle Request"},
                        {"name": "Dedicated Vehicle Allocation"},
                        {"name": "Temporary Hire / Outsourced Vehicle"},
                    ],
                    "types": [
                        {"name": "Trip Request — Official / Internal"},
                        {"name": "Trip Request — Executive / Protocol"}, # VIP / minister-level
                        {"name": "Trip Request — Inter-state"},
                        {"name": "Trip Request — Airport"},
                        {"name": "Recurring Schedule — Setup"},    # new standing allocation
                        {"name": "Recurring Schedule — Modification"},
                        {"name": "Vehicle Request — Pool"},
                        {"name": "Vehicle Request — Dedicated"},
                        {"name": "Vehicle Request — External Hire"}, # third-party hire
                        {"name": "Trip Cancellation / Amendment"},
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Vehicle Maintenance",
                    "code": "FL-VMT",
                    "categories": [
                        {"name": "Routine Service (Oil & Filter)"},
                        {"name": "Tyre & Battery"},
                        {"name": "Bodywork & Accident Repair"},
                        {"name": "Breakdown / Roadside"},
                        {"name": "Brake & Suspension"},
                        {"name": "Electrical / Electronics"},
                        {"name": "Air Conditioning"},
                    ],
                    "types": [
                        {"name": "Breakdown — Roadside"},          # immobilised in field
                        {"name": "Breakdown — Workshop"},          # drove in, not roadworthy
                        {"name": "Scheduled Service — Minor"},     # oil / filter / consumables
                        {"name": "Scheduled Service — Major"},     # full service / cam belt
                        {"name": "Accident Damage Assessment"},    # post-accident inspection
                        {"name": "Bodywork Repair"},
                        {"name": "Tyre — Replacement / Repair"},
                        {"name": "Battery — Replacement"},
                        {"name": "Electrical / Electronics Fault"},
                        {"name": "Air Conditioning Fault"},
                        {"name": "Brake & Suspension Work"},       # safety-critical
                    ],
                },

                # -------------------------------------------------------------
                {
                    "name": "Vehicle Registration",
                    "code": "FL-VRG",
                    "categories": [
                        {"name": "New Vehicle Onboarding"},
                        {"name": "Transfer of Ownership"},
                        {"name": "Change of Ownership (Disposal)"},
                        {"name": "Fleet Record Update"},
                        {"name": "Deregistration / Write-off"},
                    ],
                    "types": [
                        {"name": "New Vehicle — Government Plate"},  # new acquisition
                        {"name": "New Vehicle — Transfer In"},       # from another agency
                        {"name": "Ownership Change — Internal"},     # between depts / locations
                        {"name": "Ownership Change — Disposal"},     # auction / scrap
                        {"name": "Fleet Record Correction"},         # data amendment only
                        {"name": "Licence / Document Update"},       # change of particulars
                    ],
                },
            ],
        },
    ]
}


# =============================================================================
# LOADER
# =============================================================================

def get_or_create(env, model, domain, vals):
    record = env[model].search(domain, limit=1)
    if record:
        _logger.info("EXISTS  [%s] %s", model, vals.get("name", ""))
        return record
    # Auto-fill `code` (required by generic.mixin.name_with_code) when the
    # model has the field but the caller didn't provide one. Form-mode
    # onchange would slugify the name; programmatic create has to do it
    # explicitly.
    if "code" in env[model]._fields and not vals.get("code") and vals.get("name"):
        from odoo.addons.http_routing.models.ir_http import slugify
        vals = dict(vals, code=slugify(vals["name"], max_length=0))
    record = env[model].create(vals)
    _logger.info("CREATED [%s] %s (id=%s)", model, vals.get("name", ""), record.id)
    return record


def load_structure(env):
    """
    Load Group → Service → Category → Type into Bureaucrat ITSM.

    Auto-detects model names at runtime. If detection fails, run:
        env['ir.model'].search([('model','like','request.')]).mapped('model')
    in the Odoo shell to inspect available models.
    """
    all_models = env['ir.model'].search([]).mapped('model')

    GROUP_MODEL    = next((m for m in all_models if 'service.group' in m), None)
    SERVICE_MODEL  = next((m for m in all_models if m.endswith('request.service')
                           or m == 'generic.service'), None)
    CATEGORY_MODEL = next((m for m in all_models if 'request.category' in m), None)
    TYPE_MODEL     = next((m for m in all_models if m == 'request.type'), None)

    _logger.info("Models → group=%s  service=%s  category=%s  type=%s",
                 GROUP_MODEL, SERVICE_MODEL, CATEGORY_MODEL, TYPE_MODEL)

    if not all([GROUP_MODEL, SERVICE_MODEL, CATEGORY_MODEL, TYPE_MODEL]):
        raise RuntimeError(
            "Could not auto-detect one or more Bureaucrat ITSM models. "
            "Run: env['ir.model'].search([('model','like','request.')]).mapped('model')"
        )

    stats = {"groups": 0, "services": 0, "categories": 0, "types": 0}

    for grp_data in STRUCTURE["groups"]:

        grp = get_or_create(
            env, GROUP_MODEL,
            [("name", "=", grp_data["name"])],
            {"name": grp_data["name"], "code": grp_data["code"]},
        )
        stats["groups"] += 1

        for svc_data in grp_data["services"]:

            svc_vals = {"name": svc_data["name"], "code": svc_data["code"]}
            svc_fields = env[SERVICE_MODEL].fields_get()
            if "group_id" in svc_fields:
                svc_vals["group_id"] = grp.id
            elif "service_group_id" in svc_fields:
                svc_vals["service_group_id"] = grp.id

            svc = get_or_create(
                env, SERVICE_MODEL,
                [("name", "=", svc_data["name"])],
                svc_vals,
            )
            stats["services"] += 1

            cat_fields = env[CATEGORY_MODEL].fields_get()
            for cat_data in svc_data["categories"]:
                cat_vals = {"name": cat_data["name"]}
                domain = [("name", "=", cat_data["name"])]
                if "service_id" in cat_fields:
                    cat_vals["service_id"] = svc.id
                    domain.append(("service_id", "=", svc.id))
                get_or_create(env, CATEGORY_MODEL, domain, cat_vals)
                stats["categories"] += 1

            typ_fields = env[TYPE_MODEL].fields_get()
            for typ_data in svc_data["types"]:
                typ_vals = {"name": typ_data["name"]}
                domain = [("name", "=", typ_data["name"])]
                if "service_id" in typ_fields:
                    typ_vals["service_id"] = svc.id
                    domain.append(("service_id", "=", svc.id))
                get_or_create(env, TYPE_MODEL, domain, typ_vals)
                stats["types"] += 1

    _logger.info(
        "\n\n  ✅  NRS ITSM Structure Loaded\n"
        "  ─────────────────────────────────────\n"
        "  Groups     : %d\n"
        "  Services   : %d\n"
        "  Categories : %d\n"
        "  Types      : %d\n",
        stats["groups"], stats["services"], stats["categories"], stats["types"],
    )
    return stats


# =============================================================================
# ENTRY POINT
# =============================================================================

if "env" in dir():
    result = load_structure(env)
    env.cr.commit()
    print(f"\n✅  Done. {result}")
else:
    print("itsm_structure.py loaded. Call load_structure(env) from an Odoo shell.")
