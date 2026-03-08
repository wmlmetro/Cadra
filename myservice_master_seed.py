#!/usr/bin/env python3
"""
myservice.com.ng — Master Seed Script
========================================
Database:  myservice.com.ng
Client:    Nigeria Revenue Service (NRS)
Platform:  Bureaucrat ITSM + Fleet on Odoo 15
Powered:   WestMetro Limited | www.westmetrong.com

Consolidates:
  - nrs_seed.py       (ITSM: kinds, services, categories, types, stages, routes, classifiers)
  - nrs_fleet_seed.py (Fleet: 1,617 vehicles, 20 brands, 56 models)

Run:
    cd /opt/odoo
    sudo -u odoo /opt/odoo/venv/bin/python3 odoo/odoo-bin shell \\
        -c /opt/odoo/conf/odoo.conf \\
        -d myservice.com.ng --no-http < /root/CRND/myservice_master_seed.py

Execution order:
  Part A — Company Branding
  Part B — ITSM (Kinds → Services → Categories → Types → Stages/Routes → Classifiers)
  Part C — Fleet (Brands → Models → Tags → Vehicles)
  Part D — Summary
"""

import traceback

print()
print("=" * 70)
print("  NRS FACILITIES ITSM — SEED SCRIPT")
print("  WestMetro Limited | www.westmetrong.com")
print("=" * 70)


# ================================================================
# STEP 0: BRANDING
# ================================================================
print("\n" + "-" * 70)
print("  STEP 0: COMPANY BRANDING")
print("-" * 70)

try:
    company = env['res.company'].search([], limit=1)
    if company:
        company.write({
            'name':   'Nigeria Revenue Service',
            'email':  'facilities@nrs.gov.ng',
            'phone':  '+234 9 904 9999',
            'website':'https://www.nrs.gov.ng',
            'street': 'Integrated Tax Administration Building',
            'city':   'Abuja',
            'country_id': env['res.country'].search([('code','=','NG')], limit=1).id,
        })
        env.cr.commit()
        print(f"  ✓ Company branding updated → {company.name}")
    else:
        print("  ! No company found — set branding manually in Settings")
except Exception:
    print("  ! Branding error (non-fatal):")
    traceback.print_exc()


# ================================================================
# STEP 1: KINDS
# ================================================================
print("\n" + "-" * 70)
print("  STEP 1: REQUEST KINDS")
print("-" * 70)

KINDS = [
    ("Incident",         "INCIDENT",         "Unplanned failure or degradation of a facility service"),
    ("Service Request",  "SERVICE-REQUEST",   "Formal request for a standard facility service"),
    ("Preventive Maintenance", "PREV-MAINT",  "Scheduled preventive maintenance task"),
    ("Corrective Maintenance", "CORR-MAINT",  "Reactive repair following a failure"),
    ("Change Request",   "CHANGE",            "Planned change to facility infrastructure or configuration"),
    ("Inspection",       "INSPECTION",        "Routine inspection or audit of facility assets"),
]

kind_map = {}
for name, code, desc in KINDS:
    existing = env['request.kind'].search([('code','=',code)], limit=1)
    if not existing:
        rec = env['request.kind'].create({'name': name, 'code': code})
        kind_map[code] = rec.id
        print(f"  + Created kind: {name} ({code})")
    else:
        kind_map[code] = existing.id
        print(f"  o Exists kind: {name} ({code})")

env.cr.commit()


# ================================================================
# STEP 2: SERVICES
# ================================================================
print("\n" + "-" * 70)
print("  STEP 2: SERVICES")
print("-" * 70)

SERVICES = [
    ("Building Services",    "SVC-BLDG",   "Civil, structural, electrical, HVAC and general building maintenance"),
    ("Plumbing & Drainage",  "SVC-PLUMB",  "Water supply, drainage, sewage, sanitary fittings and pipework"),
    ("Plant & Machinery",    "SVC-PLANT",  "Generators, lifts, HVAC plant, compressors and heavy equipment"),
    ("Security & Safety",    "SVC-SEC",    "Access control, CCTV, fire safety, guards and HSE compliance"),
    ("Fleet Management",     "SVC-FLEET",  "Vehicles, drivers, fuel, maintenance and road compliance"),
    ("Facilities Helpdesk",  "SVC-HELP",   "General facilities enquiries, complaints and administration"),
]

service_map = {}
svc_model = 'generic.service' if 'generic.service' in env else None
if svc_model:
    for name, code, desc in SERVICES:
        existing = env[svc_model].search([('code','=',code)], limit=1)
        if not existing:
            rec = env[svc_model].create({'name': name, 'code': code})
            service_map[code] = rec.id
            print(f"  + Created service: {name} ({code})")
        else:
            service_map[code] = existing.id
            print(f"  o Exists service: {name} ({code})")
    env.cr.commit()
else:
    print("  ! generic.service model not available — services skipped")


# ================================================================
# STEP 3: CATEGORIES
# ================================================================
print("\n" + "-" * 70)
print("  STEP 3: CATEGORIES")
print("-" * 70)

# (name, code, domain_tag)
CATEGORIES = [
    # ── Building Services ──────────────────────────────────────
    ("Civil & Structural",        "CAT-CIVIL",     "BLDG"),
    ("Electrical Installations",  "CAT-ELEC",      "BLDG"),
    ("HVAC & Air Conditioning",   "CAT-HVAC",      "BLDG"),
    ("Painting & Finishing",      "CAT-PAINT",     "BLDG"),
    ("Roofing & Waterproofing",   "CAT-ROOF",      "BLDG"),
    ("Carpentry & Joinery",       "CAT-CARP",      "BLDG"),
    ("Glass & Glazing",           "CAT-GLASS",     "BLDG"),
    ("Cleaning & Janitorial",     "CAT-CLEAN",     "BLDG"),
    ("Waste Management",          "CAT-WASTE",     "BLDG"),
    ("Landscaping & Grounds",     "CAT-GROUNDS",   "BLDG"),

    # ── Plumbing & Drainage ─────────────────────────────────────
    ("Water Supply",              "CAT-WATER",     "PLUMB"),
    ("Drainage & Sewage",         "CAT-DRAIN",     "PLUMB"),
    ("Sanitary Fittings",         "CAT-SANIT",     "PLUMB"),
    ("Pumps & Boreholes",         "CAT-PUMP",      "PLUMB"),
    ("Hot Water Systems",         "CAT-HWS",       "PLUMB"),
    ("Pipe Repairs",              "CAT-PIPE",      "PLUMB"),

    # ── Plant & Machinery ───────────────────────────────────────
    ("Generators & UPS",          "CAT-GEN",       "PLANT"),
    ("Lifts & Escalators",        "CAT-LIFT",      "PLANT"),
    ("HVAC Plant",                "CAT-HVACPLANT", "PLANT"),
    ("Compressors & Air Systems", "CAT-COMP",      "PLANT"),
    ("Water Treatment Plant",     "CAT-WTP",       "PLANT"),
    ("BMS & Controls",            "CAT-BMS",       "PLANT"),
    ("Fuel Management",           "CAT-FUEL",      "PLANT"),

    # ── Security & Safety ───────────────────────────────────────
    ("Access Control",            "CAT-ACCESS",    "SEC"),
    ("CCTV & Surveillance",       "CAT-CCTV",      "SEC"),
    ("Fire Detection & Suppression","CAT-FIRE",    "SEC"),
    ("Security Guards",           "CAT-GUARD",     "SEC"),
    ("HSE Compliance",            "CAT-HSE",       "SEC"),
    ("Perimeter Security",        "CAT-PERIM",     "SEC"),
    ("Emergency Response",        "CAT-EMERG",     "SEC"),

    # ── Fleet Management ────────────────────────────────────────
    ("Vehicle Maintenance",       "CAT-VMAINT",    "FLEET"),
    ("Fuel & Lubricants",         "CAT-VFUEL",     "FLEET"),
    ("Driver Management",         "CAT-DRIVER",    "FLEET"),
    ("Vehicle Registration",      "CAT-VREG",      "FLEET"),
    ("Insurance & Licensing",     "CAT-VINS",      "FLEET"),
    ("Trip Scheduling",           "CAT-TRIP",      "FLEET"),
    ("Vehicle Procurement",       "CAT-VPROCURE",  "FLEET"),

    # ── Facilities Helpdesk ─────────────────────────────────────
    ("General Enquiry",           "CAT-GEN-ENQ",   "HELP"),
    ("Complaint",                 "CAT-COMPLAINT", "HELP"),
    ("Asset Request",             "CAT-ASSET",     "HELP"),
    ("Space Management",          "CAT-SPACE",     "HELP"),
    ("Vendor / Contractor",       "CAT-VENDOR",    "HELP"),
    ("Budget & Finance",          "CAT-BUDGET",    "HELP"),
]

cat_map = {}
for name, code, domain in CATEGORIES:
    existing = env['request.category'].search([('code','=',code)], limit=1)
    if not existing:
        rec = env['request.category'].create({'name': name, 'code': code})
        cat_map[code] = rec.id
        print(f"  + Created category: {name} ({code})")
    else:
        cat_map[code] = existing.id
        print(f"  o Exists category:  {name} ({code})")

env.cr.commit()
print(f"  ✓ {len(cat_map)} categories ready")


# ================================================================
# STEP 4: REQUEST TYPES
# ================================================================
print("\n" + "-" * 70)
print("  STEP 4: REQUEST TYPES")
print("-" * 70)

# Introspect available fields on request.type
rt_fields = list(env['request.type']._fields.keys())
print(f"  Available fields (subset): category={'category_ids' in rt_fields and 'category_ids' or 'category_id' if 'category_id' in rt_fields else 'NONE'}, kind={'kind_id' if 'kind_id' in rt_fields else 'NONE'}")

# (name, code, category_code, kind_code, description)
REQUEST_TYPES = [

    # ── BUILDING SERVICES ────────────────────────────────────────
    ("Civil Works Fault Report",       "BLDG-CIVIL-INC",  "CAT-CIVIL",    "INCIDENT",       "Report of structural or civil failure"),
    ("Civil Works Change Request",     "BLDG-CIVIL-CHG",  "CAT-CIVIL",    "CHANGE",         "Planned civil works or modification"),
    ("Civil Works Inspection",         "BLDG-CIVIL-INSP", "CAT-CIVIL",    "INSPECTION",     "Scheduled structural inspection"),

    ("Electrical Fault",               "BLDG-ELEC-INC",   "CAT-ELEC",     "INCIDENT",       "Electrical failure or hazard"),
    ("Electrical Installation Request","BLDG-ELEC-SVC",   "CAT-ELEC",     "SERVICE-REQUEST","New electrical installation or modification"),
    ("Electrical Preventive Maint.",   "BLDG-ELEC-PM",    "CAT-ELEC",     "PREV-MAINT",     "Scheduled electrical preventive maintenance"),
    ("Electrical Corrective Repair",   "BLDG-ELEC-CM",    "CAT-ELEC",     "CORR-MAINT",     "Reactive electrical repair"),

    ("HVAC Fault",                     "BLDG-HVAC-INC",   "CAT-HVAC",     "INCIDENT",       "HVAC system failure or malfunction"),
    ("HVAC Service Request",           "BLDG-HVAC-SVC",   "CAT-HVAC",     "SERVICE-REQUEST","HVAC servicing or new installation"),
    ("HVAC Preventive Maintenance",    "BLDG-HVAC-PM",    "CAT-HVAC",     "PREV-MAINT",     "Scheduled HVAC service"),

    ("Painting Request",               "BLDG-PAINT-SVC",  "CAT-PAINT",    "SERVICE-REQUEST","Internal/external painting or touch-up"),
    ("Roofing Fault Report",           "BLDG-ROOF-INC",   "CAT-ROOF",     "INCIDENT",       "Roof leak or structural roofing failure"),
    ("Roofing Preventive Inspection",  "BLDG-ROOF-INSP",  "CAT-ROOF",     "INSPECTION",     "Scheduled roof inspection"),

    ("Carpentry Request",              "BLDG-CARP-SVC",   "CAT-CARP",     "SERVICE-REQUEST","Furniture, door, or joinery request"),
    ("Glass Replacement",              "BLDG-GLASS-SVC",  "CAT-GLASS",    "SERVICE-REQUEST","Broken window or glass replacement"),

    ("Cleaning Request",               "BLDG-CLEAN-SVC",  "CAT-CLEAN",    "SERVICE-REQUEST","Adhoc deep clean or area cleaning request"),
    ("Cleaning Schedule Review",       "BLDG-CLEAN-CHG",  "CAT-CLEAN",    "CHANGE",         "Change to cleaning schedule or contract"),
    ("Waste Collection Request",       "BLDG-WASTE-SVC",  "CAT-WASTE",    "SERVICE-REQUEST","Request for waste removal or disposal"),

    ("Grounds Maintenance Request",    "BLDG-GRND-SVC",   "CAT-GROUNDS",  "SERVICE-REQUEST","Landscaping, mowing or ground works"),

    # ── PLUMBING & DRAINAGE ─────────────────────────────────────
    ("Water Supply Fault",             "PLUMB-WAT-INC",   "CAT-WATER",    "INCIDENT",       "Water supply outage or pressure issue"),
    ("Water Supply Service Request",   "PLUMB-WAT-SVC",   "CAT-WATER",    "SERVICE-REQUEST","Water point installation or modification"),
    ("Drainage Blockage",              "PLUMB-DRN-INC",   "CAT-DRAIN",    "INCIDENT",       "Blocked drain, sewer or gulley"),
    ("Drainage Repair",                "PLUMB-DRN-CM",    "CAT-DRAIN",    "CORR-MAINT",     "Drainage pipe repair"),
    ("Sanitary Fitting Fault",         "PLUMB-SAN-INC",   "CAT-SANIT",    "INCIDENT",       "Faulty toilet, basin, tap or urinal"),
    ("Sanitary Fitting Replacement",   "PLUMB-SAN-SVC",   "CAT-SANIT",    "SERVICE-REQUEST","Replacement or upgrade of sanitary fittings"),
    ("Pump / Borehole Fault",          "PLUMB-PUMP-INC",  "CAT-PUMP",     "INCIDENT",       "Pump or borehole failure"),
    ("Pump Preventive Maintenance",    "PLUMB-PUMP-PM",   "CAT-PUMP",     "PREV-MAINT",     "Scheduled pump servicing"),
    ("Hot Water System Fault",         "PLUMB-HWS-INC",   "CAT-HWS",      "INCIDENT",       "Hot water system outage or leak"),
    ("Pipe Leak Repair",               "PLUMB-PIPE-INC",  "CAT-PIPE",     "INCIDENT",       "Pipe burst or leak"),
    ("Pipe Replacement Request",       "PLUMB-PIPE-CHG",  "CAT-PIPE",     "CHANGE",         "Planned pipe replacement or rerouting"),

    # ── PLANT & MACHINERY ────────────────────────────────────────
    ("Generator Fault",                "PLANT-GEN-INC",   "CAT-GEN",      "INCIDENT",       "Generator failure or alarm"),
    ("Generator Preventive Service",   "PLANT-GEN-PM",    "CAT-GEN",      "PREV-MAINT",     "Scheduled generator service"),
    ("UPS Fault",                      "PLANT-UPS-INC",   "CAT-GEN",      "INCIDENT",       "UPS failure or battery alert"),
    ("Lift / Elevator Fault",          "PLANT-LIFT-INC",  "CAT-LIFT",     "INCIDENT",       "Lift out of service or stuck"),
    ("Lift Preventive Maintenance",    "PLANT-LIFT-PM",   "CAT-LIFT",     "PREV-MAINT",     "Scheduled lift servicing"),
    ("Lift Inspection",                "PLANT-LIFT-INSP", "CAT-LIFT",     "INSPECTION",     "Statutory lift inspection"),
    ("HVAC Plant Fault",               "PLANT-HVAC-INC",  "CAT-HVACPLANT","INCIDENT",       "Chiller, AHU or FCU fault"),
    ("HVAC Plant PM",                  "PLANT-HVAC-PM",   "CAT-HVACPLANT","PREV-MAINT",     "Scheduled HVAC plant service"),
    ("Compressor Fault",               "PLANT-COMP-INC",  "CAT-COMP",     "INCIDENT",       "Compressor or compressed air system fault"),
    ("Compressor Preventive Maint.",   "PLANT-COMP-PM",   "CAT-COMP",     "PREV-MAINT",     "Scheduled compressor service"),
    ("Water Treatment Plant Fault",    "PLANT-WTP-INC",   "CAT-WTP",      "INCIDENT",       "WTP process fault or quality issue"),
    ("Water Treatment PM",             "PLANT-WTP-PM",    "CAT-WTP",      "PREV-MAINT",     "Scheduled WTP service"),
    ("BMS Fault",                      "PLANT-BMS-INC",   "CAT-BMS",      "INCIDENT",       "Building Management System fault"),
    ("BMS Change Request",             "PLANT-BMS-CHG",   "CAT-BMS",      "CHANGE",         "BMS programming or configuration change"),
    ("Fuel Replenishment Request",     "PLANT-FUEL-SVC",  "CAT-FUEL",     "SERVICE-REQUEST","Fuel order for generators or plant"),
    ("Fuel Stock Inspection",          "PLANT-FUEL-INSP", "CAT-FUEL",     "INSPECTION",     "Fuel level audit and dip test"),

    # ── SECURITY & SAFETY ────────────────────────────────────────
    ("Access Control Fault",           "SEC-ACC-INC",     "CAT-ACCESS",   "INCIDENT",       "Access card reader or door lock failure"),
    ("Access Card Request",            "SEC-ACC-SVC",     "CAT-ACCESS",   "SERVICE-REQUEST","New or replacement access card"),
    ("Access Level Change",            "SEC-ACC-CHG",     "CAT-ACCESS",   "CHANGE",         "Change user access level or zone"),
    ("CCTV Fault",                     "SEC-CCTV-INC",    "CAT-CCTV",     "INCIDENT",       "Camera offline or DVR/NVR failure"),
    ("CCTV Footage Request",           "SEC-CCTV-SVC",    "CAT-CCTV",     "SERVICE-REQUEST","Request for CCTV footage review/export"),
    ("CCTV Preventive Maintenance",    "SEC-CCTV-PM",     "CAT-CCTV",     "PREV-MAINT",     "Scheduled CCTV cleaning and testing"),
    ("Fire Alarm Fault",               "SEC-FIRE-INC",    "CAT-FIRE",     "INCIDENT",       "Fire alarm activation or detector fault"),
    ("Fire Suppression Fault",         "SEC-FIREX-INC",   "CAT-FIRE",     "INCIDENT",       "Sprinkler or suppression system fault"),
    ("Fire System Preventive Maint.",  "SEC-FIRE-PM",     "CAT-FIRE",     "PREV-MAINT",     "Scheduled fire system service"),
    ("Fire System Inspection",         "SEC-FIRE-INSP",   "CAT-FIRE",     "INSPECTION",     "Statutory fire inspection"),
    ("Security Guard Complaint",       "SEC-GUARD-INC",   "CAT-GUARD",    "INCIDENT",       "Guard conduct complaint or breach"),
    ("Security Guard Request",         "SEC-GUARD-SVC",   "CAT-GUARD",    "SERVICE-REQUEST","Additional guard or escort request"),
    ("HSE Incident Report",            "SEC-HSE-INC",     "CAT-HSE",      "INCIDENT",       "Workplace accident, near-miss or hazard"),
    ("HSE Inspection",                 "SEC-HSE-INSP",    "CAT-HSE",      "INSPECTION",     "HSE audit or compliance check"),
    ("Perimeter Breach Report",        "SEC-PERIM-INC",   "CAT-PERIM",    "INCIDENT",       "Fence, gate or perimeter breach"),
    ("Perimeter Maintenance",          "SEC-PERIM-SVC",   "CAT-PERIM",    "SERVICE-REQUEST","Fence, gate or wall maintenance"),
    ("Emergency Response Drill",       "SEC-EMERG-CHG",   "CAT-EMERG",    "CHANGE",         "Fire drill or emergency evacuation exercise"),
    ("Emergency Incident",             "SEC-EMERG-INC",   "CAT-EMERG",    "INCIDENT",       "Active emergency requiring immediate response"),

    # ── FLEET MANAGEMENT ─────────────────────────────────────────
    ("Vehicle Breakdown Report",       "FLEET-VM-INC",    "CAT-VMAINT",   "INCIDENT",       "Vehicle breakdown or roadside fault"),
    ("Vehicle Corrective Repair",      "FLEET-VM-CM",     "CAT-VMAINT",   "CORR-MAINT",     "Workshop repair following breakdown"),
    ("Vehicle Preventive Service",     "FLEET-VM-PM",     "CAT-VMAINT",   "PREV-MAINT",     "Scheduled vehicle service / oil change"),
    ("Vehicle Inspection",             "FLEET-VM-INSP",   "CAT-VMAINT",   "INSPECTION",     "Pre-trip or annual vehicle inspection"),
    ("Fuel Request",                   "FLEET-FUEL-SVC",  "CAT-VFUEL",    "SERVICE-REQUEST","Fuel allocation or reimbursement request"),
    ("Fuel Reconciliation",            "FLEET-FUEL-INSP", "CAT-VFUEL",    "INSPECTION",     "Monthly fuel usage audit"),
    ("Driver Complaint",               "FLEET-DRV-INC",   "CAT-DRIVER",   "INCIDENT",       "Complaint about driver conduct"),
    ("Driver Scheduling Request",      "FLEET-DRV-SVC",   "CAT-DRIVER",   "SERVICE-REQUEST","Assign driver for official trip"),
    ("Vehicle Registration Renewal",   "FLEET-REG-SVC",   "CAT-VREG",     "SERVICE-REQUEST","Vehicle registration or licence renewal"),
    ("Insurance Renewal",              "FLEET-INS-SVC",   "CAT-VINS",     "SERVICE-REQUEST","Vehicle insurance renewal"),
    ("Trip Booking",                   "FLEET-TRIP-SVC",  "CAT-TRIP",     "SERVICE-REQUEST","Official trip scheduling request"),
    ("Vehicle Procurement Request",    "FLEET-PROC-CHG",  "CAT-VPROCURE", "CHANGE",         "Request to procure a new or replacement vehicle"),

    # ── FACILITIES HELPDESK ──────────────────────────────────────
    ("General Facilities Enquiry",     "HELP-GEN-SVC",    "CAT-GEN-ENQ",  "SERVICE-REQUEST","General facilities information request"),
    ("Facilities Complaint",           "HELP-COMP-INC",   "CAT-COMPLAINT","INCIDENT",       "Formal complaint about facilities service"),
    ("Asset Request",                  "HELP-ASSET-SVC",  "CAT-ASSET",    "SERVICE-REQUEST","Request for furniture, equipment or fittings"),
    ("Space Allocation Request",       "HELP-SPACE-SVC",  "CAT-SPACE",    "SERVICE-REQUEST","Office space or meeting room allocation"),
    ("Contractor Onboarding Request",  "HELP-VENDOR-SVC", "CAT-VENDOR",   "SERVICE-REQUEST","New contractor or vendor approval"),
    ("Contractor Complaint",           "HELP-VENDOR-INC", "CAT-VENDOR",   "INCIDENT",       "Complaint about contractor performance"),
    ("Budget Query",                   "HELP-BUDGET-SVC", "CAT-BUDGET",   "SERVICE-REQUEST","Budget approval or cost query"),
]


type_map = {}
type_cat_map = {}  # type_code → cat_code (for classifier creation in Step 6)

for name, code, cat_code, kind_code, desc in REQUEST_TYPES:
    kind_id = kind_map.get(kind_code)
    existing = env['request.type'].search([('code','=',code)], limit=1)
    if not existing:
        vals = {'name': name, 'code': code, 'active': True}
        # kind_id only on create — category/service linked via classifier in Step 6
        if kind_id:
            vals['kind_id'] = kind_id
        rec = env['request.type'].create(vals)
        type_map[code] = rec.id
        print(f"  + {name} ({code})")
    else:
        type_map[code] = existing.id
        print(f"  o {name} ({code})")
    type_cat_map[code] = cat_code

env.cr.commit()
print(f"\n  ✓ {len(type_map)} request types ready")
# ================================================================
# STEP 5: STAGES + ROUTES (per request type)
# ================================================================
print("\n" + "-" * 70)
print("  STEP 5: STAGES & ROUTES")
print("-" * 70)

# 7-stage ITIL workflow
# (name, code, sequence, closed, bg_color)
STAGE_TEMPLATE = [
    ("New",         "new",         5,  False, "rgba(52,152,219,1)"),
    ("Assigned",    "assigned",   10,  False, "rgba(52,73,94,1)"),
    ("In Progress", "in-progress",11,  False, "rgba(243,156,18,1)"),
    ("Pending",     "pending",    12,  False, "rgba(155,89,182,1)"),
    ("Escalated",   "escalated",  13,  False, "rgba(231,76,60,1)"),
    ("Resolved",    "resolved",   14,  True,  "rgba(39,174,96,1)"),
    ("Closed",      "close",      15,  True,  "rgba(127,140,141,1)"),
]

# 9 route transitions per type
# (name, from_code, to_code, close, sequence, button_style)
ROUTE_TEMPLATE = [
    ("Assign",              "new",         "assigned",    False, 10, "primary"),
    ("Start Work",          "assigned",    "in-progress", False, 20, "primary"),
    ("Request Information", "in-progress", "pending",     False, 30, "warning"),
    ("Escalate",            "in-progress", "escalated",   False, 40, "danger"),
    ("Resolve",             "in-progress", "resolved",    False, 50, "success"),
    ("Resume",              "pending",     "in-progress", False, 60, "primary"),
    ("Resolve (Escalated)", "escalated",   "resolved",    False, 70, "success"),
    ("Close",               "resolved",    "close",       True,  80, "default"),
    ("Reopen",              "close",       "new",         False, 90, "warning"),
]

def build_stages_and_routes(rtype_id, rtype_code):
    """Delete old stages/routes and rebuild for a request type."""
    try:
        rtype = env['request.type'].browse(rtype_id)

        # Delete old stages
        old_stages = env['request.stage'].search([('request_type_id','=',rtype_id)])
        old_stages.unlink()

        # Create stages and build code→id map
        stage_id_map = {}
        for s_name, s_code, s_seq, s_closed, s_bg in STAGE_TEMPLATE:
            stage = env['request.stage'].create({
                'name':            s_name,
                'code':            s_code,
                'sequence':        s_seq,
                'closed':          s_closed,
                'bg_color':        s_bg,
                'request_type_id': rtype_id,
            })
            stage_id_map[s_code] = stage.id

        # Set start stage
        rtype.write({'start_stage_id': stage_id_map.get('new')})

        # Delete old routes
        old_routes = env['request.stage.route'].search([('request_type_id','=',rtype_id)])
        old_routes.unlink()

        # Create routes
        for r_name, from_c, to_c, r_close, r_seq, r_style in ROUTE_TEMPLATE:
            from_id = stage_id_map.get(from_c)
            to_id   = stage_id_map.get(to_c)
            if from_id and to_id:
                env['request.stage.route'].create({
                    'name':            r_name,
                    'stage_from_id':   from_id,
                    'stage_to_id':     to_id,
                    'close':           r_close,
                    'sequence':        r_seq,
                    'request_type_id': rtype_id,
                })

        return True
    except Exception:
        print(f"    ! Error on {rtype_code}:")
        traceback.print_exc()
        return False

ok_count  = 0
err_count = 0
BATCH     = 10

codes = list(type_map.keys())
for i, code in enumerate(codes, 1):
    rtype_id = type_map[code]
    success  = build_stages_and_routes(rtype_id, code)
    if success:
        ok_count += 1
        print(f"  ✓ [{i}/{len(codes)}] {code}")
    else:
        err_count += 1
        print(f"  ✗ [{i}/{len(codes)}] {code} — FAILED")

    # Commit in batches
    if i % BATCH == 0:
        env.cr.commit()
        print(f"    [committed batch at {i}]")

env.cr.commit()
print(f"\n  ✓ Stages/routes: {ok_count} OK | {err_count} errors")



# ================================================================
# STEP 6: CREATE CLASSIFIERS (Service → Category → Type)
# ================================================================
print("\n" + "-" * 70)
print("  STEP 6: CLASSIFIERS (Service → Category → Type)")
print("-" * 70)

# Map domain prefix → service code
DOMAIN_SERVICE_MAP = {
    "BLDG":  "SVC-BLDG",
    "PLUMB": "SVC-PLUMB",
    "PLANT": "SVC-PLANT",
    "SEC":   "SVC-SEC",
    "FLEET": "SVC-FLEET",
    "HELP":  "SVC-HELP",
}

classifier_ok  = 0
classifier_err = 0

for type_code, type_id in type_map.items():
    prefix   = type_code.split("-")[0]
    svc_code = DOMAIN_SERVICE_MAP.get(prefix)
    cat_code = type_cat_map.get(type_code)
    svc_id   = service_map.get(svc_code) if svc_code else None
    cat_id   = cat_map.get(cat_code) if cat_code else None

    if not svc_id or not cat_id:
        print(f"  ! Skipping {type_code} — missing service or category")
        continue

    # Check if classifier already exists
    existing = env['request.classifier'].search([
        ('service_id', '=', svc_id),
        ('category_id', '=', cat_id),
        ('type_id', '=', type_id),
    ], limit=1)

    if not existing:
        try:
            env['request.classifier'].create({
                'service_id':  svc_id,
                'category_id': cat_id,
                'type_id':     type_id,
                'active':      True,
            })
            classifier_ok += 1
            print(f"  + Classifier: {svc_code} → {cat_code} → {type_code}")
        except Exception as e:
            classifier_err += 1
            print(f"  ✗ Failed: {type_code} — {e}")
    else:
        classifier_ok += 1
        print(f"  o Exists: {svc_code} → {cat_code} → {type_code}")

env.cr.commit()
print(f"\n  ✓ Classifiers: {classifier_ok} OK | {classifier_err} errors")




# ================================================================
# ================================================================
#   PART C — FLEET
# ================================================================
# ================================================================
print()
print("=" * 70)
print("  PART C: NRS FLEET — 1,617 VEHICLES")
print("=" * 70)


print()
print("=" * 70)
print("  NRS FLEET — VEHICLE IMPORT SEED SCRIPT")
print("  1,617 Vehicles | WestMetro Limited | www.westmetrong.com")
print("=" * 70)


# ================================================================
# VEHICLE DATA
# ================================================================
VEHICLES = [
  {
    "license_plate": "RB818FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2905748",
    "engine_no": "5503213673",
    "location": "S&SM REP-ABC",
    "department": "ABC SCO",
    "driver_name": "SS&FMD UNIT POOL ABC",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS733",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833863",
    "engine_no": "VF3DDNFPRDJ833863",
    "location": "H-YENAGOA GBTO",
    "department": "YENAGOA GBTO",
    "driver_name": "ISREAL UDOUDO",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS191",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E9030009959",
    "engine_no": "2ZRU090419",
    "location": "CALABAR MSTO",
    "department": "CROSS RIVER GBTO",
    "driver_name": "JOSEPH OHIEMI",
    "sco": "ABC"
  },
  {
    "license_plate": "343FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103034659",
    "engine_no": "2ZRU654502",
    "location": "AD-AKWA IBOM GBTO",
    "department": "AKWA IBOM GBTO",
    "driver_name": "OKWONG VICTOR",
    "sco": "ABC"
  },
  {
    "license_plate": "RB886FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFx02P405006422",
    "engine_no": "2694",
    "location": "ABC SCO",
    "department": "SCO ABC",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS380",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P206054057",
    "engine_no": "2TR 8171501",
    "location": "IKOM MSTO",
    "department": "IKOM MSTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS582",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108020821",
    "engine_no": "8254543",
    "location": "YENAGOA MSTO",
    "department": "YENAGOA MSTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "266FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008035312",
    "engine_no": "2TR8504215",
    "location": "GBTO BAYELSA",
    "department": "YENAGOA GBTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "272FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708035324",
    "engine_no": "2TR8504378",
    "location": "GBTO CALABAR",
    "department": "CALABAR GBTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "306FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108036002",
    "engine_no": "2TR8515617",
    "location": "GBTO AKWA IBOM",
    "department": "AKWA IBOM GBTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "350FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P600053111",
    "engine_no": "2TR8562368",
    "location": "UYO MSTO",
    "department": "UYO MSTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS869",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808044923",
    "engine_no": "2TR9000038",
    "location": "SCO ABC",
    "department": "SCO ABC",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS624",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903022212",
    "engine_no": "2ZRU297129",
    "location": "TC-MSTO YENAGOA",
    "department": "MSTO YENAGOA",
    "driver_name": "SULIEMAN MOHAMMED",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS185",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703009961",
    "engine_no": "ZZRU091769",
    "location": "TC-IKOM MSTO",
    "department": "IKOM MSTO",
    "driver_name": "UBA MBANG",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS1072",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAKXJR882585",
    "engine_no": "NC02H047402",
    "location": "TC-STO",
    "department": "STO AKWA IBOM",
    "driver_name": "UDEME BOB",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS1419",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT353929",
    "engine_no": "4A92*S3LH979",
    "location": "TC, UYO MSTO-AKWA IBOM",
    "department": "TC, UYO MSTO-AKWA IBOM",
    "driver_name": "MUKORO O. JOHNSON",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS816",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833765",
    "engine_no": "VF3DDNFPRDJ833765",
    "location": "REGIONAL ADMINISTRATION OFFICE",
    "department": "REGIONAL ADMINISTRATION OFFICE",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS665",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE900001605",
    "engine_no": "2ZRU-798853",
    "location": "AD/BAUCHI MSTO",
    "department": "KADUNA 3 MSTO",
    "driver_name": "SHEHU DARASU",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS1404",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02RT353917",
    "engine_no": "4A92*S3LJ001",
    "location": "AD/SCO,BBY",
    "department": "HCMD",
    "driver_name": "BUNU KAUMI",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS498N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL035545",
    "engine_no": "GL035545",
    "location": "RETRIEVED BACK TO FLEET POOL",
    "department": "YET TO BE RE-ALLOCATED",
    "driver_name": "ETSU MOHAMMED MADAMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS233",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLCS58E103009731",
    "engine_no": "2ZRU090659",
    "location": "AZARE ETO",
    "department": "AZARE ETO",
    "driver_name": "Ibrahim Babayo",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS751",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808728",
    "engine_no": "VF3DDNFPRDJ808728",
    "location": "SAO BBY",
    "department": "HR SAO-BBY",
    "driver_name": "Amos Mallum",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS1340",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE5RD922716",
    "engine_no": "P3C1527392",
    "location": "GBTO BAUCHI",
    "department": "GBTO BAUCHI",
    "driver_name": "MOHAMMED ADAM M.M.",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS765/134FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03027225",
    "engine_no": "2ZRU418683",
    "location": "SAO BBY",
    "department": "ACCOUNT UNIT SCO BBPY",
    "driver_name": "NURA ABUBAKAR BUNZA",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS198",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P906041544",
    "engine_no": "8135725",
    "location": "BAUCHI ETO",
    "department": "BAUCHI ETO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS362",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06073889",
    "engine_no": "2TR8226929",
    "location": "MAIDUGURI ETO",
    "department": "MAIDUGURI ETO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS363",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P006073882",
    "engine_no": "2TR8228242",
    "location": "AZARE ETO",
    "department": "AZARE ETO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS631",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608021897",
    "engine_no": "8273591",
    "location": "SAO BBY",
    "department": "BBY",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS718/142FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08012110",
    "engine_no": "2TR7147696",
    "location": "SAO BBPY",
    "department": "SSM SAO BBY",
    "driver_name": "SSM SAO BBY",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS699/169FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008027873",
    "engine_no": "ZTR8370737",
    "location": "MAIDUGURI ETO",
    "department": "MAIDUGURI ETO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "244FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308035269",
    "engine_no": "2TR8503641",
    "location": "BAUCHI GBTO",
    "department": "BAUCHI GBTO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "269FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408035314",
    "engine_no": "2TR8504292",
    "location": "YOBE GBTO",
    "department": "YOBE GBTO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "313FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108036226",
    "engine_no": "2TR8500603",
    "location": "BORNO GBTO",
    "department": "BORNO GBTO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS790",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808044422",
    "engine_no": "2TR8713696",
    "location": "TAX AUDIT BAUCHI",
    "department": "TAX AUDIT BAUCHI",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS828",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ803855",
    "engine_no": "VF3DDNFPRDJ803855",
    "location": "SAO BBPY",
    "department": "LEGAL SCO-BBY",
    "driver_name": "Ali A. Aljashim",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS1020",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P800051070",
    "engine_no": "JTFJX02P800051070",
    "location": "Loan to Damaturu ETA",
    "department": "Damaturu ETA",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS643",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03025720",
    "engine_no": "2ZRU391546",
    "location": "SAO-Baucchi ETO",
    "department": "Bauchi ETO",
    "driver_name": "Munka'ila Hussaini",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS640N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE200005009",
    "engine_no": "2ZR- U931333",
    "location": "GBTO BORNO",
    "department": "GBTO BORNO",
    "driver_name": "ALHAJI IBRAHIM",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS994",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ642747",
    "engine_no": "VF3DDNFPRDJ642747",
    "location": "AD-SC'S OFFICE BENUE, KADUNA & NIGER",
    "department": "SCO BKN",
    "driver_name": "AISHA WUSHISHI LARAI",
    "sco": "BKN"
  },
  {
    "license_plate": "FIRS1254",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP0M6010325",
    "engine_no": "7GR-FKS3456",
    "location": "BIDA MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "BKN"
  },
  {
    "license_plate": "FIRS744",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ820144",
    "engine_no": "VF3DDNFPRDJ820144",
    "location": "TC-MTO KADUNA",
    "department": "MTO KADUNA",
    "driver_name": "ABDULKADIR ALI",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS755",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808742",
    "engine_no": "VF3DDNFPRDJ808742",
    "location": "HEAD,LEGAL UNIT KADUNA",
    "department": "KADUNA SOUTH MSTO",
    "driver_name": "ABUBAKAR SULEIMAN",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1355",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05RT352017",
    "engine_no": "S3LJ016",
    "location": "AD,TC, KADUNA 2 MSTO",
    "department": "AD,TC, KADUNA 2 MSTO",
    "driver_name": "ABUBAKAR USMAN",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS923",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833800",
    "engine_no": "VF3DDNFPRDJ833800",
    "location": "KADUNA GBTO",
    "department": "KADUNA GBTO",
    "driver_name": "ALFA HASSAN MOHAMMED",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS990",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ644378",
    "engine_no": "VF3DDNFPRDJ644378",
    "location": "DD-PLATEAU GBTO",
    "department": "PLATEAU GBTO",
    "driver_name": "ARUORIWO IBILIBOR",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS523",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E703016881",
    "engine_no": "2ZRU175898",
    "location": "TC-ZARIA MSTO",
    "department": "ZARIA MSTO",
    "driver_name": "BASHIR YUSUF",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1154",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z1NUOO6201",
    "engine_no": "L6T7722Z1NUOO6201",
    "location": "SCO-BKP",
    "department": "",
    "driver_name": "STATE COORDINATION",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS779/176FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203027865",
    "engine_no": "2ZRU444156",
    "location": "H-DMO JOS",
    "department": "DMO JOS",
    "driver_name": "MARTHA HAUWA SATI",
    "sco": "BKP"
  },
  {
    "license_plate": "358FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603035063",
    "engine_no": "2ZRU680792",
    "location": "TC-JOS MSTO",
    "department": "JOS MSTO",
    "driver_name": "TC JOS MSTO, mohammad gidado auwal",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS598N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G108028082",
    "engine_no": "AHTFX22G108028082",
    "location": "OECFIRS KADUNA",
    "department": "OECFIRS",
    "driver_name": "OECFIRS POOL",
    "sco": "BKP"
  },
  {
    "license_plate": "234FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603031319",
    "engine_no": "2ZRU518892",
    "location": "BENUE GBTO STATE MONITOR",
    "department": "BENUE GBTO",
    "driver_name": "AKOLO",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS217",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P406043657",
    "engine_no": "8141118",
    "location": "MAKURDI MSTO",
    "department": "MAKURDI MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS370",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706072585",
    "engine_no": "2TR 8231894",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS562",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608021821",
    "engine_no": "8272643",
    "location": "JOS MSTO,",
    "department": "JOS MSTO",
    "driver_name": "JOS MSTO, BBPY POOL",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS658/69FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808025305",
    "engine_no": "8332549",
    "location": "JOS MSTO,",
    "department": "JOS MSTO",
    "driver_name": "JOS MSTO, BBPY POOL",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS714/156FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08025841",
    "engine_no": "2TR8341103",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS800/197FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G108016689",
    "engine_no": "2TR 7360126",
    "location": "S&SM REP BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "267FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008035326",
    "engine_no": "2TR8504359",
    "location": "BENUE GBTO",
    "department": "BENUE GBTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "304FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708036196",
    "engine_no": "2TR8518784",
    "location": "MAKURDI MSTO",
    "department": "MAKURDI MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "319FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608036206",
    "engine_no": "2TR8518929",
    "location": "PLATEAU GBTO",
    "department": "PLATEAU GBTO",
    "driver_name": "PLATEAU GBTO POOL, BBPY SCO",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS762",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08044390",
    "engine_no": "2TR8712889",
    "location": "KADUNA TAX AUDIT",
    "department": "SCO BKP",
    "driver_name": "TAX AUDIY POOL",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS781",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08044485",
    "engine_no": "2TR8714761",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS871",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708045075",
    "engine_no": "2TR9003121",
    "location": "KADUNA 1 MSTO",
    "department": "KADUNA 1 MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS629N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROHX8CD4K1388425",
    "engine_no": "MROHX8CD4K1388425",
    "location": "OECFIRS KADUNA",
    "department": "OECFIRS",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1024",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P300051140",
    "engine_no": "JTFJX02P300051140",
    "location": "VAT NORTH WEST REGION / KADUNA",
    "department": "VAT NORTH WEST REGION / KADUNA",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1155",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z7MWO36106",
    "engine_no": "L6T7824Z7MWO36106",
    "location": "AD,LARGE TAX AUDIT KANO",
    "department": "AD,LARGE TAX AUDIT KANO",
    "driver_name": "SHUAIBU SUNUSI GWARAM",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1173",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z1MW036103",
    "engine_no": "L6T7824Z1MW036103",
    "location": "TC-MTO ABUJA",
    "department": "MTO ABUJA",
    "driver_name": "AMINA TIJJANI DAURA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1336",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE0RD922719",
    "engine_no": "P301527365",
    "location": "OECFIRS",
    "department": "OEC/ TC ASOKORO MSTO",
    "driver_name": "AMINU SAMAILA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1350",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02RT351987",
    "engine_no": "S3LH970",
    "location": "AD/KUBWA MSTO",
    "department": "MSTO",
    "driver_name": "BEAUTY AGADAGA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS820",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ810410",
    "engine_no": "VF3DDNFPRDJ810410",
    "location": "HEAD ASOKORO MSTA",
    "department": "ASOKORO MSTA",
    "driver_name": "NASIRU YUSUF MOHAMMED",
    "sco": "FCT"
  },
  {
    "license_plate": "RB880FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P600009481",
    "engine_no": "422617",
    "location": "CENTRAL AREA MSTO",
    "department": "CENTRAL AREA MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS611",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P9A8019154",
    "engine_no": "2TR8237620",
    "location": "UTAKO MSTO",
    "department": "UTAKO MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS821/43FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808030830",
    "engine_no": "2ZRU8430604",
    "location": "KUBWA MSTO",
    "department": "KUBWA MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "203FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008035133",
    "engine_no": "2TR8502022",
    "location": "WUSE IETO/ FCT IRS",
    "department": "WUSE IETO/ FCT IRS",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "271FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808035333",
    "engine_no": "2TR8504437",
    "location": "GBTO ABUJA",
    "department": "",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "353FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308034722",
    "engine_no": "2TR8497378",
    "location": "SCO FCT",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS766",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108044374",
    "engine_no": "2TR8709235",
    "location": "REGIONAL DEBT MGMT OFFICE",
    "department": "RDMO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS769",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708043651",
    "engine_no": "2TR8700712",
    "location": "NORTH CENTRAL DEBT MGMT",
    "department": "DMO SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS838",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008044608",
    "engine_no": "2TR8715683",
    "location": "ASOKORO MSTO",
    "department": "ASOKORO MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS621N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CE9L6003131",
    "engine_no": "6003131",
    "location": "MABUSHI MSTO",
    "department": "MABUSHI MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1004",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P4A0047145",
    "engine_no": "JTFHX02P4A0047145",
    "location": "WUSE 2 MSTO",
    "department": "WUSE 2 MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1036",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P3A0028843",
    "engine_no": "JTGJX02P3A0028843",
    "location": "TAX INVESTIGATION NORTHERN DIVISION",
    "department": "TAX INVESTIGATION NORTHERN DIVISION",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS642",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103024813",
    "engine_no": "2ZRU361865",
    "location": "TAT ABUJA",
    "department": "TAT",
    "driver_name": "TAT",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1356",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05RT351983",
    "engine_no": "S3LJ005",
    "location": "AD/LTO/ OIL & GAS ABUJA",
    "department": "LTO",
    "driver_name": "UMOH ENOBONG ISAAC",
    "sco": "FCT"
  },
  {
    "license_plate": "209FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203033648",
    "engine_no": "2ZRU585400",
    "location": "AD-MSTA-WUSE",
    "department": "MSTA WUSE",
    "driver_name": "UNAZI OTSE",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS451N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ606825",
    "engine_no": "HJ606825",
    "location": "sco fkn /ncrdmo",
    "department": "DMO SCO FCT",
    "driver_name": "USMAN SANI KASSIM",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1446",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AGBPN230026",
    "engine_no": "LNLG32AGBPN230026",
    "location": "GARKI MTO",
    "department": "GARKI MTO",
    "driver_name": "GARKI MTO",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1447",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG2NN210055",
    "engine_no": "LNLG32AG2NN210055",
    "location": "KARU MSTA",
    "department": "KARU MSTA",
    "driver_name": "KARU MSTA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1283",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR4RA960343",
    "engine_no": "PM0AD031038",
    "location": "DD - LTO",
    "department": "LTO GARKI",
    "driver_name": "YERIMA ILIYA SILAS",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS243",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P306035811",
    "engine_no": "8120810",
    "location": "ABUJA LTO",
    "department": "LTO ABUJA",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS629",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608019244",
    "engine_no": "8273276",
    "location": "WUSE MSTO",
    "department": "WUSE MSTO",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS1241",
    "brand": "Innoson",
    "model": "Bus",
    "vin_sn": "LL3AAAAC1JA000188",
    "engine_no": "4RB-275945A",
    "location": "LTA",
    "department": "LTA",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS749/119FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903025966",
    "engine_no": "2ZRU396725",
    "location": "AD-GBO",
    "department": "SCO FKN",
    "driver_name": "YUSUF HUSSIAN",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS45",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803014957",
    "engine_no": "2ZRU133160",
    "location": "AD-ETA YOLA",
    "department": "AD- ETA YOLA",
    "driver_name": "AUWALU ABDULLAHI",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS235",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706041689",
    "engine_no": "8120776",
    "location": "GAT SCO GOMBE",
    "department": "GAT SCO GOMBE",
    "driver_name": "GAT SCO POOL",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS1084",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAKXHR879194",
    "engine_no": "NC02H0",
    "location": "TC-MSTO 9TH MILE",
    "department": "MSTO 9TH MILE",
    "driver_name": "AGU JULIANA UKAMAKA",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS522",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E703015634",
    "engine_no": "2ZRU141041",
    "location": "AD-MTO ENUGU",
    "department": "AD-MTO ENUGU",
    "driver_name": "AMANZE REGINALD",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS837/350 FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803029071",
    "engine_no": "2ZRU464642",
    "location": "SM-ENUGU GBTO",
    "department": "ENUGU GBTO",
    "driver_name": "ANAGA MARY",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS798",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808744",
    "engine_no": "VF3DDNFPRDJ808744",
    "location": "LEGAL UNIT ENUGU",
    "department": "LEGAL",
    "driver_name": "EDWIN NWEKE",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1277",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKRXRA960377",
    "engine_no": "PM0AD025843",
    "location": "YET TO BE ALLOCATED",
    "department": "YET TO BE ALLOCATED",
    "driver_name": "YET TO BE ALLOCATED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS740/95FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103027310",
    "engine_no": "2RU416554",
    "location": "TC-MSTA BAYELSA",
    "department": "MSTA BAYELSA",
    "driver_name": "EKECHUKWU SABINA",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS904",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ876086",
    "engine_no": "VF3DDNFPRDJ876086",
    "location": "AD-MTA ENUGU",
    "department": "MTA ENUGU",
    "driver_name": "CHRISTOPHER NDU",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS183",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303009939",
    "engine_no": "Z2RU090430",
    "location": "EBONYI GBTO",
    "department": "EBONYI GBTO",
    "driver_name": "ETIM EMMANUEL",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1193",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z6MW009043",
    "engine_no": "L6T7824Z6MW009043",
    "location": "AD-TPAD",
    "department": "AD-TPAD",
    "driver_name": "KAFILAT BOLANLE AZEEZ",
    "sco": "HQ"
  },
  {
    "license_plate": "RB739FG / RB028FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "3114869",
    "engine_no": "1994470",
    "location": "HEAD, ABIA GBA",
    "department": "GBA",
    "driver_name": "NDUCHE CHINYELU E",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS244",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803009760",
    "engine_no": "2ZRUO91449",
    "location": "TC-OSISIOMA MSTO",
    "department": "OSISIOMA MSTO",
    "driver_name": "NELSON DURU",
    "sco": "EEA"
  },
  {
    "license_plate": "289FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003034393",
    "engine_no": "2ZRU648704",
    "location": "AD-SCO EEA",
    "department": "SCO EEA",
    "driver_name": "NWITTE NKWO",
    "sco": "EEA"
  },
  {
    "license_plate": "219FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103032068",
    "engine_no": "2ZRU547287",
    "location": "AD-ABIA GBTO",
    "department": "ABIA GBTO",
    "driver_name": "OBIAJUNWA NICHOLAS",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS993",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ691089",
    "engine_no": "VF3DDNFPRDJ691089",
    "location": "AD-EEA SCO",
    "department": "EEA SCO",
    "driver_name": "ODEY HILARY IKADE",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS935",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ873989",
    "engine_no": "VF3DDNFPRDJ873989",
    "location": "D-MTD",
    "department": "MTD",
    "driver_name": "OKORONKWO UCHE NNANA",
    "sco": "HQ"
  },
  {
    "license_plate": "RB725FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "7102387",
    "engine_no": "3368626",
    "location": "OWERRI MSTO",
    "department": "OWERRI MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS102",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "E4002913",
    "engine_no": "289557",
    "location": "ENUGU SCO",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS145",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P5060948",
    "engine_no": "338136390",
    "location": "ABAKALIKI MSTO",
    "department": "ABAKALIKI MSTO",
    "driver_name": "ABAKILIKI MSTO POOL EEA SCOO",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS214",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706041384",
    "engine_no": "8135235",
    "location": "OSISIOMA MSTO",
    "department": "OSISIOMA MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS326",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 208017720",
    "engine_no": "8224630",
    "location": "ABA MSTO",
    "department": "ABA MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS327",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 608017638",
    "engine_no": "8223989",
    "location": "ENUGU SCO",
    "department": "UMMUAHIA MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS403",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFX12P408017864",
    "engine_no": "2TR8225994",
    "location": "ENUGU MSTO",
    "department": "ENUGU MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS566",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708017177",
    "engine_no": "8219801",
    "location": "ABAKALIKI MSTO",
    "department": "ABAKALIKI MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS580",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408021378",
    "engine_no": "8267596",
    "location": "EEA SCO",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS659/68FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808025322",
    "engine_no": "8332069",
    "location": "SCO EEA",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS660/71FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708020673",
    "engine_no": "8346071",
    "location": "ENUGU MSTO",
    "department": "ENUGU MSTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS661/87FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX05024804",
    "engine_no": "8319373",
    "location": "EEA SCO",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS719/143FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08012026",
    "engine_no": "2TR7140150",
    "location": "ENUGU SCO ENFORCEMENT",
    "department": "POLICE ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS775/124FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203027879",
    "engine_no": "2ZRU438905",
    "location": "H-ETA ABAKALIKI",
    "department": "ABAKALIKI ETA",
    "driver_name": "JUSTINA NNACHI",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS855/FIRS505",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608031846",
    "engine_no": "2TR8455737",
    "location": "ENUGU MTO",
    "department": "ENUGU MTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "246FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308035305",
    "engine_no": "2TR8504088",
    "location": "GBTO ENUGU",
    "department": "ENUGU GBTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "268FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108035321",
    "engine_no": "2TR8490773",
    "location": "MTO ENUGU",
    "department": "ENUGU MTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "305FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308036020",
    "engine_no": "2TR8515005",
    "location": "GBTO EBOYIN",
    "department": "EBONYI GBTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "311FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308036101",
    "engine_no": "2TR8517267",
    "location": "GBTO ABIA",
    "department": "ABIA GBTO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS764",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608044371",
    "engine_no": "2TR8709238",
    "location": "EEA SCO",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS779",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308044473",
    "engine_no": "2TR8714402",
    "location": "UMUAHIA MSTO/ENUGU SCO",
    "department": "UMUAHIA MSTO/ENUGU SCO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS791",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908044414",
    "engine_no": "2TR8712963",
    "location": "MSTA",
    "department": "MSTA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS840",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208044643",
    "engine_no": "2TR8717877",
    "location": "SCO EEA",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS866",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518704024703",
    "engine_no": "2TR9012161",
    "location": "SCO EEA",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1032",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P205009268",
    "engine_no": "JTFJX02P205009268",
    "location": "MTA ENUGU",
    "department": "MTA ENUGU",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "RB694FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E300110608",
    "engine_no": "12ZFF1794",
    "location": "REP,SS&FMD AEE",
    "department": "SSFMD",
    "driver_name": "ORJINWEKE O.C",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1359",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT351991",
    "engine_no": "S3LS069",
    "location": "AD/TC ENUGU ETO",
    "department": "ENUGU ETO",
    "driver_name": "STELLA OBIORA",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1085",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK3HR879019",
    "engine_no": "NC02H0",
    "location": "HEAD/STO AFIKPO",
    "department": "STO AFIKPO",
    "driver_name": "SUNDAY EZEH",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS645",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHLC58E03025832",
    "engine_no": "2ZRU392136",
    "location": "TAT ENUGU",
    "department": "TAT",
    "driver_name": "TAT",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS104",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603001553",
    "engine_no": "2ZRU055597",
    "location": "SCO GOMBE",
    "department": "SCO GOMBE",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS155",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P06041217",
    "engine_no": "8134728",
    "location": "JALINGO MSTO",
    "department": "JALINGO MSTO",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "228FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003032014",
    "engine_no": "2ZRU542279",
    "location": "TC-ETO YOLA",
    "department": "TC-ETO YOLA",
    "driver_name": "OMOTAYO AZEEZ ALAKA",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS927",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ530614",
    "engine_no": "VF3DDNFPRDJ530614",
    "location": "SCO JKK",
    "department": "KANO III MSTO",
    "driver_name": "DATTI NABABA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1313",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR2RA960793",
    "engine_no": "LS5A3AKR2RA960793",
    "location": "TC/KANO 2",
    "department": "KANO 2 MSTO",
    "driver_name": "BASHIR ALIYU",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS525",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56EX03016857",
    "engine_no": "2ZRU172140",
    "location": "HEAD-MSTA KATSINA",
    "department": "MSTA KATSINA",
    "driver_name": "ABDULKADIR YUNUSA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS364N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ613013",
    "engine_no": "VF3DDNFPRDJ613013",
    "location": "TC-DUTSE MSTO",
    "department": "DUTSE MSTO",
    "driver_name": "ABUBAKAR LIRA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS152",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "ATLCS58E703009815",
    "engine_no": "63416",
    "location": "TC-FUNTUA MSTO/SM",
    "department": "MSTO FUNTUA",
    "driver_name": "ADAMA ABDULRAHIM",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1312",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR4RA960794",
    "engine_no": "LS5A3AKR4RA960794",
    "location": "SCO (JKK)",
    "department": "SCO (JKK)",
    "driver_name": "HAFSAT SANI",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS103",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E600291588",
    "engine_no": "2911347",
    "location": "KANO 3 SMTA",
    "department": "KANO 3 SMTA",
    "driver_name": "ABBA SANI ABUBAKAR",
    "sco": "JKK"
  },
  {
    "license_plate": "RB704FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBW21E803019827",
    "engine_no": "2NZ-FE1299",
    "location": "KANO STAMP DUTIES",
    "department": "STAMP DUTIES KANO",
    "driver_name": "ISMAILA ADAMU ISA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS52",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E200267675",
    "engine_no": "1ZZ-FE 1794",
    "location": "KANO 1 MSTO POOL",
    "department": "KANO MTO",
    "driver_name": "KANO 1 MSTO POOL",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1368",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT352006",
    "engine_no": "LGJF1FE00RT352006",
    "location": "AD/TC,KANO MSTO III",
    "department": "KANO 3 MSTO",
    "driver_name": "MOHAMMED IDRIS BULTU",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS746/135FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803027157",
    "engine_no": "2ZRU422364",
    "location": "AD - JIGAWA",
    "department": "JIGAWA GBO",
    "driver_name": "MUSA RILWAN",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS533",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E903018440",
    "engine_no": "2ZRU199896",
    "location": "TC-KATSINA MSTO",
    "department": "KATSINA MSTO",
    "driver_name": "NASIRU SANI DAURA",
    "sco": "JKK"
  },
  {
    "license_plate": "RB884FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P105006376",
    "engine_no": "2TR-FE 2694",
    "location": "KANO 2 MSTO",
    "department": "KANO 2 MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS202",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P606043417",
    "engine_no": "2TR8140863",
    "location": "KATSINA MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS379",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708017910",
    "engine_no": "2TR 8226482",
    "location": "LTA KANO",
    "department": "LTA KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS565",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608017669",
    "engine_no": "8224188",
    "location": "KANO 2 MSTO",
    "department": "KANO 2 MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS567",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708017678",
    "engine_no": "8224213",
    "location": "KANO 1 MSTO POOL",
    "department": "KANO 1 MSTO POOL",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS601",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008022043",
    "engine_no": "2TR8274707",
    "location": "KATSINA MSTO",
    "department": "KATSINA MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS616",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P4A8019143",
    "engine_no": "2TR8237378",
    "location": "FUNTUA MSTO",
    "department": "FUNTUA MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS703/55FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208026952",
    "engine_no": "2TR8346819",
    "location": "SCO JKK",
    "department": "SCO JKK",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS711/52FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026920",
    "engine_no": "2TR8358501",
    "location": "MTO KANO",
    "department": "MTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS784",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808044419",
    "engine_no": "2TR8713543",
    "location": "LTA KANO",
    "department": "LTA KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS839",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08044647",
    "engine_no": "2TR8717881",
    "location": "SCO JKK",
    "department": "SCO JKK",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS872",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508045074",
    "engine_no": "2TR9003131",
    "location": "LTO KANO",
    "department": "LTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1009",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P390040165",
    "engine_no": "JTFHX02P390040165",
    "location": "MTA KANO",
    "department": "MTA KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1018",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TTRH200-0056705",
    "engine_no": "TTRH200-0056705",
    "location": "LTA KANO",
    "department": "LTA KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "274FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803034321",
    "engine_no": "2ZRU643395",
    "location": "AD-SC JKK",
    "department": "LARGE TAX AUDIT",
    "driver_name": "YUSUF NUHU TAFASHIYA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS603N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL025652",
    "engine_no": "VF38D5GYAHL025652",
    "location": "TC/ SULEJA SMTO",
    "department": "SMTO",
    "driver_name": "AHMED SA'ID",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS723",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRD842624",
    "engine_no": "VF3DDNFPRDJ842624",
    "location": "TC-LAFIA MSTO",
    "department": "",
    "driver_name": "EKPANG THOMAS ODOK",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS1075",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK5HR879099",
    "engine_no": "NC02H051299",
    "location": "TC-KEEFFI MSTO",
    "department": "KEFFI MSTO",
    "driver_name": "ADAMU SERIKI IBRAHIM",
    "sco": "KNN"
  },
  {
    "license_plate": "RB748FG/ FIRS270",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "3112232",
    "engine_no": "1969917",
    "location": "LOKOJA STAMP DUTIES",
    "department": "LOKOJA STAMP DUTIES",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS22",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "308178678",
    "engine_no": "2491469",
    "location": "KEFFI ETO",
    "department": "POOL",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS154",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P06043429",
    "engine_no": "8140694",
    "location": "LAFIA MSTO",
    "department": "LAFIA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS371",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P406073953",
    "engine_no": "2TR 8226932",
    "location": "SULEJA MSTO",
    "department": "SULEJA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS672/139FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108026618",
    "engine_no": "2TR8354523",
    "location": "MINNA MSTO",
    "department": "MINNA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "239FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708034710",
    "engine_no": "2TR8496985",
    "location": "KADUNA GBTO",
    "department": "KADUNA GBTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "323FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408036219",
    "engine_no": "2TR8508521",
    "location": "NIGER GBTO",
    "department": "MINNA GBTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "325FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508036097",
    "engine_no": "2TR8517027",
    "location": "GBTO LOKOJA",
    "department": "LOKOJA GBTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "327FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08036094",
    "engine_no": "2TR8517032",
    "location": "LAFIA GBTO",
    "department": "LAFIA GBTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS619N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9L6004019",
    "engine_no": "6004019",
    "location": "SCO/NKN",
    "department": "STAMP DUTIES MINN",
    "driver_name": "SCO/NKN POOL",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS1343/FIRS561",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT352008",
    "engine_no": "S3LH990",
    "location": "AD/GBTO NIGER",
    "department": "AD/GBTO NIGER",
    "driver_name": "SAIDU YAKUBU",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS136",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103009888",
    "engine_no": "2ZRU091720",
    "location": "NIGER GBTO",
    "department": "NIGER GBTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS834",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833860",
    "engine_no": "VF3DDNFPRDJ833860",
    "location": "TC/SMTA LAFIA ,NASARAWA",
    "department": "LAFIA SMTA",
    "driver_name": "IBRAHIM ILIYA",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS931",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE900008330",
    "engine_no": "2ZRV1411681",
    "location": "DD-SA-KNN",
    "department": "DD-SA-KNN",
    "driver_name": "DAUDA ABDULRAHEEM KAYODE",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS666",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE100002618",
    "engine_no": "2ZRU-813241",
    "location": "YOBE GBTO, BBPY SCO",
    "department": "BKP SCO",
    "driver_name": "MOHAMMED MAIGARI",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS531",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E903015456",
    "engine_no": "2ZRU141964",
    "location": "STATE MONITOR/ BORNO GBTO",
    "department": "SCO",
    "driver_name": "MOHAMMED IDRIS BULTU",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS167",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E03009987",
    "engine_no": "2ZRU0090856",
    "location": "Bauchi ETA",
    "department": "Bauchi ETA",
    "driver_name": "Abubakar Musa",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS1326",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK303207363",
    "engine_no": "JTNB19HK303207363",
    "location": "SC,BBY",
    "department": "SC,BBY",
    "driver_name": "MR DAHIRU",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS753/115FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903027104",
    "engine_no": "2ZRU421322",
    "location": "SC BBPY",
    "department": "POOL",
    "driver_name": "ETSU MOHAMMED",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS1206",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z4MW005072",
    "engine_no": "4G15-4907342",
    "location": "STATE COORDINATION OFFICE",
    "department": "STATE COORDINATION OFFICE",
    "driver_name": "SAO BBY",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS768/131FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303027745",
    "engine_no": "2ZRU437040",
    "location": "DAMATURU ETO",
    "department": "DAMATURU ETO",
    "driver_name": "Dalhatu Abubakar",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS157",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P006043803",
    "engine_no": "81415007",
    "location": "DAMATURA ETO",
    "department": "ETO DAMATURU",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS693/73FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108027784",
    "engine_no": "2TR8369670",
    "location": "SAO BBY",
    "department": "SAO BBY",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS749",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830619",
    "engine_no": "VF3DDNFPRDJ830619",
    "location": "MAIDUGURI ETO",
    "department": "MAIDUGURI ETO",
    "driver_name": "Adamu Isa",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS177",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E203009771",
    "engine_no": "2ZRU91373",
    "location": "AD/BBY SCO",
    "department": "BBY SCO",
    "driver_name": "SAIDU IBRAHIM GABARI",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS915",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ849268",
    "engine_no": "VF3DDNFPRDJ849268",
    "location": "HEAD-MSTA KADUNA",
    "department": "MSTA KADUNA",
    "driver_name": "AMEACHI DANIEL",
    "sco": "BKN"
  },
  {
    "license_plate": "FIRS1253",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP0M6010678",
    "engine_no": "7GR-FKS3456",
    "location": "SCO-BKP",
    "department": "SCO",
    "driver_name": "",
    "sco": "BKN"
  },
  {
    "license_plate": "FIRS1019",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P700038648",
    "engine_no": "JTFJX02P700038648",
    "location": "MTA MINNA",
    "department": "MTA MINNA",
    "driver_name": "NIGER MSTA",
    "sco": "BKN"
  },
  {
    "license_plate": "FIRS773",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408043476",
    "engine_no": "2TR8697547",
    "location": "NERDMO",
    "department": "JOS",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1345",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT351998",
    "engine_no": "S3LJ006",
    "location": "AD/VAT MONITOR KADUNA",
    "department": "AD/VAT MONITOR KADUNA",
    "driver_name": "ABDULLAHI FATIMAH M.",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1342",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE7RD922717",
    "engine_no": "P3C1527311",
    "location": "ADT/HEAD MSTA KADUNA",
    "department": "AD/HEAD MST KADUNA",
    "driver_name": "AMINA ETSU",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS308",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803015817",
    "engine_no": "2ZRU140246",
    "location": "TC-MAKURDI MSTO",
    "department": "TC-MAKURDI MSTO",
    "driver_name": "BULUS RIMAMSKEP NUHU",
    "sco": "BKP"
  },
  {
    "license_plate": "286FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003034345",
    "engine_no": "2ZRU647267",
    "location": "DD-VAT-COR-COORDINATOR NWR",
    "department": "VAT NORTH WEST COORDINATION",
    "driver_name": "ISMAILA ZUBAIRU IBI",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1365",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT401173",
    "engine_no": "LGJF1FE06RT401173",
    "location": "ADT/BKP/SCO",
    "department": "ADT/BKP/SCO",
    "driver_name": "MAIGARI MOHAMMED",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS169",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P206043611",
    "engine_no": "8141116",
    "location": "Zaria MSTO",
    "department": "ZARIA MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS369",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P506073835",
    "engine_no": "2TR 8228267",
    "location": "MTO KADUNA",
    "department": "MTO KADUNA",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS577",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408020277",
    "engine_no": "8252905",
    "location": "KADUNA II MSTO",
    "department": "KADUNA II MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS670/85FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708026218",
    "engine_no": "2TR8348306",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS772",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308044442",
    "engine_no": "2TR8687290",
    "location": "JOS MSTA",
    "department": "TAX AUDIT JOS",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS873",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308044828",
    "engine_no": "2TR8713032",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1046",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH2000088566",
    "engine_no": "TRH2000088566",
    "location": "KADUNA 3 MSTO",
    "department": "KADUNA 3 MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS1360",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT351788",
    "engine_no": "S3LH971",
    "location": "KADUNA MSTO",
    "department": "KADUNA MSTO",
    "driver_name": "IBRAHIM ABUBAKAR",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS595N",
    "brand": "Peugeot",
    "model": "3008",
    "vin_sn": "VF3M45GYVJS426376",
    "engine_no": "VF3M45GYVJS426376",
    "location": "TC WUSE MSTO",
    "department": "SCO",
    "driver_name": "ABDULHAMID MUAZU TADAAMA",
    "sco": "FCT"
  },
  {
    "license_plate": "225FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803031287",
    "engine_no": "2ZRU520162",
    "location": "TC WUSE MSTO",
    "department": "SCO",
    "driver_name": "ADBULHAMEED MUASU TADAMA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS648",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03024938",
    "engine_no": "2ZRU365328",
    "location": "ETD FCT",
    "department": "ETD",
    "driver_name": "OGUNMOLA MUDASIRU ALABI",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS650",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003026360",
    "engine_no": "2ZRU399479",
    "location": "MAITAMA IETO",
    "department": "MAITAMA IETO",
    "driver_name": "BELLO MUNATU",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1341",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE6RD922711",
    "engine_no": "P3C1526173",
    "location": "H-ETA KANO1",
    "department": "H-ETA KANO1",
    "driver_name": "BASHIR YUSUF",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1301",
    "brand": "Changan",
    "model": "Eado Dt",
    "vin_sn": "LS5A2AGE5PD910409",
    "engine_no": "NC9BP002023",
    "location": "TC/MABUSHI MSTO",
    "department": "MABUSHI MSTO",
    "driver_name": "CHINWE OFILI",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS637",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903023991",
    "engine_no": "2ZRU345214",
    "location": "CEG",
    "department": "FIELD OPERATIONS",
    "driver_name": "GARBA IRO GUSAU",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1287",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XPT401175",
    "engine_no": "492*53L5066*",
    "location": "H/DEBT/ENFORCEMENT",
    "department": "H/DEBT/ENFORCE",
    "driver_name": "JANADA JAMILA OJORA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS189",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E403009951",
    "engine_no": "2ZRUO93129",
    "location": "AD/TPSD",
    "department": "",
    "driver_name": "MANASSEH ORTAERGA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1190",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T782Z3MW036989",
    "engine_no": "L6T782Z3MW036989",
    "location": "AD- MAITAMA MSTA",
    "department": "MSTA MAITAMA",
    "driver_name": "JEROME A. EKLE",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1358",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE01RT352015",
    "engine_no": "S3LJ020",
    "location": "AD,TC, MAITAMA MSTO",
    "department": "MAITAMA MSTO",
    "driver_name": "KABIR ISMAIL",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS756/114FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903025658",
    "engine_no": "2ZRU396725.",
    "location": "AD-MTA ABUJA",
    "department": "MTA ABUJA",
    "driver_name": "MASAMA MUHAMMED HARUNA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS829/FIRS648",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003031235",
    "engine_no": "2ZRU519595",
    "location": "ETD FCT",
    "department": "ETD",
    "driver_name": "OGUNMOLA MUDASIRU ALABI",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1337",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE3RD910869",
    "engine_no": "P3C1502537",
    "location": "AD,/TC WUSE II MSTO",
    "department": "WUSE MSTO",
    "driver_name": "MUKHTAR HUSSANI",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS943",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586206",
    "engine_no": "VF3DDNFPRGJ586206",
    "location": "HEAD, RESEARCH UNITLEGAL DEPT POOL",
    "department": "LEGAL DEPARTMENT",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS94",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P605005517",
    "engine_no": "397320",
    "location": "GWARINPA SMTO",
    "department": "IEITO GWAGWALADA/ FCT IRS",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "RB840FG/ FIRS38",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P900007409",
    "engine_no": "358000",
    "location": "ABUJA LTO",
    "department": "LTO ABUJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "RB881FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P300009471",
    "engine_no": "2TR-FE 2694.",
    "location": "GBA JOS",
    "department": "GBA JOS",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS156",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P906043752",
    "engine_no": "8141446",
    "location": "STA SULEJA",
    "department": "STA SULEJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS74",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P800008283",
    "engine_no": "381367",
    "location": "WUSE MSTO FKN SCOO",
    "department": "WUSE MSTO FKN SCOO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS325",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 908017651",
    "engine_no": "8224096",
    "location": "LTA UTAKO",
    "department": "LTA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS372",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706073946",
    "engine_no": "2TR 8226924",
    "location": "UTAKO MSTO",
    "department": "UTAKO MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS571",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308021758",
    "engine_no": "2TR8272264",
    "location": "GBTO ABUJA",
    "department": "GBTO ABUJA",
    "driver_name": "GBTO ABUJA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS667/164FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRXT2P808025241",
    "engine_no": "8331208",
    "location": "ASOKORO MSTO",
    "department": "ASOKORO MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1226",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK7L3013581",
    "engine_no": "JTNBZ4HK7L3013581",
    "location": "ABUJA",
    "department": "GBTD",
    "driver_name": "ATIKU MUHAMMED DUKKU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS609N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL014066",
    "engine_no": "VF38D5GYAHL014066",
    "location": "LTA ABUJA/ HEAD",
    "department": "POOL",
    "driver_name": "ATIKU MOHAMMED DUKKU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS757",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833876",
    "engine_no": "VF3DDNFPRDJ833876",
    "location": "FIELD OPERATIONS MANAGEMENT DEPARTMENT",
    "department": "FIELD OPERATIONS MANAGEMENT DEPARTMENT",
    "driver_name": "EVELYN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1422",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05RT353930",
    "engine_no": "4A92*S3LH977",
    "location": "AD,LITIGATION & PROS DEPT",
    "department": "LITIGATION & PROS DEPT",
    "driver_name": "AKUBUO IFEANYI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS835",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808737",
    "engine_no": "VF3DDNFPRDJ808737",
    "location": "SOP POOL",
    "department": "SSFMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS647",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03025247",
    "engine_no": "2ZRU375535",
    "location": "AD/ BOARD SECRETARY",
    "department": "AD/ BOARD SECRETARY",
    "driver_name": "JOY KANGYANG",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS133/FIRS1029",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803009953",
    "engine_no": "2ZRU090388",
    "location": "AD-HEAD GROUP 6 LTA",
    "department": "LTA ABUJA",
    "driver_name": "ABUBAKAR ADAMU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS814",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ818557",
    "engine_no": "VF3DDNFPRDJ818557",
    "location": "OSA-COMMUNICATION",
    "department": "OSA-COMMUNICATION",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS463N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ609997",
    "engine_no": "HJ609997",
    "location": "AD-GBTO",
    "department": "GBTO",
    "driver_name": "DONALD NOSIRI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS831",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ813695",
    "engine_no": "VF3DDNFPRDJ813695",
    "location": "AD/VAT",
    "department": "F&A, FILING & ARCHIVING",
    "driver_name": "ATTAH A.O",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS545",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203017708",
    "engine_no": "2ZRU192174",
    "location": "ADH-WUSE1 AUDIT",
    "department": "WUSE1 AUDIT",
    "driver_name": "OJOGBE REUBEN UGBEDA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS825",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ810405",
    "engine_no": "VF3DDNFPRDJ810405",
    "location": "OECFIRS POOL",
    "department": "OEC POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1045",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH2000101883",
    "engine_no": "TRH2000101883",
    "location": "WUSE- MSTA",
    "department": "MSTA WUSE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1231",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508050095",
    "engine_no": "JTFRX12P508050095",
    "location": "LARGE TAX OFFICE",
    "department": "LTO",
    "driver_name": "OIL & GAS ABUJA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS137",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E03009840",
    "engine_no": "2ZRU091853",
    "location": "HEAD /BCM /RAD",
    "department": "REVENUE ACCOUNTING DEPARTMENT",
    "driver_name": "SHAMSUDDEN I. MAHUTA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1291",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03PT401180",
    "engine_no": "4A92*S3LS082*",
    "location": "CSO-OECFIRS",
    "department": "OECFIRS",
    "driver_name": "ABAYOMI OKUNDAYO",
    "sco": "HQ"
  },
  {
    "license_plate": "38FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003029453",
    "engine_no": "2ZRU471003",
    "location": "AD-LL&P",
    "department": "LEGAL",
    "driver_name": "ABBA DALHATU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS569N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4T1B11HK2KU783444",
    "engine_no": "A25AG213836",
    "location": "D-RMD",
    "department": "RMD",
    "driver_name": "IDRIS HAKEEM OLANIYI",
    "sco": "HQ"
  },
  {
    "license_plate": "RB686FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "96189",
    "engine_no": "1133092",
    "location": "SS&FM-REP AEIO",
    "department": "SSFMD AEIO",
    "driver_name": "ABBO MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1306",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR7RA960739",
    "engine_no": "LS5A3AKR7RA960739",
    "location": "BOARD SECRETARY",
    "department": "BPARD SECRETARY",
    "driver_name": "DANIEL ONUKU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS486",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E003015927",
    "engine_no": "2ZRU139848",
    "location": "AD- FMD",
    "department": "FMD",
    "driver_name": "ABDULKADIR ABBAS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS396N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "6T1BF4FK4GX635215",
    "engine_no": "2ARU312905",
    "location": "D-C&LD",
    "department": "CLD",
    "driver_name": "ABDULLAHI ISMAILA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1192",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z0MW036089",
    "engine_no": "L6T7824Z0MW036089",
    "location": "D-C&LD",
    "department": "D/COMMUNICATION POOL",
    "driver_name": "ABDULLAHI ISMAILA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1092",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK4L3016048",
    "engine_no": "JTNBZ4HK4L3016048",
    "location": "D-LL&P",
    "department": "D-LEGAL",
    "driver_name": "ABU OCHEME STEPHEN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS657",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE300002507",
    "engine_no": "2ZRU-811531",
    "location": "D-LL&P (POOL)",
    "department": "LEGAL",
    "driver_name": "ABU OCHEME STEPHEN\n1ST CAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1304",
    "brand": "Lexus",
    "model": "Rx330",
    "vin_sn": "JTHA31U060101757",
    "engine_no": "JTHA31U060101757",
    "location": "DEBT MGT",
    "department": "HEAD DEBT MGT DEPT",
    "driver_name": "FALOWO AUGUSTINE PETER",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1423",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT353916",
    "engine_no": "4A92*S3LH994",
    "location": "OECFIRS,SA",
    "department": "OEC",
    "driver_name": "ABUBAKAR M. YASSAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS420N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL03094",
    "engine_no": "GL030394",
    "location": "POLICE ENFORCEMENT UNIT",
    "department": "PEU",
    "driver_name": "KYROM KYES",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS504N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE4G5255626",
    "engine_no": "3ZRX597089",
    "location": "AD/HCMD",
    "department": "HCMD",
    "driver_name": "ADAMA AUDU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1189",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2AGE6PD910435",
    "engine_no": "JL48-P002104",
    "location": "ORDERLY/OEC/FIRS",
    "department": "OECFIRS",
    "driver_name": "SHOLA AKEEM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1184",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z3NX404788",
    "engine_no": "LB37622Z3NX404788",
    "location": "DD- PROCUREMENT DEPT",
    "department": "PROCUREMENT DEPARTMENT",
    "driver_name": "ADAMU LUCAS H",
    "sco": "HQ"
  },
  {
    "license_plate": "284FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003034362",
    "engine_no": "2ZRU647090",
    "location": "AD-P&E FMD",
    "department": "FMD",
    "driver_name": "ADBDULLAHI SALISU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS940",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE700004583",
    "engine_no": "2ZRU876989",
    "location": "D - TAX TECHNOLOGY - VAT",
    "department": "TAX TECH.",
    "driver_name": "ADEBAYO ADEFEEGBE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1421",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT353922",
    "engine_no": "4A92*S3LH969",
    "location": "AD,SPECIAL TAX CRIME OFFI",
    "department": "SPECIAL TAX CRIME",
    "driver_name": "ADEBUKOLA OLUWAYINKA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1361",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT352004",
    "engine_no": "S3LH975",
    "location": "AD/IAD ABUJA",
    "department": "IAD",
    "driver_name": "ADEMOLA AWOBADEJO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS262",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703009801",
    "engine_no": "2ZRU092916",
    "location": "AD/SPECIAL PURPOSE INVES",
    "department": "SPECIAL TAX CRIME",
    "driver_name": "ANCHI APPOLOS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1409",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVGBC7K7PG244618",
    "engine_no": "LG00192A25G",
    "location": "EC-FIRS-SA CUSTOMER\nCENT",
    "department": "ECFIRS-SA CUSTOMER CENT",
    "driver_name": "ADESOLA OYINLOYE-NDU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1334",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE4RD922710",
    "engine_no": "P3C1526969",
    "location": "OECFIRS /POOL",
    "department": "SA - PROTOCOL",
    "driver_name": "ADETOYESE IPADEOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "330FIRS",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SB1BL76L80E035628",
    "engine_no": "3RZB119886",
    "location": "AD-FMD",
    "department": "FMD",
    "driver_name": "AFESO DAVID",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1156",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z6MWO28899",
    "engine_no": "L6T7824Z6MWO28899",
    "location": "D-IAD (POOL)",
    "department": "IAD (POOL)",
    "driver_name": "AHMED IDRIS NDANUSA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1161",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK1L3016007",
    "engine_no": "JTNBZ4HK1L3016007",
    "location": "D-OEC FIRS",
    "department": "D - OEC",
    "driver_name": "AISHA MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1191",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z5MW036119",
    "engine_no": "L6T7824Z5MW036119",
    "location": "D-OEC FIRS",
    "department": "OECD (POOL)",
    "driver_name": "AISHA MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1387",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE1RD922728",
    "engine_no": "P3C1527396",
    "location": "TC VICTORIA ISLAND",
    "department": "TC VICTORIA ISLAND",
    "driver_name": "ADEBAYO KEHINDE OMOWUMI",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1380",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR3RA961001",
    "engine_no": "PM0AD14744",
    "location": "DD - KATAMPE",
    "department": "DD - KATAMPE",
    "driver_name": "AITEBI NASAMU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS662",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JEX00002620",
    "engine_no": "2ZRU-813634",
    "location": "AD/TAX AUDIT KANO",
    "department": "DMD (POOL)",
    "driver_name": "YAKUBU U. JAAFARU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1383",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASEXRD922730",
    "engine_no": "P3C1526971",
    "location": "AD/INTERNAL AFFAIRS",
    "department": "IAD",
    "driver_name": "AJIROBA TEMITOPE J",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS761/110FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903027118",
    "engine_no": "2ZRU420554",
    "location": "DD-TECHNICAL NON OIL",
    "department": "LTD NON OIL",
    "driver_name": "AJOKU CHINONSO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS640",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003023703",
    "engine_no": "2ZRU334539",
    "location": "D-GBO SOUTH",
    "department": "GBO SOUTH",
    "driver_name": "AKAJE MUSTAPHA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1331",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE9RD922718",
    "engine_no": "P3C1527389",
    "location": "OEC-FIRS POOL",
    "department": "POOL",
    "driver_name": "OEC-FIRS POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1408",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT353923",
    "engine_no": "4A92*S3LH978",
    "location": "AD/SA-ECFIRS MEDIA",
    "department": "SA- MEDIA",
    "driver_name": "AKINYINKA AKINWALE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS212",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903009850",
    "engine_no": "2ZRU92488",
    "location": "AD - LITIGATION AND PROSECUTION",
    "department": "LITIGATION AND PROSECUTION",
    "driver_name": "AKPATA EKA DIDARA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1180",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z9NX404777",
    "engine_no": "LB37622Z9NX404777",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS415N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE7F5248071",
    "engine_no": "3ZRFE1987ML",
    "location": "LIASON OFFICER NATIONAL ASSEMBLY, HQ-ABUJA",
    "department": "LIASON OFFICER NATIONAL ASSEMBLY, HQ-ABUJA",
    "driver_name": "AL-AMIN MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS546N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ868925",
    "engine_no": "HJ868925",
    "location": "AD-HCMD",
    "department": "AD-HCMD",
    "driver_name": "ALIYU MUKHTAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1138",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08MT454713",
    "engine_no": "4A92SISX531",
    "location": "AD-SPECIAL CRIME DEPT",
    "department": "ABUJA",
    "driver_name": "AMINU R.ALIYU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS474N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ661260",
    "engine_no": "HJ661260",
    "location": "FIRS SPORTS CLUB",
    "department": "FIRS SPORTS CLUB",
    "driver_name": "AMINU SHEHU USMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS407N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE2F5248124",
    "engine_no": "3ZRX545044",
    "location": "DD-TAX AUDIT HQ",
    "department": "TAX AUDIT",
    "driver_name": "AMMED ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS416N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE3F5246866",
    "engine_no": "3ZRX538490",
    "location": "D-HCMD (POOL)",
    "department": "HCMD",
    "driver_name": "ANGEL FADAHUNSI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1061",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3016370",
    "engine_no": "JTNBZ4HK2L3016370",
    "location": "D-HCMD",
    "department": "D-HCMD",
    "driver_name": "ANGEL FADAHUNSI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS717",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VFDDNFPRDJ833752",
    "engine_no": "VFDDNFPRDJ833752",
    "location": "SERVICOM",
    "department": "SERVICOM",
    "driver_name": "IFEOMA ACHU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1290",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05PT401181",
    "engine_no": "492*53L5087",
    "location": "HEAD/INTELLIGENCE ABUJA",
    "department": "H/inteligence",
    "driver_name": "OWOLABI EZEKIEL A.",
    "sco": "HQ"
  },
  {
    "license_plate": "302FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803034481",
    "engine_no": "2ZRU658610",
    "location": "TAT ABUJA POOL",
    "department": "TAT ABUJA POOL",
    "driver_name": "ANITA ERINE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1168",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB24HK9N3117142",
    "engine_no": "JTNB24HK9N3117142",
    "location": "TAT ABUJA",
    "department": "TAT ABUJA",
    "driver_name": "ANITA ERINE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS380N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "6TIBF9FK2GX638675",
    "engine_no": "2ARU318320",
    "location": "INVESTIGATION DEPT",
    "department": "INVESTIGATION DEPT",
    "driver_name": "ANULI UMUIKE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS377N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5181G4027395",
    "engine_no": "2TR9054170",
    "location": "ASCSN UNION",
    "department": "UNION",
    "driver_name": "ASCSN UNION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS821",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833862",
    "engine_no": "VF3DDNFPRDJ833862",
    "location": "SS&FMD SOP UNIT",
    "department": "SS&FMD SOP UNIT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "295FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903034487",
    "engine_no": "2ZRU658990",
    "location": "AD-TID",
    "department": "TID",
    "driver_name": "AUDU SANI LAWAL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1351",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XRT352000",
    "engine_no": "S3LJ010",
    "location": "AD,HCMD",
    "department": "AD,HCMD",
    "driver_name": "AUGUSTINA ARIORI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS439N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ608392",
    "engine_no": "HJ608392",
    "location": "DD-ICT-DEPARTMENT",
    "department": "INFORMATION & COMMUNICATION TECHNOLOGY",
    "driver_name": "AWOGUN AYORINDE S.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS910",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ873992",
    "engine_no": "VF3DDNFPRDJ873992",
    "location": "AD/RISK MGT DEPT",
    "department": "HCMD",
    "driver_name": "BENJAMIN AGEV",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS817",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808736",
    "engine_no": "VF3DDNFPRDJ808736",
    "location": "WATAF POOL",
    "department": "WATAF POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1268",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722D7PU009272",
    "engine_no": "3G15TDN2WA4403657",
    "location": "DD-CLD",
    "department": "DD-CLD",
    "driver_name": "BABATUNDE OLADAPO",
    "sco": "HQ"
  },
  {
    "license_plate": "RB845FG/FIRS69",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E903189278",
    "engine_no": "2688536",
    "location": "FCT SSFMD REP KATAMPE",
    "department": "FCT SSFMD REP",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS795",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ798600",
    "engine_no": "VF3DDNFPRDJ798600",
    "location": "DD-FOMD",
    "department": "FOMD",
    "driver_name": "BASHIR MUHAMMAD HAMIS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS728",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE800003622",
    "engine_no": "2ZRU862951",
    "location": "FIRS CO-OPREATIVE PRESIDENT",
    "department": "FIRS CO-OPREATIVE PRESID",
    "driver_name": "ADUKA BORR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS951",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ601282",
    "engine_no": "VF3DDNFPRGJ601282",
    "location": "AD- ISMS SECRETARIAT",
    "department": "ISMS SECRETARIAT",
    "driver_name": "HABU ISA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1265",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "NMTBB9BE50R118461",
    "engine_no": "1ZR-W973739",
    "location": "(TAX PRO MAX)",
    "department": "TAX PRO MAX UNIT",
    "driver_name": "BILYAMINU (TAX PRO MAX)",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS571N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4T1B11HKXKU282589",
    "engine_no": "A25AA316881",
    "location": "BOARD MEMBER CBN",
    "department": "BOARD MEMBER CBN",
    "driver_name": "BOARD MEMBER CBN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS338",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SBIBL76L80E011572",
    "engine_no": "3ZRA371442",
    "location": "BOARD SECETARIAT",
    "department": "BOARD SECRETERIAT",
    "driver_name": "BOARD SECETARIAT",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1057",
    "brand": "Innoson",
    "model": "Capa",
    "vin_sn": "LGG7E3D20LZ416906",
    "engine_no": "HG6354T-5YJ9860",
    "location": "BOARD SECRETERIAT",
    "department": "BOARD SECRETERIAT",
    "driver_name": "BOARD SECRETERIAT",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1205",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z8NX404785",
    "engine_no": "3G15TD-5606012",
    "location": "DD -M-SECRTARIAT",
    "department": "MANGEMENT SECRETARIATE",
    "driver_name": "BRAIDE LOLO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1135",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06MT454693",
    "engine_no": "4A92SITV007",
    "location": "AD- CAREER & SKILLS DEPT",
    "department": "ABUJA",
    "driver_name": "BRIGHT IDEHENRE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS161",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003009736",
    "engine_no": "2ZRU090574",
    "location": "CMAD SSFMD",
    "department": "SSFMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS532",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E303015632",
    "engine_no": "2ZRU141049",
    "location": "IAD POOL",
    "department": "IAD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS126",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E503009845",
    "engine_no": "ZZRU092563",
    "location": "SSM TOTAL CARD AND FUELING UNIT",
    "department": "SS&FMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS49",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "50317933",
    "engine_no": "2601387",
    "location": "SSFMD ARM DIVISION",
    "department": "SSFMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1377",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR0RA960775",
    "engine_no": "PM0AD107707",
    "location": "MGT PROTOCOL",
    "department": "INTERVENTION WITH GD",
    "driver_name": "NANA IBRAHIM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS847",
    "brand": "Kia",
    "model": "Mohave",
    "vin_sn": "KNAKN811DF5133622",
    "engine_no": "G6DAES235290",
    "location": "DD-HEAD MSTO NORTHERN DIV",
    "department": "MSTO NORTHERN DIV",
    "driver_name": "DAHIRU SANI MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1303",
    "brand": "Mercedes-Benz",
    "model": "Ml350",
    "vin_sn": "4JGBB86E69A528584",
    "engine_no": "4JGBB86E69A528584",
    "location": "MANAGEMENT POOL",
    "department": "MANAGEMENT POOL",
    "driver_name": "MANAGEMENT POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS756",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ829500",
    "engine_no": "VF3DDNFPRDJ829500",
    "location": "H-EDRMS PROJECT",
    "department": "EDRMS PROJECT",
    "driver_name": "DANIEL SHEBAYAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1376",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR7RA960790",
    "engine_no": "PM0AD107780",
    "location": "DD/ECFIRS/SA-MEDIA",
    "department": "",
    "driver_name": "DARE ADEKAMBI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS51",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTD BRE 40-3186935",
    "engine_no": "2671274",
    "location": "SSFMD POOL",
    "department": "SSFMD HSE DIVISION POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1319",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8506510044",
    "engine_no": "JTGAKAB8506510044",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1322",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU3FJ6PK238153",
    "engine_no": "JTEBU3FJ6PK238153",
    "location": "D,PRS",
    "department": "D, PRS",
    "driver_name": "HALIMA SHEHU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1225",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBB0BE3M0036379",
    "engine_no": "RKLBB0BE3M0036379",
    "location": "AD-BUSINESS ANALYSIS",
    "department": "BUSINESS ANALYSIS - OEC",
    "driver_name": "DOLOR EMUKOWHATE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS933",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE600008351",
    "engine_no": "2ZRV142643",
    "location": "CHANGE MGT DEPT",
    "department": "CHANGE MGT DEPT",
    "driver_name": "DR AHMED IDRIS UMAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1147",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9L3014747",
    "engine_no": "JTNBZ4HK9L3014747",
    "location": "D/OFFICE OF CD SPECIAL DUTY",
    "department": "D/OFFICE OF CD SPECIAL DUTY",
    "driver_name": "DR AHMED IDRIS UMAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1214",
    "brand": "Geely",
    "model": "Jeep",
    "vin_sn": "L6T7722Z8NU006227",
    "engine_no": "3GI5TD-2502639",
    "location": "DD,LITIGATION & PROSECUTION",
    "department": "LITIGATION & PROSEUTION",
    "driver_name": "MOSES IDEHO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS01Z",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMABBBJ4N4015259",
    "engine_no": "JTMABBBJ4N4015259",
    "location": "ECFIRS",
    "department": "OECFIRS",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS02Z",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMAUBBJXP4030569",
    "engine_no": "JTMAUBBJXP4030569",
    "location": "PA/ECFIRS",
    "department": "OECFIRS",
    "driver_name": "ALEX JUWON",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS04Z",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU97J7N5094692",
    "engine_no": "1GR-C553203",
    "location": "ECFIRS/ESCORT",
    "department": "OECFIRS",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS469N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ663782",
    "engine_no": "HJ663782",
    "location": "OECFIRS POOL",
    "department": "OECFIRS",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS428N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL032805",
    "engine_no": "GL032805",
    "location": "DD-FIRS DESK M-FINANCE (RTD & RFP)",
    "department": "FIRS DESK MIN. FINANCE",
    "driver_name": "EGWUATU OBIORA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1124",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3014749",
    "engine_no": "JTNBZ4HK2L3014749",
    "location": "D-OCD-SPECIAL DUTY",
    "department": "D-OCD-SPECIAL DUTY",
    "driver_name": "EJIGA LAWRENCE MICHEAL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS811",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808731",
    "engine_no": "VF3DDNFPRDJ808731",
    "location": "REVENUE ACCOUNTING",
    "department": "REVENUE ACCOUNTING",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1175",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z0MW036092",
    "engine_no": "L6T7824Z0MW036092",
    "location": "AD-OCD-CSG",
    "department": "CSG",
    "driver_name": "ELELE FELIX CHIBUZO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS925",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ883019",
    "engine_no": "VF3DDNFPRDJ883019",
    "location": "STATE MONITOR TARABA GBO",
    "department": "GBO TARABA",
    "driver_name": "PYIKISON NYIKUN",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS1372",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE8RD922726",
    "engine_no": "P3C1527361",
    "location": "AD,OCD/CSG",
    "department": "",
    "driver_name": "ENEJOR ODOJA AEI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1282",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR5RA960366",
    "engine_no": "PM0AD025922",
    "location": "RAD",
    "department": "RAD",
    "driver_name": "EUNICE MOMODU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS480N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROHX8CD0H0591065",
    "engine_no": "2TRA181433",
    "location": "SSFMD POOL",
    "department": "SSFMD POOL",
    "driver_name": "SSFMD POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1187",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z5NX404789",
    "engine_no": "LB37622Z5NX404789",
    "location": "D-HCMD",
    "department": "HCMD",
    "driver_name": "EZE EMMANUEL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS147",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03009873",
    "engine_no": "2ZRU091231",
    "location": "AD-IAD",
    "department": "IAD",
    "driver_name": "EZERIBE CHIMENKA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS656",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE300002622",
    "engine_no": "2ZRU-810245",
    "location": "AD-FMD",
    "department": "FMD",
    "driver_name": "FUNSHO ABIMBOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1373",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE4RD910847",
    "engine_no": "P3C1500170",
    "location": "AD,F&A",
    "department": "F & A",
    "driver_name": "FATI LAMI MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "281FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103034306",
    "engine_no": "2ZRU644548",
    "location": "HEAD-OVERHEAD F&A",
    "department": "F&A",
    "driver_name": "FATIMA INKO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1413",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVGBC74K9G248864",
    "engine_no": "LG30902A25G",
    "location": "D-TPAD",
    "department": "D-TPAD",
    "driver_name": "FEMI EDGAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS854",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SBIBL76L50E040673",
    "engine_no": "2ZRB540064",
    "location": "TPAD POOL",
    "department": "TPAD POOL",
    "driver_name": "FEMI EDGAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS783/180FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603028131",
    "engine_no": "2ZRU446680",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "ESCORT COMMANDER",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS605N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL024614",
    "engine_no": "VF38D5GYAHL024614",
    "location": "DD-TID",
    "department": "DD-TID",
    "driver_name": "FEMI OLARINDE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS471N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ661254",
    "engine_no": "HJ661254",
    "location": "SM/PMO",
    "department": "HCMD",
    "driver_name": "FESTUS OJEKHEKPAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS524",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E303016960",
    "engine_no": "2ZRU168926",
    "location": "CS&DD",
    "department": "CS&DD",
    "driver_name": "ABU O MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1330",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE0RD910862",
    "engine_no": "P3C1502566",
    "location": "AD/STA/ABUJA",
    "department": "AD/STA/ABUJA",
    "driver_name": "GARBA A.MAKAMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1333",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE1RD922714",
    "engine_no": "P3C1527119",
    "location": "AD/PUBLIC ACCOUNT UNIT",
    "department": "AD/PAC",
    "driver_name": "HALIRU HARUNA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS421N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL031728",
    "engine_no": "GL031728",
    "location": "CD - C&EG",
    "department": "COMPLIANCE & ENF. GROUP",
    "driver_name": "GBONJUBOLA MATHEW O.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS16",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBE40K503167046",
    "engine_no": "JTNBE40K503167046",
    "location": "DD-FA",
    "department": "F&A",
    "driver_name": "MR ADEDAYO OLABODE ADEFALA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1182",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z7NX404762",
    "engine_no": "LB37622Z7NX404762",
    "location": "DD-SS&FMD",
    "department": "SS&FMD",
    "driver_name": "GEORGE NNAMANI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS690",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE300001230",
    "engine_no": "2ZRU790561",
    "location": "DD-SS&FMD",
    "department": "HEAD FLEET",
    "driver_name": "GEORGE ONYELOHUNU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS973",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ606737",
    "engine_no": "VF3DDNFPRGJ606737",
    "location": "OCD-ETG",
    "department": "ETG",
    "driver_name": "ETG POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS721",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRD840974",
    "engine_no": "VF3DDNFPRDJ840974",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1264",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08NT457287",
    "engine_no": "4A92X53KLO95",
    "location": "OEC-NRS",
    "department": "OEC-NRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS462N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ605220",
    "engine_no": "HJ605220",
    "location": "AD-HCMD",
    "department": "HCMD",
    "driver_name": "JOSEPH KWATARI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1093",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9L3016336",
    "engine_no": "JTNBZ4HK9L3016336",
    "location": "D-LEGAL",
    "department": "D-LEGAL",
    "driver_name": "HAJARA ONIYANGI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1157",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z1MWO36098",
    "engine_no": "L6T7824Z1MWO36098",
    "location": "OED,FINANCE & CORPORATE SERVICE",
    "department": "POOL",
    "driver_name": "OOPL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1230",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08050061",
    "engine_no": "JTFRX12PX08050061",
    "location": "HCMD-WELFARE",
    "department": "HCMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1243",
    "brand": "Innoson",
    "model": "Bus",
    "vin_sn": "LL3AAAAC1JA000087",
    "engine_no": "4RB-275921A",
    "location": "HCMD-WELFARE",
    "department": "HCMD",
    "driver_name": "HCMD-WELFARE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS360",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2ZE1427013200",
    "engine_no": "IZZA 213390",
    "location": "HQ DTG TECHNICAL POOL",
    "department": "TECHNICAL POOL",
    "driver_name": "HQ DTG TECHNICAL POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS809",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ813714",
    "engine_no": "VF3DDNFPRDJ813714",
    "location": "LEGAL ABUJA/ OFF OF DIRECTOR/ADMIN",
    "department": "LEGAL",
    "driver_name": "IBRAHIM ABDULLAH",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS793",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ775762",
    "engine_no": "VF3DDNFPRDJ775762",
    "location": "DD-ICT",
    "department": "ICT",
    "driver_name": "IBRAHIM ABUBAKAR BALA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1339",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASEXRD922713",
    "engine_no": "P3C1527120",
    "location": "AD/PROCUREMENT DEPT",
    "department": "PROCUREMENT",
    "driver_name": "IBRAHIM SULEIMAN SANI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1055",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK0L3016323",
    "engine_no": "JTNBZ4HK0L3016323",
    "location": "D-IAD",
    "department": "D-IAD",
    "driver_name": "IDRIS AHMED NDANUSA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS800",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ796790",
    "engine_no": "VF3DDNFPRDJ796790",
    "location": "ILLICIT FUND POOL",
    "department": "ILLICIT FUND POOL",
    "driver_name": "IDRIS MUHAMMAD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS424/FIRS05",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SBIBL76L90E013007",
    "engine_no": "2RTA38046",
    "location": "TC GARKI MSTO",
    "department": "GARKI MSTO",
    "driver_name": "NUHU ASTIRA TALATU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1420",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT353928",
    "engine_no": "4A92*S3LH980",
    "location": "AD, MGT SERVICES DEPT",
    "department": "",
    "driver_name": "IJEOMA OKORO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1362",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08RT352013",
    "engine_no": "S3LJ014",
    "location": "AD/ F& A",
    "department": "",
    "driver_name": "IKANI YUNUSA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1139",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03MT454702",
    "engine_no": "4A92SISX559",
    "location": "AD-PROCUREMENT DEPT",
    "department": "PROCUREMENT",
    "driver_name": "ILORI OMOLOLU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS263",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003009817",
    "engine_no": "2ZRU093303",
    "location": "AD-IAD",
    "department": "IAD",
    "driver_name": "INUWA MOHAMMD SANUSI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1311",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR9RA960791",
    "engine_no": "LS5A3AKR9RA960791",
    "location": "DD/FMD",
    "department": "DD/FMD",
    "driver_name": "MICHAEL KAYODE ORILOYE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS460N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ609995",
    "engine_no": "HJ609995",
    "location": "H- (BCMIS) RAD",
    "department": "RAD",
    "driver_name": "IYEN OSHANUWA EUGENE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS754/298FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803027045",
    "engine_no": "2ZRU419581",
    "location": "AD-RAD",
    "department": "RAD",
    "driver_name": "JEGEDE G.M.",
    "sco": "HQ"
  },
  {
    "license_plate": "RB682FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "97090",
    "engine_no": "1140880",
    "location": "HEAD- VEHICLE INSPECTION UNIT",
    "department": "SSFMD FLEET INSPECTION",
    "driver_name": "FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "RBC451DE/ FIRS422",
    "brand": "Kia",
    "model": "Cerato",
    "vin_sn": "KNAFX417BF5319596",
    "engine_no": "G4NAEH518072",
    "location": "AD - IAD",
    "department": "IAD",
    "driver_name": "YUSUF IDRIS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS01B",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMHY7AJ0F4032976",
    "engine_no": "3UR3235178",
    "location": "MGT PROTOCOL",
    "department": "OECFIRS",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1104",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ0NY502209",
    "engine_no": "VR3F3EGZONY502209",
    "location": "Ag,D/GBTD",
    "department": "GBTD",
    "driver_name": "LIMAN HALIDU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1366",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT352021",
    "engine_no": "LGJF1FE07RT352021",
    "location": "AD/OCD-NRS",
    "department": "AD/OCD-NRS",
    "driver_name": "JOAN OWOBORADE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1110",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ9NY502208",
    "engine_no": "VR3F3EGZ9NY502208",
    "location": "MGT PROTOCOL",
    "department": "INTERVENTION WITH D-PMO",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS992",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ691090",
    "engine_no": "VF3DDNFPRDJ691090",
    "location": "RETRIEVED FROM JOHN IKATA",
    "department": "TAX EXPENDITURE",
    "driver_name": "YET TO BE ALLOCATED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1212",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z6NU006243",
    "engine_no": "3G15TD-2502687",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "PETER ALFRED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1183",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z3NX404752",
    "engine_no": "LB37622Z3NX404752",
    "location": "OED-PEOPLE STAKEH COMMUNICATION",
    "department": "OED-PEOPLE STAKEH COMMUNICATION",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS782/179FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403028127",
    "engine_no": "2ZRU446701",
    "location": "AD-F&A",
    "department": "F&A",
    "driver_name": "OLUNIYO FUNSHO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1109",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ5NY500777",
    "engine_no": "VR3F3EGZ5NY500777",
    "location": "DD-PAD ABUJA",
    "department": "TPAD ABUJA",
    "driver_name": "KEHINDE V. KAJESOMO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1281",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR3RA960284",
    "engine_no": "PM0AD017930",
    "location": "OCD/ETG",
    "department": "OCD/ETG",
    "driver_name": "KHADIJA UDU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS664",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE300002409",
    "engine_no": "2ZRU-808187",
    "location": "D-TAD ECNRS POOL",
    "department": "D-TAD TO ECNIRS- POOL",
    "driver_name": "KOLA OKUNOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1149",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3016243",
    "engine_no": "JTNBZ4HK2L3016243",
    "location": "D-TAD ECFIRS",
    "department": "D-TAD TO ECFIRS- ISDA",
    "driver_name": "KOLA OKUNOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS422N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL030400",
    "engine_no": "GL030400",
    "location": "SC-SCO (POOL)",
    "department": "CAREER AND SKILLS",
    "driver_name": "KUBILI UGBUDIA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS704/ 31FIRS",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4TIBF3EK6AU550960",
    "engine_no": "2ARD111199",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS589N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBF4HK2J3002283",
    "engine_no": "JTNBF4HK2J3002283",
    "location": "BOARD MEMBER (MINISTRY OF JUSTICE)",
    "department": "BOARD MEMBER (MINISTRY OF JUSTICE)",
    "driver_name": "LADIDI BARAATU MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1371",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE9RD922721",
    "engine_no": "P3C1527391",
    "location": "AD/CHANG MGT DEPT",
    "department": "",
    "driver_name": "LAMIDI RASHEED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1137",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04MT454692",
    "engine_no": "4A92SISX562",
    "location": "GARKI AUDIT",
    "department": "GARKI AUDIT",
    "driver_name": "LAWAL IBRAHIM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1294",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XPT397614",
    "engine_no": "4A92*S3LS067",
    "location": "AD/OCD-ESG",
    "department": "OCD-ESG",
    "driver_name": "LAWAL KAZEEM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS886",
    "brand": "Toyota",
    "model": "Avalon",
    "vin_sn": "4TIBKIEB7EU119582",
    "engine_no": "2GR7485272",
    "location": "D-OCD SPECIAL DUTIES",
    "department": "POOL",
    "driver_name": "LAWRENCE EJIGA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1074",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK4HR879160",
    "engine_no": "LNBMDBAK4HR879160",
    "location": "AD-LTA",
    "department": "LTA",
    "driver_name": "LEBI VICTORIA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS438N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ603647",
    "engine_no": "HJ603647",
    "location": "HEAD - MAINTENANCE UNIT",
    "department": "FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1171",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB29HK3N3115500",
    "engine_no": "JTNB29HK3N3115500",
    "location": "D-TPSD",
    "department": "TPSD",
    "driver_name": "LOVETTE ONANUGA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1172",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z7NU006106",
    "engine_no": "L6T7722Z7NU006106",
    "location": "D,SMALL TAX PAYER DEPT",
    "department": "CSG",
    "driver_name": "OYENIYI YIDIAT FADEKE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1318",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP5P6021356",
    "engine_no": "JTGHN9CP5P6021356",
    "location": "EC POOL",
    "department": "EC POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1328",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK803207102",
    "engine_no": "JTNB19HK803207102",
    "location": "ED-F&C",
    "department": "ED-F&C",
    "driver_name": "M.L.ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS412",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4TIBF3EK4AU551900",
    "engine_no": "2ARD113737",
    "location": "ENFORCEMENT (SIED)",
    "department": "SSFMD",
    "driver_name": "OLAIDE YEMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS555",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4TIBF3EK9AU095618",
    "engine_no": "2ARD157234",
    "location": "UNION CHAIRMAN",
    "department": "UNION CHAIRMAN",
    "driver_name": "BARR. SAMSON OKERE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS843",
    "brand": "Kia",
    "model": "Mohave",
    "vin_sn": "KNAKN811DF5133615",
    "engine_no": "G6DAES235279",
    "location": "MANAGEMENT INTERVENTION POOL",
    "department": "MANAGEMENT INTERVENTION",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS634N",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU3FJXLK180882",
    "engine_no": "JTEBU3FJXLK180882",
    "location": "MANAGEMENT EXCUTIVE POOL",
    "department": "MANAGEMENT EXECUTIVE POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS851",
    "brand": "Kia",
    "model": "Mohave",
    "vin_sn": "KNAKN811DF5133612",
    "engine_no": "KNAKN811DF5133612",
    "location": "TAX EXPENDITURE - DD",
    "department": "TAX EXP. DEPT",
    "driver_name": "IKATA OYEKUODI JOHN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1059",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS69KA745553",
    "engine_no": "LKLSBAS69KA745553",
    "location": "MGT PROTOCOL",
    "department": "MANAGEMENT FLEET POOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1314",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR5RA960755",
    "engine_no": "LS5A3AKR5RA960755",
    "location": "DD/HCMD",
    "department": "HCMD",
    "driver_name": "ISA KOLLERE",
    "sco": "HQ"
  },
  {
    "license_plate": "301FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203034475",
    "engine_no": "2ZRU651443",
    "location": "HEAD-TREASURY OPRATIONS F&A",
    "department": "F&A",
    "driver_name": "MANI RABIU M.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS688",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE000001315",
    "engine_no": "2ZRU-795047",
    "location": "DD-SERVICOM",
    "department": "SERVICOM",
    "driver_name": "MANNIR HARUNA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS803",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ802222",
    "engine_no": "VF3DDNFPRDJ802222",
    "location": "ACTU",
    "department": "POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1405",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT353933",
    "engine_no": "4A92*S3LH966",
    "location": "AD/INVEST & ENFORCEMENT",
    "department": "IED",
    "driver_name": "MARTINS MUSTAPHA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS625",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603022250",
    "engine_no": "2ZRU294026",
    "location": "AD-F&A",
    "department": "FINANCE & ACCOUNTS",
    "driver_name": "MARYAM ABUBAKAR GIDADO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1344",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT352018",
    "engine_no": "S3LJ023",
    "location": "ECFIRS/SECRTARY",
    "department": "ECFIRS/SECRTARY",
    "driver_name": "MARYAM L. ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1274",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB3762276PX410538",
    "engine_no": "N6BA5614062",
    "location": "TPAD",
    "department": "TPAD",
    "driver_name": "MATHEW OSANEKWEU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS722",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRD840972",
    "engine_no": "VF3DDNFPRDJ840972",
    "location": "AD-GBTO ABUJA",
    "department": "GBTO",
    "driver_name": "MATHIAS KANWAI",
    "sco": "HQ"
  },
  {
    "license_plate": "RBC446DE (FIRS439)",
    "brand": "Kia",
    "model": "Cerato",
    "vin_sn": "KNAFX417BF6319622",
    "engine_no": "G4NAEH518063",
    "location": "OCD-SSG",
    "department": "SSG",
    "driver_name": "MAXWEL ELSA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS441N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ602068",
    "engine_no": "HJ602068",
    "location": "F&A (HEAD CAPITAL UNIT)",
    "department": "F&A (HEAD CAPITAL UNIT)",
    "driver_name": "MICHEAL RENA",
    "sco": "HQ"
  },
  {
    "license_plate": "RBC450DE (FIRS415)",
    "brand": "Kia",
    "model": "Cerato",
    "vin_sn": "KNAFX417BF5319713",
    "engine_no": "G4NAEH518044",
    "location": "SMG TAX POOL",
    "department": "SMG",
    "driver_name": "MIKE ADOGA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS473N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ663788",
    "engine_no": "HJ663788",
    "location": "OFFICE OF THE DIRECTOR - SSFMD",
    "department": "SSFMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS827 (264FIRS)",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833868",
    "engine_no": "VF3DDNFPRDJ833868",
    "location": "OFFICE OF THE DIRECTOR- G2G OPERATIONS & SERVICES",
    "department": "G2G OPERATIONS & SERVICES",
    "driver_name": "MODAKAI OYIBO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1407",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07RT353931",
    "engine_no": "4A92S3LH974",
    "location": "EC-FIRS TA/TEC-ADVISER",
    "department": "EC-FIRS TA/TEC-ADVISER",
    "driver_name": "MOHAMMED A. KAWUYO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1179",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z9NX402155",
    "engine_no": "LB37622Z9NX402155",
    "location": "D-FCT OFFICE KATAMPE",
    "department": "D-FCT OFFICE KATAMPE",
    "driver_name": "ADAMA KURA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1280",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR0RA960372",
    "engine_no": "PM0AD031003",
    "location": "AG.D-SPECIAL TAX DEPT",
    "department": "SPECIAL TAX DEPT",
    "driver_name": "MOHAMMED DALHATU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1382",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE7RD922720",
    "engine_no": "P31527038",
    "location": "AD/SPECIAL CRIME DEPT",
    "department": "AD/SPECIAL CRIME DEPT",
    "driver_name": "MOHAMMED MURTALA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1295",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE01PT397615",
    "engine_no": "4A92S3LH952",
    "location": "AD-MTA ABUJA",
    "department": "MTA ABUJA",
    "driver_name": "MOHAMMED SHEHI M.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS313",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303018012",
    "engine_no": "2ZRU196489",
    "location": "AD-LEGAL ADVISORY & MGT",
    "department": "AD-LEGAL ADVISORY & MGT",
    "driver_name": "HAUWA GADZAMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1329",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE6RD910848",
    "engine_no": "P3C1500181",
    "location": "AD/LTA/ABUJA",
    "department": "AD/LTA/ABUJA",
    "driver_name": "MOMOH OSHONAME ISAAC",
    "sco": "HQ"
  },
  {
    "license_plate": "RB707FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "3115112",
    "engine_no": "1998752",
    "location": "GENERAL FLEET POOL",
    "department": "SSFMD SOP OPERATIONS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS461N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ609999",
    "engine_no": "HJ609999",
    "location": "MSME CLINIC PROJECT",
    "department": "MSME CLINIC PROJECT",
    "driver_name": "CLARA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1222",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK7L3014777",
    "engine_no": "JTNBZ4HK7L3014777",
    "location": "D-REGIONAL ADMIN BORNO",
    "department": "REGIONAL ADMIN BORNO",
    "driver_name": "MUAZU GARBA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS567N",
    "brand": "Peugeot",
    "model": "3008",
    "vin_sn": "VF3M45GYVJS239685",
    "engine_no": "JS239685",
    "location": "OCD- SPECIAL DUTIES",
    "department": "OCD- SPECIAL DUTIES",
    "driver_name": "WILSON YERIMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS602N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL013059",
    "engine_no": "VF38D5GYAHL013059",
    "location": "ED-COMPLIANCE",
    "department": "ED-COMPLIANCE",
    "driver_name": "TAMADI SHETTIMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1208",
    "brand": "Geely",
    "model": "Jeep",
    "vin_sn": "L6T7722ZXNU006228",
    "engine_no": "3G15TD-2502649",
    "location": "CD - SPECIAL DUTIES",
    "department": "CD - SPECIAL DUTIES",
    "driver_name": "TAMADI SHETTIMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS611N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL020809",
    "engine_no": "VF38D5GYAHL020809",
    "location": "Ag. PMO",
    "department": "PMO",
    "driver_name": "MUHAMMAD JAMEEL RINGIM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS627N",
    "brand": "Lexus",
    "model": "Lx570",
    "vin_sn": "JTHHY7AX7K4289824",
    "engine_no": "JTHHY7AX7K4289824",
    "location": "EC-FIRS",
    "department": "OECFIRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS01A",
    "brand": "Lexus",
    "model": "Lx570",
    "vin_sn": "JTJHY00WXM4354913",
    "engine_no": "JTJHY00WXM4354913",
    "location": "EC-FIRS",
    "department": "OEC-FIRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS145",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P5060948",
    "engine_no": "338136390",
    "location": "ABAKILIKI MSTO POOL",
    "department": "SCO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS615",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P0A8019060",
    "engine_no": "2TR8236621",
    "location": "GUSAU MSTO",
    "department": "SKZ POOL",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "RBC447DE / FIRS653",
    "brand": "Kia",
    "model": "Cerato",
    "vin_sn": "KNAFX417BF5319586",
    "engine_no": "G4NAEH518070",
    "location": "AD/ MTA WARRI",
    "department": "MTA WARRI",
    "driver_name": "GREEN KALIEFA",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS550N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL024953",
    "engine_no": "HL024953",
    "location": "D-RAD",
    "department": "RAD",
    "driver_name": "MUNIR MOHAMMED ABDULKADIR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1200",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z5MW036122",
    "engine_no": "L6T7824Z5MW036122",
    "location": "AD-RAD",
    "department": "REVENUE ACCOUNTING",
    "driver_name": "MUSA I. MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1279",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR4RA960357",
    "engine_no": "PM0AD025942",
    "location": "HEAD-SPECIAL TAX AUDIT",
    "department": "SPECIAL TAX AUDIT",
    "driver_name": "NASIRU ABDULRAHEM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS627",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003023958",
    "engine_no": "2ZRU344554",
    "location": "AD-RAD",
    "department": "RAD",
    "driver_name": "NASIRU NDAYAWO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS774/128FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303027860",
    "engine_no": "2ZRU438860",
    "location": "OECFIRS POOL",
    "department": "OEC FIRS",
    "driver_name": "ABUBAKAR ADAMU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS32",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "303181290",
    "engine_no": "2630037",
    "location": "ARM OPERATIONAL VEHICLE",
    "department": "ARM OPERATIONAL VEHICLE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS730/141FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103026528",
    "engine_no": "2RU401799",
    "location": "AD-TAX INCENTIVE",
    "department": "TAX INCENTIVE",
    "driver_name": "NKEMAKOSI KINGSLEY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1384",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE2RD910863",
    "engine_no": "P3C1502539",
    "location": "AD/TID",
    "department": "TID",
    "driver_name": "NKIRU ONYIA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS730",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE100004224",
    "engine_no": "2ZRU886894",
    "location": "AD-RISK MANAGEMENT DPT",
    "department": "AD-RISK MANAGEMENT DPT",
    "driver_name": "EMMANUEL IGOCHE ODUMU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1056",
    "brand": "Innoson",
    "model": "Ivm G6T",
    "vin_sn": "LMXA14AF6LZ411568",
    "engine_no": "4A91T-S2XB160",
    "location": "D-OED F&C",
    "department": "OED F&C",
    "driver_name": "NNEKA IFEKUNA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS996",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ646334",
    "engine_no": "VF3DDNFPRDJ646334",
    "location": "RAD",
    "department": "RAD",
    "driver_name": "NOEL S. BERJE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS649",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603025584",
    "engine_no": "2ZRU388924",
    "location": "TAT",
    "department": "KADUNA",
    "driver_name": "NORTH WEST",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1403",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE01RT353925",
    "engine_no": "4A92*S3LH982",
    "location": "AD/INVEST & ENFORCEMENT",
    "department": "HAMZA G. IBRAHIM",
    "driver_name": "NORTHERN ZONE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1412",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVGBC74K8PG241114",
    "engine_no": "LF56478A25G",
    "location": "REGIONAL ADMISNISTRATOR LME",
    "department": "REGIONAL ADMISNISTRATION LME",
    "driver_name": "SALIU OLANREWAJU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1414",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVG3C74K8PG664937",
    "engine_no": "LG53771A25G",
    "location": "D,F&A",
    "department": "F&A",
    "driver_name": "OLAWOYE MUSA ADESINA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS972",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ608592",
    "engine_no": "VF3DDNFPRGJ608592",
    "location": "H/ OVERHEAD UNIT",
    "department": "F&A",
    "driver_name": "NURADEEN ABDULSALAM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS641",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E03023782",
    "engine_no": "2ZRU342010",
    "location": "OCD- CSG",
    "department": "CSG",
    "driver_name": "OCD-CSG POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "339FIRS",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SB1BL76L50E036722",
    "engine_no": "3RZB153398",
    "location": "OCD-CSG",
    "department": "CSG",
    "driver_name": "OCD-CSG POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1144",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK6L3015547",
    "engine_no": "JTNBZ4HK6L3015547",
    "location": "D-OCD-PSG",
    "department": "PSG",
    "driver_name": "ODUBANJO BABAJIDE B",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1194",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z2MW036112",
    "engine_no": "L6T7824Z2MW036112",
    "location": "D-OCD-PSG",
    "department": "PSG",
    "driver_name": "ODUBANJO BABAJIDE B",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1099",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU3FJIMK202530",
    "engine_no": "1GR-FE 3956ML",
    "location": "OECFIRS EXCORT",
    "department": "OECFIRS BACK UP",
    "driver_name": "OECFIRS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS03Z",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMAUBBJIN4021501",
    "engine_no": "1GR-C601349",
    "location": "CHIEF OF STAFF/OEC",
    "department": "OECFIRS",
    "driver_name": "TAYO K",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1297",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD8N0097127",
    "engine_no": "IGR-H310653",
    "location": "ECFIRS",
    "department": "ECFIRS/ESCORT",
    "driver_name": "ZAAC",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1087",
    "brand": "Innoson",
    "model": "Granite",
    "vin_sn": "XLTA12H2P2M1000013X",
    "engine_no": "XLTA12H2P2M1000013X",
    "location": "SSFMD",
    "department": "SSFMD",
    "driver_name": "SSFMD POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1090",
    "brand": "Innoson",
    "model": "Granite A",
    "vin_sn": "LJNTGU5Y3LN400523",
    "engine_no": "LJNTGU5Y3LN400523",
    "location": "OECNRS",
    "department": "OECNRS",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1299",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD3N0098265",
    "engine_no": "IGRH332371",
    "location": "CSO TO ECNRS",
    "department": "OECNRS",
    "driver_name": "ABAYOME EGUNDAYO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS810",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808746",
    "engine_no": "VF3DDNFPRDJ808746",
    "location": "ECFIRS REGISTRY- DISPATCH",
    "department": "OECFIRS",
    "driver_name": "OEC-FIRS POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS818",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808717",
    "engine_no": "VF3DDNFPRDJ808717",
    "location": "OEC-FIRS POOL(POLICE)",
    "department": "",
    "driver_name": "CSO 2iC",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS459N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ614777",
    "engine_no": "HJ614777",
    "location": "AD-INTELLIGENCE STRATEGIC &DATA MINING & ANALYSIS",
    "department": "LEGAL",
    "driver_name": "OJUDU OLUYEMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS405N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE2F5246423",
    "engine_no": "3ZRX536146",
    "location": "D-STA (POOL)",
    "department": "STA",
    "driver_name": "OKEOWO SUNDAY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1123",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK5L3015636",
    "engine_no": "JTNBZ4HK5L3015636",
    "location": "D-SPECIAL TAX AUDIT",
    "department": "SPECIAL TAX AUDIT DEPARTMENT",
    "driver_name": "OKEOWO SUNDAY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS928",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ873983",
    "engine_no": "VF3DDNFPRDJ873983",
    "location": "F&A H/NON CURRENT ASSET",
    "department": "F&A POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS429N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL029729",
    "engine_no": "GL029729",
    "location": "RETRIEVED FROM ANTHONY OKONKWO BACK TO FLEET POOL",
    "department": "RETRIEVED TO BACK TO FLEET POOL",
    "driver_name": "YET TO BE ALLOCATED",
    "sco": "HQ"
  },
  {
    "license_plate": "235FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E503030876",
    "engine_no": "2ZRU501548",
    "location": "AD - SSFMD",
    "department": "SS&FMD",
    "driver_name": "NNAMDI OKOROAFOR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1367",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT351985",
    "engine_no": "LGJF1FE09RT351985",
    "location": "AD/ MSTA GARKI",
    "department": "",
    "driver_name": "OKUNADE ADEKUNLE A.",
    "sco": "HQ"
  },
  {
    "license_plate": "341FIRS",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SB1BL76LX0E036537",
    "engine_no": "3RZB148591",
    "location": "DD-ICT",
    "department": "ICT",
    "driver_name": "OKUNOLA TAJUDEEN BOLANLE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1402",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT353921",
    "engine_no": "4A92S3LH998",
    "location": "AD/IAD",
    "department": "IAD",
    "driver_name": "OLABODE OLUBANKOLE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS410N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE4F5246682",
    "engine_no": "2ZRX537160",
    "location": "D-TAD HQ (POOL)",
    "department": "TAD",
    "driver_name": "OLABODE SIMEON",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1250",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK0N3171767",
    "engine_no": "A25A-FKS2487",
    "location": "D-TAD",
    "department": "TAD",
    "driver_name": "OLABODE SIMEON",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1286",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05PT397620*",
    "engine_no": "4A92*53LH962*",
    "location": "TECHNICAL DEPT",
    "department": "TECHNICAL DEPT",
    "driver_name": "OLAGUNJU JOHNSON O.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1411",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVG3C74K3PG744616",
    "engine_no": "LG00185A25G",
    "location": "D-RMD",
    "department": "RMD",
    "driver_name": "AKANNI OLABANKE MONISOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "292FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203034363",
    "engine_no": "2ZRU650679",
    "location": "PDD POOL",
    "department": "PDD",
    "driver_name": "KUNLE OLLEY JOSHUA IBIKUNLE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1052",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3015982",
    "engine_no": "JTNBZ4HK2L3015982",
    "location": "D-ICT",
    "department": "D-ICT",
    "driver_name": "KUNLE OLLEY JOSHUA IBIKUNLE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1167",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB29HKXL3059469",
    "engine_no": "JTNB29HKXL3059469",
    "location": "Ag.D-FMD",
    "department": "FMD",
    "driver_name": "OLUSHOLA ADEWUNMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1381",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3DKR5RA964774",
    "engine_no": "PM0AD107784",
    "location": "DD,ECFIRS SA-LEGAL",
    "department": "SA - LEGAL",
    "driver_name": "OLUWASEGUN ADEDOLAPO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1335",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASEXRD910867",
    "engine_no": "P3C1502614",
    "location": "OECFIRS /POOL",
    "department": "OECFIRS /POOL",
    "driver_name": "ONARINDE ADEOLU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS440N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ608391",
    "engine_no": "HJ608391",
    "location": "PLANNIG & COORDINATION POOL",
    "department": "PLANNIG & COORDINATION POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS14/FIRS558",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903012189",
    "engine_no": "2ZRU197224",
    "location": "ARM-SS&FMD",
    "department": "GENERAL FLEET POOL",
    "driver_name": "ARM-SS&FMD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1375",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE2RD922723",
    "engine_no": "P3C1527377",
    "location": "AD/LARGE TAX AUDIT",
    "department": "LTA",
    "driver_name": "OYELADE O.A",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS444N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ602067",
    "engine_no": "HJ602067",
    "location": "OECNRS POOL",
    "department": "OECNRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "229FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03032862",
    "engine_no": "2ZRU553519",
    "location": "SSFMD POOL",
    "department": "SSFMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1370",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE4RD922724",
    "engine_no": "P3C1527331",
    "location": "AD,DEBT MGT DEPT",
    "department": "DMD",
    "driver_name": "BINTA POPOOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS468N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ655243",
    "engine_no": "HJ655243",
    "location": "HEAD,W,U PROCUREMENT",
    "department": "PROCUREMENT",
    "driver_name": "ISHOLA RAMON",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1338",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE8RD922712",
    "engine_no": "P3C1526955",
    "location": "AD/PROCUREMENT DEPT",
    "department": "PROCUREMENT",
    "driver_name": "PETER GODWIN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS188",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E3381788",
    "engine_no": "2ZRU090928",
    "location": "PROCUREMENT",
    "department": "PROCUREMENT",
    "driver_name": "DAUDA DAVARE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS930",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ876085",
    "engine_no": "VF3DDNFPRDJ876085",
    "location": "UNION SUPPORT VEHICLE",
    "department": "UNION SUPPORT VEHICLE",
    "driver_name": "OBI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS955",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586203",
    "engine_no": "VF3DDNFPRGJ586203",
    "location": "ENFORCEMENT UNIT",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "PEU POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS71",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "700008257",
    "engine_no": "399320",
    "location": "DMD-POOL",
    "department": "POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "RB485FG",
    "brand": "Steyr",
    "model": "Truck",
    "vin_sn": "9707122931",
    "engine_no": "9707122931",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "RB741FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "7101896",
    "engine_no": "3351394",
    "location": "MPAPE ROUTE BUS",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS28",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDRB23E063176281",
    "engine_no": "1222587583",
    "location": "GENERAL FLEET POOL/ INTERVENTION",
    "department": "SSFMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS26",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR23E463178292",
    "engine_no": "1222610724",
    "location": "BOARD SECETARIAT",
    "department": "BOARD SECETARIAT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS37",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P600007424",
    "engine_no": "358901",
    "location": "SHUTTLE BUS",
    "department": "SB",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS100",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "1302091",
    "engine_no": "MROFX22G286472846",
    "location": "TECHNOLOGY DEPT",
    "department": "TECHNOLOGY DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS132",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "943475",
    "engine_no": "8140853",
    "location": "COMPLIANCE UNIT POOL",
    "department": "COMPLIANCE UNIT POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS160",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E503009716",
    "engine_no": "ZZRU090471",
    "location": "",
    "department": "FOMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS142",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "6043447",
    "engine_no": "8140779",
    "location": "GENERAL FLEET POOL",
    "department": "SS&FMD",
    "driver_name": "LUGBE ROUTE BUS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS143",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "6043492",
    "engine_no": "8140784",
    "location": "ENFORCEMENT",
    "department": "PEU",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS204",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "506044784",
    "engine_no": "8144151",
    "location": "TECHNICAL DEPT POOL",
    "department": "TECHNICAL DEPT POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS227",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P606042090",
    "engine_no": "8137025",
    "location": "TAX INCENTIVE DEPARTMENT",
    "department": "POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS261",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803009967",
    "engine_no": "2ZRU092032",
    "location": "HCMD",
    "department": "HCMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS320",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "8006965",
    "engine_no": "2TR 8196019",
    "location": "POLICE ENFORCEMENT POOL",
    "department": "PEU",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS347",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08007389",
    "engine_no": "2TR8172246",
    "location": "F&A STORE",
    "department": "F&A",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS352",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G408007503",
    "engine_no": "2TR-9200355",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS381",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408017783",
    "engine_no": "2TR 8225176",
    "location": "LUGBE MSTO",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS383",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706063210",
    "engine_no": "2TR 8198924",
    "location": "MANAMGEMENT POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS490",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E503018984",
    "engine_no": "2ZRU201738",
    "location": "OCD-SSG",
    "department": "SSG",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS551",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G008008177",
    "engine_no": "2TR8217040",
    "location": "F&A STORE",
    "department": "FINANCE & ACCOUNT DEPARTMENT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS517",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E503015860",
    "engine_no": "2ZRU140304",
    "location": "TPAD",
    "department": "TPAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS394",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608017670",
    "engine_no": "2TR8224273",
    "location": "TPSD",
    "department": "TPSD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS549",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208018043",
    "engine_no": "2TR8227463",
    "location": "STRATEGIC MANAGEMENT DEPT",
    "department": "SMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS419",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08008252",
    "engine_no": "2TR8219766",
    "location": "FACILITY MGT",
    "department": "FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS556",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08008719",
    "engine_no": "2TR8229543",
    "location": "INTERNAL AFFAIRS POOL",
    "department": "IAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS585",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518204006061",
    "engine_no": "8284002",
    "location": "DUTSE ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS587",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518404004621",
    "engine_no": "8238228",
    "location": "JIKWOYI ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS590",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518504006085",
    "engine_no": "8284753",
    "location": "KUJE ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS595",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518X04004784",
    "engine_no": "2TR8244321",
    "location": "SULEJA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS596",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518004006155",
    "engine_no": "2TR8286605",
    "location": "GWAGWALADA",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS597",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518104006116",
    "engine_no": "2TR8284891",
    "location": "KUBWA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS602",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308022022",
    "engine_no": "2TR8274684",
    "location": "TAX INCENTIVE AUDIT ABUJA",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS607",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308023946",
    "engine_no": "2TR8301816",
    "location": "CHANGE MANAGEMENT DPT",
    "department": "CHANGE MANAGEMENT DPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS617",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P0A8019222",
    "engine_no": "2TR8238260",
    "location": "FACILITY POOL",
    "department": "FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS620",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P0A8019186",
    "engine_no": "2TR8237608",
    "location": "STRATEGIC MGT DEPT",
    "department": "STRATEGIC MGT DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS628",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008023712",
    "engine_no": "8297552",
    "location": "GBTD",
    "department": "GBTD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS633",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608023715",
    "engine_no": "8297627",
    "location": "ACTU",
    "department": "ACTU",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS794/191FIRS",
    "brand": "Ford",
    "model": "Ambulance",
    "vin_sn": "NM0XXXTTFXBEO4477",
    "engine_no": "BE04477",
    "location": "HQ AMBULANCE",
    "department": "AMBULANCE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS651/90FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRXP12008026710",
    "engine_no": "2TR8355857",
    "location": "PROCUREMENT",
    "department": "PROCUREMENT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS652/88FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRXP12008026741",
    "engine_no": "2TR8356171",
    "location": "L&P POOL",
    "department": "LEGAL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS654/67FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P80825370",
    "engine_no": "8318197",
    "location": "TPS HQ",
    "department": "TPS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS655/161FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808025269",
    "engine_no": "8331844",
    "location": "STRATEGIC MGT DEPT",
    "department": "STRATEGIC MGT DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS664/163FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P",
    "engine_no": "8321976",
    "location": "PDD POOL",
    "department": "PDD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS712/51FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026965",
    "engine_no": "2TR8358873",
    "location": "COMMUNICATION AND SERVICOM",
    "department": "CLD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS692/61FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408027780",
    "engine_no": "2TR8361492",
    "location": "IAD POOL",
    "department": "IAD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS694/168FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08027735",
    "engine_no": "2TR836858",
    "location": "TIMD",
    "department": "TIMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS696/171FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026545",
    "engine_no": "2TR8353063",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS745/41FIRS",
    "brand": "Ford",
    "model": "Ranger Pick Up",
    "vin_sn": "MMCLSPE70BW960846",
    "engine_no": "96400244",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS755/108FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903027006",
    "engine_no": "2ZRU419672",
    "location": "TAX AUDIT HQ POOL",
    "department": "TAX AUDIT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS791/188FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P400033357",
    "engine_no": "2TR8222103",
    "location": "TAT SECETARIAT",
    "department": "TAT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS790/187FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G408013110",
    "engine_no": "2TR7206420",
    "location": "TAT SECETARIAT",
    "department": "TAT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS792/189FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108028790",
    "engine_no": "2TR8402149",
    "location": "TAX INCENTIVE DEPARTMENT",
    "department": "TID",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS798/195FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08016805",
    "engine_no": "2TR 7362957",
    "location": "FIRS -INTELLIGENCE UNIT ABUJA",
    "department": "SSM",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS777/174FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003028366",
    "engine_no": "2ZRU451578",
    "location": "SPECIAL CRIMES DIV. OF TID FIRS-EFCC JOINT TASK FORCE POOL",
    "department": "STCD POOL",
    "driver_name": "STCD POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "248FIRS",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518X04013596",
    "engine_no": "2TR8513852",
    "location": "HQ- GENERAL TRANSPORT FLEET POOL",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "345FIRS",
    "brand": "Mercedes-Benz",
    "model": "Truck",
    "vin_sn": "WDB9700771L761037",
    "engine_no": "ANR3068264",
    "location": "SS&FMD",
    "department": "GENERAL FLEET",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "291FIRS",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518X04013999",
    "engine_no": "8521191",
    "location": "MASAKA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "322FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408036169",
    "engine_no": "2TR8518367",
    "location": "HQ- TAX POLICY",
    "department": "HQ- TAX POLICY",
    "driver_name": "TPAD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS654",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518904016926",
    "engine_no": "2TR8576381",
    "location": "MASAKA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS655",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518604017550",
    "engine_no": "2TR8589478",
    "location": "MARABA",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS701",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518504017507",
    "engine_no": "2TR8588624",
    "location": "MARABA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS672",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808038720",
    "engine_no": "2TR-8574120",
    "location": "INTELLIGENCE UNIT-OEC",
    "department": "INTELLIGENCE UNIT-OEC",
    "driver_name": "INTELLIGENCE/OEC UNIT HEADED BY THEOPHILUS NNAJI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS673",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808038782",
    "engine_no": "2TR-8571237",
    "location": "D(C&LD)",
    "department": "C&LD",
    "driver_name": "DURUMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS674",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708038692",
    "engine_no": "2TR-8573662",
    "location": "TPSD",
    "department": "TPSD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS677",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808038684",
    "engine_no": "2TR-8565989",
    "location": "LTO NO OIL HQ",
    "department": "LTO NO OIL HQ",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS680",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508039047",
    "engine_no": "2TR-8583308",
    "location": "DMO",
    "department": "DMD UYO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS699",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108039322",
    "engine_no": "2TR-8588896",
    "location": "ENFORCEMENT WUSE 2",
    "department": "PEU",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS685",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G408025676",
    "engine_no": "2TR-7715148",
    "location": "OEC-FIRS",
    "department": "OEC-FIRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS707",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08026203",
    "engine_no": "2TR7730726",
    "location": "POLICE ENFORCEMENT POOL",
    "department": "PEU",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS691",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518X04016854",
    "engine_no": "2TR8571136",
    "location": "HQ- GENERAL TRANSPORT FLEET POOL-Maraba Route Staff Bus",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS713",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518304017375",
    "engine_no": "2TR8585989",
    "location": "KUJE ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS714",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518904017199",
    "engine_no": "2TR8582437",
    "location": "SULEJA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS715",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518004017379",
    "engine_no": "2TR8585836",
    "location": "GWAGWALADA",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS765",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208044366",
    "engine_no": "2TR8711986",
    "location": "RAD POOL HQ",
    "department": "RAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS771",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908044445",
    "engine_no": "2TR8713346",
    "location": "TAX AUDIT ABUJA",
    "department": "TAX AUDIT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS841",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608044709",
    "engine_no": "2TR8720125",
    "location": "OCD-ETG",
    "department": "ETG",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS837",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008044625",
    "engine_no": "2TR8717343",
    "location": "PRS",
    "department": "PRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS867",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G608030491",
    "engine_no": "2TR8825084",
    "location": "SSM",
    "department": "SS&FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS868",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G108030351",
    "engine_no": "2TR8013918",
    "location": "SCO/ KNN",
    "department": "SCO KNN",
    "driver_name": "SCO/ NKN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS902",
    "brand": "Ford",
    "model": "Ranger Pick-Up",
    "vin_sn": "6FPPXXMJ2PFE72737",
    "engine_no": "FE72737",
    "location": "OFFICE OF THE CHIEF OF STAFF POOL",
    "department": "COS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS954",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ597560",
    "engine_no": "VF3DDNFPRGJ597560",
    "location": "RAD",
    "department": "RAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS983",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5182G4027566",
    "engine_no": "2TR9058957",
    "location": "DUTSE ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS984",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5186G4027540",
    "engine_no": "2TR9058359",
    "location": "KUBWA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS368N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5184G4027567",
    "engine_no": "2TR9058920",
    "location": "EXECUTIVR FLEET POOL",
    "department": "EXECUTIVE POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS378N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5186G4027571",
    "engine_no": "2TR9059154",
    "location": "MADALA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS375N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22PXF6159529",
    "engine_no": "2TR8725157",
    "location": "DMED",
    "department": "DMED",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS376N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22P9F6158498",
    "engine_no": "2TR8719817",
    "location": "EXECUTIVE FLEET POOL",
    "department": "ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS477N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5189G4028973",
    "engine_no": "2TR9087737",
    "location": "MANAGEMENT FLEET POOL",
    "department": "STAFF BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS478N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5184G4028721",
    "engine_no": "2TR9083466",
    "location": "KUJE ROUTE",
    "department": "STAFF BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS479N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5184G4027830",
    "engine_no": "2TR9069136",
    "location": "KARO ROUTE",
    "department": "STAFF BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS483N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROHX8CD0H0913947",
    "engine_no": "2TRA165896",
    "location": "SSFMD POOL",
    "department": "SSFMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS491N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P506160745",
    "engine_no": "2TR9004736",
    "location": "IAD",
    "department": "IAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS494N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508048895",
    "engine_no": "2TR9103937",
    "location": "COMMUNICATION AND LIAISON DEPT",
    "department": "CLD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS495N",
    "brand": "Tata",
    "model": "Tanker",
    "vin_sn": "4493H5L101070",
    "engine_no": "6BTAA7H163612390",
    "location": "SS&FMD",
    "department": "SS&FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS506N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MRODX8CDH0591275",
    "engine_no": "MRODX8CDH0591275",
    "location": "OCD-SSG",
    "department": "OCD-SSG",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS600N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P8A8017315",
    "engine_no": "JTGRX12P8A8017315",
    "location": "GENERAL FLEET POOL",
    "department": "WELFARE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS623N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CPOL6003132",
    "engine_no": "6003132",
    "location": "TPAD",
    "department": "TPAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1007",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH2000001336",
    "engine_no": "TRH2000001336",
    "location": "SPECIAL TAX AUDIT ABUJA",
    "department": "SPECIAL TAX AUDIT ABUJA",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1026",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P500058638",
    "engine_no": "JTFJX02P500058638",
    "location": "EMERGING & SPECIAL TAX DEPT",
    "department": "EMERGING & SPECIAL TAX DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1028",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P705036580",
    "engine_no": "JTFJX02P705036580",
    "location": "MSTD",
    "department": "D-MSTD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1030",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P3D5029644",
    "engine_no": "JTFJX02P3D5029644",
    "location": "MTD",
    "department": "D-MTD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1033",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02PXE0093133",
    "engine_no": "JTFJX02PXE0093133",
    "location": "ABUJA TAX INVESTIGATION DEPT.",
    "department": "ABUJA TAX INVESTIGATION DEPT.",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1043",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P195010954",
    "engine_no": "JTGJX02P195010954",
    "location": "TID DEPARTMENT",
    "department": "TID DEPARTMENT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1044",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P2A0047029",
    "engine_no": "JTFHX02P2A0047029",
    "location": "(SPECIAL CRIME DIVISION",
    "department": "(SPECIAL CRIME DIVISION",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS639N",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS68KA745558",
    "engine_no": "LKLSBAS68KA745558",
    "location": "OCD-DISG",
    "department": "COS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS647N",
    "brand": "Innoson",
    "model": "Pickup",
    "vin_sn": "LJTNTGU5Y1LN400651",
    "engine_no": "49787D-QR25",
    "location": "PROCUREMENT POOL",
    "department": "PROCUREMENT POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1058",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKL1BAA82KA745604",
    "engine_no": "LKL1BAA82KA745604",
    "location": "MANAGEMENT FLEET POOL",
    "department": "GUDU ROUTE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1086",
    "brand": "Innoson",
    "model": "Granite",
    "vin_sn": "XLTA12H2P2M1000016X",
    "engine_no": "XLTA12H2P2M1000016X",
    "location": "MANAGEMENT FLEET POOL",
    "department": "MANAGEMENT FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1260",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z0NU006240",
    "engine_no": "M9WA2502643",
    "location": "FCT",
    "department": "MTA ABJ",
    "driver_name": "SPACE SALAMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1223",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BX8CD1M2772536",
    "engine_no": "MR0BX8CD1M2772536",
    "location": "D-LEGAL DEPT",
    "department": "LEGAL DEPARTMENT",
    "driver_name": "ABU OCHEME",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1255",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP0M6010186",
    "engine_no": "7GR-FKS3456",
    "location": "TID",
    "department": "TID",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1256",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP0M6010552",
    "engine_no": "7GR-FKS3456",
    "location": "OD-HCMD",
    "department": "HCMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1259",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP6M6010877",
    "engine_no": "7GR-FKS3456",
    "location": "LEGAL DEPARTMENT",
    "department": "LEGAL DEPARTMENT",
    "driver_name": "LEGAL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1262",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP1L6003933",
    "engine_no": "7GR-FKS3456",
    "location": "OECPROTOCOL",
    "department": "OECFIRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1263",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CPCL6002967",
    "engine_no": "7GR-FKS3456",
    "location": "FINANCE & ACCOUNTS",
    "department": "FINANCE & ACCOUNT DEPARTMENT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1266",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CB0N6016031",
    "engine_no": "7GR-FKS3456",
    "location": "SPECIAL TAX CRIME DEPARTMENT",
    "department": "STCD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1298",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD5N0097358",
    "engine_no": "MR0BU8CD5N0097358",
    "location": "D/SS&FMD",
    "department": "SS&FMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1392",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP8P6022324",
    "engine_no": "JTGHN9CP8P6022324",
    "location": "SERVICOM",
    "department": "SERVICOM",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1393",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9P6022168",
    "engine_no": "JTGHN9CP9P6022168",
    "location": "LEGAL AND PROSECUTION DEPT",
    "department": "LEGAL AND PROSECUTION DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1395",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP4P6021307",
    "engine_no": "JTGHN9CP4P6021307",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "SS&FMD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1396",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN902BP6021383",
    "engine_no": "JTGHN902BP6021383",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1398",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP3M6009671",
    "engine_no": "JTGHN9CP3M6009671",
    "location": "STAFF SHUTTLE BUS",
    "department": "STAFF BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1015",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "ITRH2000037773",
    "engine_no": "ITRH2000037773",
    "location": "TID NORTHERN BUREAU ABJ",
    "department": "TID NORTHERN BUREAU ABJ",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1166",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB24HK6N3117891",
    "engine_no": "JTNB24HK6N3117891",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS684",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G908025687",
    "engine_no": "2TR-7715246",
    "location": "ENFORCEMENT POOL",
    "department": "POOL",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS1064",
    "brand": "Innoson",
    "model": "G40 Suv",
    "vin_sn": "LNBRCFDK4JB226628",
    "engine_no": "B231R-VA-09N021429",
    "location": "I-24 PROJECT- OCD-ETO",
    "department": "I-24 PROJECT- OCD-ETO",
    "driver_name": "Intervention with RAD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS829",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ802225",
    "engine_no": "VF3DDNFPRDJ802225",
    "location": "PROJECT VEHICLE (PROCUREMENT)",
    "department": "PROJECT VEHICLE (PROCUREMENT)",
    "driver_name": "PROCUMENT POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS924",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPREJ762333",
    "engine_no": "VF3DDNFPREJ762333",
    "location": "TC-MTO KANO",
    "department": "MTO KANO",
    "driver_name": "RABIU ALI KURA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1363",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT351996",
    "engine_no": "S3LH958",
    "location": "AD/ LTA LAGOS",
    "department": "AD/ LTA LAGOS",
    "driver_name": "ILEM THOMAS O.",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS784/181FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03028116",
    "engine_no": "2ZRU445783",
    "location": "AD-TPSD",
    "department": "TPSD",
    "driver_name": "RICHARD ABOKI JOHN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1186",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z6W404753",
    "engine_no": "LB37622Z6W404753",
    "location": "DD-BUSINESS ANALYSIS",
    "department": "BAES",
    "driver_name": "RICHARD KIMEKU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS464N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ614775",
    "engine_no": "HJ614775",
    "location": "HEAD- RDMAU",
    "department": "HEAD- RDMAU",
    "driver_name": "ROSE SHUA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS819",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ831693",
    "engine_no": "VF3DDNFPRDJ831693",
    "location": "AD-HCMD",
    "department": "AD-HCMD",
    "driver_name": "RUTH EJIKE FREDRICKS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS173",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403009982",
    "engine_no": "2ZRUO93154",
    "location": "OECFIRS POOL",
    "department": "OECFIRS /POOL",
    "driver_name": "OECFIRS POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS660/FIRS1032",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE400002371",
    "engine_no": "2ZRU-808386",
    "location": "D-TPSD (POOL)",
    "department": "TPSD (POOL)",
    "driver_name": "SAADATU YERO",
    "sco": "HQ"
  },
  {
    "license_plate": "293FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003034359",
    "engine_no": "2ZRU646992",
    "location": "AD/LAGE TAX AUDIT",
    "department": "LTA ABUJA",
    "driver_name": "SABA MOBOLAJI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1417",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9P3029982",
    "engine_no": "JTNBZ4HK9P3029982",
    "location": "SA-COMPLIANCE",
    "department": "SA-COMPLIANCE",
    "driver_name": "SIMEON OBIDAIRO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1418",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK1N3025762",
    "engine_no": "JTNBZ4HK1N3025762",
    "location": "SA,FACILITY BULDING ,INFRA",
    "department": "SA,FACILITY BULDING ,INFRA",
    "driver_name": "JAMES ADEKUNLE OGIDI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS687",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JEX00001287",
    "engine_no": "2ZRU-791582",
    "location": "OCD-SPECIAL DUTY",
    "department": "OCD SPECIAL DUTY",
    "driver_name": "SECRTARIAT",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS520",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E303015565",
    "engine_no": "2ZRU143339",
    "location": "O-COS",
    "department": "O-COS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS799",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ777557",
    "engine_no": "VF3DDNFPRDJ777557",
    "location": "AD-HCMD (APPEALS & PETITION)",
    "department": "HCMD",
    "driver_name": "SALEH MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1385",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE0RD922722",
    "engine_no": "P3C1527335",
    "location": "AD/LTA ABUJA",
    "department": "AD/LTA ABUJA",
    "driver_name": "SALIMATU MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS341",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SBIBL76L90E011399",
    "engine_no": "3ZRA362331",
    "location": "REGIONAL ADMISNISTRATOR",
    "department": "REGIONAL ADMISNISTRATION LME",
    "driver_name": "SALIU OLANREWAJU",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1378",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR1KR960784",
    "engine_no": "PM0AD107729",
    "location": "DD/ECFIRS/SA ICT",
    "department": "DD/ECFIRS/SA ICT",
    "driver_name": "SAMAD AMUSAT",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1292",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE07PT397618",
    "engine_no": "4A92*S3LH955*",
    "location": "CHIEF DETAILS/ECFIRS",
    "department": "OECFIRS",
    "driver_name": "SAMUEL ADESOJI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1235",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBX9FJ8N5111104",
    "engine_no": "2TR-FE2694",
    "location": "BOARD MEMBER (NORTH WEST)",
    "department": "BOARD MEMBER NORTH WEST",
    "driver_name": "DANIEL ONUKUN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1415",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK8P3027933",
    "engine_no": "JTNBZ4HK8P3027933",
    "location": "SA SPECIAL DUTIES",
    "department": "SA SPECIAL DUTIES",
    "driver_name": "ADEDAYOR IYANIWURA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1416",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9P3030193",
    "engine_no": "JTNBZ4HK9P3030193",
    "location": "SA,ECFIR, TECHNICAL",
    "department": "SA,ECFIR, TECHNICAL",
    "driver_name": "WALE ADEGBOYEGA",
    "sco": "HQ"
  },
  {
    "license_plate": "RBC445DE (40FIRS)",
    "brand": "Kia",
    "model": "Cerato",
    "vin_sn": "KNAFX417BF5319608",
    "engine_no": "G4NAEH518064",
    "location": "FMD",
    "department": "FMD",
    "driver_name": "SHAMUNA ABDULLAHI MASHI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS824",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ803856",
    "engine_no": "VF3DDNFPRDJ803856",
    "location": "HEAD ITSM UNIT",
    "department": "TECHNOLOGY DEPT",
    "driver_name": "FARUK",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1406",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08RT353923",
    "engine_no": "4A92*S3LH973",
    "location": "EC-FIRS TA/TEC-ADVISER",
    "department": "EC-FIRS TA/TEC-ADVISER",
    "driver_name": "SHERIFF GANMBONI",
    "sco": "HQ"
  },
  {
    "license_plate": "294FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903034490",
    "engine_no": "2ZRU661277",
    "location": "AD-F&A",
    "department": "F&A",
    "driver_name": "SIAKA ADAVIZE SALAMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1285",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03PT397616",
    "engine_no": "492*53LH963",
    "location": "TECHNICAL DEPT",
    "department": "TECHNICAL DEPT",
    "driver_name": "SIMEON C. ONYEGBULA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS12",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E603180098",
    "engine_no": "2619034",
    "location": "FIX ASSET UNIT F&A",
    "department": "F&A",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1096",
    "brand": "Innoson",
    "model": "Granite",
    "vin_sn": "LTA12H2P2M1000008",
    "engine_no": "4K22D4M-SYT8174",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "GENERAL FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1316",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR3RA960768",
    "engine_no": "LS5A3AKR3RA960768",
    "location": "DD,HCMD",
    "department": "DD,HCMD",
    "driver_name": "FANTAJAM LIMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1317",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP4P6021378",
    "engine_no": "JTGHN9CP4P6021378",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1320",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8106510073",
    "engine_no": "JTGAKAB8106510073",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS609",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808023831",
    "engine_no": "2TR8300060",
    "location": "MSTA WUSE II",
    "department": "MSTA WUSE II",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1239",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z2NU006241",
    "engine_no": "L6T7722Z2NU006241",
    "location": "REGIONAL COORD. FCT",
    "department": "REGIONAL COORD. FCT",
    "driver_name": "AKHUEMOKHAN STANLEY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS977",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ606740",
    "engine_no": "VF3DDNFPRGJ606740",
    "location": "GENERAL FLEET POOL",
    "department": "SS&FMD",
    "driver_name": "FUELLING & JOURNEY MANAGEMENT UNIT",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS720",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRD842625",
    "engine_no": "VF3DDNFPRDJ842625",
    "location": "SPECIAL CRIMES DIV. OF TID FIRS-EFCC JOINT TASK FORCE POOL",
    "department": "",
    "driver_name": "STCD POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1293",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09PT397605",
    "engine_no": "4A9*S3LS049",
    "location": "FEDERAL AUDIT",
    "department": "FEDERAL AUDIT",
    "driver_name": "SUBANGA NAOMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS549N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL024607",
    "engine_no": "HL024607",
    "location": "AD-PROCUREMENT",
    "department": "PROCUREMENT",
    "driver_name": "SUOWERE EBAMUGHA MICHAEL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS544",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E003017743",
    "engine_no": "2ZRU191783",
    "location": "OECNRS DSS",
    "department": "OECNRS",
    "driver_name": "BELLO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS644N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE400004685",
    "engine_no": "2ZR- U889942",
    "location": "DD-BUILDING AND WORKS",
    "department": "BUILDING AND WORKS",
    "driver_name": "TAIWO AIMOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "357FIRS/232FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203035061",
    "engine_no": "2ZRU681457",
    "location": "DD-P&CD",
    "department": "P&CD",
    "driver_name": "TAIWO AJANI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1221",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z1MW009029",
    "engine_no": "L6T7824Z1MW009029",
    "location": "ADT-HEAD,TAX INCENTIVES",
    "department": "TAX INCENTIVES DEPT",
    "driver_name": "TANKO BWESE DANJUMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1348",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02RT351990",
    "engine_no": "S3LH972",
    "location": "DD/OCD-CSG",
    "department": "OCD-CSG",
    "driver_name": "TARFA DEBORAH",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1352",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT352023",
    "engine_no": "S3LH998",
    "location": "TAT,COMMISSIONER",
    "department": "TAT,COMMISSIONER",
    "driver_name": "TAT,COMMISSIONER",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS220",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "50603473",
    "engine_no": "8140864",
    "location": "TAX POLICY HQ",
    "department": "TAX POLICY HQ",
    "driver_name": "TAX POLICY HQ",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS128",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803009788",
    "engine_no": "2ZR0757459",
    "location": "DATA MANAGEMENT PROJECT PRS (TAX PRO)",
    "department": "PRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1379",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3DKR77RA964775",
    "engine_no": "PM0AD107697",
    "location": "EMO PH1",
    "department": "EMO PH1",
    "driver_name": "UCHENNA OBIAKOR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS900",
    "brand": "Ford",
    "model": "Ranger Pick-Up",
    "vin_sn": "6FPPXXMJ2PFE69237",
    "engine_no": "FE69237",
    "location": "SS&FMD",
    "department": "SS&FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS830",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833763",
    "engine_no": "VF3DDNFPRDJ833763",
    "location": "AD-NEW PROJECT DEPT SOUTH WEST REGION",
    "department": "AD-NEW PROJECT DEPT SOUTH WEST REGION",
    "driver_name": "UMAR DOKOCHI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS735",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ694506",
    "engine_no": "VF3DDNFPRDJ694506",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "EC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS918",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ871037",
    "engine_no": "VF3DDNFPRDJ871037",
    "location": "AD/PMO",
    "department": "AD/PMO",
    "driver_name": "AMINU ADAMU DINAWA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS991",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ653645",
    "engine_no": "VF3DDNFPRDJ653645",
    "location": "SM/F&A",
    "department": "SM/F&A",
    "driver_name": "TAOFIK OMOFOYEWA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS33",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E703176531",
    "engine_no": "2598570",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "UNIT HEADFLEET APP",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1332",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE9RD910861",
    "engine_no": "P3C1502600",
    "location": "AD/OCD CORPORATE SERV",
    "department": "OCD-CSG",
    "driver_name": "UTIB C. AGBAEGBU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS518",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56EX03016681",
    "engine_no": "2RU163544",
    "location": "AD-ICT",
    "department": "ICT",
    "driver_name": "ATABON E.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS408",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "4TIBF3EK5AU019121",
    "engine_no": "2ARD044056",
    "location": "PROTOCOL UNIT",
    "department": "OECFIRS",
    "driver_name": "YD IBRAHIM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS804",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830608",
    "engine_no": "VF3DDNFPRDJ830608",
    "location": "PROTOCOL",
    "department": "OECFIRS",
    "driver_name": "WAHIDI MOHAMMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1188",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z6MW009057",
    "engine_no": "L6T7824Z6MW009057",
    "location": "OED-F&C",
    "department": "OED-F&C",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1296",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08PT397594",
    "engine_no": "4A92*S3LS065",
    "location": "AD/OCD-ESG",
    "department": "OCD-ESG",
    "driver_name": "YAHAYA AHIABA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS929",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ883014",
    "engine_no": "VF3DDNFPRDJ883014",
    "location": "HEAD EXECUTIVE POOL MAINT.",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1273",
    "brand": "Innoson",
    "model": "Capa",
    "vin_sn": "LGG7E3D22LZ416910",
    "engine_no": "4G6354T*SYN3383*",
    "location": "ECFIRS",
    "department": "ECFIRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1053",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3016324",
    "engine_no": "JTNBZ4HK2L3016324",
    "location": "D-TPSD",
    "department": "D-TPSD",
    "driver_name": "YERO SA'ADATU AHMED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS737/104FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603027321",
    "engine_no": "2RU426030",
    "location": "AD-SSFMD",
    "department": "SSFMD",
    "driver_name": "MUSTAPHA MBURA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1051",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F35GY6LY006111",
    "engine_no": "VR3F35GY6LY006111",
    "location": "AD-E-SERVICES COORDINATOR",
    "department": "AD-E-SERVICES COORDINATOR",
    "driver_name": "ZAINAB GOBIR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1134",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09MT454719",
    "engine_no": "4A92515X530",
    "location": "AD-SPECIAL CRIME DEPT",
    "department": "ABUJA",
    "driver_name": "ZAKO MUSTAPHA M",
    "sco": "HQ"
  },
  {
    "license_plate": "285FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603034303",
    "engine_no": "2ZRU649141",
    "location": "AD-LARGE TAX OFFICE",
    "department": "LTA",
    "driver_name": "ZOAKAH BB",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1390",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BX8CD502788183",
    "engine_no": "MR0BX8CD502788183",
    "location": "POLICE ENFORCEMENT UNIT",
    "department": "HEAD,ENFORCEMENT ABUJA",
    "driver_name": "HEAD,ENFORCEMENT ABUJA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1391",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BX8CD402788305",
    "engine_no": "MR0BX8CD402788305",
    "location": "FMD/ POOL",
    "department": "FMD/ POOL",
    "driver_name": "FMD/ POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1401",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK503030627",
    "engine_no": "JTNBZ4HK503030627",
    "location": "ED-E&MTD",
    "department": "EMTD",
    "driver_name": "BOLAJI AKINTOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1426",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD9P0125911",
    "engine_no": "1GRH349966",
    "location": "ECFIRS-SA-PROTOCOL",
    "department": "ECFIRS-SA-PROTOCOL",
    "driver_name": "ADETOYOSI DAMOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1427",
    "brand": "Toyota",
    "model": "Granvia",
    "vin_sn": "JTFYM8AP308003677",
    "engine_no": "JTFYM8AP308003677",
    "location": "OEC-FIRS",
    "department": "OEC POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1428",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD0P0100315",
    "engine_no": "MR0BU8CD0P0100315",
    "location": "GD-SS",
    "department": "GD-SS",
    "driver_name": "JAMES ADEKUNLE OGIDI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1430",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2T1BR32E94C291991",
    "engine_no": "2T1BR32E94C291991",
    "location": "INTELLIGENCE UNIT",
    "department": "INTELLIGENCE UNIT",
    "driver_name": "WUSE 2",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1433",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU9FJ0PK238474",
    "engine_no": "JTEBU9FJ0PK238474",
    "location": "ECFIRS-SA SINGLE WINDOW",
    "department": "POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1435",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBX3FJX0K349057",
    "engine_no": "2TR-2571700",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1437",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMAB7BJXP4101305",
    "engine_no": "V35A0178676",
    "location": "ECFIRS-SA SINGLE WINDOW",
    "department": "SINGLE WINDOW",
    "driver_name": "TOLA FAKOLADE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1438",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMAB7BJXP4096218",
    "engine_no": "V35A0171389",
    "location": "ILLICIT FUNDS.ADVISER 1",
    "department": "ILLICIT FUNDS.ADVISER 1",
    "driver_name": "PROF, BOLAJI OWASANOY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1443",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9R3033761",
    "engine_no": "JTNBZ4HK9R3033761",
    "location": "D-DIGITAL & TECH",
    "department": "DIGITAL AND TECHNOLOGY",
    "driver_name": "BIMBO LADELE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1444",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HKP3031678",
    "engine_no": "JTNBZ4HKP3031678",
    "location": "SA-DIGITAL SERVICES",
    "department": "SA-DIGITAL SERVICES",
    "driver_name": "GANIU FASASI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1449",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG5PN230013",
    "engine_no": "LNLG32AG5PN230013",
    "location": "PLANNING COORDINATION",
    "department": "PLANNING COORDINATION",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1456",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B300P0025351",
    "engine_no": "LDDC8B300P0025351",
    "location": "PROCUREMENT DEPT POOL",
    "department": "PROCUREMENT POOL",
    "driver_name": "PROCUREMENT POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1458",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B304P0025353",
    "engine_no": "LDDC8B304P0025353",
    "location": "OCD/CSG POOL",
    "department": "OCD/CSG POOL",
    "driver_name": "BOLAJI AKINTOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1459",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B306P0025337",
    "engine_no": "LDDC8B306P0025337",
    "location": "C&SD",
    "department": "C&SD",
    "driver_name": "C&SD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1460",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B308P0025355",
    "engine_no": "LDDC8B308P0025355",
    "location": "SS&FMD",
    "department": "SS&FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1461",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B309P0025347",
    "engine_no": "LDDC8D309P0025347",
    "location": "SSFMD POOL",
    "department": "SSFMD POOL",
    "driver_name": "SSFMD POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1462",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B309P0025350",
    "engine_no": "LDDC8B309P0025350",
    "location": "SSFMD/POOL",
    "department": "SSFMD/POOL",
    "driver_name": "S&SM",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1463",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B302P0025352",
    "engine_no": "LDDC8B302P0025352",
    "location": "ECFIRS PROTOCOL",
    "department": "ECFIRS PROTOCOL",
    "driver_name": "NASIRU YABAGI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1464",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK5P3028005",
    "engine_no": "JTNBZ4HK5P3028005",
    "location": "D,DEBT MGT DEPARTMENT",
    "department": "D,DEBT MGT DEPARTMENT",
    "driver_name": "KUNLE OLALEKAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1465",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK9P3028041",
    "engine_no": "JTNBZ4HK9P3028041",
    "location": "GD-GOVT BUSINESS",
    "department": "GD-GOVT BUSINESS",
    "driver_name": "WANDE AKINPELU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1466",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2P3027099",
    "engine_no": "JTNBZ4HK2P3027099",
    "location": "CHIEF ECONOMIC ADVISER",
    "department": "CHIEF ECONOMIC ADVISER",
    "driver_name": "DR, MOHAMMED ADAYA S.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1467",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU80DXP0126761",
    "engine_no": "MR0BU80DXP0126761",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1468",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD41P0126867",
    "engine_no": "MR0BU8CD41P0126867",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1469",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAA9AJ00K004286",
    "engine_no": "JTEAA9AJ00K004286",
    "location": "SA-COMPLIANCE",
    "department": "SA-COMPLIANCE",
    "driver_name": "SIMEON OBIDAIRO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1470",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAX9AJ80K002123",
    "engine_no": "JTEAX9AJ80K002123",
    "location": "ILLICIT FUNDS.ADVISER 3",
    "department": "ILLICIT FUNDS.ADVISER 3",
    "driver_name": "PROF, AKINKOYE E. YEMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1309",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR6RA960375",
    "engine_no": "LS5A3AKR6RA960375",
    "location": "TAX INVESTIGATION",
    "department": "TAX INVESTIGATION",
    "driver_name": "ABDUL YAHAYA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS612N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL025275",
    "engine_no": "VF38D5GYAHL025275",
    "location": "DD - LEGAL ADV. & MGT",
    "department": "DD-LEGAL ADVISORY & MGT",
    "driver_name": "MOHAMMED SHEHU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1178",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z2NU006210",
    "engine_no": "L6T7722Z2NU006210",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1247",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK2N3171012",
    "engine_no": "A25A-FKS2487",
    "location": "D-TID",
    "department": "TID",
    "driver_name": "OBASI MBA OKOKO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1227",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK1L3014774",
    "engine_no": "JTNBZ4HK1L3014774",
    "location": "D/LTD/OIL & GAS",
    "department": "SCO",
    "driver_name": "OYENIYI YIDIAST FADEKE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1307",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR1RA960641",
    "engine_no": "LS5A3AKR1RA960641",
    "location": "DD/FACILITY DEPARTMENT",
    "department": "DD/LTO(NON-OIL LAGOS)",
    "driver_name": "ABUBAKAIR ABDULKADIR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1302",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTEBU3FJ7AK011884",
    "engine_no": "JTEBU3FJ7AK011884",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1228",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK3L3014422",
    "engine_no": "JTNBZ4HK3L3014422",
    "location": "LTO/MANUFACTURING",
    "department": "SCO",
    "driver_name": "OYEBANJI MATTHEW",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS725",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE400002273",
    "engine_no": "2ZRU806812",
    "location": "AD- TAX AUDIT",
    "department": "AD-TAX AUDIT",
    "driver_name": "PAUL VIANANA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1442",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU9FJ1PK244218",
    "engine_no": "JTEBU9FJ1PK244218",
    "location": "D,/ECFIRS LIAISON OFFICE",
    "department": "D,/ECFIRS LIAISON OFFICE",
    "driver_name": "AUWALU ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1471",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E3SA940473",
    "engine_no": "LS4ASE2E3SA940473",
    "location": "DD,OECFIRS",
    "department": "DD,OECFIRS",
    "driver_name": "COMFORT OLUSHOLA. A.",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1472",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROKX8CD3P1884202",
    "engine_no": "MROKX8CD3P1884202",
    "location": "OSA SPECIAL DUTIES",
    "department": "OSA SPECIAL DUTIES",
    "driver_name": "ADEDAYOR IYANIWURA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1473",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROKX8CD2P1907453",
    "engine_no": "MROKX8CD2P1907453",
    "location": "OSA SPECIAL DUTIES",
    "department": "OSA SPECIAL DUTIES",
    "driver_name": "ADEDAYOR IYANIWURA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1475",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B960RD070048",
    "engine_no": "LDP41B960RD070048",
    "location": "CD, CSG",
    "department": "CD, CSG",
    "driver_name": "BOLAJI AKINTOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1476",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B967RD048127",
    "engine_no": "LDP41B967RD048127",
    "location": "CD, LTG",
    "department": "CD, LTG",
    "driver_name": "AMINA ADO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1477",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B960RD056554",
    "engine_no": "LDP41B960RD056554",
    "location": "CD,MTG",
    "department": "CD,MTG",
    "driver_name": "DICK IRRI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1478",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B969RD067102",
    "engine_no": "LDP41B969RD067102",
    "location": "CD: SSG",
    "department": "CD: SSG",
    "driver_name": "ML ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1479",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B962RD074084",
    "engine_no": "LDP41B962RD074084",
    "location": "CD CHIEF OF STAFF",
    "department": "CD CHIEF OF STAFF",
    "driver_name": "TAYO KOLEOSHO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1480",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B962RD067104",
    "engine_no": "LDP41B962RD067104",
    "location": "CD:SPECIAL DUTTIES",
    "department": "CD:SPECIAL DUTTIES",
    "driver_name": "TAMADI SHETTIMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1481",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B965RD070062",
    "engine_no": "LDP41B965RD070062",
    "location": "CD:PSG",
    "department": "CD:PSG",
    "driver_name": "ANTHONY OKONKWO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1482",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B960RD067098",
    "engine_no": "LDP41B960RD067098",
    "location": "CD - ETG",
    "department": "CD - ETG",
    "driver_name": "MATTHEW O. GBONJUBOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1483",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B968RD057080",
    "engine_no": "LDP41B968RD057080",
    "location": "CD - ETG",
    "department": "CD - ETG",
    "driver_name": "KABIR ABBA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1484",
    "brand": "Electric",
    "model": "Car",
    "vin_sn": "LDP41B968RD067091",
    "engine_no": "LDP41B968RD067091",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "OECFIRS POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1492",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD4M0120062",
    "engine_no": "MR0BU8CD4M0120062",
    "location": "ECFIRS/ESCORT",
    "department": "ECFIRS/ESCORT",
    "driver_name": "ZAAC",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1493",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD4R0101907",
    "engine_no": "MR0BU8CD4R0101907",
    "location": "OEC",
    "department": "OEC",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1494",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD3S0134435",
    "engine_no": "MR0BU8CD3S0134435",
    "location": "OEC POOL",
    "department": "OEC POOL",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1495",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMABBBJ804158899",
    "engine_no": "JTMABBBJ804158899",
    "location": "OEC POOL",
    "department": "OEC POOL",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1496",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK4S3022828",
    "engine_no": "JTNA14CK4S3022828",
    "location": "FORMER-ECFIRS",
    "department": "FORMER-ECFIRS",
    "driver_name": "OEC POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1497",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CDXS0133878",
    "engine_no": "MR0BU8CDXS0133878",
    "location": "OEC POOL",
    "department": "OEC POOL IBADAN",
    "driver_name": "OEC POOL IBADAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS740",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ829485",
    "engine_no": "VF3DDNFPRDJ829485",
    "location": "DD - LT O&G NO26",
    "department": "LARGE TAX OIL & GAS",
    "driver_name": "YUSUF OTHMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS833/291FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903031539",
    "engine_no": "2ZRU528648",
    "location": "SSFMD POOL",
    "department": "SSFMD POOL",
    "driver_name": "SOP DIVISION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1150",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK2L3016257",
    "engine_no": "JTNBZ4HK2L3016257",
    "location": "MGT PROTOCOL",
    "department": "INTERVENTION WITH OECNRS",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS934",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE800008352",
    "engine_no": "2ZRV143299",
    "location": "",
    "department": "SS&FMD",
    "driver_name": "GREGORY ASUQUO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1436",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBX3FJ50K348995",
    "engine_no": "2TR-2570492",
    "location": "TEMPORARY ALLOCATION",
    "department": "ILLICIT FUNDS",
    "driver_name": "PROF AKINKOYE E. YEMI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1441",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU3FJXPK246546",
    "engine_no": "JTEBU3FJXPK246546",
    "location": "ECFIRS-SA SINGLE WINDOW",
    "department": "POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1488",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E3SA940635",
    "engine_no": "LS4ASE2E3SA940635",
    "location": "PA TO EC-FIRS DOMESTIC",
    "department": "PA TO EC-FIRS DOMESTIC",
    "driver_name": "GBENGA ADEBISI ABERE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1499",
    "brand": "Changan",
    "model": "Cs55 Plus Pro",
    "vin_sn": "LS4ASE2EXSA945217",
    "engine_no": "LS4ASE2EXSA945217",
    "location": "MGT POOL (AIRPORT PICKUPS & EVENTS)",
    "department": "MGT POOL(AIRPORT PICKUPS",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1500",
    "brand": "Changan",
    "model": "Cs55 Plus Pro",
    "vin_sn": "LS4ASE2E7TA941286",
    "engine_no": "LS4ASE2E7TA941286",
    "location": "MGT POOL (AIRPORT PICKUPS & EVENTS)",
    "department": "MGT POOL(AIRPORT PICKUPS",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1501",
    "brand": "Changan",
    "model": "Cs55 Plus Pro",
    "vin_sn": "LS4ASE2E2TA941227",
    "engine_no": "LS4ASE2E2TA941227",
    "location": "MGT POOL (AIRPORT PICKUPS & EVENTS)",
    "department": "MGT POOL(AIRPORT PICKUPS",
    "driver_name": "MGT PROTOCOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1502",
    "brand": "Dongfeng",
    "model": "S50",
    "vin_sn": "LGJF1FE0XPT421166",
    "engine_no": "LGJF1FE0XPT421166",
    "location": "AD-COMMUNICATION",
    "department": "CLD",
    "driver_name": "FRANK OGBOLE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1506",
    "brand": "Changan",
    "model": "Cs55 Plus Pro",
    "vin_sn": "LS4ASE2E7SA940220",
    "engine_no": "",
    "location": "DD- HCMD",
    "department": "HCMD",
    "driver_name": "SA'AD LAWAL SULEIMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1504",
    "brand": "Changan",
    "model": "Cs55 Plus Pro",
    "vin_sn": "LS4ASE2E4TA941939",
    "engine_no": "LS4ASE2E4TA941939",
    "location": "DD-PROCUREMENT",
    "department": "PROCUREMENT",
    "driver_name": "BABAGANA KARRAMA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1151",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z5NUOO6248",
    "engine_no": "L6T7722Z5NU006248",
    "location": "SCO IA",
    "department": "SCO IA",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS906",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ873988",
    "engine_no": "VF3DDNFPRDJ873988",
    "location": "STATE MONITOR-IMO GBTO",
    "department": "IMO GBTO",
    "driver_name": "ANELE LILIAN C.",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1073",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAKXJR881615",
    "engine_no": "NC02J014175",
    "location": "H-STO OKIGWE",
    "department": "STO OKIGWE",
    "driver_name": "ANTHONY CHUKWU M",
    "sco": "IA"
  },
  {
    "license_plate": "218FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903032612",
    "engine_no": "2ZRU560606",
    "location": "AG.SM-AWKA GBTO",
    "department": "AWKA GBTO",
    "driver_name": "COSMAS UZOKWE C.",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS360N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ655207",
    "engine_no": "VF3DDNFPRDJ655207",
    "location": "TC-ONITSHA MSTO",
    "department": "ONITSHA MSTO",
    "driver_name": "DARIA DANIEL",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS752",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808733",
    "engine_no": "VF3DDNFPRDJ808733",
    "location": "TC-AWKA MSTO",
    "department": "AWKA MSTO",
    "driver_name": "CHARLES NMERIBE",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS834/293FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903029368",
    "engine_no": "2ZRU469656",
    "location": "TC-OWERRI MSTO",
    "department": "WARRI MSTO",
    "driver_name": "EZE CHIMAOBI",
    "sco": "IA"
  },
  {
    "license_plate": "RB738FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "1994941",
    "engine_no": "3114876",
    "location": "STAMP DUTIES OWERRI",
    "department": "OWERRI STAMP DUTIES",
    "driver_name": "GEORGE CHUKE",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS493",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703028929",
    "engine_no": "2ZRU458269",
    "location": "THE VEHICLE IS BURNT",
    "department": "THE VEHICLE IS BURNT",
    "driver_name": "MICHAEL EGBUZOBI-RETIRED",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1071",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK7HR872221",
    "engine_no": "NC02H047235",
    "location": "H-MSTO NKPOR",
    "department": "MSTO NKPOR",
    "driver_name": "NJOKU CHINYERE",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS239",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403009948",
    "engine_no": "2ZRUO 93210",
    "location": "OWERRI MSTO",
    "department": "OWERRI MSTO",
    "driver_name": "EMEKA ANTHONY NZEAKOR",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS216",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P106041512",
    "engine_no": "2TR-FE 8135423",
    "location": "ONITSHA MSTO",
    "department": "ONITSHA MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS219",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P806041507",
    "engine_no": "8135595",
    "location": "ORLU MSTO",
    "department": "ORLU MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS328",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 308017659",
    "engine_no": "8224148",
    "location": "AWKA MSTO POOL",
    "department": "AWKA MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS329",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 008017635",
    "engine_no": "8223831",
    "location": "NNEWI IMSTO",
    "department": "NNEWI IMSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS563",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508017792",
    "engine_no": "8225055",
    "location": "OWERRI MSTO",
    "department": "OWERRI MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS568",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308017709",
    "engine_no": "8224576",
    "location": "NNEWI MSTO",
    "department": "NNEWI MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS579",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708022119",
    "engine_no": "8275477",
    "location": "ONITSHA MSTO",
    "department": "ONITSHA MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS581",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808022193",
    "engine_no": "8276538",
    "location": "AWKA MSTO",
    "department": "AWKA MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS662/83FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "HQ+728:751",
    "engine_no": "8333879",
    "location": "OWERRI MSTO",
    "department": "OWERRI MSTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "247FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08035267",
    "engine_no": "2TR8503726",
    "location": "GBTO IMO",
    "department": "OWERRI GBTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "310FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608036092",
    "engine_no": "2TR8517162",
    "location": "GBTO ANAMBRA",
    "department": "AWKA GBTO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS870",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08045071",
    "engine_no": "2TR9003025",
    "location": "SCO IA",
    "department": "SCO IA",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1006",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02PX70016264",
    "engine_no": "JTFJX02PX70016264",
    "location": "SCO-IA",
    "department": "IMO&ANAMBRA SCO",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1040",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P400063361",
    "engine_no": "JTFHX02P400063361",
    "location": "MSTA ANAMBRA",
    "department": "MSTA ANAMBRA",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1050",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH2000073594",
    "engine_no": "TRH2000073594",
    "location": "LTO AWKA",
    "department": "LTO AWKA",
    "driver_name": "",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS741/101FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603027111",
    "engine_no": "2ZRU420733",
    "location": "TC-LTO AWKA",
    "department": "TC-LTO AWKA",
    "driver_name": "UKAHA OKEREKE",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1490/1245",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP5S6030891",
    "engine_no": "JTGHN9CP5S6030891",
    "location": "LTO",
    "department": "POOL",
    "driver_name": "POOL AWKA",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS1450",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG9PN230001",
    "engine_no": "LNLG32AG9PN230001",
    "location": "DEBT MGT DEPARTMENT",
    "department": "DEBT MGT DEPARTMENT",
    "driver_name": "DEBT MGT DEPARTMENT",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS686/93FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108027753",
    "engine_no": "2TR8345212",
    "location": "GARKI MSTO",
    "department": "GARKI MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS688/72FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608027800",
    "engine_no": "2TR8361525",
    "location": "MTO ABUJA",
    "department": "MTO ABUJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS689/64FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508027755",
    "engine_no": "2TR8369070",
    "location": "GWAGWALADA MSTO",
    "department": "GWAGWALADA MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS824/46FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808031492",
    "engine_no": "2ZRU8447338",
    "location": "MAITAMA MSTO",
    "department": "MAITAMA MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS830/FIRS288",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208031388",
    "engine_no": "2TR8445510",
    "location": "GWARIMPA MSTA",
    "department": "GWARIMPA MSTA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS845/ FIRS 495",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708030348",
    "engine_no": "2TR8430604",
    "location": "WUSE 3 STA",
    "department": "WUSE 3 STA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "202FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908035289",
    "engine_no": "2TR8503935",
    "location": "GARKI Il SMTA",
    "department": "GARKI Il SMTA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "204FIRS/ (212FIRS)",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408035295",
    "engine_no": "2TR8504025",
    "location": "GBA ABIA",
    "department": "GBA ABIA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "309FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508036214",
    "engine_no": "2TR8518963",
    "location": "MTO ABUJA",
    "department": "MTO ABUJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS675",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908038757",
    "engine_no": "2TR-8575215",
    "location": "KUBWA MSTO",
    "department": "KUBWA MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS676",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708038756",
    "engine_no": "2TR-8574832",
    "location": "GBTO ABUJA",
    "department": "GBTO ABUJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS786",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908044395",
    "engine_no": "2TR8712532",
    "location": "MTA 2",
    "department": "MTA 2",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS622N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP0L6006421",
    "engine_no": "6006421",
    "location": "TID NORTHERN DIV",
    "department": "TID NORTHERN DIV",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1035",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P550001472",
    "engine_no": "JTGJX02P550001472",
    "location": "MSTA KUBWA",
    "department": "MSTA KUBWA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1027",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJXO2P200060217",
    "engine_no": "JTFJXO2P200060217",
    "location": "MSTA MAITAMA",
    "department": "MSTA MAITAMA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1111",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ9NY502211",
    "engine_no": "VR3F3EGZ9NY502211",
    "location": "DD-LTA ABUJA",
    "department": "LTA ABUJA",
    "driver_name": "SALISU SAA'D",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS759",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ808715",
    "engine_no": "VF3DDNFPRDJ808715",
    "location": "ETD - NORTH",
    "department": "EMERGING TAX DEPARTMENT",
    "driver_name": "UDOCHUKWU AHAWIE",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS673/81FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026559",
    "engine_no": "2TR8353614",
    "location": "MSTA GWAGWALADA",
    "department": "MSTA GWAGWALADA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1431",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP4P6022286",
    "engine_no": "JTGHN9CP4P6022286",
    "location": "MTA, GARKI POOL",
    "department": "GARKI MTA POOL",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1445",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AGXPN230010",
    "engine_no": "LNLG32AGXPN230010",
    "location": "SMALL TAXPAYERS DEPT",
    "department": "SMALL TAXPAYERS DEPT",
    "driver_name": "NORTH",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1448",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG6PN230019",
    "engine_no": "LNLG32AG6PN230019",
    "location": "LUGBE MSTA",
    "department": "LUGBE MSTA",
    "driver_name": "LUGBE MSTA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1453",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG6PN230022",
    "engine_no": "LNLG32AG6PN230022",
    "location": "GARKI 1 SMTA",
    "department": "GARKI 1 SMTA",
    "driver_name": "GARKI 1 SMTA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1048",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH2000053789",
    "engine_no": "TRH2000053789",
    "location": "CENTRAL SMALL TAX AUDIT",
    "department": "STD",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1573",
    "brand": "Dongfeng",
    "model": "T5L",
    "vin_sn": "LMXA14AFXSZ376869",
    "engine_no": "LMXA14AFXSZ376869",
    "location": "DD-GAWALADA ETO",
    "department": "ETO",
    "driver_name": "BUNSHAK SIMON EMMANUEL",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1539",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE01RT358431",
    "engine_no": "LGJF1FE01RT358431",
    "location": "AD-GARKI ETA",
    "department": "AD-GARKI ETO",
    "driver_name": "ANULUNKO AUGUSTINA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1531",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT358425",
    "engine_no": "LGJF1FE06RT358425",
    "location": "TC, KUBWA ETO",
    "department": "TC-KUBWA ETO",
    "driver_name": "RAJI MOMOH ABIODUN",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1521",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT396513",
    "engine_no": "LGJF1FE06RT396513",
    "location": "TC/ LUGBE ETO",
    "department": "TC-LUGBE ETO",
    "driver_name": "ARIKAWE OLADIGBO VERONICA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1516",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02RT396492",
    "engine_no": "LGJF1FE02RT396492",
    "location": "TC-GARKI ETO",
    "department": "TC-GARKI ETO",
    "driver_name": "AJOGE JABEMI YAKUBU",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1515",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT396484",
    "engine_no": "LGJF1FE03RT396484",
    "location": "TC/ GWARIMPA ETO",
    "department": "GWARIMPA ETO",
    "driver_name": "OKAFOR FRANCISCA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1514",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT358421",
    "engine_no": "LGJF1FE09RT358421",
    "location": "TC/GWARIMPA AUDIT",
    "department": "GWARIMPA AUDIT",
    "driver_name": "MARIAN ROBERT AGABA",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS1203",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z4NX404783",
    "engine_no": "3G15TD-5600011",
    "location": "DD-LEGAL",
    "department": "LPD",
    "driver_name": "FATIMA BELLO",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS840/ FIRS 487",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003029369",
    "engine_no": "2ZRU466301",
    "location": "AD-FKN SCO",
    "department": "SCO FKN",
    "driver_name": "HAMEED TAJUDEEN ADEMOLA",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS815",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833870",
    "engine_no": "VF3DDNFPRDJ833870",
    "location": "DD-VAT COORD FCT",
    "department": "SCO FKN",
    "driver_name": "MECHANIC - ATANDA",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS685/170FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208027762",
    "engine_no": "2TR8360184",
    "location": "CENTRAL AREA MSTO",
    "department": "CENTRAL AREA MSTO",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS1244",
    "brand": "Innoson",
    "model": "Bus",
    "vin_sn": "LL3AAAAC1JA000101",
    "engine_no": "4RB-275981A",
    "location": "WUSE MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS81",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "96927",
    "engine_no": "1139305",
    "location": "FCT RDMO",
    "department": "SSFMD ARM-INSURANCE",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS748",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830615",
    "engine_no": "VF3DDNFPRDJ830615",
    "location": "TC-GOMBE MSTO",
    "department": "GOMBE MSTO",
    "driver_name": "APOLLO GARBA",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS306",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003015889",
    "engine_no": "2ZRU140068",
    "location": "SM-GOMBE GBTO",
    "department": "SM-GOMBE GBTO",
    "driver_name": "KURGA A. WASA",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS537",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56EX03019158",
    "engine_no": "2ZRU210020",
    "location": "TC- JALINGO MSTO",
    "department": "JALINGO MSTO",
    "driver_name": "UGBABE STEPHEN",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS398",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208017751",
    "engine_no": "2TR8224813",
    "location": "YOLA MSTO",
    "department": "YOLA MSTO",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS683/66FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308026068",
    "engine_no": "2TR8345927",
    "location": "YOLA MSTO",
    "department": "YOLA MSTO",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS690/63FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608027795",
    "engine_no": "2TR8369891",
    "location": "TARABA GBTO",
    "department": "TARABA GBTO",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "238FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108034704",
    "engine_no": "2TR8496996",
    "location": "GBTO GOMBE",
    "department": "GBTO GOMBE",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "335FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003034880",
    "engine_no": "2ZRU667135",
    "location": "TC-ILORIN MSTO",
    "department": "ILORIN MSTO",
    "driver_name": "ADAMA ISA",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS914",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ856075",
    "engine_no": "VF3DDNFPRDJ856075",
    "location": "EKITI GBO",
    "department": "EKITI GBO",
    "driver_name": "ADEJUWON AYODELE",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS1067",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK9HR872334",
    "engine_no": "NC02H047123",
    "location": "HEAD-STO OFFA",
    "department": "STO OFFA",
    "driver_name": "GBENGA ALFRED",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS907",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ856076",
    "engine_no": "VF3DDNFPRDJ856076",
    "location": "TC ORE SMTO",
    "department": "ORE SMTO",
    "driver_name": "OWA ESTHER",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS745",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830605",
    "engine_no": "VF3DDNFPRDJ830605",
    "location": "TC-OWO MSTO",
    "department": "OWO MSTO",
    "driver_name": "OLAREWAJU MATHEW",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS741",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ796798",
    "engine_no": "VF3DDNFPRDJ796798",
    "location": "KWARA GBTO",
    "department": "KWARA GBTO",
    "driver_name": "FATIMA OMAR",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS538",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E903018258",
    "engine_no": "2RU 198056",
    "location": "ILORIN MSTO POOL",
    "department": "ILORIN MSTO",
    "driver_name": "FORMERLY ADAMA ISA (IN NEED OF REPAIRS)",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS941",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586202",
    "engine_no": "VF3DDNFPRGJ586202",
    "location": "STAMP DUTIES ILORIN",
    "department": "STAMP DUTIES ILORIN",
    "driver_name": "MARGARET ANIKOH",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS747",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830598",
    "engine_no": "VF3DDNFPRDJ830598",
    "location": "TC-ADO-EKITI MSTO",
    "department": "ADO-EKITI MSTO",
    "driver_name": "PATRICK AKINSEYE",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS226",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303009990",
    "engine_no": "2ZRU090825",
    "location": "AD-MTO IBADAN",
    "department": "MTO IBADAN",
    "driver_name": "KINGSLEY BINITE",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS236",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P506043554",
    "engine_no": "2TR-FE8141016",
    "location": "AKURE MSTO",
    "department": "AKURE MSTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS238",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JIT-SX22P106045124",
    "engine_no": "8144415",
    "location": "ILORIN MSTO POOL",
    "department": "ILORIN MSTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS218",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P306041706",
    "engine_no": "2TR-FE8133994",
    "location": "ADO-EKITI MSTO POOL",
    "department": "ADO-EKITI MSTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS365",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P506073735",
    "engine_no": "2TR8235092",
    "location": "ORE MSTO POOL",
    "department": "ORE MSTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS709/157FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208026997",
    "engine_no": "2TR8346024",
    "location": "KEO SCO",
    "department": "KEO SCO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "206FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208035120",
    "engine_no": "2TR8501948",
    "location": "GBTO EKITI POOL",
    "department": "EKITI GBTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "324FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708036215",
    "engine_no": "2TR8508490",
    "location": "ONDO GBTO POOL",
    "department": "ONDO GBTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "326FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08036208",
    "engine_no": "2TR8518928",
    "location": "KWARA GBTO POOL",
    "department": "KWARA GBTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "354FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808035798",
    "engine_no": "2TR8512271",
    "location": "OWO MSTO",
    "department": "OWO MSTO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS601N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P9A8016884",
    "engine_no": "JTGRX12P9A8016884",
    "location": "SCO-KEO",
    "department": "KEO SCO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS1041",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02PX95001284",
    "engine_no": "JTFHX02PX95001284",
    "location": "ILORIN STAMP DUTY",
    "department": "ILORIN STAMP DUTY",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS889",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G808030508",
    "engine_no": "2TR8826532",
    "location": "SCO/EKITI",
    "department": "SCO KEO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS1451",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AGXPN230024",
    "engine_no": "LNLG32AGXPN230024",
    "location": "DEBT MGT DEPARTMENT",
    "department": "DEBT MGT DEPARTMENT",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "318FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108036095",
    "engine_no": "2TR8517239",
    "location": "GBTO ADAMAWA",
    "department": "GBTO ADAMAWA",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS1021",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P300051736",
    "engine_no": "JTFJX02P300051736",
    "location": "GOMBE MSTO",
    "department": "GOMBE MSTO",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS1023",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P405033989",
    "engine_no": "JTFJX02P405033989",
    "location": "DEBT MANAGEMENT & ENFORCEMENT",
    "department": "DEBT MANAGEMENT & ENFORCEMENT GOMBE",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS1215",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z1NU005229",
    "engine_no": "3G15TD-2502707",
    "location": "SCO-JKK",
    "department": "MGT POOL",
    "driver_name": "STATE COORDINATION",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1315",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR7RA960756",
    "engine_no": "LS5A3AKR7RA960756",
    "location": "DD/STATE MONITOR",
    "department": "DD/STATE MONITOR",
    "driver_name": "AISHA L.WUSHISHI",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS750/125FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903026745",
    "engine_no": "2ZRU414799",
    "location": "MTO KANO",
    "department": "MTO KANO",
    "driver_name": "SAMINU SALU JIBIA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS976",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ612234",
    "engine_no": "VF3DDNFPRGJ612234",
    "location": "GBTO KANO",
    "department": "KANO GBTO",
    "driver_name": "FATIHU UMAR",
    "sco": "JKK"
  },
  {
    "license_plate": "RB356FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "RZH1147102730",
    "engine_no": "RZH114LBRMRS",
    "location": "FUNTUA MSTO",
    "department": "FUNTUA MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS619",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P1A8019357",
    "engine_no": "2TR8239852",
    "location": "LTO KANO",
    "department": "LTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS630",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P6080 19244",
    "engine_no": "8238439",
    "location": "DUTSE MSTO",
    "department": "DUTSE MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS706/56FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108027168",
    "engine_no": "2TR8360251",
    "location": "KANO 1 MSTO POOL",
    "department": "KANO 1 MSTO POOL",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "207FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008035293",
    "engine_no": "2TR8503965",
    "location": "GBTO KATSINA",
    "department": "GBTO KATSINA",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "241FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008035262",
    "engine_no": "2TR8502636",
    "location": "GBTO KANO",
    "department": "GBTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "316FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608036223",
    "engine_no": "2TR8518642",
    "location": "GBTO DUTSE",
    "department": "GBTO DUTSE",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS670",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G508026416",
    "engine_no": "2TR-7737487",
    "location": "SCO JKK",
    "department": "SCO JKK",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS683",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308038558",
    "engine_no": "2TR-8565627",
    "location": "MTO KANO",
    "department": "MTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS763",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508044393",
    "engine_no": "2TR8712865",
    "location": "DEBT MANAGEMENT NORTH WEST (KANO)",
    "department": "DMO WEST",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS782",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508044474",
    "engine_no": "2TR8714580",
    "location": "MSTA 2 KANO",
    "department": "MSTA 2 KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS783",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908044493",
    "engine_no": "2TR8706989",
    "location": "MSTA 1",
    "department": "MSTA 1",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS860",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518204023958",
    "engine_no": "2TR8716270",
    "location": "LTO KANO",
    "department": "LTO KANO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1572",
    "brand": "Dongfeng",
    "model": "T5L",
    "vin_sn": "LMXA14AF0SZ376878",
    "engine_no": "LMXA14AF0SZ376878",
    "location": "DD-MTA KANO",
    "department": "DD-MTA KANO",
    "driver_name": "ABDULKADIR YUNUSA",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS1498",
    "brand": "Changan",
    "model": "X7",
    "vin_sn": "LS4ASE2E1TA992475",
    "engine_no": "LS4ASE2E1TA992475",
    "location": "DD-LTA KANO",
    "department": "LTA KANO",
    "driver_name": "ALIYU YUSUF",
    "sco": "KANO"
  },
  {
    "license_plate": "FIRS44",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR220B000268193",
    "engine_no": "2713320",
    "location": "NIGER GBA",
    "department": "NIGER GBA",
    "driver_name": "MUSA ALIYU",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS1410",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "LVGBC74K79G241234",
    "engine_no": "LF57888A25G",
    "location": "OOO REGIONAL ADMINISTRATOR",
    "department": "OOO REGIONAL ADMINISTRATOR",
    "driver_name": "OLUWATOBI ABIOLA",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1240",
    "brand": "Innoson",
    "model": "Bus",
    "vin_sn": "LL3AAAAC1JA000124",
    "engine_no": "4RB-275945A",
    "location": "PRESS TEAM-COMM",
    "department": "PRESS TEAM / COMM",
    "driver_name": "PRESS TEAM",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1209",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z2MW005068",
    "engine_no": "4G15-4907320",
    "location": "ETO ISOLO",
    "department": "ETO ISOLO",
    "driver_name": "IDOWU ADEKUNLE",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1224",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX0ZP805049595",
    "engine_no": "JTFJX0ZP805049595",
    "location": "ISOLO MSTO",
    "department": "MSTO",
    "driver_name": "ISOLO MSTO",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1242",
    "brand": "Innoson",
    "model": "Bus",
    "vin_sn": "LL3AAAAC1JA000084",
    "engine_no": "4RB-275986A",
    "location": "ORILE MSTO",
    "department": "MSTO",
    "driver_name": "LAGOS",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1439",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMABJBJ9P4065526",
    "engine_no": "JTMABJBJ9P4065526",
    "location": "OFFICE OF CHIEF OF STAFF",
    "department": "POOL",
    "driver_name": "OECFIRS POOL LAGOS",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1454",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG2PN230020",
    "engine_no": "LNLG32AG2PN230020",
    "location": "LTA, FINANCIAL LAGOS",
    "department": "LTA, FINANCIALS LAGOS",
    "driver_name": "",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1474",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD8R0103093",
    "engine_no": "MR0BU8CD8R0103093",
    "location": "SA-PROTOCOL TO ECFIRS",
    "department": "SA-PROTOCOL TO ECFIRS",
    "driver_name": "ADETOYESE IPADEOLA",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1485/851",
    "brand": "Changan",
    "model": "X7",
    "vin_sn": "LS4ASE2E9TA992451",
    "engine_no": "LS4ASE2E9TA992451",
    "location": "DD- LTA",
    "department": "LTA LAGOS",
    "driver_name": "ADEPOJU AJAYI",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1486/589",
    "brand": "Changan",
    "model": "X7",
    "vin_sn": "LS4ASE2E6TA992438",
    "engine_no": "LS4ASE2E6TA992438",
    "location": "DD-LTA OIL & GAS",
    "department": "DD LARGE TAX AUDIT OIL & GAS",
    "driver_name": "HADOMEH B. ONYEKA",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1487/615",
    "brand": "Changan",
    "model": "X7",
    "vin_sn": "LS4ASE2E1TA992492",
    "engine_no": "LS4ASE2E1TA992492",
    "location": "DD-LTO CONSTRUCTION & LOG.",
    "department": "LTO CONST. & LOG.",
    "driver_name": "DIAMOND TIETIE",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1489/645",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP7S6030617",
    "engine_no": "JTGHN9CP7S6030617",
    "location": "OCD-LTG",
    "department": "POOL",
    "driver_name": "",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1491/1162",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE5SD914847",
    "engine_no": "LS5A2ASE5SD914847",
    "location": "AD-OCD-LTG",
    "department": "OCD-LTG",
    "driver_name": "JAYNE OKPALA",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS1503",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAA9AJ30K005674",
    "engine_no": "JTEAA9AJ30K005674",
    "location": "D-IAD",
    "department": "D-IAD",
    "driver_name": "JOEl SABO",
    "sco": "HQ"
  },
  {
    "license_plate": "332FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103034872",
    "engine_no": "2ZRU676023",
    "location": "AD-ETA",
    "department": "AD-ETA",
    "driver_name": "IDRIS HAKEEM OLANIYI",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS710",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE000002447",
    "engine_no": "2ZRU-777252",
    "location": "DIRECTOR SOUTH WEST MTO",
    "department": "SOUTH WEST MTO",
    "driver_name": "ODUNSI KEHINDE OLA",
    "sco": "LAGOS"
  },
  {
    "license_plate": "FIRS849",
    "brand": "Kia",
    "model": "Mohave",
    "vin_sn": "KNAKN811DF5133619",
    "engine_no": "G6DAES235865",
    "location": "DD-TID",
    "department": "TAX INVESTIGATION DEPARTMENT",
    "driver_name": "ABDUL YAHAYA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1269",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z7PX410533",
    "engine_no": "N6BA5613081",
    "location": "DD-ITD",
    "department": "INTERNATIONAL TAX DEPARTMENT",
    "driver_name": "ABDULLAHI ALIYU",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS736/96FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203027364",
    "engine_no": "2ZRU427153",
    "location": "TC-ONIKAN MSTO",
    "department": "TC-ONIKAN MSTO",
    "driver_name": "ADEYEMO STEPHEN ADEKUNLE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1176",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z0MW036111",
    "engine_no": "L6T7824Z0MW036111",
    "location": "AD-LTA DOWNSTREAM",
    "department": "LTA (O&G) DOWN STREAM LAGOS",
    "driver_name": "ADUMATI I.A.",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS964",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ604928",
    "engine_no": "VF3DDNFPRGJ604928",
    "location": "DD-IKOYOI 1 MSTO",
    "department": "DD-IKOYOI 1 MSTO",
    "driver_name": "AHAAIWE U UCHENDU",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS408N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE5F5247713",
    "engine_no": "3ZRX542897",
    "location": "DD-ITD",
    "department": "ITD",
    "driver_name": "AKANNI MONISOLA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS959",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ599437",
    "engine_no": "VF3DDNFPRGJ599437",
    "location": "AD-MTA LI",
    "department": "MTA LI",
    "driver_name": "ALAO ASIMIYU AKINLOYE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1069",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAKJTR880859",
    "engine_no": "NC02H058251",
    "location": "AD-LARGE TAX AUDIT",
    "department": "AD/LTA (O&G) LAGOS",
    "driver_name": "AMINU O.R.",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1196",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z3MW036104",
    "engine_no": "L6T7824Z3MW036104",
    "location": "AD- L T O (O & G)",
    "department": "LTA (O&G) UPSTREAM LAGOS",
    "driver_name": "ANIKO EMMANUEL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1199",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z5MW009051",
    "engine_no": "L6T7824Z5MW009051",
    "location": "AD-LTA OIL&GAS DOWNST",
    "department": "LTA (O&G) DOWN STREAM LAGOS",
    "driver_name": "ASONYE C.K",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS254",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703009789",
    "engine_no": "2ZRU090969",
    "location": "AD-OIL &GAS DOWN STREAM- ITD",
    "department": "ITD",
    "driver_name": "AYENI OLUKEMI TAIWO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS712",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE600002517",
    "engine_no": "2ZRU-811211",
    "location": "AD-SPECIAL TAX AUDIT",
    "department": "STA",
    "driver_name": "BABAKURA MUSTAPHA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS892",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL006970",
    "engine_no": "VF38D5FCAGL006970",
    "location": "DD-LI SCO",
    "department": "LI SCO",
    "driver_name": "BADMUS AMINAT",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1078",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAKXHR879325",
    "engine_no": "NC02H051372",
    "location": "TC-EPE MSTO",
    "department": "EPE MSTO",
    "driver_name": "CHINEDU S. ADIRIJE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS432N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL030396",
    "engine_no": "GL030396",
    "location": "AD-AGUDA MSTO",
    "department": "AGUDA MSTO",
    "driver_name": "CLARA KIKELOMO LAWAL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "220FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403032582",
    "engine_no": "2ZRU558370",
    "location": "AJAH MSTA",
    "department": "LTA",
    "driver_name": "NWOSU IFUNAYA CHINELO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS833",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ831691",
    "engine_no": "VF3DDNFPRDJ831691",
    "location": "STAMP DUTIES LAGOS ISLAND",
    "department": "STAMP DUTIES LAGOS ISLAND",
    "driver_name": "COMMISSIONER",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS05Z",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU9FJ2P5099799",
    "engine_no": "JTEBU9FJ2P5099799",
    "location": "ECFIRS/ESCORT LAGOS",
    "department": "OECFIRS",
    "driver_name": "ECFIRS",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1300",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD3M0119288",
    "engine_no": "1GR-H268381",
    "location": "ECFIRS/ESCORT LAGOS",
    "department": "ECFIRS LAGOS",
    "driver_name": "ECFIRS",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1270",
    "brand": "Changan",
    "model": "Eado Dt",
    "vin_sn": "LS5A2AGE7PD910153",
    "engine_no": "NC9BP000847",
    "location": "AD-ITD",
    "department": "INTERNATIONAL TAX DEPARTMENT",
    "driver_name": "EDWARD OKAFOR",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS752/116FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903026955",
    "engine_no": "2ZRU418402",
    "location": "ADT-LTO NON-OIL(FINANCIAL)",
    "department": "LTO",
    "driver_name": "EZECHI PHINA THELMA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1195",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824ZXMW036116",
    "engine_no": "L6T7824ZXMW036116",
    "location": "AD-LTA(O & G)DOWNSTREAM",
    "department": "AD-LTA(O & G)DOWNSTREAM",
    "driver_name": "GIWA H.O.",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS616N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL014070",
    "engine_no": "VF38D5GYAHL014070",
    "location": "DD/LARGE TAX DEPARTMENT",
    "department": "LTA OIL & GAS SERVICES LAGOS",
    "driver_name": "HASSAN ABUBAKAR",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS739",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ831690",
    "engine_no": "VF3DDNFPRDJ831690",
    "location": "TC-MTA 2",
    "department": "FESTAC MSTO",
    "driver_name": "IGWILO ROSE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS920",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ852644",
    "engine_no": "VF3DDNFPRDJ852644",
    "location": "AD-SPECIAL TAX AUDIT",
    "department": "AD-SPECIAL TAX AUDIT",
    "driver_name": "JIBRIN AUDU",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1158",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z8NX404804",
    "engine_no": "JLH-3G15TDM9GA5605991",
    "location": "DD-LI",
    "department": "LAGOS",
    "driver_name": "KELIN OBAITAN",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS981",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL011659",
    "engine_no": "VF38D5FCAGL011659",
    "location": "DD-SPECIAL TAX AUDIT",
    "department": "SPECIAL TAX AUDIT",
    "driver_name": "KSENIA KOFO ABAYOMI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "296FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103034466",
    "engine_no": "2ZRU652722",
    "location": "AD-LTA LAGOS",
    "department": "LI SCO",
    "driver_name": "KULEPA OLASUMBO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS163",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003009851",
    "engine_no": "2ZRU091657",
    "location": "RETRIEVED BACK TO FSSMD POOL",
    "department": "RETRIEVED BACK TO FSSMD",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1143",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE01MT454715",
    "engine_no": "4A92SISX578",
    "location": "AD/TECHNICAL DEPT",
    "department": "TECHNICAL DEPT",
    "driver_name": "OLAPOSI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS03",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBE40K103097061",
    "engine_no": "2577054",
    "location": "FLEET POOL LI",
    "department": "LI SCO",
    "driver_name": "MGT PROTOCOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS811/25FIRS (04FIRS)",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBF4FK903006591",
    "engine_no": "2AR0607409",
    "location": "MINISTERS USE IN LAGOS",
    "department": "MINISTERS USE IN LAGOS",
    "driver_name": "MGT PROTOCOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS384N",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "6TIBF9FK7GX642947",
    "engine_no": "2ARU324462",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1152",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z3NUOO6216",
    "engine_no": "L6T7722Z3NU006216",
    "location": "SCO-LI",
    "department": "SCO LAGOS ISLAND",
    "driver_name": "MGT PROTOCOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS01D",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEBU3FJ6MK201664",
    "engine_no": "1GR-FE 3956ML",
    "location": "OEC/FIRS POOL LAGOS",
    "department": "OECFIRS",
    "driver_name": "OEC FIRS POOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1141",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02MT454707",
    "engine_no": "4A92SISX530",
    "location": "AD/TAX INVESTIGATION",
    "department": "TAX INVESTIGATION DEPARTMENT",
    "driver_name": "MUSTAPHA B.J",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS945",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586207",
    "engine_no": "VF3DDNFPRGJ586207",
    "location": "AD-TAX INVESTGN DEPT",
    "department": "TID LI",
    "driver_name": "NGOZI INOMA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS162",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC38EX03009887",
    "engine_no": "2ZRU091707",
    "location": "LTA O&G",
    "department": "LI SCO",
    "driver_name": "AMINU OLUSHOLA RICHARD",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS894",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL006344",
    "engine_no": "VF38D5FCAGL006344",
    "location": "DD/LARGE TAX DEPT (O & G)",
    "department": "DD/LARGE TAX DEPT (O & G)",
    "driver_name": "SHODIPO S.A.",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS963",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ599434",
    "engine_no": "VF3DDNFPRGJ599434",
    "location": "LI REGIONAL TAX AUDIT LAGOS",
    "department": "RETRIEVED",
    "driver_name": "BUNU ABUBAKAR UMAR",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS939",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ595818",
    "engine_no": "VF3DDNFPRGJ595818",
    "location": "DD-TAX INVESTIGATION DEPT. LAGOS",
    "department": "TID LI",
    "driver_name": "OBASI MBA OKOKO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS944",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586194",
    "engine_no": "VF3DDNFPRGJ586194",
    "location": "AD-VAT",
    "department": "VAT",
    "driver_name": "OBIAJULU CHIZOBA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS599N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MROFX22G2E1408577",
    "engine_no": "MROFX22G2E1408577",
    "location": "OECFIRS LAGOS",
    "department": "OECFIRS",
    "driver_name": "OECFIRS POOL",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS414N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE3F5246446",
    "engine_no": "3ZRX536719",
    "location": "D-LTD O&G",
    "department": "LTD OIL & GAS",
    "driver_name": "EHIGIEGBA ABIONA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS526",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E703015861",
    "engine_no": "2ZRU143143",
    "location": "AD-ITD",
    "department": "ITD",
    "driver_name": "OKAFOR EDWARD ONYEKA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1174",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z6MW036128",
    "engine_no": "L6T7824Z6MW036128",
    "location": "AD -L T O (O & G)",
    "department": "LTA (O&G) UPSTREAM LAGOS",
    "driver_name": "OKON E. P",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1197",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z6MW306095",
    "engine_no": "L6T7824Z6MW306095",
    "location": "AD-LARGE TAX AUDIT",
    "department": "LTA (O&G) DOWN STREAM LAGOS",
    "driver_name": "OLABANJI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1142",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06MT454709",
    "engine_no": "4A92SISX534",
    "location": "AD-TAX INVESTIGATION",
    "department": "TAX INVESTIGATION DEPARTMENT",
    "driver_name": "OLABIYI A.ABISOLA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS961",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586201",
    "engine_no": "VF3DDNFPRGJ586201",
    "location": "AD-SCO LI",
    "department": "AD-SCO LI",
    "driver_name": "MRS OLA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS890",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL008686",
    "engine_no": "VF38D5FCAGL008686",
    "location": "DD-LTO",
    "department": "LTO",
    "driver_name": "OLANIYI OTIVBO EHI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1272",
    "brand": "Changan",
    "model": "Eado Dt",
    "vin_sn": "LS5A2AGE9ND000663",
    "engine_no": "MC9BP004097",
    "location": "AD-ITD",
    "department": "INTERNATIONAL TAX DEPARTMENT",
    "driver_name": "OLUWOLE ONI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS769/130FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303027762",
    "engine_no": "2ZRU437941",
    "location": "TC LTA NON-OIL (FINANCIAL)",
    "department": "LTA NON-OIL",
    "driver_name": "OREBAJO ADEMOLA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS817/37FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903030956",
    "engine_no": "2ZRU504713",
    "location": "TC-BROADSTREET MSTO",
    "department": "LI SCO",
    "driver_name": "OSUNWA NGOZI DOROTHY",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS942",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ603100",
    "engine_no": "VF3DDNFPRGJ603100",
    "location": "AD-MTA LAGOS",
    "department": "MTA LI",
    "driver_name": "OTSE CLEMENT FAVOUR",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS686",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE700001277",
    "engine_no": "2ZRU-791502",
    "location": "AD/ TC, IKOYI MSTO",
    "department": "SCO",
    "driver_name": "AGBO AMEH",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1397",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP6P6018188",
    "engine_no": "JTGHN9CP6P6018188",
    "location": "OECFIRS POOL,LAGOS",
    "department": "OECFIRS POOL LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1399",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8506510108",
    "engine_no": "JTGAKAB8506510108",
    "location": "FIRS/STAFF BUS",
    "department": "LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1400",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8206510101",
    "engine_no": "JTGAKAB8206510101",
    "location": "FIRS/STAFF BUS",
    "department": "LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB531FG",
    "brand": "Peugeot",
    "model": "504",
    "vin_sn": "61533630",
    "engine_no": "61533630",
    "location": "REG OFFICE Parked in Ilupeju",
    "department": "SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB843FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "264507",
    "engine_no": "2688211",
    "location": "OIL & GAS",
    "department": "OIL & GAS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB893FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2904426",
    "engine_no": "EX00291478",
    "location": "SC LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB841FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTESX02P000007418",
    "engine_no": "2TR-FF-2694MR",
    "location": "SC LI / REG. ACCOUNTANY",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB885FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTPJX02P205006242",
    "engine_no": "435384",
    "location": "AJAH MSTO",
    "department": "AJAH MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS187",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E303009925",
    "engine_no": "2ZRUO8270",
    "location": "AJA MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS197",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06041654",
    "engine_no": "8135934",
    "location": "FLEET POOL LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS199",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P306041365",
    "engine_no": "8135049",
    "location": "FLEET POOL LI",
    "department": "LAGOS ISLAN",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS259",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E103009874",
    "engine_no": "2ZRU09282",
    "location": "LI SCO - FACILITY",
    "department": "LI SCO - FACILITY",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS355",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2ZE1427014908",
    "engine_no": "IZZA215082",
    "location": "LI SCO POOL",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS377",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008017814",
    "engine_no": "2TR 8225556",
    "location": "VI MSTO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS397",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308017810",
    "engine_no": "2TR8225494",
    "location": "ENFORCEMENT LAGOS",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS399",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12708017907",
    "engine_no": "2TR8225361",
    "location": "OIL AND GAS AUDIT",
    "department": "OIL AND GAS AUDIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS400",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308017677",
    "engine_no": "2TR82242110",
    "location": "TAX AUDIT LI",
    "department": "TAX AUDIT LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS402",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108017675",
    "engine_no": "2TR8224264",
    "location": "SURULERE/MUSHIN STAFF BUS (SC LI)",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS588",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518004006088",
    "engine_no": "8284820",
    "location": "MOWE STAFFBUS (S/C L/I)",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS591",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518X04006079",
    "engine_no": "8284656",
    "location": "FLEET POOL LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS592",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518004005992",
    "engine_no": "8282603",
    "location": "SONGO STAFF BUS (S/C V/I)",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS574",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108021564",
    "engine_no": "2TR8270154",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS575",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208021511",
    "engine_no": "2TR8269452",
    "location": "NEW BROAD STREET",
    "department": "NEW BROAD STREET",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS600",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108022052",
    "engine_no": "JTFRX12P108022052",
    "location": "FED AUDIT LAGOS",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS603",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808021996",
    "engine_no": "2TR8264759",
    "location": "MTA LI",
    "department": "MTA LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS605",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208022416",
    "engine_no": "2TR8279172",
    "location": "VI MSTO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS606",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708022010",
    "engine_no": "2TR8274469",
    "location": "OIL AND GAS SERVICING",
    "department": "LTO OIL AND GAS SERV",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS613",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P3A8019084",
    "engine_no": "2TR82369122",
    "location": "OIL/GAS DOWN STREAM",
    "department": "OIL/GAS DOWN STREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS674/82FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026271",
    "engine_no": "2TR8349491",
    "location": "IKOYI MSTO",
    "department": "IKOYI 1 MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS679/57FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408026001",
    "engine_no": "2TR8343468",
    "location": "VI MSTO",
    "department": "VI MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS684/59FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108026182",
    "engine_no": "2TR8348158",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS671/84FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708026364",
    "engine_no": "2TR8351042",
    "location": "Non-oil L/ISLAND",
    "department": "LTO NON OIL FINANCIAL",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS665/162FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208025434",
    "engine_no": "2TR8334482",
    "location": "TAX INV",
    "department": "TID LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS666/165FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808025403",
    "engine_no": "8334036",
    "location": "TAX INV",
    "department": "TID LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS704/54FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208026949",
    "engine_no": "2TR8346980",
    "location": "OIL&GAS UPSTREAM",
    "department": "OIL&GAS UPSTREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS705/53FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208027003",
    "engine_no": "2TR8358762",
    "location": "OIL&GAS UPSTREAM",
    "department": "OIL&GAS UPSTREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS717/145FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08012074",
    "engine_no": "2TR7143606",
    "location": "ENFORCEMENT TEAM LAGOS ISLAND",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS701/172FIRS",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518504008371",
    "engine_no": "2TR8369634",
    "location": "OIL & GAS UPSTREAM",
    "department": "OIL & GAS UPSTREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS698/92FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308027768",
    "engine_no": "2TR8369444",
    "location": "ONIKAN MSTO",
    "department": "ONIKAN MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS747/136FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803027188",
    "engine_no": "2ZRU422093",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS820/42FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308030590",
    "engine_no": "2ZRU8434174",
    "location": "OIL AND GAS AUDIT",
    "department": "OIL AND GAS AUDIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS831/FIRS289",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108031401",
    "engine_no": "2TR8445841",
    "location": "OIL & GAS DOWNSTREAM",
    "department": "OIL & GAS DOWNSTREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS854/FIRS 503",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008031843",
    "engine_no": "2TR8455736",
    "location": "BARBEACH MSTO",
    "department": "BARBEACH MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS353",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2ZE1427013630",
    "engine_no": "IZZA213808",
    "location": "NEW BROAD STREET",
    "department": "NEW BROAD STREET",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "303FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108036100",
    "engine_no": "2TR8517247",
    "location": "BAR BEACH LAGOS",
    "department": "BARBEACH MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "355FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03035566",
    "engine_no": "2ZRU715266",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "351FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708034688",
    "engine_no": "2TR8496841",
    "location": "INTERNATIONAL TAX DEPT",
    "department": "ITD",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS698",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208039314",
    "engine_no": "2TR-8557177",
    "location": "SPECIAL TAX AUDIT LAGOS",
    "department": "SPECIAL TAX AUDIT LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS669",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G908026435",
    "engine_no": "2TR-7737546",
    "location": "ENFORCEMENT",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS671",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G308026432",
    "engine_no": "2TR-7737485",
    "location": "ENFORCEMENT LAGOS",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS682",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208038521",
    "engine_no": "2TR-8569036",
    "location": "SPECIAL TAX AUDIT LAGOS",
    "department": "SPECIAL TAX AUDIT LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS700/166FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008027937",
    "engine_no": "2TR8372854",
    "location": "MTO LI",
    "department": "MTO LI",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS768",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708043083",
    "engine_no": "2TR8690524",
    "location": "REGIONAL DEBT MGMT L/I",
    "department": "REGIONAL DEBT MGMT L/I",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS777",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308044490",
    "engine_no": "2TR8714837",
    "location": "FLEET POOL LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS787",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508044409",
    "engine_no": "2TR8712946",
    "location": "TAX AUDIT L/I",
    "department": "TAX AUDIT L/I",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS794",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ818569",
    "engine_no": "VF3DDNFPRDJ818569",
    "location": "LEGAL SERVICES/ LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS861",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518804024726",
    "engine_no": "2TR9012620",
    "location": "IKOTUN EGBE STAFF BUS (SC LI)",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS855",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708045013",
    "engine_no": "2TR9001877",
    "location": "AJAH MSTO 2",
    "department": "AJAH MSTO 2",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS856",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208045016",
    "engine_no": "2TR9001942",
    "location": "IKOYI MTO 2",
    "department": "IKOYI MTO 2",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS858",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308045011",
    "engine_no": "2TR9001707",
    "location": "VI 2 MSTO",
    "department": "VI 2 MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS859",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908045028",
    "engine_no": "2TR9001212",
    "location": "ITD",
    "department": "ITD",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS887",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G908030453",
    "engine_no": "2TR8823702",
    "location": "ECFIRS ESCORT LAGOS",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS888",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G208030553",
    "engine_no": "2TR8819725",
    "location": "MINISTER ESCORT LAGOS",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS369N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22P9F6162230",
    "engine_no": "2TR9012149",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS370N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22PXF6158848",
    "engine_no": "2TR8716052",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS373N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22P2F6159606",
    "engine_no": "2TR9000105",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS374N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22PXF6162463",
    "engine_no": "2TR9014373",
    "location": "SCO LI",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS437N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ606826",
    "engine_no": "HJ606826",
    "location": "MGT PROTOCOL",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS476N",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK5183G4028757",
    "engine_no": "2TR9084022",
    "location": "MANAGEMENT FLEET POOL/ LAGOS ISLAND",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS487N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308048894",
    "engine_no": "2TR9101152",
    "location": "LTO O&G UPSTREAM",
    "department": "LI SCO POOL",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS488 N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308048913",
    "engine_no": "2TR9105275",
    "location": "LTO NON-OIL (FINANCE)",
    "department": "LTO NON OIL FINANCIAL",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS489N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408048936",
    "engine_no": "2TR9106320",
    "location": "LTO O&G SERVICES",
    "department": "LTO OIL AND GAS SERV",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS493N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308048930",
    "engine_no": "2TR9106316",
    "location": "INTERNATIONAL TAX DEPT",
    "department": "ITD",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS501N",
    "brand": "Hyundai",
    "model": "Truck",
    "vin_sn": "KMFGA17BPEC267285",
    "engine_no": "KMFGA17BPEC267285",
    "location": "LAGOS ISLAND CAR PARK",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS542N",
    "brand": "Peugeot",
    "model": "4X4 Pick-Up",
    "vin_sn": "VF3FA4HMGJX200715",
    "engine_no": "JX200715",
    "location": "GENERAL FLEET POOL",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS552N",
    "brand": "Isuzu",
    "model": "Mobile Office Truck",
    "vin_sn": "JAAN1R71LK100288",
    "engine_no": "JAAN1R71LK100288",
    "location": "OD/TPSD",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1000",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "TRH200-0143124",
    "engine_no": "TRH200-0143124",
    "location": "BAR BEACH MSTA (TAX AUDIT",
    "department": "BAR BEACH MSTA (TAX AUDIT",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1003",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P405029859",
    "engine_no": "JTFJX02P405029859",
    "location": "INTERNATIONAL TAX DEPARTMENT LAGOS",
    "department": "INTERNATIONAL TAX DEPARTMENT LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1005",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P6C0069599",
    "engine_no": "JTFHX02P6C0069599",
    "location": "MTA2 LAGOS ISLAND",
    "department": "MTA2 LAGOS ISLAND",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1008",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P4A0047064",
    "engine_no": "JTFHX02P4A0047064",
    "location": "AJAH 2 MSTO",
    "department": "AJAH 2 MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1010",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P805036829",
    "engine_no": "JTFJX02P805036829",
    "location": "VI MSTA",
    "department": "BARBEACH MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1013",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P105030113",
    "engine_no": "JTFJX02P105030113",
    "location": "TID LAGOS ILAND & LMW DIVISION",
    "department": "TID LAGOS ILAND & LMW DIVISION",
    "driver_name": "TOBI ABIOLA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1017",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P450001658",
    "engine_no": "JTFHX02P450001658",
    "location": "MTO ISLAND",
    "department": "MTO ISLAND",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1034",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P405028713",
    "engine_no": "JTFJX02P405028713",
    "location": "BROAD STREET MSTA",
    "department": "BROAD STREET MSTA",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1042",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P1A5015883",
    "engine_no": "JTGJX02P1A5015883",
    "location": "TID LAGOS ISLAND",
    "department": "TID LAGOS ISLAND",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1094",
    "brand": "Innoson",
    "model": "Capa",
    "vin_sn": "LGG7E3D2XLZ416914",
    "engine_no": "4G6354T-5YN3380",
    "location": "OECFIRS POOL",
    "department": "OECFIRS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1113",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS62NA769892",
    "engine_no": "LKLSBAS62NA769892",
    "location": "LARGE TAX OFFICE (OIL & GAS)",
    "department": "LTO OIL & GAS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1114",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS66NA769894",
    "engine_no": "LKLSBAS66NA769894",
    "location": "LARGE TAX OFFICE (OIL & GAS)",
    "department": "LTO OIL & GAS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1115",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS68NA769895",
    "engine_no": "LKLSBAS68NA769895",
    "location": "LARGE TAX OFFICE (OIL & GAS)",
    "department": "LTO OIL & GAS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1116",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS69NA769890",
    "engine_no": "LKLSBAS69NA769890",
    "location": "LARGE AUDIT(OIL & GAS)",
    "department": "LTA OIL & GAS",
    "driver_name": "UPSTREAM",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1117",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS6XNA769896",
    "engine_no": "LKLSBA6XNA769896",
    "location": "LARGE AUDIT(OIL & GAS)",
    "department": "LTA OIL & GAS",
    "driver_name": "DOWNSTREAM",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1118",
    "brand": "Pan",
    "model": "Higer Bus",
    "vin_sn": "LKLSBAS64NA769893",
    "engine_no": "LKLSBAS64NA769893",
    "location": "LARGE TAX AUDIT(OIL & GAS)",
    "department": "LTA OIL & GAS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1125",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP7N6011750",
    "engine_no": "7GR-FKS3456",
    "location": "TELECOM & BROADCAST",
    "department": "TELECOM & BROADCAST",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1126",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9N6012074",
    "engine_no": "7GR-FKS3456",
    "location": "TELECOM & BROADCAST",
    "department": "TELECOM & BROADCAST",
    "driver_name": "LARGE TAX OFFICE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1127",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP7N6011764",
    "engine_no": "7GR-FKS3456",
    "location": "TELECOM & BROADCAST",
    "department": "TELECOM & BROADCAST",
    "driver_name": "MEDIUM TAX OFFICE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1128",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9N6012141",
    "engine_no": "7GR-FKS3456",
    "location": "TELECOM & BROADCAST",
    "department": "TELECOM & BROADCAST",
    "driver_name": "AUDIT",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1132",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD1M0093564",
    "engine_no": "1GRH278899",
    "location": "OECFIRS LAGOS POOL",
    "department": "LAGOS",
    "driver_name": "NAMI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1133",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CDXM0094471",
    "engine_no": "1GRH286178",
    "location": "OECFIRS LAGOS POOL",
    "department": "LAGOS",
    "driver_name": "NAMI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1131",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BX8CD6M2766991",
    "engine_no": "2TRA802633",
    "location": "OCD/ETG",
    "department": "ETG LAGOS",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1236",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608050090",
    "engine_no": "JTFRX12P608050090",
    "location": "BARBEACH MSTO",
    "department": "MSTO",
    "driver_name": "BARBEACH MSTO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1237",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308049995",
    "engine_no": "JTFRX12P308049995",
    "location": "MTA-LI",
    "department": "MTA",
    "driver_name": "MTA II/LI/SCO",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS702",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G608026084",
    "engine_no": "2TR7727337",
    "location": "ECFIRS ESCORT LAGOS",
    "department": "LI SCO",
    "driver_name": "POOL ESCORT",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1201",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622Z3NX404760",
    "engine_no": "3G15TD-5600075",
    "location": "DD-(OIL & GAS)LAGOS",
    "department": "LTA (O&G) LAGOS",
    "driver_name": "SHODIPO S.A",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS608",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608023777",
    "engine_no": "2TR8299317",
    "location": "STAFF WELFARE BUS LAGOS",
    "department": "LISCO",
    "driver_name": "STAFF WELFARE BUS LAGOS",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS618",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P7A8019105",
    "engine_no": "2TR8237133",
    "location": "STAFF WELFARE BUS LAGOS",
    "department": "LI SCO",
    "driver_name": "STAFF WELFARE BUS LAGOS",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1198",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z8MW036115",
    "engine_no": "L6T7824Z8MW036115",
    "location": "AD-L T O (O & G)",
    "department": "LTA (O&G) UPSTREAM LAGOS",
    "driver_name": "UGEH P M.",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS509N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCA GL040499",
    "engine_no": "GL040499",
    "location": "AD-SS&FMD",
    "department": "SS&FMD",
    "driver_name": "UGOCHUKWU OGBONS O",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS956",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586184",
    "engine_no": "VF3DDNFPRGJ586184",
    "location": "AD-MSTA AJAH",
    "department": "MSTA AJAH",
    "driver_name": "UHUABA OKEZIE",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1271",
    "brand": "Changan",
    "model": "Eado Dt",
    "vin_sn": "LS5A2AGE9PD910641",
    "engine_no": "NCPBP002210",
    "location": "AD-ITD",
    "department": "INTERNATIONAL TAX DEPARTMENT",
    "driver_name": "UMAR HUSSAINI",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS957",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ610414",
    "engine_no": "VF3DDNFPRGJ610414",
    "location": "TC-ALIMOSHO MSTO",
    "department": "ALIMOSHO MSTO TC",
    "driver_name": "UMARU GABRIEL GARBA",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS913",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ861168",
    "engine_no": "VF3DDNFPRDJ861168",
    "location": "LAGOS ISLAND",
    "department": "LAGOS ISLAND",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1374",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE3RD922729",
    "engine_no": "P3C1526911",
    "location": "DD,OCD - LARGE TAX LAGOS",
    "department": "OCD - LARGE TAX",
    "driver_name": "BUSARI MUSIBAU",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS732/103FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703027022",
    "engine_no": "2ZRU418854",
    "location": "AD-LAGOS",
    "department": "LAGOS",
    "driver_name": "MOHAMMED GARBA",
    "sco": "LI"
  },
  {
    "license_plate": "356FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E603035533",
    "engine_no": "2ZRU717268",
    "location": "TC-IKOYI ETO",
    "department": "TC-IKOYI II, ETO",
    "driver_name": "MAIYAKI FATIMA",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1207",
    "brand": "Geely",
    "model": "Jeep",
    "vin_sn": "L6T7722Z4NU006242",
    "engine_no": "3G15TD-2502642",
    "location": "SC-BBY",
    "department": "SCO/LAGOS ISLAND",
    "driver_name": "SCO",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1305",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR1RA960042",
    "engine_no": "LS5A3AKR1RA960042",
    "location": "HEAD, LTA FINANCIAL",
    "department": "LTA FINANCIAL",
    "driver_name": "SALIHU GAJO",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1310",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR6RA960649",
    "engine_no": "LS5A3AKR6RA960649",
    "location": "DD/LTO(NON-OIL LAGOS)",
    "department": "TC/KANO 2",
    "driver_name": "CLARA OBASI",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1347",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05RT351997",
    "engine_no": "S3LH965",
    "location": "AD/HEAD IKOYI AUDIT",
    "department": "AD/HEAD IKOYI AUDIT",
    "driver_name": "GEORGINA EBELE",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS223",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903009766",
    "engine_no": "2ZRUO91393",
    "location": "AD-TID LAGOS",
    "department": "SSFMD POOL",
    "driver_name": "SSFMD POOL",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1252",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9M6010507",
    "engine_no": "7GR-FKS3456",
    "location": "LME/SCO-LAGOS",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1177",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z9NU006219",
    "engine_no": "L6T7722Z9NU006219",
    "location": "DD/LAGOS ISLAND",
    "department": "SCO",
    "driver_name": "AYABAM TERHEMBA",
    "sco": "LI SCO"
  },
  {
    "license_plate": "FIRS1364",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT351986",
    "engine_no": "LGJF1FE00RT351986",
    "location": "TC,IKORODU MSTO",
    "department": "TC, IKORODU MSTO",
    "driver_name": "JONATHAN OGBODAGEH",
    "sco": "LM"
  },
  {
    "license_plate": "FIRS1357",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT352002",
    "engine_no": "S3LJ012",
    "location": "AD, TC,IKEJA 2 MSTO",
    "department": "AD, TC IKEJA 2 MSTO",
    "driver_name": "WAKIRWA SALIHU IDRISA",
    "sco": "LM"
  },
  {
    "license_plate": "FIRS1095",
    "brand": "Innoson",
    "model": "Granite",
    "vin_sn": "LTA12H2P2M1000018",
    "engine_no": "4K22D4M-SYT8153",
    "location": "OECFIRS POOL LAGOS",
    "department": "SS&FMD",
    "driver_name": "SS&FMD MGT PROTOCOL",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1248",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK0N3171428",
    "engine_no": "A25A-FKS2487",
    "location": "SC-EEA",
    "department": "D-STA / LME",
    "driver_name": "OKORONKWO UCHE NNANA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS767/132FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303027725",
    "engine_no": "2ZRU435758",
    "location": "AD-TAD",
    "department": "TAD",
    "driver_name": "NNEKWE JOHN IKECHUKWU",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS442N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ609996",
    "engine_no": "HJ609996",
    "location": "DEBT Mgt pool",
    "department": "LME",
    "driver_name": "DMO POOL",
    "sco": "LME"
  },
  {
    "license_plate": "236FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903030861",
    "engine_no": "2ZRU500644",
    "location": "MGT PROTOCOL LME",
    "department": "LTA LAGOS",
    "driver_name": "LME (POOL)",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS917",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ844222",
    "engine_no": "VF3DDNFPRDJ844222",
    "location": "AD-VAT COORDINATION LME",
    "department": "VAT COORD",
    "driver_name": "ABDUKARIM YUSUF",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS937",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586195",
    "engine_no": "VF3DDNFPRGJ586195",
    "location": "TC- AGEGE MSTO",
    "department": "AGEGE MSTO",
    "driver_name": "ABDULKAREEM OLAMIDE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS844/ FIRS 494",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003029372",
    "engine_no": "2ZRU469900",
    "location": "ADT GBTO LAGOS",
    "department": "GBTO LAGOS",
    "driver_name": "ADEGBOYEGA ADEWALE NURUDEEN",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1386",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASEXRD910870",
    "engine_no": "P3C1502535",
    "location": "AD/LTA IKEJA",
    "department": "AD/LTA IKEJA",
    "driver_name": "ADENIYI OJO GANIYU",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS256",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703009653",
    "engine_no": "2ZRU89986",
    "location": "MTA LAGOS",
    "department": "LEGAL",
    "driver_name": "OYENIYI COMFORT OMOLOLA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS762/127FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03026172",
    "engine_no": "..",
    "location": "AD-LTO NON OIL",
    "department": "AD-LTO NON OIL",
    "driver_name": "AD-LTO NON OIL",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS997",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ646337",
    "engine_no": "VF3DDNFPRDJ646337",
    "location": "AD-STA LME",
    "department": "STA",
    "driver_name": "AKAEZE FELIX IFEANYI",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1278",
    "brand": "Changan",
    "model": "Cs35 Plus",
    "vin_sn": "LS5A3AKR3RA960351",
    "engine_no": "PM0AD025161",
    "location": "HEAD-TID LME",
    "department": "TID-LME",
    "driver_name": "BALA YAHAYA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS594",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "ATHLC58E503021896",
    "engine_no": "2ZR-U290560",
    "location": "SS&FM/ REP LAGOS",
    "department": "",
    "driver_name": "CHARITY UCHENNA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS649N",
    "brand": "Innoson",
    "model": "Ambulance",
    "vin_sn": "LL3AAAAC1JA000154",
    "engine_no": "4RB2-75890A",
    "location": "SCO-LME",
    "department": "LAGOS MAINLAND EAST",
    "driver_name": "CLINIC",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS358",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2ZE1427013248",
    "engine_no": "IZZA 213437",
    "location": "D/SMALL TAX PAYERS DEPT",
    "department": "LAGOS MAINLAND EAST",
    "driver_name": "SOSIMI OLUBUNMI",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS166",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E03009969",
    "engine_no": "2ZRU092905",
    "location": "LME SCO / S&SM POOL",
    "department": "SS&FMD",
    "driver_name": "AUSTIN ALLENS",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS772/121FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303027826",
    "engine_no": "2ZRU439574",
    "location": "AD-IKEJA 2 MSTO",
    "department": "LI SCO",
    "driver_name": "HAMIDU HARUNA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1165",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB29HKXL3057334",
    "engine_no": "JTNB29HKXL3057334",
    "location": "SCO/JKK",
    "department": "SC JKK SCO",
    "driver_name": "HASSAN SULE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS938",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ610413",
    "engine_no": "VF3DDNFPRGJ610413",
    "location": "AD-MTA LAGOS",
    "department": "MTA LI",
    "driver_name": "MOHAMMED MUINAT A",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS709",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE000002304",
    "engine_no": "2ZRU-771973",
    "location": "AD-LTD NON OIL LAGOS-MAINLAND",
    "department": "LTA LAGOS",
    "driver_name": "MR NWODO FERDINAND SUNDAY",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS431N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL034537",
    "engine_no": "GL034537",
    "location": "AD-LTO NON OIL",
    "department": "LTO NON OIL APAPA",
    "driver_name": "NAIYEJU",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS969",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ606741",
    "engine_no": "VF3DDNFPRGJ606741",
    "location": "ONIGBOGBO MSTO LAGOS",
    "department": "ONIGBONGO MSTO",
    "driver_name": "OBABORI BABATUNDE OLUBANJI",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS417N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "RKLBL9HE0F5246730",
    "engine_no": "3ZRX537337",
    "location": "AD-LTA LME",
    "department": "LTA LAGOS",
    "driver_name": "OBODOEKE GANIAT",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS950",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ601283",
    "engine_no": "VF3DDNFPRGJ601283",
    "location": "TAX INVESTIGATION DEPT. LAGOS/TRAINING SCHOOL",
    "department": "TID/TRAINING SCHOOL",
    "driver_name": "OGUNNIYI ALIU OLUKAYODE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS736",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ803853",
    "engine_no": "VF3DDNFPRDJ803853",
    "location": "TC-YABA MSTO",
    "department": "TC-YABA MSTO",
    "driver_name": "OGUNSHOLA IDOWU BELLO",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS465N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ605221",
    "engine_no": "HJ605221",
    "location": "TEAM LEADER, TAX AUDIT REVIEW TEAM 1 LAGOS",
    "department": "SCO LME",
    "driver_name": "OKEZIE FINECOUNTRY OKEZIE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS554N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "NMTBF9JE9KR015892",
    "engine_no": "2ZRW015482",
    "location": "H-LT NON OIL",
    "department": "LTO NONOIL",
    "driver_name": "YIDIAT OYENIYI",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS967",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ603101",
    "engine_no": "VF3DDNFPRGJ603101",
    "location": "AD-MTO LAGOS",
    "department": "MTO",
    "driver_name": "OLUWEMIMO OLALEKAN OLUKUNLE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS960",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ604931",
    "engine_no": "VF3DDNFPRGJ604931",
    "location": "DD-MTA LAGOS",
    "department": "MTA 2",
    "driver_name": "OYENIYI COMFORT OMOLOLA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS90",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P505006266",
    "engine_no": "437180",
    "location": "SCO-LME",
    "department": "TRAINING SCHOOL",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS241",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX22P06049844",
    "engine_no": "8158485",
    "location": "ALIMOSHO MSTO",
    "department": "ALIMOSHO MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS240",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX 22P106043549",
    "engine_no": "8140781",
    "location": "IKEJA 1 MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS242",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P306041899",
    "engine_no": "8136535",
    "location": "GBTO LAGOS",
    "department": "GBTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS250",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06050158",
    "engine_no": "5147297",
    "location": "NON OIL LAGOS LTA",
    "department": "LTA",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS330",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12PX 08017724",
    "engine_no": "8224695",
    "location": "ILUPEJU I MSTO",
    "department": "ILUPEJU I MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS332",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 408017640",
    "engine_no": "8223687",
    "location": "AGEGE MSTO",
    "department": "AGEGE MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS333",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 708017650",
    "engine_no": "8223924",
    "location": "IKORODU MSTO",
    "department": "IKORODU MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS334",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12PX08017691",
    "engine_no": "8224410",
    "location": "LTO NON OIL-LME",
    "department": "LTO NON OIL LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS361",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06073729",
    "engine_no": "2TR8235087",
    "location": "BAUHI POOL",
    "department": "POOL",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS378",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408017847",
    "engine_no": "2TR 8225869",
    "location": "LTO AUDIT NON OIL",
    "department": "LTA LAGOS",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS396",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508017727",
    "engine_no": "2TR8224592",
    "location": "ONIGBONBO MSTO",
    "department": "ONIGBONGO MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS569",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808021724",
    "engine_no": "2TR8271403",
    "location": "IKORODU MSTO",
    "department": "IKORODU MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS570",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308021680",
    "engine_no": "2TR8271500",
    "location": "ILUPEJU II MSTO",
    "department": "ILUPEJU 2 MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS572",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208021685",
    "engine_no": "2TR8271058",
    "location": "ONIGBONBO MSTO",
    "department": "ONIGBONBO MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS653/91FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026755",
    "engine_no": "2TR8356059",
    "location": "AGEGE MSTO",
    "department": "AGEGE MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS675/80FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108026506",
    "engine_no": "2TR8352778",
    "location": "LTO NON OIL LME",
    "department": "LTO NON OIL LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS676/77FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026464",
    "engine_no": "2TR8349950",
    "location": "YABA MSTO",
    "department": "YABA MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS681/78FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026528",
    "engine_no": "2TR8352655",
    "location": "IKEJA 1 MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS663/86FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "2TR8331448",
    "engine_no": "8331448",
    "location": "MTO LME",
    "department": "MTO LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS715/144FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G708012131",
    "engine_no": "2TR7148583",
    "location": "SCO-ENFORCEMENT LAGOS LME",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS852/FIRS501",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808022744",
    "engine_no": "2TR8282731",
    "location": "ILPEJU II MSTO",
    "department": "ILUPEJU 2 MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "242FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908034708",
    "engine_no": "2TR8497146",
    "location": "LME SCO",
    "department": "LAGOS GBTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS678",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708038711",
    "engine_no": "2TR-8573919",
    "location": "MTO LAGOS MAINLAND",
    "department": "MTO LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS679",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808038765",
    "engine_no": "2TR-8576119",
    "location": "GBTO LAGOS",
    "department": "LAGOS GBTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS774",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908044428",
    "engine_no": "2TR8685781",
    "location": "DEBT MANAGEMENT L/M EAST",
    "department": "DMO LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS789",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08044406",
    "engine_no": "2TR8713005",
    "location": "TAX AUDIT L/M EAST",
    "department": "SCO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS797",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ813707",
    "engine_no": "VF3DDNFPRDJ813707",
    "location": "STATE COORD'S OFFICE LEGAL LME",
    "department": "LEGAL UNIT",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS832",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833764",
    "engine_no": "VF3DDNFPRDJ833764",
    "location": "SCO LME",
    "department": "SCO",
    "driver_name": "OLODEOKUN RASHEED KOLAWOLE",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS371N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22POF6161306",
    "engine_no": "2TR9007922",
    "location": "IKEJA 2 MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1012",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P405023477",
    "engine_no": "JTFJX02P405023477",
    "location": "LTO NON FINANCIAL",
    "department": "LTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1014",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P605016594",
    "engine_no": "JTFJX02P605016594",
    "location": "TIDLAGOS MAINLAND&SOUTH WEST DIVISION",
    "department": "TID LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS648N",
    "brand": "Innoson",
    "model": "Ambulance",
    "vin_sn": "LL3AAAAC1JA000128",
    "engine_no": "4RB2-75818A",
    "location": "SCO-LME",
    "department": "SCO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1229",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308050077",
    "engine_no": "JTFRX12P308050077",
    "location": "MTA-LME",
    "department": "MTA",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1251",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP9M6010758",
    "engine_no": "7GR-FKS3456",
    "location": "SCO-LME",
    "department": "SCO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS547",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108019930",
    "engine_no": "2TR8247948",
    "location": "OSHODI CELE ROUTE BUS",
    "department": "OSHODI CELE ROUTE BUS",
    "driver_name": "OSHODI CELE ROUTE BUS",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS589",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518004006043",
    "engine_no": "8283748",
    "location": "SC LME",
    "department": "STAFF BUS",
    "driver_name": "MOWE ROUTE BUS",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS593",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518404005980",
    "engine_no": "8282262",
    "location": "SC LME",
    "department": "STAFF BUS",
    "driver_name": "IKOTUN ROUTE BUS",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS863",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518304022897",
    "engine_no": "2TR8717859",
    "location": "LAGOS MAINLAND EAST",
    "department": "STAFF BUS",
    "driver_name": "IKORODU ROUTE BUS",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS952",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ608595",
    "engine_no": "VF3DDNFPRGJ608595",
    "location": "OEC/RELATNSHIP MGMT. LAGOS",
    "department": "TID",
    "driver_name": "ODO CHUKWUMA",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS1425",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XRT353924",
    "engine_no": "4A92*S3LH984",
    "location": "AD-MSTO IKEJA",
    "department": "IKEJA MSTO",
    "driver_name": "AGBABIAKA T. ABIODUN",
    "sco": "LME"
  },
  {
    "license_plate": "273FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403034302",
    "engine_no": "2ZRU648837",
    "location": "AD-HR LMW SCO",
    "department": "LMW SCO",
    "driver_name": "ABUBAKAR BIMBO A.",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1107",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ3NY502205",
    "engine_no": "VR3F3EGZ3NY502205",
    "location": "HEAD-APAPA MSTA",
    "department": "APAPA MSTA",
    "driver_name": "ADENIRAN ADEMOLA BUKOLA",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS796",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ791625",
    "engine_no": "VF3DDNFPRDJ791625",
    "location": "DD-LL&P",
    "department": "LMW SCO",
    "driver_name": "EGODI ADEDEJI",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS932",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBFOJE400008364",
    "engine_no": "2ZRV143210",
    "location": "DD-LL&P LMW",
    "department": "DD-LL&P LMW",
    "driver_name": "MRS EGODI",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1108",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ1NY500744",
    "engine_no": "VR3F3EGZ1NY500744",
    "location": "DD-SPECIAL TAX AUDIT LIMW",
    "department": "SPECIAL TAX AUDIT LIMW",
    "driver_name": "EWA KELECHUKWU O.",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS787/184FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56EX03028309",
    "engine_no": "2ZRU448874",
    "location": "AD, HEAD OF AUDIT ALABA ETA",
    "department": "HEAD OF AUDIT ALABA ETA",
    "driver_name": "AJIBOYE OLAYINKA PHILLIP",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1211",
    "brand": "Geely",
    "model": "Jeep",
    "vin_sn": "L6T7722Z5NU006234",
    "engine_no": "3GI5TD-2502697",
    "location": "SCO-LMW",
    "department": "SCO LMW",
    "driver_name": "LMW",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS434N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ613226",
    "engine_no": "HJ613226",
    "location": "TC-AGEGE MSTO",
    "department": "AGEGE MSTO",
    "driver_name": "MOHAMMED ABDULLAHI SANI",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS908",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ854369",
    "engine_no": "VF3DDNFPRDJ854369",
    "location": "TC-FESTAC MSTO",
    "department": "FESTAC MSTO",
    "driver_name": "OLASUNBO KULEPA",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS361N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ703553",
    "engine_no": "VF3DDNFPRDJ703553",
    "location": "HEAD-MTA AGUDA",
    "department": "HEAD-MTA AGUDA",
    "driver_name": "MUAZU SANI HAMIDU",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS312",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403017953",
    "engine_no": "2ZRU194647",
    "location": "TC-ORILE MSTO",
    "department": "TC-ORILE MSTO",
    "driver_name": "NNAJI CHUKA INNOCENT",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS738",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ812039",
    "engine_no": "VF3DDNFPRDJ812039",
    "location": "TC-ALABA MSTO",
    "department": "TC-ALABA MSTO",
    "driver_name": "EDOBOR I.I",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS936",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ888893",
    "engine_no": "VF3DDNFPRDJ888893",
    "location": "TC-AGUDA MSTO",
    "department": "AGUDA MSTO",
    "driver_name": "OLADELE GABRIEL OGUNDOKUM",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS307",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903015597",
    "engine_no": "2ZRU143524",
    "location": "AD-LMW SCO",
    "department": "AD-LMW SCO",
    "driver_name": "OLAJIDE A.S",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS419N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL031731",
    "engine_no": "GL031731",
    "location": "AD/SCO",
    "department": "LMW SCO",
    "driver_name": "OLUMIDE OLUOLA",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS965",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ586200",
    "engine_no": "VF3DDNFPRGJ586200",
    "location": "HEAD- SURULERE MSTA",
    "department": "LTA LAGOS",
    "driver_name": "ONWERE CHIBUIKE AFORNNE",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1082",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK6HR879239",
    "engine_no": "NC02H051449",
    "location": "TC-BADAGRY MSTO",
    "department": "BADAGRY MDSTO",
    "driver_name": "OSHO RUTH",
    "sco": "LMW"
  },
  {
    "license_plate": "RB891FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "105006457",
    "engine_no": "442904",
    "location": "MTO POOL",
    "department": "LMW SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS196",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "X22P306044072",
    "engine_no": "8120762",
    "location": "ORILE MSTO",
    "department": "ORILE MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS221",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX 22P006050198",
    "engine_no": "8160018",
    "location": "FESTAC MSTO",
    "department": "FESTAC MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS331",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P 808017379",
    "engine_no": "8221682",
    "location": "ISOLO MSTO",
    "department": "ISOLO MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS348",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P500026708",
    "engine_no": "8207001",
    "location": "ALABA MSTO",
    "department": "ALABA MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS395",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608017879",
    "engine_no": "2TR8226202",
    "location": "SURULERE MSTO",
    "department": "SURULERE MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS564",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208021606",
    "engine_no": "8250595",
    "location": "FESTAC MSTO",
    "department": "FESTAC MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS573",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208021475",
    "engine_no": "2TR8268935",
    "location": "SURULERE MSTO",
    "department": "SURULERE MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS576",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308021534",
    "engine_no": "2TR8269228",
    "location": "ISOLO MSTO",
    "department": "ISOLO MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS604",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708022007",
    "engine_no": "2TR8274592",
    "location": "APAPA MSTO",
    "department": "APAPA MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS678/140FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026383",
    "engine_no": "2TR8351215",
    "location": "LMW SCO",
    "department": "LMW SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS680/79FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408026452",
    "engine_no": "2TR8351733",
    "location": "ALABA MSTO",
    "department": "ALABA MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS853/ FIRS502",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808031847",
    "engine_no": "2TR8455732",
    "location": "AGUDA MSTO",
    "department": "AGUDA MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS770",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208043086",
    "engine_no": "2TR8689910",
    "location": "LTO NON OIL APAPA",
    "department": "LTO NON OIL APAPA",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS775",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508040537",
    "engine_no": "2TR8619102",
    "location": "DEBT MANAGEMENT L/M WEST",
    "department": "ORILE MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS788",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408044403",
    "engine_no": "2TR8713042",
    "location": "APAPA MSTO/ MTA APAPA",
    "department": "APAPA MSTO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS862",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518504022870",
    "engine_no": "2TR8717563",
    "location": "LMW SONGO ROUTE",
    "department": "LMW SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS857",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608045018",
    "engine_no": "2TR9001938",
    "location": "LMW SCO",
    "department": "LMW SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS490N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208048918",
    "engine_no": "2TR9105338",
    "location": "MTO LMW",
    "department": "MTO LMW",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1022",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P105020391",
    "engine_no": "JTFJX02P105020391",
    "location": "MSTA AGUDA",
    "department": "MSTA AGUDA",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1037",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02PB0058126",
    "engine_no": "JTFHX02PB0058126",
    "location": "MTA2 LAGOS MAINLAND WEST",
    "department": "MTA2 LAGOS MAINLAND WEST",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1038",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P690022854",
    "engine_no": "JTGJX02P690022854",
    "location": "VAT LAGOS MAINLAND WEST",
    "department": "VAT LAGOS MAINLAND WEST",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1025",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P600062035",
    "engine_no": "JTFJX02P600062035",
    "location": "LAGOS MAILAND WEST SCO",
    "department": "LAGOS MAILAND WEST SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1232",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108050000",
    "engine_no": "JTFRX12P108050000",
    "location": "FESTAC MSTO",
    "department": "MSTO",
    "driver_name": "LME",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1234",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708050034",
    "engine_no": "JTFRX12P708050034",
    "location": "ALABA MSTO",
    "department": "ALABA MSTO",
    "driver_name": "LAGOS",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS842",
    "brand": "Kia",
    "model": "Mohave",
    "vin_sn": "KNAKN811DF5133604",
    "engine_no": "G6DAES23568",
    "location": "MGT PROTOCOL",
    "department": "MGT PROTOCOL",
    "driver_name": "MGT PROTOCOL",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS255",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E203009902",
    "engine_no": "2ZRU0",
    "location": "TC-ORILE MSTO",
    "department": "ORILE MSTO",
    "driver_name": "TOYIN OJUKUTU",
    "sco": "LMW"
  },
  {
    "license_plate": "221FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03030335",
    "engine_no": "2ZRU489704",
    "location": "HEAD-VAT",
    "department": "VAT LMW",
    "driver_name": "USMAN IBRAHIM ALFADARAI",
    "sco": "LMW"
  },
  {
    "license_plate": "222FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803030835",
    "engine_no": "2ZRU501012",
    "location": "TC-LTO NON OIL",
    "department": "LTO NON APAPA",
    "driver_name": "WILLIAMS OLUFUNKE OMOTAYO",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS1424",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGTF1FE03RT353926",
    "engine_no": "4A92*S3LH986",
    "location": "SCO LMW",
    "department": "LMW",
    "driver_name": "OYEBANJI O. MATTHEW",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS836",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ810400",
    "engine_no": "VF3DDNFPRDJ810400",
    "location": "STATE MONITOR LOKOJA",
    "department": "GBTO LOKOJA",
    "driver_name": "ADULLAHI ABUBAKAR",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS998",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ611553",
    "engine_no": "VF3DDNFPRDJ611553",
    "location": "DD-LTO IBADAN",
    "department": "LTO IBADAN",
    "driver_name": "BASHIR LAWAL",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS201",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06041413",
    "engine_no": "8134289",
    "location": "LTA IBADAN",
    "department": "LTA IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1353",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08RT351993",
    "engine_no": "S3LH967",
    "location": "AD- SAGAMU MSTO",
    "department": "SAGAMU MSTO",
    "driver_name": "GANIYU ADEBOWALE LAWAL",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1080",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK4HR879238",
    "engine_no": "NC02H051451",
    "location": "TC-IJEBU ODE STO",
    "department": "STO",
    "driver_name": "AMUSA S.O",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1105",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VR3F3EGZ0NY502212",
    "engine_no": "VR3F3EGZ0NY502212",
    "location": "DD-SAO IBADAN",
    "department": "SAO IBADAN",
    "driver_name": "AYODELE FLORENCE OYENIKE",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS916",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPREJ546221",
    "engine_no": "VF3DDNFPREJ546221",
    "location": "AD- ABEOKUTA SMTO",
    "department": "ABEOKUTA SMTO",
    "driver_name": "KORODE LAWAL",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS168",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06043419",
    "engine_no": "8140685",
    "location": "LTA IBADAN",
    "department": "LTA IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS606N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL013062",
    "engine_no": "VF38D5GYAHL013062",
    "location": "AD/SSFMD",
    "department": "SSFMD",
    "driver_name": "WAHEED AFOLABI",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS146",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P306041754",
    "engine_no": "2TR-FE8121427",
    "location": "ABEOKUTA MSTO",
    "department": "ABEOKUTA MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS638",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803024002",
    "engine_no": "2ZRU345750",
    "location": "TC-MTO IBADAN",
    "department": "MTO",
    "driver_name": "ANGO LIMAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS807",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833766",
    "engine_no": "VF3DDNFPRDJ833766",
    "location": "H-LL&P IBADAN",
    "department": "SAO-OOO (LEGAL )",
    "driver_name": "DANIEL ONUMUN",
    "sco": "OOO"
  },
  {
    "license_plate": "RB889FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJX02P50506462",
    "engine_no": "2TR-FE0442815",
    "location": "LTO IBADAN",
    "department": "IBADAN LTO",
    "driver_name": "FD&E (IKARE MSTO) SC OOO",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS178",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E503009943",
    "engine_no": "2ZRU092946",
    "location": "DD - IBADAN",
    "department": "STATE ADMIN IBADAN",
    "driver_name": "AYODELE FLORENCE OYENIKE",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1354",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT351999",
    "engine_no": "S3LJ015",
    "location": "AD/TC,OTA, MSTO",
    "department": "AD/TC,OTA, MSTO",
    "driver_name": "KOLAWALE THOMAS O.",
    "sco": "OOO"
  },
  {
    "license_plate": "249FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03030920",
    "engine_no": "2ZRU503594",
    "location": "TC-OTA MSTO",
    "department": "OTA MSTO",
    "driver_name": "KOLAWOLE THOMAS OLUSEGUN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS50",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E500267671",
    "engine_no": "2710558",
    "location": "OSHOGBO MSTO",
    "department": "OSHOGBO MSTO",
    "driver_name": "MUSLIM AKEEM",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS903",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ874000",
    "engine_no": "VF3DDNFPRDJ874000",
    "location": "TC-OYO MSTO",
    "department": "OYO MSTO",
    "driver_name": "MAMUDA RUFAI",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1323",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNB19HK203207189",
    "engine_no": "JTNB19HK203207189",
    "location": "SC,OOO",
    "department": "SC,OOO",
    "driver_name": "OLUGBENGA GABRIEL D.",
    "sco": "OOO"
  },
  {
    "license_plate": "RB745FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "RZH114-7101664",
    "engine_no": "1RZ-3342838",
    "location": "SCO OOO IBADAN",
    "department": "SCO OOO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "RB883FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFX02P100009467",
    "engine_no": "422982",
    "location": "ADEOYO MSTO",
    "department": "ADEOYO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS129",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003009767",
    "engine_no": "2ZRU091424",
    "location": "SOUTH WEST REGIONAL AUDIT, SCO OOO IBADAN",
    "department": "SCO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS159",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003009784",
    "engine_no": "2ZRU090970",
    "location": "ADEOYO MSTO POOL",
    "department": "ADEOYO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS194",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203009964",
    "engine_no": "8135725",
    "location": "SCO OOO",
    "department": "SCO OOO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS174",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E503009912",
    "engine_no": "2ZRU092823",
    "location": "AD-HR ADVISOR",
    "department": "IWO ROAD MSTO",
    "driver_name": "ADENIYI JIMOH",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS175",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403009884",
    "engine_no": "2ZRU091733",
    "location": "SCO OOO",
    "department": "SCO OOO",
    "driver_name": "TAJUDEEN BASHIR",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS354",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "2ZE1427013186",
    "engine_no": "IZZA213348",
    "location": "LTO IBADAN",
    "department": "IBADAN LTO",
    "driver_name": "OLUFEMI OTULANA",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS366",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P706064809",
    "engine_no": "2TR 8192953",
    "location": "OSOGBO MSTO",
    "department": "OSOGBO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS367",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P906053441",
    "engine_no": "2TR 8169937",
    "location": "OYO MSTO",
    "department": "OYO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS598",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008021426",
    "engine_no": "2TR8268444",
    "location": "OTA MSTO",
    "department": "OTA MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS612",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P1A8019116",
    "engine_no": "2TR8237217",
    "location": "OSOGBO MSTO",
    "department": "OSOGBO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS632",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308023719",
    "engine_no": "8297729",
    "location": "IWO RD MSTO",
    "department": "IWO ROAD MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS634",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRXP108023041",
    "engine_no": "8286769",
    "location": "OTA MSTO",
    "department": "OTA MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS707/160FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208026854",
    "engine_no": "2TR8357468",
    "location": "SHAGAMU MSTO",
    "department": "SAGAMU MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS708/159FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208026918",
    "engine_no": "2TR8357751",
    "location": "MTO IBADAN",
    "department": "MTO IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS710/158FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026867",
    "engine_no": "2TR8356761",
    "location": "ADEOYO MSTO",
    "department": "ADEOYO MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS687/167FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908027757",
    "engine_no": "2TR8369186",
    "location": "ABEOKUTA SMTA",
    "department": "ABEOKUTA SMTA",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS799/196FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX008016814",
    "engine_no": "2TR 7362942",
    "location": "SCO OOO",
    "department": "SCO OOO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "240FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708034707",
    "engine_no": "2TR8496873",
    "location": "GBTO OGUN",
    "department": "OGUN GBTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "265FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408035331",
    "engine_no": "2TR8504446",
    "location": "GBTO OSUN",
    "department": "OSUN GBTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "307FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808036143",
    "engine_no": "2TR8518023",
    "location": "GBTO IBADAN",
    "department": "OYO GBTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS776",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308044487",
    "engine_no": "2TR8714836",
    "location": "DEBT MANAGEMENT IBADAN",
    "department": "SCO DMO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS372N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGSX22P2F6159136",
    "engine_no": "2TR8723379",
    "location": "LTO IBADAN",
    "department": "LTO IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1011",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFJXO2P905028626",
    "engine_no": "JTFJXO2P905028626",
    "location": "MTA IBADAN",
    "department": "MTA IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS368",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P806073342",
    "engine_no": "2TR 8234764",
    "location": "SHAGAMU MSTO",
    "department": "SAGAMU MSTO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS546",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108019717",
    "engine_no": "2TR8244735",
    "location": "LTA",
    "department": "SCO OOO",
    "driver_name": "SC OOO F&A",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS864",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518204023913",
    "engine_no": "2TR9003348",
    "location": "SCO OOO POOL IBADAN",
    "department": "SCO OOO",
    "driver_name": "SCO OOO POOL (STAFF BUS) IBADAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS583",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808020153",
    "engine_no": "8250775",
    "location": "OYO 2 MSTA",
    "department": "SCO OOO",
    "driver_name": "SCO OOO RAD&PROCUREMENT UNIT IBADAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS364",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P406073838",
    "engine_no": "2TR 8228260",
    "location": "ADEOYO MSTA",
    "department": "ADEOYO MSTA",
    "driver_name": "SW REG. TAX AUDIT",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS646",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803025733",
    "engine_no": "2ZRU394322",
    "location": "TAT IBADAN",
    "department": "TAT",
    "driver_name": "TAT",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS362N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ638035",
    "engine_no": "VF3DDNFPRDJ638035",
    "location": "TC-SAGAMU MSTO",
    "department": "SAGAMU MSTO",
    "driver_name": "UCHEGBU DONATUS NNABUIKE",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1429",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0DX9CD4P2529127",
    "engine_no": "MR0DX9CD4P2529127",
    "location": "OEC-FIRS POOL IBADAN",
    "department": "OEC-FIRS POOL IBADAN",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1455",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG8PN230023",
    "engine_no": "LNLG32AG8PN230023",
    "location": "MTO IBADAN",
    "department": "MTO IBADAN",
    "driver_name": "MTO IBADAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1457",
    "brand": "Nord",
    "model": "Tusk Truck",
    "vin_sn": "LDDC8B30GP0025354",
    "engine_no": "LDDC8B30GP0025354",
    "location": "SSFMD FIELD COORD",
    "department": "SSFMD FIELD COORD",
    "driver_name": "AFOLABI WAHEED",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS1140",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03MT454697",
    "engine_no": "4A92SKP837",
    "location": "AD/ TC,ASABA MSTO",
    "department": "AD/ TC,ASABA MSTO",
    "driver_name": "EKONG NSIKAK",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1349",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02RT352024",
    "engine_no": "S3LJ004",
    "location": "MTO PH",
    "department": "MTO PH",
    "driver_name": "DDT/TC/M. HUSSAIN",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1284",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05PT397598",
    "engine_no": "492S*53KL087",
    "location": "RUMUKWURUSHI ETA I",
    "department": "RUMUKWURUSHI ETA I",
    "driver_name": "ADT/NNANNA IKWUO O.",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1346",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT352022",
    "engine_no": "S3LJ018",
    "location": "LTO PH OIL & GAS",
    "department": "LTO PH OIL & GAS",
    "driver_name": "AD/TC/PHILIP ZAKKA",
    "sco": "RED"
  },
  {
    "license_plate": "344FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703034729",
    "engine_no": "2ZRU664667",
    "location": "DELTA GBO",
    "department": "DELTA GBO",
    "driver_name": "SM/AD/AGBO GERALD S.",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS853",
    "brand": "Toyota",
    "model": "Avensis",
    "vin_sn": "SBIBL76L50E040690",
    "engine_no": "2ZRB541402",
    "location": "HEAD- SPECIAL TAX AUDIT DEPT",
    "department": "SAO RED",
    "driver_name": "PETER ALFRED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1049",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02PXA5015476",
    "engine_no": "JTGJX02PXA5015476",
    "location": "RUMUKWURUSHI ETO II",
    "department": "RUMUKWURUSHI ETO II",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS314",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03017682",
    "engine_no": "2ZRU190923",
    "location": "EDO GBTO",
    "department": "EDO GBTO",
    "driver_name": "ABORISADE KEHINDE ADEBOSUN",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS130",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703009684",
    "engine_no": "2ZRU090949",
    "location": "DELTA GBTO",
    "department": "DELTA GBTO",
    "driver_name": "AGIRI OSAIN",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS806",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ830613",
    "engine_no": "VF3DDNFPRDJ830613",
    "location": "TC-MTA WARRI",
    "department": "MTA WARRI",
    "driver_name": "AUDU JOHNSON ONAH",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1081",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK6JR881613",
    "engine_no": "NC02H047388",
    "location": "BONNY ISLAND ETO",
    "department": "BONNY ISLAND ETO",
    "driver_name": "SM/TC/KAGBARA",
    "sco": "RED"
  },
  {
    "license_plate": "251FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903030892",
    "engine_no": "2ZRU504330",
    "location": "PH ETO III",
    "department": "PH ETO III",
    "driver_name": "BOMA SIAMINABO",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS135",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58EX03009973",
    "engine_no": "2ZRU092170",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS363N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ614539",
    "engine_no": "VF3DDNFPRDJ614539",
    "location": "PH ETO II",
    "department": "PH ETO II",
    "driver_name": "CHRISTOPHER ASHIGYE",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS732",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833762",
    "engine_no": "VF3DDNFPRDJ833762",
    "location": "TC-RUMUKWURUSHI MSTO 0",
    "department": "RUMUKWURUSHI MSTO 1",
    "driver_name": "DALHATU YUSUF",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS921",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ844224",
    "engine_no": "VF3DDNFPRDJ844224",
    "location": "AUCHI ETO",
    "department": "AUCHI ETO",
    "driver_name": "FAKOREDE",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS971",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ606739",
    "engine_no": "VF3DDNFPRGJ606739",
    "location": "LTA NON OIL",
    "department": "LTA NON OIL",
    "driver_name": "AD/TONY MOCHI",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS68",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTBR22E7032000049",
    "engine_no": "122F1794",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "ICT/HEAD ICT",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1369",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE6RD922725",
    "engine_no": "P3C1527380",
    "location": "AD/FMD,RED SCO",
    "department": "AD/FMD,RED SCO",
    "driver_name": "IFUEKO OMOREGIE",
    "sco": "RED"
  },
  {
    "license_plate": "336FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803034870",
    "engine_no": "2ZRU677371",
    "location": "LTO PH NON OIL",
    "department": "LTO PH NON OIL",
    "driver_name": "ADT/TC/CHARLES ILEKA",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS667",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE000002500",
    "engine_no": "2ZRU-782580",
    "location": "H-TID SOUTHERN DIV",
    "department": "SSTID",
    "driver_name": "IME IKPAISONG",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS802",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833840",
    "engine_no": "VF3DDNFPRDJ833840",
    "location": "H-SCO PH LL&P",
    "department": "SCO RED",
    "driver_name": "JOE NWOKOLOBIA",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS735/109FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303026157",
    "engine_no": "2ZRU397950",
    "location": "SAPELE ETO",
    "department": "SAPELE ETO",
    "driver_name": "MGR/AG TC/KENNEDY IYO",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS344",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E703034729",
    "engine_no": "AHTLC58E703034729",
    "location": "DELTA GBO",
    "department": "DELTA GBO",
    "driver_name": "SM/AD/AGBO GERALD S.",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS230",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC53E300009956",
    "engine_no": "2ZRU-093119",
    "location": "TC-BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "IFUEKO NEHIKHARE",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS435N",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPDHJ608390",
    "engine_no": "HJ608390",
    "location": "HEAD RVGBA",
    "department": "HEAD RVGBA",
    "driver_name": "DD/TC/KWAJAFFA",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1388",
    "brand": "Changan",
    "model": "Alsvin",
    "vin_sn": "LS5A2ASE4RD910850",
    "engine_no": "P3C1500423",
    "location": "LTO PH NON OIL",
    "department": "LTO PH NON OIL",
    "driver_name": "ADT/TC/MABEL IWELU",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1153",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z9NU006205",
    "engine_no": "L6T7722Z9NU006205",
    "location": "SCO-RED",
    "department": "SCO-RED",
    "driver_name": "MGT PROTOCOL",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS839/ FIRS 485",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303029060",
    "engine_no": "2ZRU459380",
    "location": "TC-BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "MOHAMMAD MUKHTAR JUNGUDO",
    "sco": "RED"
  },
  {
    "license_plate": "252FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E803030950",
    "engine_no": "2ZRU503933",
    "location": "PH ETO I",
    "department": "PH ETO I",
    "driver_name": "ADT/PAUL ANYEBE",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1079",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK8JR882584",
    "engine_no": "NC02H047376",
    "location": "AGBOR MSTO",
    "department": "AGBOR MSTO",
    "driver_name": "KOFFIE DAVID",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1289",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02PT397607",
    "engine_no": "492*53KL079",
    "location": "MTO WARRI",
    "department": "MTO WARRI",
    "driver_name": "ADT/TC/OKOEDION",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS966",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ597561",
    "engine_no": "VF3DDNFPRGJ597561",
    "location": "TC-RUMUKWURUSHI MSTO 0",
    "department": "RUMUKWURUSHI MSTO 1",
    "driver_name": "OKONAH EZEKIEL ASUQUO",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS269",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203010760",
    "engine_no": "2ZRU100622",
    "location": "MTA PH",
    "department": "MTA PH",
    "driver_name": "AD/HEAD/JAPHET",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS760",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ810414",
    "engine_no": "VF3DDNFPRDJ810414",
    "location": "AD-LOKOJA MSTO",
    "department": "LOKOJA MSTO",
    "driver_name": "DONGSON YAKI SANDA",
    "sco": "KNN"
  },
  {
    "license_plate": "RB070FG/ RB010FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "R-ZH114427103266",
    "engine_no": "RZE111467103266",
    "location": "BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "RB723FG",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "0.71027",
    "engine_no": "3375528",
    "location": "RUMUEME ETO",
    "department": "RUMUEME ETO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS148",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P106043650",
    "engine_no": "8141197",
    "location": "ASABA MSTO",
    "department": "ASABA MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS213",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTF5x2ZP406041309",
    "engine_no": "8135050",
    "location": "RUMUEME ETO",
    "department": "RUMUEME ETO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS215",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSx22P*06047556",
    "engine_no": "8098421",
    "location": "WARRI MSTO",
    "department": "WARRI MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS141",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "6043592",
    "engine_no": "8141019",
    "location": "AUCHI MSTO",
    "department": "AUCHI MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS153",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22PX06043811",
    "engine_no": "8141487",
    "location": "LTO PH NON OIL",
    "department": "LTO PH NON OIL",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS340",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G408007405",
    "engine_no": "2TR8200621",
    "location": "ENFORCEMENT UNIT PH",
    "department": "SCO RED",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS382",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608017770",
    "engine_no": "2TR 8225126",
    "location": "SAPELE MSTO",
    "department": "SAPELE MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS401",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08017738",
    "engine_no": "2TR8224872",
    "location": "ENUGU SAO",
    "department": "ENUGU SAO",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS404",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608017803",
    "engine_no": "2TR8225412",
    "location": "ASABA MSTO",
    "department": "ASABA MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS578",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608021091",
    "engine_no": "8204302",
    "location": "WARRI AUDIT",
    "department": "WARRI AUDIT",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS584",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408020182",
    "engine_no": "8251553",
    "location": "SCO PH LEGAL",
    "department": "SCO RED",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS599",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308022019",
    "engine_no": "2TR8262676",
    "location": "RUMUKWURUSHI ETO I",
    "department": "RUMUKWURUSHI ETO I",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS677/76FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108026232",
    "engine_no": "2TR8347275",
    "location": "MTO P/H",
    "department": "MTO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS713/75FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08025838",
    "engine_no": "2TR8341003",
    "location": "MTA PH",
    "department": "MTA PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS716/173FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22GX08012128",
    "engine_no": "2TR7148525",
    "location": "WARRI ENFORCEMENT UNIT",
    "department": "ENFORCEMENT UNIT",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS691/62FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908027788",
    "engine_no": "2TR8369896",
    "location": "RUMUKWURUSHI MSTO 2",
    "department": "RUMUKWURUSHI MSTO 2",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS695/65FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P608027778",
    "engine_no": "2TR8361768",
    "location": "BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS697/74FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108027770",
    "engine_no": "2TR8361764",
    "location": "PH ETO I",
    "department": "PH ETO I",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS822/44FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508031062",
    "engine_no": "2ZRU8440385",
    "location": "MTO PH",
    "department": "MTO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "201FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708035131",
    "engine_no": "2TR8502026",
    "location": "SCO RED",
    "department": "SCO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "245FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308034705",
    "engine_no": "2TR8496857",
    "location": "GBTO DELTA",
    "department": "DELTA GBTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "270FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908035325",
    "engine_no": "2TR8504368",
    "location": "RIVERS GBTO",
    "department": "PH GBTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "312FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P808036210",
    "engine_no": "2TR8519023",
    "location": "GBTO EDO",
    "department": "EDO GBTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "328FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908036216",
    "engine_no": "2TR8519069",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "352FIRS/FIRS692",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P508036584",
    "engine_no": "2TR8513203",
    "location": "LTO PH NON OIL",
    "department": "LTO PH NON OIL",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS681",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708038613",
    "engine_no": "2TR-8571362",
    "location": "LTA PH NON OIL",
    "department": "LTA PH NON OIL",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS767",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408044384",
    "engine_no": "2TR8711940",
    "location": "DMO POOL",
    "department": "DMO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS780",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208044481",
    "engine_no": "2TR8714583",
    "location": "PH ETA I",
    "department": "PH ETA I",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS785",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408044417",
    "engine_no": "2TR8713521",
    "location": "LTA PH",
    "department": "LTA PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS492N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308048927",
    "engine_no": "2TR9105680",
    "location": "MTO WARRI",
    "department": "MTO WARRI",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1001",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJXO2P360005862",
    "engine_no": "JTGJXO2P360005862",
    "location": "RED SCO-TIMO",
    "department": "RED SCO/TIMO",
    "driver_name": "TIMO",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1002",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P8A0028806",
    "engine_no": "JTGJX02P8A0028806",
    "location": "RUMUEME ETA",
    "department": "RUMUEME ETA",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1016",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P195010551",
    "engine_no": "JTGJX02P195010551",
    "location": "GTA RIVERS",
    "department": "GTA RIVERS",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1031",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFHX02P890039755",
    "engine_no": "JTFHX02P890039755",
    "location": "MTA WARRI",
    "department": "MTA WARRI",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1039",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02PXB0035905",
    "engine_no": "JTGJX02PXB0035905",
    "location": "PH ETO II",
    "department": "PH ETO II",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1047",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGJX02P1A0028985",
    "engine_no": "JTGJX02P1A0028985",
    "location": "RUMUKWURUSHI ETO III",
    "department": "RUMUKWURUSHI ETO III",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1233",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308050001",
    "engine_no": "JTFRX12P308050001",
    "location": "AUCHI ETO",
    "department": "AUCHI ETO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1258",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP8N6015175",
    "engine_no": "7GR-FKS3456",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS865",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518904022600",
    "engine_no": "2TR8714717",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "STAFF BUS",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS644",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTL58E703025738",
    "engine_no": "2ZRU389906",
    "location": "TAT BENIN",
    "department": "TAT",
    "driver_name": "TAT",
    "sco": "RED"
  },
  {
    "license_plate": "311FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308036101",
    "engine_no": "2TR8517267",
    "location": "ABIA GBO",
    "department": "ABIA GBO",
    "driver_name": "ABIA GBO",
    "sco": "EEA"
  },
  {
    "license_plate": "246FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P308035305",
    "engine_no": "2TR8504088",
    "location": "ENUGU GBO",
    "department": "ENUGU GBO",
    "driver_name": "ENUGU GBO",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1070",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK5HR879006",
    "engine_no": "A151E-1-NCO2H058321",
    "location": "ONNE ETO",
    "department": "ONNE ETO",
    "driver_name": "SM/TC/SHEHU",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS310",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303015739",
    "engine_no": "2ZRU144572",
    "location": "RUMUKWURUSHI ETO II",
    "department": "RUMUKWURUSHI ETO II",
    "driver_name": "ADT/TC/USMAN",
    "sco": "RED"
  },
  {
    "license_plate": "231FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E003030005",
    "engine_no": "2ZRU483091",
    "location": "TC-RUMUKWURUSHI MSTO 2",
    "department": "RUMUKWURUSHI MSTO 3",
    "driver_name": "YUSUFU IBRAHIM",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1288",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE02PT387854",
    "engine_no": "4A92*53KL075",
    "location": "WARRI SMTO/TEMPORARY",
    "department": "WARRI SMTO/TEMPORARY",
    "driver_name": "AD/SS/SE CORD/ANGELA",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1389",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BX8CD102788178",
    "engine_no": "MR0BX8CD102788178",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "SSFMD OP",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1452",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32AG2PN230003",
    "engine_no": "LNLG32AG2PN230003",
    "location": "LTA/ PORT HARCOURT",
    "department": "LTA/ PORT HARCOURT",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS211",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E903009847",
    "engine_no": "AHTLC58E903009847",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "REPAIR IN PROGRESS",
    "sco": "RED"
  },
  {
    "license_plate": "213FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC5BE00303005",
    "engine_no": "AHTLC5BE00303005",
    "location": "RUMUKWURUSHI ETO III",
    "department": "RUMUKWURUSHI ETO III",
    "driver_name": "YUSUFU IBRAHIM",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS 215",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTR-SX22PX06041556",
    "engine_no": "JTR-SX22PX06041556",
    "location": "WARRI MSTO",
    "department": "WARRI MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS57",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDR022E400249985",
    "engine_no": "JTDR022E400249985",
    "location": "WARRI MSTO",
    "department": "WARRI MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1076",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK8HR878304",
    "engine_no": "NC02H051281",
    "location": "HEAD-ANYIGBA STO",
    "department": "STO",
    "driver_name": "MOHAMMED SANI IBRAHIM",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS618N",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP7L6003032",
    "engine_no": "6003032",
    "location": "OECFIRS POOL",
    "department": "OECFIRS POOL",
    "driver_name": "OECFIRS MINNA POOL",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS131",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "105043647",
    "engine_no": "8141338",
    "location": "LOKOJA MSTO",
    "department": "LOKOJA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS548",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P708018040",
    "engine_no": "2TR8227462",
    "location": "MINNA MSTO",
    "department": "MINNA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS657/70FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P908024955",
    "engine_no": "8323352",
    "location": "LOKOJA MSTO",
    "department": "LOKOJA MSTO",
    "driver_name": "",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS1077",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK3HR879134",
    "engine_no": "LNBMDBAK3HR879134",
    "location": "TC-BIDA MSTO",
    "department": "BIDA MSTO",
    "driver_name": "SAIDU ADO ALLAWA",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS507N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCA GL032060",
    "engine_no": "GL032060",
    "location": "AD,LTA SULEJA",
    "department": "SMTA",
    "driver_name": "SULEIMAN U. TANKO",
    "sco": "KNN"
  },
  {
    "license_plate": "FIRS505N",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MRDHX8CD7H0911824",
    "engine_no": "MRDHX8CD7H0911824",
    "location": "SCO/ NKN",
    "department": "NKN",
    "driver_name": "SCO - NKN",
    "sco": "NKN"
  },
  {
    "license_plate": "FIRS823/45FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408031490",
    "engine_no": "2ZRU8447349",
    "location": "SOKOTO DEBT MANAGEMENT OFFICE/SOKOTO",
    "department": "SOKOTO DMO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1202",
    "brand": "Geely",
    "model": "Coolray",
    "vin_sn": "LB37622ZXNX404755",
    "engine_no": "3G15TD-5600006",
    "location": "STATE ADMINISTRATOR SKZ/GUSAU",
    "department": "SKZ SAO",
    "driver_name": "HAMZA SHEHU",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS193",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E203009832",
    "engine_no": "922541",
    "location": "TC-BIRNIN KEBBI ETO/BIRNIN-KEBBI",
    "department": "BIRNIN KEBBI ETO",
    "driver_name": "ABUBAKAR A. ISAH",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1213",
    "brand": "Geely",
    "model": "Saloon Emgrand7",
    "vin_sn": "L6T7824Z3MW036118",
    "engine_no": "4GI5-4917037",
    "location": "STATE MONITOR/SOKOTO GBO",
    "department": "SOKOTO GBO",
    "driver_name": "HARUNA MUHAMMED DAURA",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS151",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E403009786",
    "engine_no": "8131635",
    "location": "SOKOTO ETA/SOKOTO",
    "department": "SOKOTO ETA",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS200",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFSX22P606042123",
    "engine_no": "8137223",
    "location": "BIRNIN KEBBI ETO/BIRNIN-KEBBI",
    "department": "BIRNIN KEBBI ETO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS324",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX 12P108017692",
    "engine_no": "8224513",
    "location": "SOKOTO ETO/SOKOTO",
    "department": "SOKOTO ETO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS615",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P0A8019060",
    "engine_no": "2TR8236621",
    "location": "GUSAU ETO/GUSAU",
    "department": "GUSAU ETO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS682/58FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P008026223",
    "engine_no": "2TR8348534",
    "location": "SOKOTO ETO/SOKOTO",
    "department": "SOKOTO ETO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS668/146FIRS",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX22G08011875",
    "engine_no": "2TR133898",
    "location": "SKZ SAO/GUSAU",
    "department": "SKZ SAO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1505",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E7TA941935",
    "engine_no": "LS4ASE2E7TA941935",
    "location": "DD,TECHNICAL, OECFIRS",
    "department": "OECFIRS",
    "driver_name": "MAKINDE OLAOLU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1587",
    "brand": "Electric",
    "model": "Bus",
    "vin_sn": "LCD2A6D53P1000890",
    "engine_no": "LCD2A6D53P1000890",
    "location": "KUBWA F01 ROUTE BUS",
    "department": "KUBWA F01 ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1586",
    "brand": "Electric",
    "model": "Bus",
    "vin_sn": "LCD2A6D55P1000826",
    "engine_no": "LCD2A6D55P1000826",
    "location": "DAKWA ROUTE BUS",
    "department": "DAKWA ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1585",
    "brand": "Electric",
    "model": "Bus",
    "vin_sn": "LCD2A6D5XP1000811",
    "engine_no": "LCD2A6D5XP1000811",
    "location": "KARU JIKWOI ROUTE BUS",
    "department": "KARU JIKWOI ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1584",
    "brand": "Electric",
    "model": "Bus",
    "vin_sn": "LCD2A6D55P1000891",
    "engine_no": "LCD2A6D55P1000891",
    "location": "GWARINPA ROUTE BUS",
    "department": "GWARINPA ROUTE BUS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1576",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E0SA945713",
    "engine_no": "LS4ASE2E0SA945713",
    "location": "DD/OCD SPECIAL DUTIES",
    "department": "",
    "driver_name": "KAYODE BALOGUN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1595",
    "brand": "Toyota",
    "model": "Granvia",
    "vin_sn": "JTNYM3AP7P8002145",
    "engine_no": "JTNYM3AP7P8002145",
    "location": "SINGLE WINDOW PROJECT",
    "department": "SINGLE WINDOW POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1594",
    "brand": "Toyota",
    "model": "Granvia",
    "vin_sn": "JTNYM3AP9R8003834",
    "engine_no": "JTNYM3AP9R8003834",
    "location": "SINGLE WINDOW PROJECT",
    "department": "SINGLE WINDOW POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1593",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAX9AJ60K004856",
    "engine_no": "JTEAX9AJ60K004856",
    "location": "",
    "department": "",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1592",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMAUBBJ8S4094778",
    "engine_no": "JTMAUBBJ8S4094778",
    "location": "GD-FINANCE SERVICES",
    "department": "KOLADE OLA",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1591",
    "brand": "Misc",
    "model": "Fire Truck",
    "vin_sn": "LZGJDDN14SX038965",
    "engine_no": "LZGJDDN14SX038965",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1590",
    "brand": "Misc",
    "model": "Fire Truck",
    "vin_sn": "LZGJDDN14SX038966",
    "engine_no": "LZGJDDN14SX038966",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1589",
    "brand": "Innoson",
    "model": "Ambulance",
    "vin_sn": "JTGHN9CPX56034077",
    "engine_no": "JTGHN9CPX56034077",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1588",
    "brand": "Innoson",
    "model": "Ambulance",
    "vin_sn": "JTGHN9CPX56029428",
    "engine_no": "JTGHN9CPX56029428",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1575",
    "brand": "Sino",
    "model": "Truck",
    "vin_sn": "LEZAD1EC3SF139979",
    "engine_no": "LEZAD1EC3SF139979",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1574",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BU8CD5S0107527",
    "engine_no": "MR0BU8CD5S0107527",
    "location": "OGD-F&C",
    "department": "OGD-F&C",
    "driver_name": "JAMES ADEKUNLE OGIDI",
    "sco": "HQ"
  },
  {
    "license_plate": "314FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408036222",
    "engine_no": "2TR8518704",
    "location": "SOKOTO GBO/SOKOTO",
    "department": "SOKOTO GBO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "315FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P408036091",
    "engine_no": "2TR8517158",
    "location": "KEBBI GBO/BIRNIN-KEBBI",
    "department": "KEBBI GBO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1566",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTKX80DX02264609",
    "engine_no": "AHTKX80DX02264609",
    "location": "SS&FMD OPERATIONAL VEHICLE",
    "department": "SS&FMD OPERATIONAL VEHICLE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1565",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTKX8CDX02264576",
    "engine_no": "AHTKX8CDX02264576",
    "location": "SS&FMD OPERATIONAL VEHICLE",
    "department": "SS&FMD OPERATIONAL VEHICLE",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1564",
    "brand": "Nord",
    "model": "A9 Suv",
    "vin_sn": "LUYDB2G23SA011298",
    "engine_no": "LUYDB2G23SA011298",
    "location": "UNION CHAIRMAN",
    "department": "UNION CHAIRMAN",
    "driver_name": "LEKWOT THOMAS FRIDAY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1563",
    "brand": "Nord",
    "model": "A9 Suv",
    "vin_sn": "LUYDB2G33SA011309",
    "engine_no": "LUYDB2G33SA011309",
    "location": "DD-COMMUNICATION",
    "department": "COMMUNICATIO DEPT",
    "driver_name": "EMMANUELLA ETETA- ITA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1562",
    "brand": "Nord",
    "model": "A9 Suv",
    "vin_sn": "LUYDB2G38SA011306",
    "engine_no": "LUYDB2G38SA011306",
    "location": "DD-LITIGATION & PROSECUT",
    "department": "LITIGATION & PROSECUT",
    "driver_name": "NNEKA CECILIA ESOMEJU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1561",
    "brand": "Nord",
    "model": "A9 Suv",
    "vin_sn": "LUYDB2G23SA011303",
    "engine_no": "LUYDB2G23SA011303",
    "location": "DD-FACILITY DEPARTMENT",
    "department": "FACILITY DEPARTMENT",
    "driver_name": "ADEDEJI AKANDE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1560",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E4SA945519",
    "engine_no": "LS4ASE2E4SA945519",
    "location": "DD-OCD MTG",
    "department": "OCD MTG",
    "driver_name": "MICHEAL OSE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1559",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E2SA945504",
    "engine_no": "LS4ASE2E2SA945504",
    "location": "DD-ACTU",
    "department": "ACTU",
    "driver_name": "ADOFU OBAJE NAPOLEON",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1558",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E8SA945717",
    "engine_no": "LS4ASE2E8SA945717",
    "location": "SA-TO ECFIRS",
    "department": "OECFIRS",
    "driver_name": "MOHAMMED BAGUDU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1557",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E8SA945507",
    "engine_no": "LS4ASE2E8SA945507",
    "location": "DD-GBO ABUJA",
    "department": "GBO ABUJA",
    "driver_name": "HADIZA UKACHUKWU",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1556",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E3SA945513",
    "engine_no": "LS4ASE2E3SA945513",
    "location": "DD-HCMD",
    "department": "HCMD",
    "driver_name": "BEMISOLA SALAKO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1555",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2EXSA945511",
    "engine_no": "LS4ASE2EXSA945511",
    "location": "DD-OSA-SPECIAL DUTIES",
    "department": "OSA-SPECIAL DUTIES",
    "driver_name": "ADEGOKE OLANIKE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1554",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E1SA945476",
    "engine_no": "LS4ASE2E1SA945476",
    "location": "SA-BROADCAST MEDIA",
    "department": "BROADCAST MEDIA",
    "driver_name": "ADERONKE BELLO",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1553",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E8SA945698",
    "engine_no": "LS4ASE2E8SA945698",
    "location": "DD, MTO 2 LAGOS",
    "department": "MTO 2 LAGOS",
    "driver_name": "OGUNMODEDE BAMIDELE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1552",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAACAJ805009196",
    "engine_no": "JTEAACAJ805009196",
    "location": "OECFIRS POOL",
    "department": "OEC-FIRS",
    "driver_name": "ALEX",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1551",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG6SN000047",
    "engine_no": "LNLG32DG6SN000047",
    "location": "JOINT REVENUE BOARD",
    "department": "JOINT REVENUE BOARD",
    "driver_name": "",
    "sco": ""
  },
  {
    "license_plate": "FIRS1550",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG9SN000043",
    "engine_no": "LNLG32DG9SN000043",
    "location": "RESOURCE ROYALTY DEPT",
    "department": "RESOURCE ROYALTY DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1543",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP6S6030382",
    "engine_no": "JTGHN9CP6S6030382",
    "location": "OED,GOVERNMENT AND LARGE TAX PAYERS",
    "department": "OED-GOVERNMENT AND LARGE",
    "driver_name": "OED-GOVERNMENT & LARGE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1540",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CP3S56031831",
    "engine_no": "JTGHN9CP3S56031831",
    "location": "PROCUREMENT DEPT",
    "department": "PROCUREMENT DEPT POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "317FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P108036209",
    "engine_no": "2TR8518849",
    "location": "SKZ SAO/GUSAU",
    "department": "SKZ SAO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1538",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT396488",
    "engine_no": "LGJF1FE00RT396488",
    "location": "AD-OECFIRS",
    "department": "AD-OECFIRS",
    "driver_name": "MARIAM ALGAZLI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1537",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE05RT358433",
    "engine_no": "LGJF1FE05RT358433",
    "location": "TA-IFRASTRUCTURE",
    "department": "TA-INFRASTRUCTURE",
    "driver_name": "FASUNLORO OLUGBENGA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1536",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XRT358427",
    "engine_no": "LGJF1FE0XRT358427",
    "location": "TA-OECFIRS",
    "department": "TA-OECFIRS",
    "driver_name": "OLANIRAN GBADEBOR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1535",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT358439",
    "engine_no": "LGJF1FE06RT358439",
    "location": "AD-CUSTOM LIASON",
    "department": "AD-CUSTOMS LIASON",
    "driver_name": "VICTORIA UDO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1534",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT358415",
    "engine_no": "LGJF1FE03RT358415",
    "location": "SA- TAX POLICY",
    "department": "SA-TAX POLICY",
    "driver_name": "FEMI OLARINDE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1533",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT358429",
    "engine_no": "LGJF1FE03RT358429",
    "location": "AD,PROCUREMENT",
    "department": "AD,PROCUREMENT",
    "driver_name": "MISAL SAMUEL GABRIEL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1532",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE09RT358435",
    "engine_no": "LGJF1FE09RT358435",
    "location": "TC, ISOLO",
    "department": "TC, ISOLO",
    "driver_name": "EFIOM FRANCIS",
    "sco": "LMW"
  },
  {
    "license_plate": "321FIRS",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12PX08036225",
    "engine_no": "2TR8519130",
    "location": "ZAMFARA GBO/GUSAU",
    "department": "ZAMFARA GBO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1530",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT358438",
    "engine_no": "LGJF1FE04RT358438",
    "location": "TC, SABA ETO",
    "department": "TC ,ASABA ETO",
    "driver_name": "YUSUF YA'U",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1529",
    "brand": "Honda",
    "model": "Crv",
    "vin_sn": "MRHRS4868SP040093",
    "engine_no": "MRHRS4868SP040093",
    "location": "SA-POLICY & STRATEGY",
    "department": "SA-POLICY & STRATEGY",
    "driver_name": "TELEOLA OYEGOKE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1528",
    "brand": "Honda",
    "model": "Crv",
    "vin_sn": "MRHRS4863SP040101",
    "engine_no": "MRHRS4863SP040101",
    "location": "D-HUMAN CAPITAL",
    "department": "D-HUMAN CAPITAL",
    "driver_name": "FATIMA KAKURI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1527",
    "brand": "Honda",
    "model": "Crv",
    "vin_sn": "2HKRS6H94PHZ05860",
    "engine_no": "2HKRS6H94PHZ05860",
    "location": "SA-RESEACH & STATISTIC",
    "department": "SA-RESEACH & STATISTIC",
    "driver_name": "AISHA MAHMOUD HAMMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1526",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAACAJISK020786",
    "engine_no": "JTEAACAJISK020786",
    "location": "D,PROCUREMENT DEPT",
    "department": "D,PROCUREMENT DEPT",
    "driver_name": "MOHAMMED ALIKO AISHA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1525",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAX9AJ70K004087",
    "engine_no": "JTEAX9AJ70K004087",
    "location": "D,F&A",
    "department": "D, F&A",
    "driver_name": "OLUWOYE MUSA ADESHINA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1524",
    "brand": "Toyota",
    "model": "Prado",
    "vin_sn": "JTEAA9AJ70K020436",
    "engine_no": "JTEAA9AJ70K020436",
    "location": "D-SS&FMD",
    "department": "D-SS&FMD",
    "driver_name": "GREGORY ASUQUO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1523",
    "brand": "Dongfeng",
    "model": "T5 Evo",
    "vin_sn": "LMXA14AF3RZ438025",
    "engine_no": "LMXA14AF3RZ438025",
    "location": "DD-F&A",
    "department": "DD-F&A",
    "driver_name": "WASIU ASHA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1522",
    "brand": "Dongfeng",
    "model": "T5 Evo",
    "vin_sn": "LMXA14AF1RZ438024",
    "engine_no": "LMXA14AF1RZ438024",
    "location": "DD, SS&FMD",
    "department": "DD-SS&FMD",
    "driver_name": "MUHAMMAD IDA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS919",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ888894",
    "engine_no": "VF3DDNFPRDJ888894",
    "location": "TC-GUSAU ETO/GUSAU",
    "department": "GUSAU ETO",
    "driver_name": "SULEIMAN SIRAJO",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1520",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE03RT396520",
    "engine_no": "LGJF1FE03RT396520",
    "location": "TC/PORT-HARCOURT ETO",
    "department": "TC/PORT-HARCOURT ETO",
    "driver_name": "OMINI MICHEAL",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS1519",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE06RT396530",
    "engine_no": "LGJF1FE06RT396530",
    "location": "AD-PROCUREMENT",
    "department": "AD-PROCUREMENT",
    "driver_name": "OLANREWAJU A AYINLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1518",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE08RT396528",
    "engine_no": "LGJF1FE08RT396528",
    "location": "AD-PROCUREMENT",
    "department": "AD-PROCUREMENT",
    "driver_name": "AKINWEHINMI SAMUEL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1517",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XRT358413",
    "engine_no": "LGJF1FE0XRT358413",
    "location": "AD/ IAD",
    "department": "AD/IAD",
    "driver_name": "ATTAHIRU YUSUF MAIYAKI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS922",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ833770",
    "engine_no": "VF3DDNFPRDJ833770",
    "location": "STATE MONITOR/ZAMFARA GBO/GUSAU",
    "department": "ZAMFARA GBO",
    "driver_name": "UMAR MUAZU MARAFA",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS614",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12PA48019319",
    "engine_no": "2TR8239220",
    "location": "BIRNIN KEBBI ETO/BIRNIN-KEBBI",
    "department": "BIRNIN KEBBI ETO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS260",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58F003009980",
    "engine_no": "A151N600822",
    "location": "SKZ SAO/KANO",
    "department": "SKZ SAO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1513",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE0XRT396501",
    "engine_no": "LGJF1FE0XRT396501",
    "location": "TA-OECFIRS",
    "department": "OECFIRS",
    "driver_name": "ALIYU ABBA GABASAWA",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS1512",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE04RT358424",
    "engine_no": "LGJF1FE04RT358424",
    "location": "AD/LTA NON OIL",
    "department": "LTA",
    "driver_name": "OLOSUNDE OLUBUNMI",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS1511",
    "brand": "Innoson",
    "model": "Caris",
    "vin_sn": "LGJF1FE00RT396507",
    "engine_no": "LGJF1FE00RT396507",
    "location": "TA/PRINT MEDIA, OECFIRS",
    "department": "OECFIRS",
    "driver_name": "SIKIRU AKINOLA",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1510",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "MR0BUBCDXS0107233",
    "engine_no": "MR0BUBCDXS0107233",
    "location": "OECFIRS ESCORT",
    "department": "OECFIRS",
    "driver_name": "OECFIRS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1509",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E1SA940410",
    "engine_no": "LS4ASE2E1SA940410",
    "location": "DD/HCMD",
    "department": "HCMD",
    "driver_name": "AYENI TITUS",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1508",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E6SA940466",
    "engine_no": "LS4ASE2E6SA940466",
    "location": "DD/ECFIRS-COMMUNICATION",
    "department": "OECFIRS",
    "driver_name": "COLLINS O OMOKARO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1507",
    "brand": "Toyota",
    "model": "Land Cruiser",
    "vin_sn": "JTMABCBJ4R4174794",
    "engine_no": "JTMABCBJ4R4174794",
    "location": "OEC NRS POOL",
    "department": "OEC NRS POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1506",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E7SA940220",
    "engine_no": "LS4ASE2E7SA940220",
    "location": "DD,HCMD",
    "department": "HCMD",
    "driver_name": "SA'AD LAWAL SULEIMAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1583",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E2SA945440",
    "engine_no": "LS4ASE2E2SA945440",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1582",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E9SA945743",
    "engine_no": "LS4ASE2E9SA945743",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1581",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E1SA945719",
    "engine_no": "LS4ASE2E1SA945719",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1580",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E3SA945432",
    "engine_no": "LS4ASE2E3SA945432",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1579",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E3SA945723",
    "engine_no": "LS4ASE2E3SA945723",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1578",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E5SA945514",
    "engine_no": "LS4ASE2E5SA945514",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1577",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E5SA945450",
    "engine_no": "LS4ASE2E5SA945450",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1571",
    "brand": "Changan",
    "model": "Cs55 Plus",
    "vin_sn": "LS4ASE2E1TA943406",
    "engine_no": "LS4ASE2E1TA943406",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1570",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8506510660",
    "engine_no": "JTGAKAB8506510660",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1569",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8706510384",
    "engine_no": "JTGAKAB8706510384",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1568",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8106510378",
    "engine_no": "JTGAKAB8106510378",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1567",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGAKAB8006510727",
    "engine_no": "JTGAKAB8006510727",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1549",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG2RN000301",
    "engine_no": "LNLG32DG2RN000301",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1548",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG4RN000302",
    "engine_no": "LNLG32DG4RN000302",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1547",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG8RN000304",
    "engine_no": "LNLG32DG8RN000304",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1546",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG0SN000044",
    "engine_no": "LNLG32DG0SN00044",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1545",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG5RN000308",
    "engine_no": "LNLG32DG5RN000308",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1544",
    "brand": "Nord",
    "model": "Flit Bus",
    "vin_sn": "LNLG32DG8SN000048",
    "engine_no": "LNLG32DG8SN000048",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1542",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CPXS6028246",
    "engine_no": "JTGHN9CPXS6028246",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1541",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGHN9CPXS6029428",
    "engine_no": "JTGHN9CPXS6029428",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1596",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK6S3012706",
    "engine_no": "JTNA14CK6S3012706",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1597",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK6S3016500",
    "engine_no": "JTNA14CK6S3016500",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1598",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CKXS3015964",
    "engine_no": "JTNA14CKXS3015964",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1599",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK9S3016023",
    "engine_no": "JTNA14CK9S3016023",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1600",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK9S3025899",
    "engine_no": "JTNA14CK9S3025899",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1601",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CKXS3025331",
    "engine_no": "JTNA14CKXS3025331",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1602",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CKXS3027810",
    "engine_no": "JTNA14CKXS3027810",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1603",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK6S3016920",
    "engine_no": "JTNA14CK6S3016920",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1604",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNA14CK7S3026257",
    "engine_no": "JTNA14CK7S3026257",
    "location": "NEW SUPPLY",
    "department": "AWAITING ALLOCATION",
    "driver_name": "AWAITING ALLOCATION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS390",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DRFJE 85157840",
    "engine_no": "VF 33DRFJE 85157840",
    "location": "S&SM UNIT ABC SCO",
    "department": "SCO ABC",
    "driver_name": "SS&FM UNIT",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS105",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DTFJE5147729",
    "engine_no": "VF33DTFJE5147729",
    "location": "CALABAR STAMP DUTIES",
    "department": "CALABAR STAMP DUTIES",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS385",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157864",
    "engine_no": "VF 33DRFJE 85157864",
    "location": "STAMP DUTIES UYO",
    "department": "UYO STAMP DUTIES",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS480",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64240983",
    "engine_no": "UF3XCRFHB64240983",
    "location": "CALABAR MSTO",
    "department": "CALABAR MSTO",
    "driver_name": "",
    "sco": "ABC"
  },
  {
    "license_plate": "FIRS278",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157865",
    "engine_no": "VF33DRFJE85157865",
    "location": "SAO BBY",
    "department": "SAO BBY",
    "driver_name": "SSM-BBY",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS374",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DR5E 85156655",
    "engine_no": "VF 33DR5E 85156655",
    "location": "SAO BBY",
    "department": "SAO BBY",
    "driver_name": "SAO BBY POOL",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS457",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64240360",
    "engine_no": "UF3XCRFHB64240360",
    "location": "Borno ETA",
    "department": "Borno ETA",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS459",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64238986",
    "engine_no": "UF3XCRFHB64238986",
    "location": "SAO BBY",
    "department": "SAO BBY",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS465",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244687",
    "engine_no": "UF3XCRFHB64244687",
    "location": "BAUCHI MSTO",
    "department": "BAUCHI MSTO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "RB825FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64190792",
    "engine_no": "64190792",
    "location": "ZARIA MSTO",
    "department": "ZARIA MSTO",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS302",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157836",
    "engine_no": "VF33DRFJE85157836",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS282",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64251566",
    "engine_no": "VF3XDRFHB64251566",
    "location": "SCO BKP",
    "department": "SCO BKP",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS288",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64247528",
    "engine_no": "VF3XDRFHB64247528",
    "location": "TAT-KADUNA",
    "department": "KADUNA",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS289",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252154",
    "engine_no": "VF3XDRFHB64252154",
    "location": "TAT- JOS",
    "department": "TAT",
    "driver_name": "",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS725/154FIRS",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW9K456810",
    "engine_no": "VF33DN6AW9K456810",
    "location": "BKP SCOO",
    "department": "SCO BKP",
    "driver_name": "KBN SCOO POOL",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS59",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "86319919",
    "engine_no": "86319919",
    "location": "GARKI MSTO POOL",
    "department": "GARKI MSTO POOL",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "RB875FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64190791",
    "engine_no": "64190791",
    "location": "LTA ABUJA",
    "department": "LTA ABUJA",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS469",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244690",
    "engine_no": "UF3XCRFHB64244690",
    "location": "WUSE MSTO",
    "department": "WUSE MSTO",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS483",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64241586",
    "engine_no": "UF3XCRFHB64241586",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS461",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64240367",
    "engine_no": "UF3XCRFHB64240367",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "FKN"
  },
  {
    "license_plate": "FIRS114",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DDRFJE5147305",
    "engine_no": "VF33DDRFJE5147305",
    "location": "",
    "department": "JALINGO GBTA",
    "driver_name": "ISHAYA ELIJAH",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS272",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252569",
    "engine_no": "VF3XDRFHB64252569",
    "location": "ENUGU MSTO",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS299",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157823",
    "engine_no": "VF33DRFJE85157823",
    "location": "SCO EEA",
    "department": "SCO EEA",
    "driver_name": "",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS294",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85147297",
    "engine_no": "85147297",
    "location": "HEAD, MSTA,ONITSHA",
    "department": "ONITSHA SMTA",
    "driver_name": "UCHE OHAEGBULAM",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS443",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087066",
    "engine_no": "VF33DN6AW91087066",
    "location": "Disband office",
    "department": "Disband office",
    "driver_name": "SAO-BBT Pool",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS728/152FIRS",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW1087462",
    "engine_no": "VF33DN6AW1087462",
    "location": "DAMATURU ETO",
    "department": "DAMATURA ETO",
    "driver_name": "",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS426",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VT33DN6AW91087034",
    "engine_no": "VT33DN6AW91087034",
    "location": "STAMP DUTIES JOS",
    "department": "STAMP DUTIES JOS",
    "driver_name": "JOS",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS292",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252575",
    "engine_no": "VF3XDRFHB64252575",
    "location": "TAT-NORTH-CENTRAL",
    "department": "TAT",
    "driver_name": "TAT",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS723/153FIRS",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AWK456800",
    "engine_no": "VF33DN6AWK456800",
    "location": "KADUNA STAMP DUTY",
    "department": "KADUNA STAMP DUTY",
    "driver_name": "YAKUBBU MOHAMMED",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS64",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3BRDFNG-86320853",
    "engine_no": "86320853",
    "location": "FKN SCO POOL",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS274",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64246953",
    "engine_no": "VF3XDRFHB64246953",
    "location": "INTERNAL AFFAIRS SCO FKN",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS298",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157839",
    "engine_no": "VF33DRFJE85157839",
    "location": "FKN SCO POOL",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS447",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087067",
    "engine_no": "VF33DN6AW91087067",
    "location": "FKN SCO POOL",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS448",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087059",
    "engine_no": "VF33DN6AW91087059",
    "location": "FKN SCO SFO",
    "department": "SCO FKN",
    "driver_name": "",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS470",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244684",
    "engine_no": "UF3XCRFHB64244684",
    "location": "MAITAMA MSTO",
    "department": "MAITAMA MSTO",
    "driver_name": "UNDER REPAIR",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS290",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252873",
    "engine_no": "VF3XDRFHB64252873",
    "location": "KUBWA CHIKAKWERE ROUTE",
    "department": "SSFMD GENERAL ROUTE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS25",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64189665",
    "engine_no": "64189665",
    "location": "TAX DATA MGT DEPARTMENT",
    "department": "TDMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS434",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087044",
    "engine_no": "VF33DN6AW91087044",
    "location": "JOURNEY AND FUELLING UNIT,SSFMD",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS435",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087064",
    "engine_no": "VF33DN6AW91087064",
    "location": "HCM- PROMOTION",
    "department": "HCMD",
    "driver_name": "AMBROSE APOLLO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS300",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157822",
    "engine_no": "VF33DRFJE85157822",
    "location": "SSFMD POOL",
    "department": "POOL",
    "driver_name": "GENERAL FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS444",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087038",
    "engine_no": "VF33DN6AW91087038",
    "location": "SSFMD POOL",
    "department": "SSFMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS280",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157882",
    "engine_no": "VF33DRFJE85157882",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "GENERAL POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS450",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087050",
    "engine_no": "VF33DN6AW91087050",
    "location": "M-ER&D HCMD",
    "department": "HCMD",
    "driver_name": "ISOKEN UKPOMWAN",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS429",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087060",
    "engine_no": "VF33DN6AW91087060",
    "location": "SS&FMD-CMAU",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS375",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DR5E 85156893",
    "engine_no": "VF 33DR5E 85156893",
    "location": "PMO",
    "department": "PMO",
    "driver_name": "KAMALU MCDONALD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS430",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087049",
    "engine_no": "VF33DN6AW91087049",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS388",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DRFJE 85157817",
    "engine_no": "VF 33DRFJE 85157817",
    "location": "OCD - LTG",
    "department": "CD LTG POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS440",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087046",
    "engine_no": "VF33DN6AW91087046",
    "location": "POLICE ENFORCEMENT UNIT",
    "department": "PEU",
    "driver_name": "PEU",
    "sco": "HQ"
  },
  {
    "license_plate": "RB871FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VP3XDRP415846",
    "engine_no": "64188496",
    "location": "GENERAL FLEET POOL",
    "department": "SSFMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS61",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "86320286",
    "engine_no": "86320286",
    "location": "LEGAL",
    "department": "LEGAL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS89",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64186204",
    "engine_no": "64186204",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "RB835FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "64188496",
    "engine_no": "64188496",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS04A",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64191366",
    "engine_no": "64191366",
    "location": "PRS POOL",
    "department": "PRS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS112",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "5147720",
    "engine_no": "5147720",
    "location": "COMMUNICATION AND SERVICOM",
    "department": "CLD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS73",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VFX3DRFHB64186205",
    "engine_no": "64186205",
    "location": "FOMD",
    "department": "FOMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS271",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64251563",
    "engine_no": "VF3XDRFHB64251563",
    "location": "SS&FMD",
    "department": "GEN FLEET POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS275",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252576",
    "engine_no": "VF3XDRFHB64252576",
    "location": "RAD",
    "department": "RAD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS277",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252871",
    "engine_no": "VF3XDRFHB64252871",
    "location": "SS&FMD",
    "department": "SSM",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS287",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64248698",
    "engine_no": "VF3XDRFHB64248698",
    "location": "COMMUNICATION AND SERVICOM",
    "department": "COMMUNICATION AND SERVICOM",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS387",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DRFJE 85157834",
    "engine_no": "VF 33DRFJE 85157834",
    "location": "GENERAL FLEET POOL",
    "department": "SS&FMD POOL",
    "driver_name": "SOP DIVISION",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS433",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087053",
    "engine_no": "VF33DN6AW91087053",
    "location": "SS&FMD POOL",
    "department": "SS&FMD POOL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS441",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087043",
    "engine_no": "VF33DN6AW91087043",
    "location": "CAPITAL UNIT F&A",
    "department": "FINANCE & ACCOUNT DEPARTMENT",
    "driver_name": "TANKO",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS471",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64242178",
    "engine_no": "UF3XCRFHB64242178",
    "location": "STCD FIRS-EFCC JOINT TASK FORCE",
    "department": "STCD FIRS-EFCC JOINT TASK FORCE",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS472",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244674",
    "engine_no": "UF3XCRFHB64244674",
    "location": "F&A POOL",
    "department": "F&A",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS474",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244683",
    "engine_no": "UF3XCRFHB64244683",
    "location": "D-HCMD POOL",
    "department": "HCMD",
    "driver_name": "D/HCMD POOL-HQ",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS475",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64242180",
    "engine_no": "UF3XCRFHB64242180",
    "location": "TID NORTH DIV",
    "department": "TID",
    "driver_name": "FROM JKK SCO KATSINA OFFICE",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS477",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64238390",
    "engine_no": "UF3XCRFHB64238390",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "GENERAL FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS478",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244680",
    "engine_no": "UF3XCRFHB64244680",
    "location": "ICT POOL",
    "department": "ICT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS481",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64240365",
    "engine_no": "UF3XCRFHB64240365",
    "location": "BOARD SECRETARY",
    "department": "BS",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS482",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244682",
    "engine_no": "UF3XCRFHB64244682",
    "location": "LEGAL",
    "department": "LEGAL",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS484",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64241585",
    "engine_no": "UF3XCRFHB64241585",
    "location": "HQ-TAX POLICY",
    "department": "HQ-TAX POLICY",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS793/190FIRS",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHBAZ060256",
    "engine_no": "VF3XDRFHBAZ060256",
    "location": "ENFORCEMENT POOL",
    "department": "ENF DEPT",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS116",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85419166",
    "engine_no": "5149166",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "RETREIVED BACK TO FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS425",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087040",
    "engine_no": "VF33DN6AW91087040",
    "location": "GENERAL FLEET POOL",
    "department": "FLEET POOL",
    "driver_name": "FLEET POOL",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS106",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE5148126",
    "engine_no": "5148126",
    "location": "SS&FMD",
    "department": "SS&FMD",
    "driver_name": "",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS376",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DR5E 85149844",
    "engine_no": "VF 33DR5E 85149844",
    "location": "FMD/ P& E",
    "department": "FMD",
    "driver_name": "ENGR ABDULLAHI",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS456",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244664",
    "engine_no": "UF3XCRFHB64244664",
    "location": "BAUCHI ETO",
    "department": "ETO",
    "driver_name": "BAUCHI ETO",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS93",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "85147307",
    "engine_no": "8517307",
    "location": "STAMP DUTIES GOMBE",
    "department": "GOVT BUSINESS TAX AUDIT",
    "driver_name": "DANJUMA ABDULLAHI MANGA",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS92",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33BRFJE85148831",
    "engine_no": "VF33BRFJE85148831",
    "location": "STAMP DUTY COMMISSIONER",
    "department": "STAMP DUTY COMMISSIONER",
    "driver_name": "LAWAL Y. NASIR",
    "sco": "GAT"
  },
  {
    "license_plate": "RB829FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64189108",
    "engine_no": "64189108",
    "location": "GAT SCO GOMBE",
    "department": "GAT SCO GOMBE",
    "driver_name": "",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS115",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "5147719",
    "engine_no": "5147719",
    "location": "SSM REP KEO",
    "department": "KEO SCO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS281",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252166",
    "engine_no": "VF3XDRFHB64252166",
    "location": "KEO SCO",
    "department": "KEO SCO",
    "driver_name": "",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS449",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087058",
    "engine_no": "VF33DN6AW91087058",
    "location": "GBA EKITI",
    "department": "GBA EKITI",
    "driver_name": "JOHN IBITOYE",
    "sco": "KEO"
  },
  {
    "license_plate": "FIRS114",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE5147305",
    "engine_no": "5147305",
    "location": "C-JALINGO STAMP DUTIES",
    "department": "JALINGO STAMP DUTIES",
    "driver_name": "ISHAYA ELIJAH",
    "sco": "GAT"
  },
  {
    "license_plate": "FIRS99",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "85148469",
    "engine_no": "85148469",
    "location": "DUTSE STAMP DUTIES",
    "department": "DUTSE STAMP DUTIES",
    "driver_name": "ABU DAURA",
    "sco": "JKK"
  },
  {
    "license_plate": "RB824FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "64191922",
    "engine_no": "64191922",
    "location": "DUTSE MSTO",
    "department": "MSTO",
    "driver_name": "",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS301",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85157868",
    "engine_no": "VF33DRFJE85157868",
    "location": "SCO FSSM JKK",
    "department": "SS&FMD UNIT",
    "driver_name": "SS&FMD REP",
    "sco": "JKK"
  },
  {
    "license_plate": "FIRS66/RB879FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "86317896",
    "engine_no": "86317896",
    "location": "SC LI",
    "department": "SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "RB887FG",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "64187328",
    "engine_no": "64187328",
    "location": "SCO LI/ ICT",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS98",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85148830",
    "engine_no": "85148830",
    "location": "LI SCO",
    "department": "OIL&GAS DOWN STREAM",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS67",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64186759",
    "engine_no": "VF3XDRFHB64186759",
    "location": "AJAH MSTO",
    "department": "AJAH MSTO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS466",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64238391",
    "engine_no": "UF3XCRFHB64238391",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS468",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64239755",
    "engine_no": "UF3XCRFHB64239755",
    "location": "LI SCO",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS722/94FIRS",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64249797",
    "engine_no": "VF3XDRFHB64249797",
    "location": "SC-LI ICT",
    "department": "LI SCO",
    "driver_name": "",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS41",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64186758",
    "engine_no": "64186758",
    "location": "LTO NON OIL LME",
    "department": "LTO NON OIL LME",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS284",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64251570",
    "engine_no": "VF3XDRFHB64251570",
    "location": "TAT/LAGOS",
    "department": "TAT",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS458",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244667",
    "engine_no": "UF3XCRFHB64244667",
    "location": "SCO LME",
    "department": "ICT UNIT",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS464",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64238990",
    "engine_no": "UF3XCRFHB64238990",
    "location": "SC LME",
    "department": "MSTO",
    "driver_name": "",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS454",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087055",
    "engine_no": "VF33DN6AW91087055",
    "location": "LMW SCO",
    "department": "LMW SCO",
    "driver_name": "NOT ALLOCATED",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS241",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85148463",
    "engine_no": "85148463",
    "location": "TAX AUDIT",
    "department": "TAX AUDIT LMW",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS467",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64240369",
    "engine_no": "UF3XCRFHB64240369",
    "location": "LMW SCO/ VAT",
    "department": "LMW SCO",
    "driver_name": "",
    "sco": "LMW"
  },
  {
    "license_plate": "FIRS720/149FIRS",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64250423",
    "engine_no": "VF3XDRFHB64250423",
    "location": "OGUN GBO",
    "department": "OGUN GBO",
    "driver_name": "SALAWU GANAYU",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS453",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087057",
    "engine_no": "VF33DN6AW91087057",
    "location": "MTO IBADAN",
    "department": "MTO IBADAN",
    "driver_name": "FILING & DEBT ENFORCEMENT-TAX DRIVE TEAM",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS139",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64191365",
    "engine_no": "VF3XDRFHB64191365",
    "location": "SCO OOO",
    "department": "SCO",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS109",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85148123",
    "engine_no": "85148123",
    "location": "ABEOKUTA STAMP DUTIES",
    "department": "ABEOKUTA STAMP DUTIES",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS386/RB449FG",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DREJE 85152313",
    "engine_no": "VF 33DREJE 85152313",
    "location": "OSUN GBA",
    "department": "OSUN GBA",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS460",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "UF3XCRFHB64244671",
    "engine_no": "UF3XCRFHB64244671",
    "location": "AUDIT, SCO OOO OSUN",
    "department": "SCO AUDIT",
    "driver_name": "",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS373",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DR5E 85157259",
    "engine_no": "VF 33DR5E 85157259",
    "location": "SCO OOO IBADAN/FM REP",
    "department": "SCO OOO",
    "driver_name": "SCO OOO POOL, IBADAN",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS276",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64246958",
    "engine_no": "VF3XDRFHB64246958",
    "location": "AD - TAT",
    "department": "TAT",
    "driver_name": "MR HILLARY ONWE",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS432",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087039",
    "engine_no": "VF33DN6AW91087039",
    "location": "LTA PH NON OIL",
    "department": "LTA PH NON OIL",
    "driver_name": "AD/HEAD/MANTU",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS108",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "5147306",
    "engine_no": "5147306",
    "location": "BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS451",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087036",
    "engine_no": "VF33DN6AW91087036",
    "location": "SCO PH",
    "department": "SCO RED",
    "driver_name": "KEVIN OSUJI",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS19",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VT3XDRFIJB641867464",
    "engine_no": "6418676",
    "location": "SCO-RED",
    "department": "SCO RED",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS283",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64251574",
    "engine_no": "VF3XDRFHB64251574",
    "location": "BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS293",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64252573",
    "engine_no": "VF3XDRFHB64252573",
    "location": "TAT BENIN",
    "department": "TAT",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS391",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DRFJE 85157813",
    "engine_no": "VF33DRFJE85157813",
    "location": "ASABA ETO",
    "department": "ASABA ETO",
    "driver_name": "",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS83",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DRFJE85147714",
    "engine_no": "85147714",
    "location": "KSZ SAO/GUSAU",
    "department": "KSZ SAO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS427",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087054",
    "engine_no": "VF33DN6AW91087054",
    "location": "INTERNAL AFFAIRS UNIT SKZ SAO/SOKOTO",
    "department": "KSZ SAO",
    "driver_name": "",
    "sco": "SKZ"
  },
  {
    "license_plate": "FIRS743",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ788031",
    "engine_no": "VF3DDNFPRDJ788031",
    "location": "GROUNDED",
    "department": "GROUNDED",
    "driver_name": "GROUNDED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS949",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ597559",
    "engine_no": "VF3DDNFPRGJ597559",
    "location": "GROUNDED",
    "department": "GROUNDED",
    "driver_name": "WITH MECHANIC IN KD",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS805",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ793330",
    "engine_no": "VF3DDNFPRDJ793330",
    "location": "GROUNDED",
    "department": "GROUNDED",
    "driver_name": "GROUNDED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS739/99FIRS",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E503027052",
    "engine_no": "2ZRU418870",
    "location": "UNDERGOING REPAIRS",
    "department": "GROUNDED",
    "driver_name": "GROUNDED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS982",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5FCAGL010169",
    "engine_no": "VF38D5FCAGL010169",
    "location": "RETRIEVED FROM UNION CHAIRMAN ASCSN",
    "department": "GROUNDED",
    "driver_name": "GROUNDED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS610N",
    "brand": "Peugeot",
    "model": "508",
    "vin_sn": "VF38D5GYAHL016687",
    "engine_no": "VF38D5GYAHL016687",
    "location": "RETRIEVED FROM D-PRS",
    "department": "FAULTY",
    "driver_name": "CAR PARK",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS1210",
    "brand": "Geely",
    "model": "Azkarra",
    "vin_sn": "L6T7722Z9NU006236",
    "engine_no": "3GI5TD-2502683",
    "location": "RETRIEVED FROM THEO ADEGOR",
    "department": "FAULTY",
    "driver_name": "FAULTY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS958",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ610416",
    "engine_no": "VF3DDNFPRGJ610416",
    "location": "TAX AUDIT REVIEW UNIT",
    "department": "FAULTY",
    "driver_name": "NOT ALLOCATED (FAULTY)",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS1063",
    "brand": "Toyota",
    "model": "Camry",
    "vin_sn": "JTNBZ4HK8L3016327",
    "engine_no": "JTNBZ4HK8L3016327",
    "location": "CD-CSG",
    "department": "ACCIDENTED",
    "driver_name": "M. L. ABUBAKAR",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS778",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRX12P208044495",
    "engine_no": "JTFRX12P208044495",
    "location": "SAO, IBADAN",
    "department": "SAO, IBADAN (ACCIDENTED)",
    "driver_name": "ACCIDENTED",
    "sco": "OOO"
  },
  {
    "license_plate": "FIRS186",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E303009957",
    "engine_no": "2ZRU093006",
    "location": "ABA MSTO",
    "department": "ABA MSTO",
    "driver_name": "FAULTY",
    "sco": "EEA"
  },
  {
    "license_plate": "FIRS1068",
    "brand": "Innoson",
    "model": "Ikenga",
    "vin_sn": "LNBMDBAK9HR879154",
    "engine_no": "NC02H058241",
    "location": "RETRIEVED FROM PROC",
    "department": "RETRIEVED FROM BABAGANA PROCUREMENT",
    "driver_name": "FAULTY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS641N",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTBF0JE400004086",
    "engine_no": "2ZR- U878926",
    "location": "GENERAL FLEET",
    "department": "GENERAL FLEET",
    "driver_name": "FAULTY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS552",
    "brand": "Toyota",
    "model": "Hilux",
    "vin_sn": "AHTFX229108007538",
    "engine_no": "2TR8201731",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL WITH MECHANIC IN KD",
    "driver_name": "FAULTY",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS182",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC 58E103009857",
    "engine_no": "2ZRU063384",
    "location": "SCO IA",
    "department": "SCO IA",
    "driver_name": "INNOCENT EZEJI (FAULTY)",
    "sco": "IA"
  },
  {
    "license_plate": "FIRS258",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC58E303009813",
    "engine_no": "2ZRUO93342",
    "location": "VAT LI",
    "department": "VAT LI",
    "driver_name": "FAULTY",
    "sco": "LI"
  },
  {
    "license_plate": "FIRS586",
    "brand": "Toyota",
    "model": "Coaster",
    "vin_sn": "JTGFK518204005377",
    "engine_no": "8264836",
    "location": "SC LME",
    "department": "SCO-POOL",
    "driver_name": "FAULTY",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS813",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ813718",
    "engine_no": "VF3DDNFPRDJ813718",
    "location": "LARGE TAX AUDIT LME",
    "department": "LARGE TAX AUDIT LME",
    "driver_name": "FAULTY",
    "sco": "LME"
  },
  {
    "license_plate": "FIRS974",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRGJ608594",
    "engine_no": "VF3DDNFPRGJ608594",
    "location": "RETRIEVED FROM DD PH1 ETO BACK TO FLEET",
    "department": "RETRIEVED FROM OBIAKOR UCHENNA",
    "driver_name": "FAULTY",
    "sco": "HQ"
  },
  {
    "license_plate": "RB713FG",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "3114882",
    "engine_no": "1993251122/K590",
    "location": "RUMEMEM MSTO",
    "department": "RUMUKRUSHI ITO",
    "driver_name": "FAULTY",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS753",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ827126",
    "engine_no": "VF3DDNFPRDJ827126",
    "location": "SSFMD POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "POOL (GROUNDED)",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS610",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTGRX12P4A8019160",
    "engine_no": "2TR8237056",
    "location": "SULEJA ROUTE",
    "department": "ROUTE BUS",
    "driver_name": "GROUNDED IN KADUNA",
    "sco": "BKP"
  },
  {
    "license_plate": "FIRS758",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ829506",
    "engine_no": "VF3DDNFPRDJ829506",
    "location": "SSFMD",
    "department": "GENERAL FLEET POOL",
    "driver_name": "POOL (GROUNDED)",
    "sco": "FCT"
  },
  {
    "license_plate": "FIRS737",
    "brand": "Peugeot",
    "model": "301",
    "vin_sn": "VF3DDNFPRDJ827136",
    "engine_no": "VF3DDNFPRDJ827136",
    "location": "BROAD STREET MSTO",
    "department": "BROAD STREET MSTO",
    "driver_name": "GROUNDED",
    "sco": "LAGOS ISLAND"
  },
  {
    "license_plate": "FIRS57",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "JTDBR22E400249985",
    "engine_no": "1ZZ-17914",
    "location": "WARRI MSTO",
    "department": "WARRI MSTO",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "155FIRS",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087463",
    "engine_no": "VF33DN6AW91087463",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS70",
    "brand": "Peugeot",
    "model": "Expert",
    "vin_sn": "VF3XDRFHB64187329",
    "engine_no": "VF3XDRFHB64187329",
    "location": "SAO PH",
    "department": "SAO PH",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS111",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "",
    "engine_no": "147308",
    "location": "HEAD ENFORCEMENT",
    "department": "HEAD/MOPOL",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS107",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DTFJE514889",
    "engine_no": "VF33DTFJE514889",
    "location": "LTO PH NON OIL",
    "department": "LTO PH NON OIL",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS393",
    "brand": "Toyota",
    "model": "Hiace",
    "vin_sn": "JTFRXT2P808017673",
    "engine_no": "JTFRXT2P808017673",
    "location": "PH ETO I",
    "department": "PH ETO I",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS446",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087042",
    "engine_no": "VF33DN6AW91087042",
    "location": "BENIN MSTO",
    "department": "BENIN MSTO",
    "driver_name": "GROUNDED",
    "sco": "RED"
  },
  {
    "license_plate": "FIRS437",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF33DN6AW91087065",
    "engine_no": "VF33DN6AW91087065",
    "location": "Disband office",
    "department": "Disband office",
    "driver_name": "Grounded",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS392",
    "brand": "Peugeot",
    "model": "307",
    "vin_sn": "VF 33DRFJE 81149823",
    "engine_no": "VF 33DRFJE 81149823",
    "location": "Disband office",
    "department": "Disband office",
    "driver_name": "Grounded",
    "sco": "BBY"
  },
  {
    "license_plate": "FIRS901",
    "brand": "Ford",
    "model": "Ranger Pick-Up",
    "vin_sn": "6FPPXXMJ2PFE70860",
    "engine_no": "FE70860",
    "location": "GENERAL FLEET POOL",
    "department": "GENERAL FLEET POOL",
    "driver_name": "ACCIDENTED",
    "sco": "HQ"
  },
  {
    "license_plate": "FIRS541",
    "brand": "Toyota",
    "model": "Corolla",
    "vin_sn": "AHTLC56E903018471",
    "engine_no": "2ZRUZ001114",
    "location": "KEO SCO",
    "department": "KEO SCO",
    "driver_name": "ACCIDENTED",
    "sco": "KEO"
  }
]


# ================================================================
# STEP 1: ENSURE FLEET MODULE IS AVAILABLE
# ================================================================
print("\n" + "-" * 70)
print("  STEP 1: CHECKING FLEET MODULE")
print("-" * 70)

if 'fleet.vehicle' not in env:
    print("  ✗ fleet.vehicle model not found!")
    print("  Install the Fleet module first:")
    print("    cd /opt/odoo && sudo -u odoo odoo-helper addons install -d nrs-facilities fleet")
    raise SystemExit("Fleet module not installed")

print("  ✓ fleet.vehicle model available")


# ================================================================
# STEP 2: CREATE BRANDS AND MODELS
# ================================================================
print("\n" + "-" * 70)
print("  STEP 2: BRANDS & MODELS")
print("-" * 70)

brand_map = {}   # brand_name → fleet.vehicle.model.brand id
model_map = {}   # (brand_name, model_name) → fleet.vehicle.model id

# Collect unique brand/model pairs
pairs = sorted(set((v['brand'], v['model']) for v in VEHICLES))

for brand_name, model_name in pairs:
    # Get or create brand
    if brand_name not in brand_map:
        existing_brand = env['fleet.vehicle.model.brand'].search(
            [('name', '=ilike', brand_name)], limit=1)
        if not existing_brand:
            b = env['fleet.vehicle.model.brand'].create({'name': brand_name})
            brand_map[brand_name] = b.id
            print(f"  + Brand: {brand_name}")
        else:
            brand_map[brand_name] = existing_brand.id
            print(f"  o Brand exists: {brand_name}")

    # Get or create model
    key = (brand_name, model_name)
    brand_id = brand_map[brand_name]
    existing_model = env['fleet.vehicle.model'].search([
        ('name', '=ilike', model_name),
        ('brand_id', '=', brand_id),
    ], limit=1)
    if not existing_model:
        m = env['fleet.vehicle.model'].create({
            'name':     model_name,
            'brand_id': brand_id,
        })
        model_map[key] = m.id
        print(f"    + Model: {brand_name} {model_name}")
    else:
        model_map[key] = existing_model.id

env.cr.commit()
print(f"\n  ✓ {len(brand_map)} brands | {len(model_map)} models ready")


# ================================================================
# STEP 3: CREATE TAGS (SCO LOCATIONS + DEPARTMENTS)
# ================================================================
print("\n" + "-" * 70)
print("  STEP 3: TAGS (SCO LOCATIONS & DEPARTMENTS)")
print("-" * 70)

tag_map = {}

def get_or_create_tag(name):
    if not name or name.upper() in ('NAN', '', 'POOL'):
        return None
    if name in tag_map:
        return tag_map[name]
    existing = env['fleet.vehicle.tag'].search([('name', '=', name)], limit=1)
    if not existing:
        t = env['fleet.vehicle.tag'].create({'name': name})
        tag_map[name] = t.id
    else:
        tag_map[name] = existing.id
    return tag_map[name]

# Create SCO location tags
sco_locations = sorted(set(v['sco'] for v in VEHICLES if v['sco'] and v['sco'] != 'nan'))
for sco in sco_locations:
    get_or_create_tag(f"SCO:{sco}")
    print(f"  + Tag: SCO:{sco}")

env.cr.commit()
print(f"  ✓ {len(tag_map)} tags created")


# ================================================================
# STEP 4: IMPORT VEHICLES
# ================================================================
print("\n" + "-" * 70)
print("  STEP 4: IMPORTING VEHICLES")
print("-" * 70)

created  = 0
updated  = 0
skipped  = 0
errors   = 0
BATCH    = 50

for i, v in enumerate(VEHICLES, 1):
    try:
        plate    = v['license_plate'].strip()
        brand    = v['brand']
        model    = v['model']
        vin      = v['vin_sn']
        eng_no   = v['engine_no']
        location = v['location']
        dept     = v['department']
        driver   = v['driver_name']
        sco      = v['sco']

        if not plate or plate.upper() == 'NAN':
            skipped += 1
            continue

        model_id = model_map.get((brand, model))
        if not model_id:
            skipped += 1
            print(f"  ! No model for {plate} ({brand} {model})")
            continue

        # Build tag list
        tag_ids = []
        sco_tag = tag_map.get(f"SCO:{sco}")
        if sco_tag:
            tag_ids.append(sco_tag)

        vals = {
            'license_plate': plate,
            'model_id':      model_id,
            'vin_sn':        vin,
            'location':      f"{location} | {dept}".strip(' |'),
            'tag_ids':       [(6, 0, tag_ids)] if tag_ids else [],
        }

        # Check if vehicle already exists
        existing = env['fleet.vehicle'].search(
            [('license_plate', '=', plate)], limit=1)

        if not existing:
            env['fleet.vehicle'].create(vals)
            created += 1
            if created <= 20 or created % 100 == 0:
                print(f"  + [{i}] {plate} — {brand} {model}")
        else:
            existing.write(vals)
            updated += 1

        # Commit in batches
        if i % BATCH == 0:
            env.cr.commit()
            print(f"  [committed batch at {i}/{len(VEHICLES)}]")

    except Exception as e:
        errors += 1
        print(f"  ✗ [{i}] {v.get('license_plate', '?')} — {e}")

env.cr.commit()
print(f"\n  ✓ Created: {created} | Updated: {updated} | Skipped: {skipped} | Errors: {errors}")




# ================================================================
# PART D — MASTER SUMMARY
# ================================================================
total_vehicles = env['fleet.vehicle'].search_count([])
total_types    = env['request.type'].search_count([])
total_cats     = env['request.category'].search_count([])

print()
print("=" * 70)
print("  myservice.com.ng — MASTER SEED COMPLETE")
print("=" * 70)
print(f"  Database:       myservice.com.ng")
print()
print("  ITSM:")
print(f"    Kinds:          {len(kind_map)}")
print(f"    Services:       {len(service_map) if service_map else 'N/A'}")
print(f"    Categories:     {total_cats}")
print(f"    Request Types:  {total_types}")
print(f"    Stages/Routes:  {ok_count} types configured (7 stages, 9 routes each)")
print(f"    Classifiers:    {classifier_ok}")
print()
print("  Fleet:")
print(f"    Brands:         {len(brand_map)}")
print(f"    Models:         {len(model_map)}")
print(f"    Vehicles:       {total_vehicles}")
print()
print("  Next Steps:")
print("  1. http://myservice.com.ng → log in → verify data")
print("  2. Settings → Company → upload NRS logo")
print("  3. Settings → Users → create team leads per domain")
print("  4. Fleet → Vehicles → assign drivers to non-POOL vehicles")
print("  5. ITSM → Configuration → set SLA rules per kind")
print("  6. Settings → Email → configure outbound mail server")
print()
print("  WestMetro Limited | www.westmetrong.com | +234 806 902 0996")
print("=" * 70)
