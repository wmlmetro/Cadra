#!/usr/bin/env python3
"""
fleet_taxonomy_seed.py — Fleet Management Taxonomy Merge & Seed
===============================================================
Merges the existing 7-category flat structure into a proper
9-service × 4-category × ~100-type hierarchy.

EXISTING RECORDS PRESERVED:
  Service Group: Fleet Management (ID:5)
  Service:       Fleet Management (ID:7) — renamed to Fleet Operations Management
  Categories promoted to Services: Vehicle Maintenance(32), Fuel & Lubricants(33),
    Driver Management(34), Vehicle Registration(35), Insurance & Licensing(36),
    Trip Scheduling(37), Vehicle Procurement(38)
  12 existing Types redistributed — IDs preserved

Run:
    sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \\
        -c /etc/odoo/odoo.conf -d myservice --no-http < fleet_taxonomy_seed.py
"""

import traceback

print()
print("=" * 70)
print("  FLEET TAXONOMY MERGE SEED")
print("  Preserving existing IDs | 10 services | ~35 categories | ~120 types")
print("=" * 70)

# ── Helpers ────────────────────────────────────────────────────────────

def make_code(name):
    """Generate a short uppercase code from service name."""
    import re
    words = re.findall(r'[A-Za-z]+', name)
    if len(words) >= 2:
        code = ''.join(w[0] for w in words[:4]).upper()
    else:
        code = name[:6].upper().replace(' ', '')
    return code

def get_or_create_service(name, group_id, existing_id=None):
    if existing_id:
        rec = env['generic.service'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                old_name = rec.name
                rec.write({'name': name})
                print(f"  ~ Service RENAMED: '{old_name}' → '{name}' (ID:{existing_id})")
            else:
                print(f"  o Service EXISTS:  '{name}' (ID:{existing_id})")
            return rec
    existing = env['generic.service'].search([('name','=',name),('service_group_id','=',group_id)], limit=1)
    if existing:
        print(f"  o Service EXISTS:  '{name}' (ID:{existing.id})")
        return existing
    # Generate unique code
    base_code = make_code(name)
    code = base_code
    suffix = 1
    while env['generic.service'].search([('code','=',code)], limit=1):
        code = f"{base_code}{suffix}"
        suffix += 1
    rec = env['generic.service'].create({'name': name, 'service_group_id': group_id, 'code': code})
    print(f"  + Service NEW:     '{name}' code:{code} (ID:{rec.id})")
    return rec

def get_or_create_category(name, service_ids, existing_id=None):
    if existing_id:
        rec = env['request.category'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                print(f"  ~ Category RENAMED: '{rec.name}' → '{name}' (ID:{existing_id})")
                rec.write({'name': name})
            # ensure service linkage
            rec.write({'service_ids': [(4, sid) for sid in service_ids]})
            print(f"  o Category EXISTS:  '{name}' (ID:{existing_id})")
            return rec
    existing = env['request.category'].search([('name','=',name)], limit=1)
    if existing:
        existing.write({'service_ids': [(4, sid) for sid in service_ids]})
        print(f"  o Category EXISTS:  '{name}' (ID:{existing.id})")
        return existing
    rec = env['request.category'].create({
        'name': name,
        'service_ids': [(6, 0, service_ids)],
    })
    print(f"  + Category NEW:     '{name}' (ID:{rec.id})")
    return rec

def get_or_create_type(name, category_ids, existing_id=None, old_name=None):
    if existing_id:
        rec = env['request.type'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                print(f"    ~ Type RENAMED: '{rec.name}' → '{name}' (ID:{existing_id})")
                rec.write({'name': name})
            rec.write({'category_ids': [(4, cid) for cid in category_ids]})
            return rec
    existing = env['request.type'].search([('name','=',name)], limit=1)
    if existing:
        existing.write({'category_ids': [(4, cid) for cid in category_ids]})
        return existing
    rec = env['request.type'].create({
        'name': name,
        'category_ids': [(6, 0, category_ids)],
    })
    print(f"    + Type NEW: '{name}' (ID:{rec.id})")
    return rec

# ── Step 1: Service Group (preserve ID:5) ─────────────────────────────
print("\n[ Service Group ]")
fleet_group = env['generic.service.group'].browse(5)
assert fleet_group.exists(), "Fleet Management group (ID:5) not found!"
print(f"  o Fleet Management (ID:5) — EXISTING")
GID = 5

env.cr.commit()

# ── Step 2: Services ───────────────────────────────────────────────────
print("\n[ Services ]")

# Rename existing Service ID:7 from "Fleet Management" → "Fleet Operations Management"
svc_fleet_ops   = get_or_create_service("Fleet Operations Management",   GID, existing_id=7)
svc_driver      = get_or_create_service("Driver Management",              GID)
svc_maintenance = get_or_create_service("Vehicle Maintenance",            GID)
svc_fuel        = get_or_create_service("Fuel Management",                GID)
svc_compliance  = get_or_create_service("Compliance & Regulatory Management", GID)
svc_safety      = get_or_create_service("Fleet Safety & Risk Management", GID)
svc_telematics  = get_or_create_service("Telematics & Technology Services", GID)
svc_reporting   = get_or_create_service("Reporting & Analytics Services", GID)
svc_emergency   = get_or_create_service("Emergency & Support Services",   GID)
svc_procurement = get_or_create_service("Vehicle Procurement",            GID)

env.cr.commit()

# ── Step 3: Categories & Types ─────────────────────────────────────────
TAXONOMY = [

  # ── Fleet Operations Management ──────────────────────────────────────
  (svc_fleet_ops, [
    ("Vehicle Allocation & Dispatch", None, [
      ("Vehicle request not assigned", None),
      ("No vehicle available",         None),
      ("Vehicle booking conflict",     None),
      ("Driver unavailable",           None),
      ("Last minute transport request",None),
      ("Vehicle reassignment",         None),
      ("Trip cancellation",            None),
    ]),
    # Rename existing Cat ID:37 "Trip Scheduling" → "Transport Request Management"
    ("Transport Request Management", 37, [
      ("Trip Booking",              75),   # EXISTING type ID:75
      ("Staff transport request",   None),
      ("Logistics transport request",None),
      ("Airport pickup request",    None),
      ("VIP transport request",     None),
      ("Urgent transport request",  None),
    ]),
    ("Route Planning & Optimization", None, [
      ("Route inefficiency",           None),
      ("Traffic disruption",           None),
      ("Driver route deviation",       None),
      ("Delivery delay due to routing",None),
      ("Route redesign request",       None),
    ]),
    ("Vehicle Utilization Monitoring", None, [
      ("Vehicle underutilization",  None),
      ("Excessive idle time",       None),
      ("Unauthorized vehicle use",  None),
      ("Missing trip logs",         None),
      ("Fleet capacity shortage",   None),
    ]),
  ]),

  # ── Driver Management ─────────────────────────────────────────────────
  (svc_driver, [
    ("Driver Administration", None, [
      ("Driver license expired",       None),
      ("Missing driver documentation", None),
      ("Driver onboarding",            None),
      ("Driver record update",         None),
      ("Driver contract renewal",      None),
    ]),
    ("Driver Scheduling", None, [
      # Absorb existing Type ID:72
      ("Driver Scheduling Request", 72),
      ("Driver shift conflict",     None),
      ("Driver absence",            None),
      ("Driver overtime approval",  None),
      ("Driver replacement",        None),
    ]),
    ("Driver Safety Programs", None, [
      ("Unsafe driving complaint", None),
      ("Driver safety violation",  None),
      ("Driver training required", None),
      ("Safety awareness request", None),
    ]),
    # Absorb existing Cat ID:34 "Driver Management" → "Driver Performance Monitoring"
    ("Driver Performance Monitoring", 34, [
      # Rename existing Type ID:71 "Driver Complaint" → "Driver behavior complaint"
      ("Driver behavior complaint", 71),
      ("Speeding violation",        None),
      ("Harsh braking alert",       None),
      ("Driver disciplinary review",None),
    ]),
  ]),

  # ── Vehicle Maintenance ───────────────────────────────────────────────
  (svc_maintenance, [
    ("Preventive Maintenance", None, [
      # Rename existing Type ID:67 "Vehicle Preventive Service" → "Scheduled vehicle service"
      ("Scheduled vehicle service", 67),
      ("Oil change required",       None),
      ("Tire replacement",          None),
      ("Brake servicing",           None),
      ("Battery replacement",       None),
    ]),
    # New category absorbing existing Types ID:65 and ID:66
    ("Corrective Maintenance", None, [
      ("Vehicle breakdown",        65),  # renamed from "Vehicle Breakdown Report"
      ("Vehicle corrective repair",66),  # EXISTING
      ("Engine malfunction",       None),
      ("Electrical fault",         None),
      ("Cooling system failure",   None),
      ("Transmission issue",       None),
    ]),
    ("Maintenance Planning", None, [
      ("Vehicle inspection",         68),  # EXISTING type ID:68
      ("Missed maintenance schedule",None),
      ("Maintenance backlog",        None),
      ("Maintenance record update",  None),
    ]),
    # Absorb existing Cat ID:32 "Vehicle Maintenance" → "Spare Parts Management"
    # (the cat ID:32 itself is now the service; repurpose for spare parts)
    ("Spare Parts Management", 32, [
      ("Spare part unavailable",       None),
      ("Wrong spare part installed",   None),
      ("Spare part procurement",       None),
      ("Spare parts inventory shortage",None),
    ]),
  ]),

  # ── Fuel Management ───────────────────────────────────────────────────
  (svc_fuel, [
    ("Fuel Monitoring", None, [
      ("High fuel consumption", None),
      ("Missing fuel data",     None),
      ("Fuel efficiency drop",  None),
    ]),
    ("Fuel Fraud Detection", None, [
      ("Suspected fuel theft",    None),
      ("Fuel receipt mismatch",   None),
      ("Fuel card misuse",        None),
      ("Fuel quantity discrepancy",None),
    ]),
    # Absorb existing Cat ID:33 "Fuel & Lubricants" → "Fuel Procurement"
    ("Fuel Procurement", 33, [
      ("Fuel request",        69),  # EXISTING type ID:69
      ("Fuel supply delay",   None),
      ("Vendor fuel shortage",None),
      ("Fuel price discrepancy",None),
    ]),
    ("Fuel Reporting", None, [
      ("Fuel reconciliation issue",70),  # renamed from "Fuel Reconciliation"
      ("Fuel report request",      None),
      ("Missing fuel logs",        None),
    ]),
  ]),

  # ── Compliance & Regulatory Management ───────────────────────────────
  (svc_compliance, [
    # Rename existing Cat ID:35 "Vehicle Registration" → "Vehicle Licensing"
    ("Vehicle Licensing", 35, [
      ("Vehicle registration renewal",73),  # EXISTING type ID:73
      ("Registration expired",         None),
      ("Missing vehicle documents",    None),
    ]),
    # Rename existing Cat ID:36 "Insurance & Licensing" → "Insurance Management"
    ("Insurance Management", 36, [
      ("Insurance renewal",          74),  # EXISTING type ID:74
      ("Insurance expired",          None),
      ("Insurance claim",            None),
      ("Accident insurance processing",None),
    ]),
    ("Regulatory Compliance", None, [
      ("Roadworthiness expired",    None),
      ("Inspection failure",        None),
      ("Safety compliance violation",None),
    ]),
    ("Driver Compliance", None, [
      ("Driver license expired",    None),
      ("Medical certificate expired",None),
      ("Compliance breach",         None),
    ]),
  ]),

  # ── Fleet Safety & Risk Management ───────────────────────────────────
  (svc_safety, [
    ("Incident Management", None, [
      ("Vehicle accident",      None),
      ("Minor collision",       None),
      ("Accident investigation",None),
      ("Vehicle damage report", None),
    ]),
    ("Safety Monitoring", None, [
      ("Speed violation",        None),
      ("Dangerous driving alert",None),
      ("Safety complaint",       None),
    ]),
    ("Risk Mitigation", None, [
      ("High risk driver",            None),
      ("Safety policy violation",     None),
      ("Risk mitigation intervention",None),
    ]),
  ]),

  # ── Telematics & Technology Services ─────────────────────────────────
  (svc_telematics, [
    ("GPS Tracking", None, [
      ("GPS device failure",   None),
      ("Location not updating",None),
      ("GPS signal lost",      None),
    ]),
    ("Telematics Data Analytics", None, [
      ("Missing telematics data",None),
      ("Reporting error",        None),
      ("Incorrect vehicle data", None),
    ]),
    ("Fleet Monitoring Dashboards", None, [
      ("Dashboard not updating",None),
      ("KPI reporting error",   None),
      ("Missing metrics",       None),
    ]),
    ("IoT Sensor Integration", None, [
      ("Tire pressure sensor failure",None),
      ("Engine health sensor issue",  None),
      ("IoT connectivity problem",    None),
    ]),
  ]),

  # ── Reporting & Analytics Services ───────────────────────────────────
  (svc_reporting, [
    ("Operational Reports", None, [
      ("Fleet utilization report",None),
      ("Trip history report",     None),
      ("Driver report request",   None),
    ]),
    ("Financial Reports", None, [
      ("Fleet expense report",     None),
      ("Maintenance cost analysis",None),
      ("Fuel cost summary",        None),
    ]),
    ("Performance Analytics", None, [
      ("Driver performance analysis",None),
      ("Fleet efficiency analysis",  None),
      ("Cost per kilometer analysis",None),
    ]),
  ]),

  # ── Emergency & Support Services ─────────────────────────────────────
  (svc_emergency, [
    ("Roadside Assistance", None, [
      ("Vehicle breakdown — roadside",None),
      ("Flat tire",                   None),
      ("Battery failure",             None),
    ]),
    ("Emergency Response", None, [
      ("Vehicle accident emergency",None),
      ("Driver medical emergency",  None),
      ("Emergency vehicle dispatch",None),
    ]),
  ]),

  # ── Vehicle Procurement ───────────────────────────────────────────────
  (svc_procurement, [
    # Absorb existing Cat ID:38 "Vehicle Procurement" → "Procurement Requests"
    ("Procurement Requests", 38, [
      ("Vehicle procurement request",76),  # EXISTING type ID:76
      ("Vehicle replacement request", None),
      ("New vehicle specification",   None),
      ("Vendor evaluation request",   None),
    ]),
  ]),
]

# ── Step 4: Seed all categories & types ───────────────────────────────
print("\n[ Categories & Types ]")
cat_count  = 0
type_count = 0
err_count  = 0

for svc_rec, categories in TAXONOMY:
    print(f"\n  Service: {svc_rec.name} (ID:{svc_rec.id})")
    for cat_name, cat_existing_id, types in categories:
        try:
            cat = get_or_create_category(cat_name, [svc_rec.id], existing_id=cat_existing_id)
            cat_count += 1
            for type_item in types:
                type_name = type_item[0]
                type_existing_id = type_item[1] if len(type_item) > 1 else None
                try:
                    get_or_create_type(type_name, [cat.id], existing_id=type_existing_id)
                    type_count += 1
                except Exception as e:
                    print(f"    ✗ Type '{type_name}': {e}")
                    err_count += 1
        except Exception as e:
            print(f"  ✗ Category '{cat_name}': {e}")
            traceback.print_exc()
            err_count += 1

    env.cr.commit()
    print(f"  [committed after {svc_rec.name}]")

# ── Final summary ──────────────────────────────────────────────────────
total_svcs  = env['generic.service'].search_count([('service_group_id','=',GID)])
total_cats  = env['request.category'].search_count([])
total_types = env['request.type'].search_count([])

print()
print("=" * 70)
print("  FLEET TAXONOMY SEED COMPLETE")
print("=" * 70)
print(f"  Services in Fleet group : {total_svcs}")
print(f"  Categories processed    : {cat_count}")
print(f"  Types processed         : {type_count}")
print(f"  Errors                  : {err_count}")
print(f"  Total categories (all)  : {total_cats}")
print(f"  Total types (all)       : {total_types}")
print()
print("  PRESERVED EXISTING IDs:")
print("  Service Group Fleet Management  ID:5")
print("  Service Fleet Ops Management    ID:7  (renamed)")
print("  Categories: 32,33,34,35,36,37,38 (renamed/repurposed)")
print("  Types:      65,66,67,68,69,70,71,72,73,74,75,76 (preserved/renamed)")
print("=" * 70)
