#!/usr/bin/env python3
"""
NRS Facilities Service Desk — ITSM Seed Script
================================================
Client:   Nigeria Revenue Service (NRS)
Domains:  Building Services | Plumbing | Plant & Machinery
          Security & Safety | Fleet Management
Platform: Bureaucrat ITSM / CRND on Odoo 15
Powered:  WestMetro Limited | www.westmetrong.com

Provisions:
  1. Company branding (NRS)
  2. Service kinds
  3. Services  (one per domain)
  4. Categories (grouped by domain)
  5. Request types (per domain + sub-type)
  6. Stages (7-stage ITIL workflow)
  7. Routes (9 transitions per request type)

Run:
    cd /opt/odoo
    sudo -u odoo python3 odoo-bin shell \\
        -c /opt/odoo/conf/odoo.conf \\
        -d nrs-facilities --no-http < nrs_seed.py
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
# SUMMARY
# ================================================================
print()
print("=" * 70)
print("  NRS FACILITIES ITSM — SEED COMPLETE")
print("=" * 70)
print(f"  Kinds:         {len(kind_map)}")
print(f"  Services:      {len(service_map) if service_map else 'N/A'}")
print(f"  Categories:    {len(cat_map)}")
print(f"  Request Types: {len(type_map)}")
print(f"  Stages/Routes: {ok_count} types configured (7 stages, 9 routes each)")
print(f"  Classifiers:   {classifier_ok} (Service → Category → Type)")
print()
print("  Next Steps:")
print("  1. Settings → Company → Upload NRS logo")
print("  2. Settings → Users → Create team leads per domain")
print("  3. ITSM → Configuration → Assign teams to services")
print("  4. ITSM → Configuration → Set SLA rules per kind")
print("  5. Settings → Email → Configure outbound mail server")
print("  6. Activate Developer Mode → Apps → Update Apps List")
print()
print("  WestMetro Limited | www.westmetrong.com | +234 806 902 0996")
print("=" * 70)
