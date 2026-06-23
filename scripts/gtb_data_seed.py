#!/usr/bin/env python3
"""
GTB demo data depth — staff, assets, fleet + their interconnections.

Runs in the `gtb` profile after the branches + company + requests seeds.
All DEMO data (generated), tied to the 122 GTB branches and to each other:

  * ~60 employees           — mapped to a branch (in-memory, for co-location)
  * ~150 facilities assets  — GTB-AST-#### code, located at a branch, with a
                              custodian who works at that branch
  * ~30 fleet vehicles      — located at a branch, with a driver
  * requests                — each assigned to an officer (res.users)

Idempotent + backfilling: ensures the target counts AND wires the relationships
onto records that already exist (re-running fixes prior un-linked data). The
asset-code prefix is switched from NRS-AST- to GTB-AST- for the GTB tenant.

ROBUSTNESS: every create/write goes through a SAVEPOINT (_sp_create/_sp_write),
so a DB-level error (constraint, etc.) rolls back just that operation instead
of aborting the whole transaction and cascading. Exec'd by bootstrap.py with
only {env} in scope (no __file__).
"""
import logging
import random

_logger = logging.getLogger("cadra.seed.gtb_data")
random.seed(7)

N_EMPLOYEES = 60
N_ASSETS = 150
N_VEHICLES = 30
N_OFFICERS = 8

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


def _sp_create(env, Model, vals):
    """Create inside a savepoint; return the record or None on DB/validation error."""
    try:
        with env.cr.savepoint():
            return Model.create(vals)
    except Exception as ex:  # noqa: BLE001
        _logger.info("create %s skipped: %s", Model._name, str(ex)[:120])
        return None


def _sp_write(env, rec, vals):
    """Write inside a savepoint; return True/False."""
    try:
        with env.cr.savepoint():
            rec.write(vals)
            return True
    except Exception:  # noqa: BLE001
        return False


def _slug(name, i):
    return name.lower().replace(" ", ".") + f".{i}@gtb.demo"


def fix_asset_codes_and_tags(env):
    """Re-brand asset codes AND barcode tags to the tenant's short code
    (NRS- → <brand>-). The asset module auto-generates both on create with a
    prefix; the brand-aware code only affects NEW records, so existing ones
    (seeded earlier) keep the old NRS- prefix and must be renamed in place."""
    brand = env["ir.config_parameter"].sudo().get_param("cadra.brand_short_name", "NRS")
    if brand == "NRS":
        return  # NRS tenant — already correct, nothing to re-brand
    old = "NRS-"
    new = f"{brand}-"

    # asset_code sequence prefix (future codes)
    seq = env["ir.sequence"].search([("code", "=", "nrs.asset")], limit=1)
    if seq and (seq.prefix or "").startswith(old):
        if _sp_write(env, seq, {"prefix": f"{brand}-AST-"}):
            print(f"  ✓ asset_code sequence prefix → {brand}-AST-")

    # existing asset_code + asset_tag on every asset
    codes = tags = 0
    for a in env["nrs.asset"].search(["|", ("asset_code", "=like", "NRS-%"), ("asset_tag", "=like", "NRS-%")]):
        vals = {}
        if a.asset_code and a.asset_code.startswith(old):
            vals["asset_code"] = a.asset_code.replace(old, new, 1)
        if a.asset_tag and a.asset_tag.startswith(old):
            vals["asset_tag"] = a.asset_tag.replace(old, new, 1)
        if vals and _sp_write(env, a, vals):
            codes += 1 if "asset_code" in vals else 0
            tags += 1 if "asset_tag" in vals else 0

    # the barcode tag.label history records
    labels = 0
    if "nrs.asset.tag.label" in env:
        for t in env["nrs.asset.tag.label"].search([("name", "=like", "NRS-%")]):
            if _sp_write(env, t, {"name": t.name.replace(old, new, 1)}):
                labels += 1
    env.cr.commit()
    print(f"  ✓ re-branded → {brand}-  (asset_code:{codes} asset_tag:{tags} tag-labels:{labels})")


def seed_employees(env, branches):
    """Ensure N employees; map each to a branch in-memory (for co-location);
    promote N_OFFICERS to res.users (request assignees). Returns (emps, officers, by_branch)."""
    Emp = env["hr.employee"]
    efields = Emp.fields_get()
    have = Emp.search_count([])
    made = 0
    for i in range(max(0, N_EMPLOYEES - have)):
        vals = {"name": f"{random.choice(_FIRST)} {random.choice(_LAST)}"}
        if "job_title" in efields:
            vals["job_title"] = _TITLES[i % len(_TITLES)]
        if _sp_create(env, Emp, vals) is not None:
            made += 1
    emps = Emp.search([], limit=N_EMPLOYEES)

    # Deterministic in-memory employee→branch map (no hr.employee branch field
    # here; hr.work.location needs an address we don't want to fabricate).
    by_branch = {}
    for i, e in enumerate(emps):
        if branches:
            by_branch.setdefault(branches[i % len(branches)].name, []).append(e)

    # Promote a few employees to internal users (request assignees). Random
    # passwords — they exist to be assignees, not to log in.
    officers = env["res.users"]
    grp = env.ref("base.group_user", raise_if_not_found=False)
    for i, e in enumerate(emps[:N_OFFICERS]):
        if "user_id" in efields and e.user_id:
            officers |= e.user_id
            continue
        login = _slug(e.name, i)
        u = env["res.users"].search([("login", "=", login)], limit=1)
        if not u:
            uvals = {"name": e.name, "login": login,
                     "password": "Gtb!" + "".join(random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(14))}
            if grp:
                uvals["groups_id"] = [(6, 0, [grp.id])]
            u = _sp_create(env, env["res.users"], uvals)
        if u:
            if "user_id" in efields:
                _sp_write(env, e, {"user_id": u.id})
            officers |= u
    env.cr.commit()
    print(f"  ✓ Employees: {len(emps)} (+{made} new) | officer-users: {len(officers)} | branches mapped: {len(by_branch)}")
    return emps, officers, by_branch


def wire_assets(env, branches, emps, by_branch):
    """Ensure N assets; give EVERY asset a custodian (employee at its branch)."""
    Asset = env["nrs.asset"]
    afields = Asset.fields_get()
    have = Asset.search_count([])
    Cat = env["nrs.asset.category"]
    cat_map = {c.name: c for c in Cat.search([])}
    for cn in sorted({t[2] for t in _ASSET_TYPES}):
        if cn not in cat_map:
            rec = _sp_create(env, Cat, {"name": cn})
            if rec:
                cat_map[cn] = rec
    made = 0
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
        if _sp_create(env, Asset, vals) is not None:
            made += 1
    env.cr.commit()

    all_emps = list(emps)
    wired = 0
    if "custodian_id" in afields and all_emps:
        for a in Asset.search([("custodian_id", "=", False)]):
            pool = by_branch.get(a.location_id.name) if a.location_id else None
            cust = random.choice(pool) if pool else random.choice(all_emps)
            if _sp_write(env, a, {"custodian_id": cust.id}):
                wired += 1
        env.cr.commit()
    print(f"  ✓ Assets: {Asset.search_count([])} (+{made} new) | custodians wired: {wired}")


def wire_fleet(env, branches, emps, by_branch):
    """Ensure N vehicles; give each a driver (res.partner via the employee)."""
    Veh = env["fleet.vehicle"]
    vfields = Veh.fields_get()
    have = Veh.search_count([])
    Brand = env["fleet.vehicle.model.brand"]
    Model = env["fleet.vehicle.model"]
    model_ids = []
    for brand_name, model_name in _VEHICLES:
        brand = Brand.search([("name", "=", brand_name)], limit=1) or _sp_create(env, Brand, {"name": brand_name})
        if not brand:
            continue
        model = Model.search([("name", "=", model_name), ("brand_id", "=", brand.id)], limit=1)
        if not model:
            model = _sp_create(env, Model, {"name": model_name, "brand_id": brand.id})
        if model:
            model_ids.append(model.id)
    made = 0
    if model_ids:
        for i in range(max(0, N_VEHICLES - have)):
            branch = branches[i % len(branches)] if branches else None
            vals = {"model_id": model_ids[i % len(model_ids)]}
            if "license_plate" in vfields:
                vals["license_plate"] = f"GTB-{random.randint(100,999)}{chr(65+i%26)}{chr(65+(i//26)%26)}"
            if "location" in vfields and branch:
                vals["location"] = branch.name
            if _sp_create(env, Veh, vals) is not None:
                made += 1
    env.cr.commit()

    all_emps = list(emps)
    wired = 0
    if "driver_id" in vfields and all_emps:
        Partner = env["res.partner"]
        for v in Veh.search([("driver_id", "=", False)]):
            pool = by_branch.get(v.location) if getattr(v, "location", None) else None
            emp = random.choice(pool) if pool else random.choice(all_emps)
            partner = emp.address_home_id
            if not partner:
                partner = _sp_create(env, Partner, {"name": emp.name})
                if partner:
                    _sp_write(env, emp, {"address_home_id": partner.id})
            if partner and _sp_write(env, v, {"driver_id": partner.id}):
                wired += 1
        env.cr.commit()
    print(f"  ✓ Fleet: {Veh.search_count([])} (+{made} new) | drivers wired: {wired}")


def wire_request_assignees(env, officers):
    """Give every request an assignee (res.users), round-robin across officers."""
    Req = env["request.request"]
    if "user_id" not in Req.fields_get() or not officers:
        print("  ! Request assignees: no user_id field or no officers — skipping")
        return
    pool = list(officers)
    wired = 0
    for i, r in enumerate(Req.search([("user_id", "=", False)])):
        if _sp_write(env, r, {"user_id": pool[i % len(pool)].id}):
            wired += 1
    env.cr.commit()
    print(f"  ✓ Request assignees wired: {wired}")


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
fix_asset_codes_and_tags(env)                       # noqa: F821
_emps, _officers, _by_branch = seed_employees(env, _branches)   # noqa: F821
wire_assets(env, _branches, _emps, _by_branch)      # noqa: F821
wire_fleet(env, _branches, _emps, _by_branch)       # noqa: F821
wire_request_assignees(env, _officers)              # noqa: F821
