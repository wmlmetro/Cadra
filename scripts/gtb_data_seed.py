#!/usr/bin/env python3
"""
GTB demo data depth — staff, assets, fleet + their interconnections.

Runs in the `gtb` profile after the branches + company + requests seeds.
All DEMO data (generated), tied to the 122 GTB branches and to each other:

  * ~60 employees           — assigned to a branch (work_location)
  * ~150 facilities assets  — GTB-AST-#### code, located at a branch, with a
                              custodian who works at that branch
  * ~30 fleet vehicles      — located at a branch, with a driver
  * requests                — each assigned to an officer (res.users)

Idempotent + backfilling: ensures the target counts AND wires the relationships
onto records that already exist (so re-running fixes prior un-linked data). The
asset-code prefix is switched from NRS-AST- to GTB-AST- for the GTB tenant
(the ir.sequence is per-DB) and existing codes are renamed. Defensive: each
step is guarded and never breaks the seed.

Exec'd by scripts/bootstrap.py with only {env} in scope (no __file__).
"""
import logging
import random

_logger = logging.getLogger("cadra.seed.gtb_data")
random.seed(7)

N_EMPLOYEES = 60
N_ASSETS = 150
N_VEHICLES = 30
N_OFFICERS = 8          # employees promoted to res.users to assign requests to

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


def _slug(name, i):
    return name.lower().replace(" ", ".") + f".{i}@gtb.demo"


def fix_asset_code_prefix(env):
    """The asset_code ir.sequence ships with prefix 'NRS-AST-'. For the GTB
    tenant, switch it to 'GTB-AST-' (the sequence is per-DB) and rename any
    already-created NRS-prefixed codes so the tenant is uniform."""
    try:
        seq = env["ir.sequence"].search([("code", "=", "nrs.asset")], limit=1)
        if seq and (seq.prefix or "").startswith("NRS-"):
            seq.write({"prefix": "GTB-AST-"})
            print(f"  ✓ asset_code sequence prefix → GTB-AST-")
        renamed = 0
        for a in env["nrs.asset"].search([("asset_code", "=like", "NRS-%")]):
            try:
                a.write({"asset_code": a.asset_code.replace("NRS-", "GTB-", 1)})
                renamed += 1
            except Exception:  # noqa: BLE001
                pass
        if renamed:
            print(f"  ✓ renamed {renamed} existing asset codes NRS- → GTB-")
        env.cr.commit()
    except Exception as ex:  # noqa: BLE001
        _logger.warning("asset code prefix fix skipped: %s", ex)
        print(f"  ! asset code prefix fix skipped: {ex}")


def seed_employees(env, branches):
    """Ensure N employees, each assigned to a branch (work_location). Returns
    the recordset. Also promotes N_OFFICERS of them to res.users (assignees)."""
    Emp = env["hr.employee"]
    efields = Emp.fields_get()
    have = Emp.search_count([])
    made = 0
    for i in range(max(0, N_EMPLOYEES - have)):
        name = f"{random.choice(_FIRST)} {random.choice(_LAST)}"
        vals = {"name": name}
        if "job_title" in efields:
            vals["job_title"] = _TITLES[i % len(_TITLES)]
        try:
            Emp.create(vals)
            made += 1
        except Exception as ex:  # noqa: BLE001
            _logger.info("emp create skipped: %s", ex)
    emps = Emp.search([], limit=N_EMPLOYEES)

    # Assign each employee to a branch (round-robin) so assets/vehicles can
    # co-locate their custodian/driver.
    if branches and "work_location" in efields:
        for i, e in enumerate(emps):
            if not e.work_location:
                try:
                    e.work_location = branches[i % len(branches)].name
                except Exception:  # noqa: BLE001
                    pass

    # Promote a few employees to internal users (request assignees). Random
    # passwords — they exist to be assignees, not to log in.
    officers = env["res.users"]
    try:
        grp = env.ref("base.group_user", raise_if_not_found=False)
        for i, e in enumerate(emps[:N_OFFICERS]):
            if "user_id" in efields and e.user_id:
                officers |= e.user_id
                continue
            login = _slug(e.name, i)
            existing = env["res.users"].search([("login", "=", login)], limit=1)
            if existing:
                u = existing
            else:
                uvals = {"name": e.name, "login": login,
                         "password": "Gtb!" + "".join(random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(14))}
                if grp:
                    uvals["groups_id"] = [(6, 0, [grp.id])]
                u = env["res.users"].create(uvals)
            if "user_id" in efields:
                try:
                    e.user_id = u.id
                except Exception:  # noqa: BLE001
                    pass
            officers |= u
    except Exception as ex:  # noqa: BLE001
        _logger.warning("officer users skipped: %s", ex)
    env.cr.commit()
    print(f"  ✓ Employees: {len(emps)} (+{made} new) | officer-users: {len(officers)}")
    return emps, officers


def _emps_by_branch(emps):
    m = {}
    for e in emps:
        key = (e.work_location or "").strip()
        if key:
            m.setdefault(key, []).append(e)
    return m


def wire_assets(env, branches, emps):
    """Ensure N assets and give EVERY asset a custodian — an employee at the
    asset's own branch when possible, else any employee."""
    Asset = env["nrs.asset"]
    afields = Asset.fields_get()
    have = Asset.search_count([])
    cat_names = sorted({t[2] for t in _ASSET_TYPES})
    Cat = env["nrs.asset.category"]
    cat_map = {c.name: c for c in Cat.search([])}
    for cn in cat_names:
        if cn not in cat_map:
            try:
                cat_map[cn] = Cat.create({"name": cn})
            except Exception:  # noqa: BLE001
                pass
    made, first_err = 0, None
    for i in range(max(0, N_ASSETS - have)):
        name, mfr, cat_name = _ASSET_TYPES[i % len(_ASSET_TYPES)]
        branch = branches[i % len(branches)] if branches else None
        vals = {"name": name}
        if "category_id" in afields and cat_map.get(cat_name):
            vals["category_id"] = cat_map[cat_name].id
        if "location_id" in afields and branch:
            vals["location_id"] = branch.id
        if "manufacturer" in afields:
            vals["manufacturer"] = mfr
        try:
            Asset.create(vals)
            made += 1
        except Exception as ex:  # noqa: BLE001
            first_err = first_err or str(ex)
    env.cr.commit()

    # Backfill custodians on every asset missing one (co-located by branch).
    by_branch = _emps_by_branch(emps)
    all_emps = list(emps)
    wired = 0
    if "custodian_id" in afields and all_emps:
        for a in Asset.search([("custodian_id", "=", False)]):
            pool = by_branch.get(a.location_id.name) if a.location_id else None
            cust = random.choice(pool) if pool else random.choice(all_emps)
            try:
                a.custodian_id = cust.id
                wired += 1
            except Exception:  # noqa: BLE001
                pass
        env.cr.commit()
    msg = f"  ✓ Assets: {Asset.search_count([])} (+{made} new) | custodians wired: {wired}"
    if made == 0 and have == 0 and first_err:
        msg += f"  (first error: {first_err[:120]})"
    print(msg)


def wire_fleet(env, branches, emps):
    """Ensure N vehicles and give each a driver (res.partner) — the home-address
    partner of an employee at the vehicle's branch (created if needed)."""
    Veh = env["fleet.vehicle"]
    vfields = Veh.fields_get()
    have = Veh.search_count([])
    Brand = env["fleet.vehicle.model.brand"]
    Model = env["fleet.vehicle.model"]
    model_ids = []
    for brand_name, model_name in _VEHICLES:
        brand = Brand.search([("name", "=", brand_name)], limit=1) or Brand.create({"name": brand_name})
        model = Model.search([("name", "=", model_name), ("brand_id", "=", brand.id)], limit=1)
        if not model:
            model = Model.create({"name": model_name, "brand_id": brand.id})
        model_ids.append(model.id)
    made, first_err = 0, None
    for i in range(max(0, N_VEHICLES - have)):
        branch = branches[i % len(branches)] if branches else None
        vals = {"model_id": model_ids[i % len(model_ids)]}
        if "license_plate" in vfields:
            vals["license_plate"] = f"GTB-{random.randint(100,999)}{chr(65+i%26)}{chr(65+(i//26)%26)}"
        if "location" in vfields and branch:
            vals["location"] = branch.name
        try:
            Veh.create(vals)
            made += 1
        except Exception as ex:  # noqa: BLE001
            first_err = first_err or str(ex)
    env.cr.commit()

    # Backfill drivers (res.partner via employee.address_home_id).
    by_branch = _emps_by_branch(emps)
    all_emps = list(emps)
    wired = 0
    if "driver_id" in vfields and all_emps:
        Partner = env["res.partner"]
        for v in Veh.search([("driver_id", "=", False)]):
            pool = by_branch.get(v.location) if getattr(v, "location", None) else None
            emp = random.choice(pool) if pool else random.choice(all_emps)
            try:
                partner = emp.address_home_id
                if not partner:
                    partner = Partner.create({"name": emp.name})
                    try:
                        emp.address_home_id = partner.id
                    except Exception:  # noqa: BLE001
                        pass
                v.driver_id = partner.id
                wired += 1
            except Exception:  # noqa: BLE001
                pass
        env.cr.commit()
    msg = f"  ✓ Fleet: {Veh.search_count([])} (+{made} new) | drivers wired: {wired}"
    if made == 0 and have == 0 and first_err:
        msg += f"  (first error: {first_err[:120]})"
    print(msg)


def wire_request_assignees(env, officers):
    """Give every request an assignee (res.users), round-robin across officers."""
    try:
        Req = env["request.request"]
        if "user_id" not in Req.fields_get() or not officers:
            print("  ! Request assignees: no user_id field or no officers — skipping")
            return
        pool = list(officers)
        wired = 0
        for i, r in enumerate(Req.search([("user_id", "=", False)])):
            try:
                r.user_id = pool[i % len(pool)].id
                wired += 1
            except Exception:  # noqa: BLE001
                pass
        env.cr.commit()
        print(f"  ✓ Request assignees wired: {wired}")
    except Exception as ex:  # noqa: BLE001
        _logger.warning("request assignees skipped: %s", ex)
        print(f"  ! Request assignees skipped: {ex}")


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

# (brand, model)
_VEHICLES = [
    ("Toyota", "Hilux"), ("Toyota", "Hiace Bus"), ("Toyota", "Corolla"),
    ("Toyota", "Land Cruiser Prado"), ("Ford", "Ranger"), ("Mitsubishi", "L200"),
    ("Hyundai", "H1 Bus"), ("Nissan", "Patrol"),
]


_branches = env["generic.location"].search([("latitude", "!=", False)])  # noqa: F821
print(f"  GTB demo data depth across {len(_branches)} branches:")
fix_asset_code_prefix(env)                          # noqa: F821
_emps, _officers = seed_employees(env, _branches)   # noqa: F821
wire_assets(env, _branches, _emps)                  # noqa: F821
wire_fleet(env, _branches, _emps)                   # noqa: F821
wire_request_assignees(env, _officers)              # noqa: F821
