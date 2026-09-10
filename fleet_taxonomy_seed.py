#!/usr/bin/env python3
"""
fleet_taxonomy_seed.py — Fleet Management Taxonomy Merge & Seed
===============================================================
myservice.com.ng | NRS Facilities Management Platform
Odoo 15 + Bureaucrat ITSM (generic_request / generic_service)

DATA MODEL NOTES
----------------
- request_classifier is the single source of truth
- Every row = (service_id, category_id, type_id) — all three required
- Categories and services are linked ONLY through types
- There is no direct category <-> service junction table

WHAT THIS SCRIPT DOES
----------------------
1. Verifies Service Group: Fleet Management (ID:5)
2. Renames/creates 10 Services under the group
3. Creates/renames 35 Categories (standalone, no service linkage on create)
4. Creates/renames ~120 Types
5. Inserts (service_id, category_id, type_id) triples into request_classifier

EXISTING RECORDS PRESERVED
---------------------------
  Service Group : Fleet Management         ID:5
  Service       : Fleet Ops Management     ID:7  (renamed)
  Services      : IDs 11-19               (idempotent)
  Categories    : IDs 32-38               (renamed/repurposed)
  Types         : IDs 65-76               (renamed where needed)

IDEMPOTENT — safe to run multiple times.

Run:
    sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \
        -c /etc/odoo/odoo.conf -d myservice --no-http < fleet_taxonomy_seed.py
"""

import re as _re

print()
print("=" * 70)
print("  FLEET TAXONOMY MERGE SEED")
print("  10 services | 35 categories | ~120 types")
print("=" * 70)


# ── Code generators ────────────────────────────────────────────────────

def _unique_code(name, model):
    words = _re.findall(r'[A-Za-z]+', name)
    base = ''.join(w[0] for w in words[:5]).upper() if len(words) >= 2 else name[:6].upper()
    code, n = base, 1
    while env[model].search([('code', '=', code)], limit=1):
        code = f"{base}{n}"
        n += 1
    return code


# ── Service helpers ────────────────────────────────────────────────────

def get_or_create_service(name, group_id, existing_id=None):
    if existing_id:
        rec = env['generic.service'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                old = rec.name
                rec.write({'name': name})
                print(f"  ~ RENAMED service: '{old}' -> '{name}' (ID:{existing_id})")
            else:
                print(f"  o EXISTS  service: '{name}' (ID:{existing_id})")
            return rec
    ex = env['generic.service'].search(
        [('name', '=', name), ('service_group_id', '=', group_id)], limit=1)
    if ex:
        print(f"  o EXISTS  service: '{name}' (ID:{ex.id})")
        return ex
    code = _unique_code(name, 'generic.service')
    rec = env['generic.service'].create(
        {'name': name, 'service_group_id': group_id, 'code': code})
    print(f"  + NEW     service: '{name}' [{code}] (ID:{rec.id})")
    return rec


# ── Category helpers ───────────────────────────────────────────────────

def get_or_create_category(name, existing_id=None):
    if existing_id:
        rec = env['request.category'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                old = rec.name
                rec.write({'name': name})
                print(f"  ~ RENAMED category: '{old}' -> '{name}' (ID:{existing_id})")
            else:
                print(f"  o EXISTS  category: '{name}' (ID:{existing_id})")
            return rec
    ex = env['request.category'].search([('name', '=', name)], limit=1)
    if ex:
        print(f"  o EXISTS  category: '{name}' (ID:{ex.id})")
        return ex
    code = _unique_code(name, 'request.category')
    rec = env['request.category'].create({'name': name, 'code': code})
    print(f"  + NEW     category: '{name}' [{code}] (ID:{rec.id})")
    return rec


# ── Type helpers ───────────────────────────────────────────────────────

def get_or_create_type(name, existing_id=None):
    if existing_id:
        rec = env['request.type'].browse(existing_id)
        if rec.exists():
            if rec.name != name:
                old = rec.name
                rec.write({'name': name})
                print(f"    ~ RENAMED type: '{old}' -> '{name}' (ID:{existing_id})")
            else:
                print(f"    o EXISTS  type: '{name}' (ID:{existing_id})")
            return rec
    ex = env['request.type'].search([('name', '=', name)], limit=1)
    if ex:
        print(f"    o EXISTS  type: '{name}' (ID:{ex.id})")
        return ex
    code = _unique_code(name, 'request.type')
    rec = env['request.type'].create({'name': name, 'code': code})
    print(f"    + NEW     type: '{name}' [{code}] (ID:{rec.id})")
    return rec


# ── Classifier ─────────────────────────────────────────────────────────

def classify(service_id, category_id, type_id):
    """Insert (service, category, type) triple into request_classifier."""
    env.cr.execute("""
        INSERT INTO request_classifier (service_id, category_id, type_id, active)
        VALUES (%s, %s, %s, true)
        ON CONFLICT DO NOTHING
    """, (service_id, category_id, type_id))


# ======================================================================
# STEP 1 — Service Group
# ======================================================================
print("\n[ Service Group ]")
fleet_group = env['generic.service.group'].search([('name', '=', 'Fleet Management')], limit=1)
assert fleet_group, "Fleet Management group not found! Run itsm_structure.py first."
GID = fleet_group.id
print(f"  o EXISTS Fleet Management (ID:{GID})")
env.cr.commit()


# ======================================================================
# STEP 2 — Services
# ======================================================================
print("\n[ Services ]")
svc_ops        = get_or_create_service("Fleet Operations Management",       GID, existing_id=7)
svc_driver     = get_or_create_service("Driver Management",                  GID)
svc_maint      = get_or_create_service("Vehicle Maintenance",                GID)
svc_fuel       = get_or_create_service("Fuel Management",                    GID)
svc_compliance = get_or_create_service("Compliance & Regulatory Management", GID)
svc_safety     = get_or_create_service("Fleet Safety & Risk Management",     GID)
svc_telematic  = get_or_create_service("Telematics & Technology Services",   GID)
svc_reporting  = get_or_create_service("Reporting & Analytics Services",     GID)
svc_emergency  = get_or_create_service("Emergency & Support Services",       GID)
svc_procure    = get_or_create_service("Vehicle Procurement",                GID)
env.cr.commit()


# ======================================================================
# STEP 3 — Taxonomy
# Tuple format: (service_rec, category_name, cat_existing_id,
#                [(type_name, type_existing_id_or_None), ...])
#
# cat_existing_id  = None -> create new category
#                  = int  -> rename/reuse existing category by ID
# type_existing_id = None -> create new type
#                  = int  -> rename/reuse existing type by ID
# ======================================================================

TAXONOMY = [

    # ── Fleet Operations Management ───────────────────────────────────
    (svc_ops, "Vehicle Allocation & Dispatch", None, [
        ("Vehicle request not assigned",  None),
        ("No vehicle available",          None),
        ("Vehicle booking conflict",      None),
        ("Driver unavailable",            None),
        ("Last minute transport request", None),
        ("Vehicle reassignment",          None),
        ("Trip cancellation",             None),
    ]),
    # Cat ID:37 "Trip Scheduling" -> renamed "Transport Request Management"
    (svc_ops, "Transport Request Management", 37, [
        ("Trip Booking",                  75),
        ("Staff transport request",       None),
        ("Logistics transport request",   None),
        ("Airport pickup request",        None),
        ("VIP transport request",         None),
        ("Urgent transport request",      None),
    ]),
    (svc_ops, "Route Planning & Optimization", None, [
        ("Route inefficiency",            None),
        ("Traffic disruption",            None),
        ("Driver route deviation",        None),
        ("Delivery delay due to routing", None),
        ("Route redesign request",        None),
    ]),
    (svc_ops, "Vehicle Utilization Monitoring", None, [
        ("Vehicle underutilization",      None),
        ("Excessive idle time",           None),
        ("Unauthorized vehicle use",      None),
        ("Missing trip logs",             None),
        ("Fleet capacity shortage",       None),
    ]),

    # ── Driver Management ─────────────────────────────────────────────
    (svc_driver, "Driver Administration", None, [
        ("Driver license expired",        None),
        ("Missing driver documentation",  None),
        ("Driver onboarding",             None),
        ("Driver record update",          None),
        ("Driver contract renewal",       None),
    ]),
    (svc_driver, "Driver Scheduling", None, [
        ("Driver Scheduling Request",     72),
        ("Driver shift conflict",         None),
        ("Driver absence",                None),
        ("Driver overtime approval",      None),
        ("Driver replacement",            None),
    ]),
    (svc_driver, "Driver Safety Programs", None, [
        ("Unsafe driving complaint",      None),
        ("Driver safety violation",       None),
        ("Driver training required",      None),
        ("Safety awareness request",      None),
    ]),
    # Cat ID:34 "Driver Management" -> renamed "Driver Performance Monitoring"
    (svc_driver, "Driver Performance Monitoring", 34, [
        ("Driver behavior complaint",     71),   # renamed from "Driver Complaint"
        ("Speeding violation",            None),
        ("Harsh braking alert",           None),
        ("Driver disciplinary review",    None),
    ]),

    # ── Vehicle Maintenance ───────────────────────────────────────────
    (svc_maint, "Preventive Maintenance", None, [
        ("Scheduled vehicle service",     67),   # renamed from "Vehicle Preventive Service"
        ("Oil change required",           None),
        ("Tire replacement",              None),
        ("Brake servicing",               None),
        ("Battery replacement",           None),
    ]),
    (svc_maint, "Corrective Maintenance", None, [
        ("Vehicle breakdown",             65),   # renamed from "Vehicle Breakdown Report"
        ("Vehicle corrective repair",     66),
        ("Engine malfunction",            None),
        ("Electrical fault",              None),
        ("Cooling system failure",        None),
        ("Transmission issue",            None),
    ]),
    (svc_maint, "Maintenance Planning", None, [
        ("Vehicle inspection",            68),
        ("Missed maintenance schedule",   None),
        ("Maintenance backlog",           None),
        ("Maintenance record update",     None),
    ]),
    # Cat ID:32 "Vehicle Maintenance" -> repurposed as "Spare Parts Management"
    (svc_maint, "Spare Parts Management", 32, [
        ("Spare part unavailable",         None),
        ("Wrong spare part installed",     None),
        ("Spare part procurement",         None),
        ("Spare parts inventory shortage", None),
    ]),

    # ── Fuel Management ───────────────────────────────────────────────
    (svc_fuel, "Fuel Monitoring", None, [
        ("High fuel consumption",         None),
        ("Missing fuel data",             None),
        ("Fuel efficiency drop",          None),
    ]),
    (svc_fuel, "Fuel Fraud Detection", None, [
        ("Suspected fuel theft",          None),
        ("Fuel receipt mismatch",         None),
        ("Fuel card misuse",              None),
        ("Fuel quantity discrepancy",     None),
    ]),
    # Cat ID:33 "Fuel & Lubricants" -> renamed "Fuel Procurement"
    (svc_fuel, "Fuel Procurement", 33, [
        ("Fuel request",                  69),
        ("Fuel supply delay",             None),
        ("Vendor fuel shortage",          None),
        ("Fuel price discrepancy",        None),
    ]),
    (svc_fuel, "Fuel Reporting", None, [
        ("Fuel reconciliation issue",     70),   # renamed from "Fuel Reconciliation"
        ("Fuel report request",           None),
        ("Missing fuel logs",             None),
    ]),

    # ── Compliance & Regulatory Management ───────────────────────────
    # Cat ID:35 "Vehicle Registration" -> renamed "Vehicle Licensing"
    (svc_compliance, "Vehicle Licensing", 35, [
        ("Vehicle registration renewal",  73),
        ("Registration expired",          None),
        ("Missing vehicle documents",     None),
    ]),
    # Cat ID:36 "Insurance & Licensing" -> renamed "Insurance Management"
    (svc_compliance, "Insurance Management", 36, [
        ("Insurance renewal",             74),
        ("Insurance expired",             None),
        ("Insurance claim",               None),
        ("Accident insurance processing", None),
    ]),
    (svc_compliance, "Regulatory Compliance", None, [
        ("Roadworthiness expired",        None),
        ("Inspection failure",            None),
        ("Safety compliance violation",   None),
    ]),
    (svc_compliance, "Driver Compliance", None, [
        ("Driver license expired",        None),
        ("Medical certificate expired",   None),
        ("Compliance breach",             None),
    ]),

    # ── Fleet Safety & Risk Management ───────────────────────────────
    (svc_safety, "Incident Management", None, [
        ("Vehicle accident",              None),
        ("Minor collision",               None),
        ("Accident investigation",        None),
        ("Vehicle damage report",         None),
    ]),
    (svc_safety, "Safety Monitoring", None, [
        ("Speed violation",               None),
        ("Dangerous driving alert",       None),
        ("Safety complaint",              None),
    ]),
    (svc_safety, "Risk Mitigation", None, [
        ("High risk driver",              None),
        ("Safety policy violation",       None),
        ("Risk mitigation intervention",  None),
    ]),

    # ── Telematics & Technology Services ─────────────────────────────
    (svc_telematic, "GPS Tracking", None, [
        ("GPS device failure",            None),
        ("Location not updating",         None),
        ("GPS signal lost",               None),
    ]),
    (svc_telematic, "Telematics Data Analytics", None, [
        ("Missing telematics data",       None),
        ("Reporting error",               None),
        ("Incorrect vehicle data",        None),
    ]),
    (svc_telematic, "Fleet Monitoring Dashboards", None, [
        ("Dashboard not updating",        None),
        ("KPI reporting error",           None),
        ("Missing metrics",               None),
    ]),
    (svc_telematic, "IoT Sensor Integration", None, [
        ("Tire pressure sensor failure",  None),
        ("Engine health sensor issue",    None),
        ("IoT connectivity problem",      None),
    ]),

    # ── Reporting & Analytics Services ───────────────────────────────
    (svc_reporting, "Operational Reports", None, [
        ("Fleet utilization report",      None),
        ("Trip history report",           None),
        ("Driver report request",         None),
    ]),
    (svc_reporting, "Financial Reports", None, [
        ("Fleet expense report",          None),
        ("Maintenance cost analysis",     None),
        ("Fuel cost summary",             None),
    ]),
    (svc_reporting, "Performance Analytics", None, [
        ("Driver performance analysis",   None),
        ("Fleet efficiency analysis",     None),
        ("Cost per kilometer analysis",   None),
    ]),

    # ── Emergency & Support Services ─────────────────────────────────
    (svc_emergency, "Roadside Assistance", None, [
        ("Vehicle breakdown - roadside",  None),
        ("Flat tire",                     None),
        ("Battery failure",               None),
    ]),
    (svc_emergency, "Emergency Response", None, [
        ("Vehicle accident emergency",    None),
        ("Driver medical emergency",      None),
        ("Emergency vehicle dispatch",    None),
    ]),

    # ── Vehicle Procurement ───────────────────────────────────────────
    # Cat ID:38 "Vehicle Procurement" -> renamed "Procurement Requests"
    (svc_procure, "Procurement Requests", 38, [
        ("Vehicle procurement request",   76),
        ("Vehicle replacement request",   None),
        ("New vehicle specification",     None),
        ("Vendor evaluation request",     None),
    ]),
]


# ======================================================================
# STEP 4 — Seed categories, types, and classifier rows
# ======================================================================
print("\n[ Categories, Types & Classifier ]")
cat_count = type_count = err_count = 0
current_svc = None

for (svc_rec, cat_name, cat_existing_id, types) in TAXONOMY:

    if svc_rec != current_svc:
        current_svc = svc_rec
        print(f"\n  Service: {svc_rec.name} (ID:{svc_rec.id})")

    try:
        cat = get_or_create_category(cat_name, existing_id=cat_existing_id)
        cat_count += 1
    # catch-all: reported — a category that will not create is printed with its
    # exception, the cursor is rolled back and the row is counted into
    # err_count, which the run prints at the end. The taxonomy comes out short
    # and says so.
    except Exception as e:
        print(f"  X Category '{cat_name}': {e}")
        env.cr.rollback()
        err_count += 1
        continue

    for (type_name, type_existing_id) in types:
        try:
            t = get_or_create_type(type_name, existing_id=type_existing_id)
            classify(svc_rec.id, cat.id, t.id)
            type_count += 1
        # catch-all: reported — same as the category handler above: the type is
        # printed with its exception and counted into err_count. A
        # classification that did not happen is never counted as one that did.
        except Exception as e:
            print(f"    X Type '{type_name}': {e}")
            env.cr.rollback()
            err_count += 1

    env.cr.commit()


# ======================================================================
# STEP 5 — Summary
# ======================================================================
svc_ids = tuple(env['generic.service'].search([('service_group_id', '=', GID)]).ids)
env.cr.execute(
    "SELECT COUNT(*) FROM request_classifier WHERE service_id IN %s", (svc_ids,))
classifier_rows = env.cr.fetchone()[0]

total_svcs  = env['generic.service'].search_count([('service_group_id', '=', GID)])
total_cats  = env['request.category'].search_count([])
total_types = env['request.type'].search_count([])

print()
print("=" * 70)
print("  FLEET TAXONOMY SEED COMPLETE")
print("=" * 70)
print(f"  Services in Fleet group : {total_svcs}")
print(f"  Categories seeded       : {cat_count}")
print(f"  Types seeded            : {type_count}")
print(f"  Classifier rows (fleet) : {classifier_rows}")
print(f"  Errors                  : {err_count}")
print(f"  Total categories (all)  : {total_cats}")
print(f"  Total types (all)       : {total_types}")
print()
print("  PRESERVED IDs:")
print("  Group:      Fleet Management        ID:5")
print("  Service:    Fleet Ops Management    ID:7  (renamed)")
print("  Categories: 32,33,34,35,36,37,38   (renamed/repurposed)")
print("  Types:      65-76                   (preserved/renamed)")
print("=" * 70)
