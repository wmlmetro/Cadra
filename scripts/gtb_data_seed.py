#!/usr/bin/env python3
"""
GTB demo data depth — employees, assets, fleet (tied to the 122 GTB branches).

Runs in the `gtb` profile AFTER load_gtb_locations.py + gtb_seed.py, so the
branches (generic.location with coords) and company exist. Everything here is
DEMO data (not real) — names/plates/serials are generated. Built defensively:
each model ensures its prerequisites, creates with proven-minimal fields, and
enriches best-effort, so a model mismatch never breaks the seed.

Exec'd by scripts/bootstrap.py with only {env} in scope (no __file__).
Idempotent: skips a dataset if it already has >= its target count.
"""
import logging
import random

_logger = logging.getLogger("cadra.seed.gtb_data")
random.seed(7)

# ── How much demo data ───────────────────────────────────────────────
N_EMPLOYEES = 60
N_ASSETS = 150
N_VEHICLES = 30

_FIRST = ["Adebayo", "Chidinma", "Ifeoma", "Emeka", "Aisha", "Tunde", "Ngozi",
          "Yusuf", "Folake", "Obinna", "Halima", "Segun", "Amaka", "Musa",
          "Bola", "Uche", "Zainab", "Kunle", "Chioma", "Ibrahim", "Funmi",
          "Nkechi", "Sani", "Temitope", "Grace", "Abubakar", "Blessing", "Femi"]
_LAST = ["Okafor", "Adeyemi", "Bello", "Eze", "Mohammed", "Okoro", "Balogun",
         "Abubakar", "Nwosu", "Ogunleye", "Sani", "Afolabi", "Ibrahim",
         "Chukwu", "Lawal", "Onyeka", "Yakubu", "Adeleke", "Obi", "Danjuma"]
_TITLES = ["Branch Manager", "Operations Officer", "Customer Service Officer",
           "Teller", "Relationship Manager", "Cash Officer", "IT Support Officer",
           "Facilities Officer", "Security Supervisor", "Internal Control Officer",
           "Funds Transfer Officer", "Compliance Officer"]


def seed_employees(env, branches):
    try:
        Emp = env["hr.employee"]
        if Emp.search_count([]) >= N_EMPLOYEES:
            print(f"  ✓ Employees: already populated — skipping")
            return
        efields = Emp.fields_get()
        made, first_err = 0, None
        for i in range(N_EMPLOYEES):
            name = f"{random.choice(_FIRST)} {random.choice(_LAST)}"
            vals = {"name": name}
            if "job_title" in efields:
                vals["job_title"] = _TITLES[i % len(_TITLES)]
            try:
                rec = Emp.create(vals)
            except Exception as ex:  # noqa: BLE001
                first_err = first_err or str(ex)
                continue
            made += 1
            # Best-effort: note the branch in work_location (free-text on hr.employee).
            if branches and "work_location" in efields:
                try:
                    rec.write({"work_location": branches[i % len(branches)].name})
                except Exception:  # noqa: BLE001
                    pass
        env.cr.commit()
        msg = f"  ✓ Employees created: {made}"
        if made == 0 and first_err:
            msg += f"  (first error: {first_err[:120]})"
        print(msg)
    except Exception as ex:  # noqa: BLE001
        _logger.warning("GTB employees skipped: %s", ex)
        print(f"  ! Employees skipped: {ex}")


# (asset name, manufacturer, category)
_ASSET_TYPES = [
    ("NCR SelfServ 22 ATM", "NCR", "ATM"),
    ("Wincor Nixdorf ATM", "Diebold Nixdorf", "ATM"),
    ("Perkins 100KVA Diesel Generator", "Perkins", "Power Generation"),
    ("Mikano 60KVA Diesel Generator", "Mikano", "Power Generation"),
    ("Luminous 5KVA Inverter/UPS", "Luminous", "Power/UPS"),
    ("APC Smart-UPS 10KVA", "APC", "Power/UPS"),
    ("Hisense 1.5HP Split AC", "Hisense", "Cooling/HVAC"),
    ("LG 2HP Inverter Split AC", "LG", "Cooling/HVAC"),
    ("Hikvision 4MP IP Dome Camera", "Hikvision", "Security/CCTV"),
    ("ZKTeco K40 Access Control", "ZKTeco", "Security/CCTV"),
    ("HP EliteDesk 800 Desktop", "HP", "IT Equipment"),
    ("Dell OptiPlex 7090 Desktop", "Dell", "IT Equipment"),
    ("Canon iR2206N Photocopier", "Canon", "IT Equipment"),
    ("Cash Counting Machine GLORY", "Glory", "Banking Equipment"),
    ("Note Sorter Machine", "Giesecke+Devrient", "Banking Equipment"),
    ("Steel Vault Door", "Chubb", "Banking Equipment"),
    ("4-Door Steel Filing Cabinet", "Generic", "Furniture"),
    ("Teller Counter Station", "Generic", "Furniture"),
    ("Executive Office Desk", "Generic", "Furniture"),
    ("Grundfos CM5 Water Pump", "Grundfos", "Plumbing"),
]


def seed_assets(env, branches):
    try:
        Asset = env["nrs.asset"]
        if Asset.search_count([]) >= N_ASSETS:
            print(f"  ✓ Assets: already populated — skipping")
            return
        afields = Asset.fields_get()
        Cat = env["nrs.asset.category"]
        # Ensure categories exist (create any missing ones referenced above).
        cat_names = sorted({t[2] for t in _ASSET_TYPES})
        cat_map = {c.name: c for c in Cat.search([])}
        for cn in cat_names:
            if cn not in cat_map:
                try:
                    cat_map[cn] = Cat.create({"name": cn})
                except Exception:  # noqa: BLE001
                    pass
        has_cat = "category_id" in afields
        has_loc = "location_id" in afields
        has_mfr = "manufacturer" in afields
        has_serial = "serial_number" in afields

        made, first_err = 0, None
        for i in range(N_ASSETS):
            name, mfr, cat_name = _ASSET_TYPES[i % len(_ASSET_TYPES)]
            branch = branches[i % len(branches)] if branches else None
            vals = {"name": name}
            if has_serial:
                vals["serial_number"] = f"GTB-{cat_name[:3].upper()}-{i+1:04d}"
            if has_cat and cat_map.get(cat_name):
                vals["category_id"] = cat_map[cat_name].id
            if has_loc and branch:
                vals["location_id"] = branch.id
            if has_mfr:
                vals["manufacturer"] = mfr
            try:
                Asset.create(vals)
                made += 1
            except Exception as ex:  # noqa: BLE001
                first_err = first_err or str(ex)
            if made and made % 50 == 0:
                env.cr.commit()
        env.cr.commit()
        msg = f"  ✓ Assets created: {made}"
        if made == 0 and first_err:
            msg += f"  (first error: {first_err[:120]})"
        print(msg)
    except Exception as ex:  # noqa: BLE001
        _logger.warning("GTB assets skipped: %s", ex)
        print(f"  ! Assets skipped: {ex}")


# (brand, model)
_VEHICLES = [
    ("Toyota", "Hilux"), ("Toyota", "Hiace Bus"), ("Toyota", "Corolla"),
    ("Toyota", "Land Cruiser Prado"), ("Ford", "Ranger"), ("Mitsubishi", "L200"),
    ("Hyundai", "H1 Bus"), ("Nissan", "Patrol"),
]


def seed_fleet(env, branches):
    try:
        Veh = env["fleet.vehicle"]
        if Veh.search_count([]) >= N_VEHICLES:
            print(f"  ✓ Fleet: already populated — skipping")
            return
        vfields = Veh.fields_get()
        Brand = env["fleet.vehicle.model.brand"]
        Model = env["fleet.vehicle.model"]
        # Ensure brands + models.
        model_ids = []
        for brand_name, model_name in _VEHICLES:
            brand = Brand.search([("name", "=", brand_name)], limit=1) or Brand.create({"name": brand_name})
            model = Model.search([("name", "=", model_name), ("brand_id", "=", brand.id)], limit=1)
            if not model:
                model = Model.create({"name": model_name, "brand_id": brand.id})
            model_ids.append(model.id)

        has_plate = "license_plate" in vfields
        has_loc = "location" in vfields  # free-text on fleet.vehicle
        made, first_err = 0, None
        for i in range(N_VEHICLES):
            branch = branches[i % len(branches)] if branches else None
            vals = {"model_id": model_ids[i % len(model_ids)]}
            if has_plate:
                vals["license_plate"] = f"GTB-{random.randint(100,999)}{chr(65+i%26)}{chr(65+(i//26)%26)}"
            if has_loc and branch:
                vals["location"] = branch.name
            try:
                Veh.create(vals)
                made += 1
            except Exception as ex:  # noqa: BLE001
                first_err = first_err or str(ex)
        env.cr.commit()
        msg = f"  ✓ Fleet vehicles created: {made}"
        if made == 0 and first_err:
            msg += f"  (first error: {first_err[:120]})"
        print(msg)
    except Exception as ex:  # noqa: BLE001
        _logger.warning("GTB fleet skipped: %s", ex)
        print(f"  ! Fleet skipped: {ex}")


_branches = env["generic.location"].search([("latitude", "!=", False)])  # noqa: F821
print(f"  GTB demo data depth across {len(_branches)} branches:")
seed_employees(env, _branches)   # noqa: F821
seed_assets(env, _branches)      # noqa: F821
seed_fleet(env, _branches)       # noqa: F821
