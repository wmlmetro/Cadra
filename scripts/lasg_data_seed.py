#!/usr/bin/env python3
"""
LASG (Lagos State Ministry of Health) demo data depth — staff, assets, fleet
+ their interconnections.

Runs in the `lasg` profile after the facilities + company + requests seeds.
Mostly DEMO data (generated), tied to the 90 LASG health facilities and to each
other, EXCEPT the 30 hospital Medical Directors, which are REAL names taken from
the client's General/secondary hospital list and seeded first as facility heads:

  * ~60 employees           — 30 real Medical Directors + generated clinical/
                              facilities staff, mapped to a facility (in-memory)
  * ~150 assets             — <brand>-AST-#### code, healthcare-themed (medical
                              equipment, power, cold-chain, etc.), at a facility,
                              with a custodian who works at that facility
  * ~30 fleet vehicles      — ambulances + utility, at a facility, with a driver
  * requests                — each assigned to an officer (res.users)

Idempotent + backfilling: ensures the target counts AND wires the relationships
onto records that already exist (re-running fixes prior un-linked data). The
asset-code prefix is switched from NRS-AST- to the tenant's short code
(read from cadra.brand_short_name → LASG-AST-; the short name "LASG Health" is
uppercased and de-spaced to "LASGHEALTH", so we override to a clean "LASG" here).

ROBUSTNESS: every create/write goes through a SAVEPOINT (_sp_create/_sp_write),
so a DB-level error (constraint, etc.) rolls back just that operation instead
of aborting the whole transaction and cascading. Exec'd by bootstrap.py with
only {env} in scope (no __file__).
"""
import logging
import random

_logger = logging.getLogger("cadra.seed.lasg_data")
random.seed(7)

# Short code used for asset codes / IR numbers / plates. brand_short_name is a
# human label ("LASG Health"); we want a clean machine prefix here.
BRAND_CODE = "LASG"

N_EMPLOYEES = 60
N_ASSETS = 150
N_VEHICLES = 30
N_OFFICERS = 8

# Real Medical Directors / facility heads from the client's General & secondary
# hospital list. Seeded first (as "Medical Director") so the demo shows real
# leadership names against real facilities.
_MEDICAL_DIRECTORS = [
    "Dr Muyiwa Balogun Oluwa", "Dr Sotunde Yetunde", "Dr Soyinka Ayodapo Samuel",
    "Dr Ogungbemile Babalola Dokun", "Dr Agbaje Omolara", "Dr Bakare Surajudeen Olatunde",
    "Dr Folakemi Irewole-Ojo", "Dr Adesola Sunday Oluseyi", "Dr Adeiyi Taiwo",
    "Dr Babafemi Olusegun Joseph", "Dr Fadare Folasade Oluseye", "Dr Ime Okon",
    "Dr Mustapha Bamidele", "Dr Olufemi Babatunde Aletan", "Dr Hassan Taiwo Kamorudeen",
    "Dr Oseni Saliu Olugbenga", "Dr Idowu Ayoola Ayokunle", "Dr Aduke Mafe",
    "Dr Omololu Olufemi Motunolani", "Dr Arogundade Adeolu", "Dr Adejumo Adedeji Olusola",
    "Dr Taiwo Oluyemi", "Dr Olanike Olutekunbi", "Dr Pitan Adesola Ayodele",
    "Dr Adebajo Madewa Adewole", "Dr Sojinrin Mobolaji Olumide", "Dr Quadri Mustapha Adebola",
    "Dr Olayinka Shoneye-Vaughan", "Dr Funmi Eso", "Dr Adenike Omosun",
]

_FIRST = ["Adebayo", "Chidinma", "Ifeoma", "Emeka", "Aisha", "Tunde", "Ngozi",
          "Yusuf", "Folake", "Obinna", "Halima", "Segun", "Amaka", "Musa",
          "Bola", "Uche", "Zainab", "Kunle", "Chioma", "Ibrahim", "Funmi",
          "Nkechi", "Sani", "Temitope", "Grace", "Abubakar", "Blessing", "Femi"]
_LAST = ["Okafor", "Adeyemi", "Bello", "Eze", "Mohammed", "Okoro", "Balogun",
         "Abubakar", "Nwosu", "Ogunleye", "Sani", "Afolabi", "Ibrahim",
         "Chukwu", "Lawal", "Onyeka", "Yakubu", "Adeleke", "Obi", "Danjuma"]
# Clinical + facilities roles for a hospital / PHC network.
_TITLES = ["Matron", "Nursing Officer", "Medical Officer", "Pharmacist",
           "Laboratory Scientist", "Health Records Officer", "Facilities Officer",
           "Biomedical Engineer", "Environmental Health Officer", "Security Supervisor",
           "Store Officer", "Community Health Officer"]


def _sp_create(env, Model, vals):
    """Create inside a savepoint; return the record or None on DB/validation error."""
    try:
        with env.cr.savepoint():
            return Model.create(vals)
    # catch-all: reported — the savepoint is the point: one bad row must not
    # roll back the seed. The skip is logged with the model and the error and
    # None is returned, and every caller gates its counter on `is not None`, so
    # a row that did not create is never counted as one that did.
    except Exception as ex:  # noqa: BLE001
        _logger.info("create %s skipped: %s", Model._name, str(ex)[:120])
        return None


def _sp_write(env, rec, vals):
    """Write inside a savepoint; return True/False."""
    try:
        with env.cr.savepoint():
            rec.write(vals)
            return True
    # catch-all: reported — returns False, and the callers that own a counter
    # gate it on the return value, so the seed's printed totals count writes
    # that landed. A savepoint keeps the failure from taking the transaction
    # with it.
    except Exception:  # noqa: BLE001
        return False


def _slug(name, i):
    return name.lower().replace(" ", ".") + f".{i}@lasg.demo"


def fix_asset_codes_and_tags(env):
    """Re-brand asset codes AND barcode tags to the tenant's short code
    (NRS- → LASG-). The asset module auto-generates both on create with a
    prefix; the brand-aware code only affects NEW records, so existing ones
    (seeded earlier) keep the old NRS- prefix and must be renamed in place."""
    old = "NRS-"
    new = f"{BRAND_CODE}-"
    target = f"{BRAND_CODE}-AST-"

    # asset_code sequence prefix (future codes). active_test=False because the
    # question is whether this sequence EXISTS, not whether it is in use. The
    # old `if seq and (seq.prefix or "").startswith(old)` made "no sequence on
    # this database" indistinguishable from "already re-branded" — both fell
    # through to the same silent nothing.
    seq = env["ir.sequence"].with_context(active_test=False).search(
        [("code", "=", "nrs.asset")], limit=1)
    if not seq:
        # Fatal, and fatal HERE rather than later: nrs.asset.create() raises
        # when this sequence is missing, _sp_create swallows that per record,
        # and the run would report "+0 new" for the 150 assets it never made.
        raise RuntimeError(
            "asset-code sequence missing: no ir.sequence with code 'nrs.asset' "
            "on this database (searched archived-inclusive). It ships in "
            "myservice_asset_register/data/asset_sequences.xml — install or "
            f"upgrade that module so future assets can mint {target} codes.")
    prefix = seq.prefix or ""
    if prefix.startswith(old):
        if not _sp_write(env, seq, {"prefix": target}):
            raise RuntimeError(
                f"asset-code sequence prefix write failed: ir.sequence id={seq.id} "
                f"still reads {prefix!r} — every asset created after this seed "
                f"would keep minting {old} codes.")
        print(f"  ✓ asset_code sequence prefix {prefix} → {target}")
    elif prefix == target:
        print(f"  = asset_code sequence prefix already {target} — nothing to re-brand")
    else:
        # Someone set it by hand. Not ours to overwrite, but not a success
        # either: future codes will be neither NRS- nor this tenant's.
        print(f"  ! asset_code sequence prefix is {prefix!r} — neither {old} nor "
              f"{target}; left as found, future asset codes will NOT be {target}")
    if "active" in seq._fields and not seq.active:
        # next_by_code() only searches ACTIVE sequences, so an archived one
        # mints nothing however its prefix now reads.
        print(f"  ! asset-code sequence id={seq.id} is ARCHIVED — no asset code "
              f"can be generated from it until it is un-archived")

    # Rename existing codes/tags via RAW SQL. The ORM write() path was being
    # silently rolled back (a write hook/constraint on nrs.asset, swallowed by
    # the per-record savepoint), so asset_tag stayed NRS-. Raw UPDATEs bypass
    # that. substring(x FROM 5) drops the 4-char "NRS-" prefix.
    cr = env.cr
    cr.execute("UPDATE nrs_asset SET asset_code = %s || substring(asset_code FROM 5) "
               "WHERE asset_code LIKE 'NRS-%%'", (new,))
    codes = cr.rowcount
    cr.execute("UPDATE nrs_asset SET asset_tag = %s || substring(asset_tag FROM 5) "
               "WHERE asset_tag LIKE 'NRS-%%'", (new,))
    tags = cr.rowcount
    labels = 0
    if "nrs.asset.tag.label" in env:
        cr.execute("UPDATE nrs_asset_tag_label SET name = %s || substring(name FROM 5) "
                   "WHERE name LIKE 'NRS-%%'", (new,))
        labels = cr.rowcount
    env.cr.commit()
    env.invalidate_all()
    if codes or tags or labels:
        print(f"  ✓ re-branded via SQL → {BRAND_CODE}-  (asset_code:{codes} asset_tag:{tags} tag-labels:{labels})")
    else:
        # A real zero, and a legitimate one on a re-run: every row already
        # carries the tenant prefix. Printed WITHOUT a tick — a ✓ over three
        # zeros read exactly like work that had happened.
        print(f"  = no {old} rows left to re-brand "
              f"(asset_code / asset_tag / tag-labels all 0)")


def seed_employees(env, facilities):
    """Ensure N employees; seed the 30 real Medical Directors first, then fill
    with generated clinical/facilities staff. Map each to a facility in-memory
    (for co-location); promote N_OFFICERS to res.users (request assignees).
    Returns (emps, officers, by_facility)."""
    Emp = env["hr.employee"]
    efields = Emp.fields_get()

    # 1) Real Medical Directors (idempotent by name).
    md_made = 0
    for name in _MEDICAL_DIRECTORS:
        if Emp.search_count([("name", "=", name)]):
            continue
        vals = {"name": name}
        if "job_title" in efields:
            vals["job_title"] = "Medical Director"
        if _sp_create(env, Emp, vals) is not None:
            md_made += 1

    # 2) Generated clinical/facilities staff to reach the target headcount.
    have = Emp.search_count([])
    made = 0
    for i in range(max(0, N_EMPLOYEES - have)):
        vals = {"name": f"{random.choice(_FIRST)} {random.choice(_LAST)}"}
        if "job_title" in efields:
            vals["job_title"] = _TITLES[i % len(_TITLES)]
        if _sp_create(env, Emp, vals) is not None:
            made += 1
    emps = Emp.search([], limit=N_EMPLOYEES)

    # Ensure every employee carries a unique IR number — the cross-system staff
    # key used for custodian linking and the /hr/employees/by-ir lookup. Demo
    # employees have none, so we assign tenant-prefixed IRs here. Idempotent:
    # only fills in the blanks.
    if "ir_number" in efields:
        prefix = f"{BRAND_CODE}-IR-"
        used = {e.ir_number for e in Emp.search([("ir_number", "!=", False)])}
        seq = 0
        assigned = 0
        for e in Emp.search([("ir_number", "=", False)]):
            seq += 1
            code = f"{prefix}{seq:05d}"
            while code in used:
                seq += 1
                code = f"{prefix}{seq:05d}"
            used.add(code)
            if _sp_write(env, e, {"ir_number": code}):
                assigned += 1
        if assigned:
            env.cr.commit()
            print(f"  ✓ IR numbers assigned: {assigned} (prefix {prefix})")

    # Deterministic in-memory employee→facility map (no hr.employee facility
    # field here; hr.work.location needs an address we don't want to fabricate).
    by_facility = {}
    for i, e in enumerate(emps):
        if facilities:
            by_facility.setdefault(facilities[i % len(facilities)].name, []).append(e)

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
                     "password": "Lasg!" + "".join(random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(14))}
            if grp:
                # Odoo 19 renamed res.users.groups_id → group_ids.
                grp_field = "group_ids" if "group_ids" in env["res.users"]._fields else "groups_id"
                uvals[grp_field] = [(6, 0, [grp.id])]
            u = _sp_create(env, env["res.users"], uvals)
        if u:
            if "user_id" in efields:
                _sp_write(env, e, {"user_id": u.id})
            officers |= u
    env.cr.commit()
    print(f"  ✓ Employees: {len(emps)} (+{made} generated, +{md_made} real MDs) | "
          f"officer-users: {len(officers)} | facilities mapped: {len(by_facility)}")
    return emps, officers, by_facility


def wire_assets(env, facilities, emps, by_facility):
    """Ensure N assets; give EVERY asset a custodian (employee at its facility)."""
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
        facility = facilities[i % len(facilities)] if facilities else None
        vals = {"name": name}
        if "category_id" in afields and cat_map.get(cat_name):
            vals["category_id"] = cat_map[cat_name].id
        if "location_id" in afields and facility:
            vals["location_id"] = facility.id
        if "manufacturer" in afields:
            vals["manufacturer"] = mfr
        if _sp_create(env, Asset, vals) is not None:
            made += 1
    env.cr.commit()

    all_emps = list(emps)
    # Two different outcomes, counted apart. `matched` is the intended one: a
    # custodian who works at the asset's own facility. `fallback` is a random
    # employee, used when the asset's facility has nobody mapped to it (staff are
    # spread round-robin, so with more facilities than employees some have none) or
    # when the asset has no facility at all. The fallback is KEPT — a demo asset
    # with no custodian is worse than one with an off-site custodian — but it is
    # not the same thing, so it is never folded into a single "custodians wired"
    # number again. The case where EVERY assignment was a fallback (no facilities
    # loaded) now fails at the foot of this script instead of reaching here.
    matched = 0
    fallback = 0
    if "custodian_id" in afields and all_emps:
        for a in Asset.search([("custodian_id", "=", False)]):
            pool = by_facility.get(a.location_id.name) if a.location_id else None
            cust = random.choice(pool) if pool else random.choice(all_emps)
            if _sp_write(env, a, {"custodian_id": cust.id}):
                if pool:
                    matched += 1
                else:
                    fallback += 1
        env.cr.commit()
    print(f"  ✓ Assets: {Asset.search_count([])} (+{made} new) | custodians wired: "
          f"{matched} at their own facility, {fallback} random "
          f"(no staff mapped to that facility)")


def wire_fleet(env, facilities, emps, by_facility):
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
            facility = facilities[i % len(facilities)] if facilities else None
            vals = {"model_id": model_ids[i % len(model_ids)]}
            if "license_plate" in vfields:
                vals["license_plate"] = f"{BRAND_CODE}-{random.randint(100,999)}{chr(65+i%26)}{chr(65+(i//26)%26)}"
            if "location" in vfields and facility:
                vals["location"] = facility.name
            if _sp_create(env, Veh, vals) is not None:
                made += 1
    env.cr.commit()

    all_emps = list(emps)
    # Same split as the custodians above: a driver who works at the vehicle's
    # own facility versus a random employee because that facility has no staff
    # mapped to it. One number covering both hid a matching step that had
    # fallen through entirely.
    matched = 0
    fallback = 0
    if "driver_id" in vfields and all_emps:
        Partner = env["res.partner"]
        for v in Veh.search([("driver_id", "=", False)]):
            pool = by_facility.get(v.location) if getattr(v, "location", None) else None
            emp = random.choice(pool) if pool else random.choice(all_emps)
            # Odoo 19 removed hr.employee.address_home_id; the fleet driver just
            # needs a res.partner, so fall back to the work contact / user
            # partner, else create one (and backfill address_home_id on 15).
            has_home = "address_home_id" in emp._fields
            partner = emp.address_home_id if has_home else False
            if not partner:
                partner = getattr(emp, "work_contact_id", False) \
                    or (emp.user_id.partner_id if emp.user_id else False)
            if not partner:
                partner = _sp_create(env, Partner, {"name": emp.name})
                if partner and has_home:
                    _sp_write(env, emp, {"address_home_id": partner.id})
            if partner and _sp_write(env, v, {"driver_id": partner.id}):
                if pool:
                    matched += 1
                else:
                    fallback += 1
        env.cr.commit()
    print(f"  ✓ Fleet: {Veh.search_count([])} (+{made} new) | drivers wired: "
          f"{matched} at their own facility, {fallback} random "
          f"(no staff mapped to that facility)")


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


# (asset name, manufacturer, category) — hospital / PHC facilities equipment.
_ASSET_TYPES = [
    ("Mindray Patient Monitor", "Mindray", "Medical Equipment"),
    ("GE Logiq Ultrasound Scanner", "GE Healthcare", "Medical Equipment"),
    ("Drager Anaesthesia Machine", "Dräger", "Medical Equipment"),
    ("Fresenius Dialysis Machine", "Fresenius", "Medical Equipment"),
    ("Tuttnauer Autoclave Steriliser", "Tuttnauer", "Medical Equipment"),
    ("Philips Defibrillator", "Philips", "Medical Equipment"),
    ("Oxygen Concentrator 10L", "Yuwell", "Medical Equipment"),
    ("Infant Incubator", "GE Healthcare", "Medical Equipment"),
    ("Hospital Bed (Electric)", "Hill-Rom", "Ward Equipment"),
    ("Examination Couch", "Generic", "Ward Equipment"),
    ("Vaccine Cold-Chain Refrigerator", "Haier Biomedical", "Cold Chain"),
    ("Laboratory Centrifuge", "Eppendorf", "Laboratory"),
    ("Haematology Analyser", "Sysmex", "Laboratory"),
    ("Perkins 100KVA Diesel Generator", "Perkins", "Power Generation"),
    ("Mikano 60KVA Diesel Generator", "Mikano", "Power Generation"),
    ("Luminous 5KVA Inverter/UPS", "Luminous", "Power/UPS"),
    ("Solar Inverter System 10KVA", "Felicity", "Power/UPS"),
    ("Hisense 2HP Split AC", "Hisense", "Cooling/HVAC"),
    ("Hikvision 4MP IP Dome Camera", "Hikvision", "Security/CCTV"),
    ("Grundfos CM5 Water Pump", "Grundfos", "Plumbing"),
]

# (brand, model) — ambulances + Ministry utility fleet.
_VEHICLES = [
    ("Toyota", "Hiace Ambulance"), ("Mercedes-Benz", "Sprinter Ambulance"),
    ("Ford", "Transit Ambulance"), ("Toyota", "Hilux"),
    ("Toyota", "Hiace Bus"), ("Toyota", "Corolla"),
    ("Mitsubishi", "L200"), ("Nissan", "Urvan"),
]


# active_test=False: the question is whether this tenant's facilities EXIST, not
# whether they are active — an archived facility still anchors the assets and
# staff already seeded against it, so an empty result here has to mean absent.
_facilities = env["generic.location"].with_context(active_test=False).search(  # noqa: F821
    [("latitude", "!=", False)])
if not _facilities:
    # Every relationship this seed wires is keyed on this set: asset→facility,
    # custodian→facility, vehicle→facility. Empty, the seed used to run to
    # completion and print "across 0 facilities" followed by full-success counts
    # for assets placed nowhere and custodians drawn at random. Fail at the
    # door instead, naming the step that should have produced them.
    raise RuntimeError(
        "no generic.location on this database has a latitude (searched "
        "archived-inclusive) — the \"LASG Facilities (90)\" step "
        "(scripts/load_lasg_locations.py) has not run here, or ran and failed. "
        "Run it first; without it assets get no facility and every custodian "
        "and driver is a random employee.")
print(f"  LASG demo data depth across {len(_facilities)} facilities:")
fix_asset_codes_and_tags(env)                          # noqa: F821
_emps, _officers, _by_facility = seed_employees(env, _facilities)   # noqa: F821
wire_assets(env, _facilities, _emps, _by_facility)     # noqa: F821
wire_fleet(env, _facilities, _emps, _by_facility)      # noqa: F821
wire_request_assignees(env, _officers)                 # noqa: F821
