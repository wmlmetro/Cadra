"""
NRS Asset Register Seed Script
================================
Seeds 150+ assets across all 20 categories and NRS locations.
Also replicates all assets + categories into generic.resource model.
WestMetro Limited | myservice.com.ng
"""
import random
from datetime import date, timedelta

env = env  # noqa: Odoo shell

# ── Helpers ──────────────────────────────────────────────────────────────────

def rdate(start_year=2018, end_year=2024):
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))

def depreciating(cost, acq_date, rate=0.15):
    years = (date.today() - acq_date).days / 365.25
    return round(cost * ((1 - rate) ** years), 2)

# ── Load reference data ───────────────────────────────────────────────────────

print("=" * 70)
print("  NRS ASSET REGISTER SEED — WestMetro Limited")
print("=" * 70)

# Categories
cats = {c.name: c for c in env['nrs.asset.category'].search([])}
print(f"Categories loaded: {len(cats)}")

# Locations — pick a spread of real NRS offices
all_locs = env['generic.location'].search([('name', '!=', False)], limit=80)
locs = [l for l in all_locs if l.name]
print(f"Locations loaded: {len(locs)}")

if not locs:
    print("ERROR: No locations found. Run location seed first.")
    exit()

# States for domain mapping
DOMAINS = ['civil', 'electrical', 'hvac', 'plumbing', 'mechanical',
           'ict', 'security', 'fire_safety', 'fleet', 'general']

CONDITIONS = ['new', 'good', 'fair', 'poor', 'critical']
STATES     = ['active', 'active', 'active', 'active', 'under_maintenance',
              'under_maintenance', 'disposed', 'retrieved']

DEPTS = [
    'Executive Office', 'Finance & Accounts', 'ICT Department',
    'Facilities Management', 'Human Resources', 'Legal Services',
    'Tax Operations', 'Internal Audit', 'Procurement', 'Security'
]

# ── Asset definitions ─────────────────────────────────────────────────────────
# Each tuple: (name_template, category, manufacturer, model, cost_range,
#              domain, serial_prefix)

ASSET_TYPES = [
    # ── Power & Energy ────────────────────────────────────────────────────
    ("Perkins 100KVA Diesel Generator",    "Generators",      "Perkins",    "100KVA",     (3500000, 5500000),  "mechanical", "GEN"),
    ("Mikano 60KVA Diesel Generator",      "Generators",      "Mikano",     "60KVA",      (2000000, 3500000),  "mechanical", "GEN"),
    ("FG Wilson 200KVA Generator",         "Generators",      "FG Wilson",  "200KVA",     (6000000, 9000000),  "mechanical", "GEN"),
    ("Prag 10KVA UPS System",              "UPS",             "Prag",       "10KVA",      (400000,  800000),   "electrical", "UPS"),
    ("Emerson 20KVA UPS",                  "UPS",             "Emerson",    "20KVA-N",    (900000,  1500000),  "electrical", "UPS"),
    ("Luminous 5KVA Inverter/UPS",         "UPS",             "Luminous",   "5KVA-INV",   (180000,  350000),   "electrical", "UPS"),
    ("ABB Electrical Panel 3-Phase",       "Electrical Panels","ABB",       "DB-3PH",     (350000,  700000),   "electrical", "ELP"),
    ("Schneider Distribution Board",       "Electrical Panels","Schneider", "DB-250A",    (250000,  500000),   "electrical", "ELP"),

    # ── HVAC & Cooling ────────────────────────────────────────────────────
    ("Hisense 1.5HP Split AC Unit",        "A/C Units",       "Hisense",    "HIS-1.5HP",  (150000,  250000),   "hvac", "ACU"),
    ("LG 2HP Inverter Split AC",           "A/C Units",       "LG",         "S4-W18KL3AA",(220000,  380000),   "hvac", "ACU"),
    ("Daikin 3HP Cassette AC",             "A/C Units",       "Daikin",     "FCAG71",     (450000,  750000),   "hvac", "ACU"),
    ("Samsung 2.5HP Floor Standing AC",    "A/C Units",       "Samsung",    "AF28FSS",    (350000,  600000),   "hvac", "ACU"),
    ("York 5-Ton Central AHU",             "AHUs",            "York",       "AHU-5T",     (1200000, 2500000),  "hvac", "AHU"),
    ("Carrier Precision AHU 10-Ton",       "AHUs",            "Carrier",    "AHU-10T",    (2500000, 4500000),  "hvac", "AHU"),
    ("Tecumseh 3HP Compressor",            "Compressors",     "Tecumseh",   "CAJ9513Z",   (180000,  350000),   "hvac", "CMP"),

    # ── Water & Plumbing ──────────────────────────────────────────────────
    ("Grundfos CM5 Water Pump",            "Water Pumps",     "Grundfos",   "CM5-3",      (180000,  350000),   "plumbing", "WPM"),
    ("DAB Water Pump 1HP",                 "Water Pumps",     "DAB",        "K30/30M",    (120000,  220000),   "plumbing", "WPM"),
    ("Polytank 10,000L Overhead Tank",     "Overhead Tanks",  "Polytank",   "OHT-10000",  (150000,  280000),   "plumbing", "OHT"),
    ("Grundfos Water Treatment Unit",      "Water Treatment", "Grundfos",   "AQF-500",    (800000,  1500000),  "plumbing", "WTU"),

    # ── Fire Safety ───────────────────────────────────────────────────────
    ("Minimax 6KG CO2 Extinguisher",       "Fire Extinguishers","Minimax",  "CO2-6KG",    (18000,   35000),    "fire_safety", "FEX"),
    ("Amerex 9L Foam Extinguisher",        "Fire Extinguishers","Amerex",   "FOAM-9L",    (22000,   40000),    "fire_safety", "FEX"),
    ("Notifier Fire Alarm Panel",          "Fire Safety",     "Notifier",   "ID3000",     (450000,  900000),   "fire_safety", "FAP"),
    ("Hochiki Smoke Detector",             "Fire Safety",     "Hochiki",    "ESP-ROR",    (25000,   50000),    "fire_safety", "SMK"),

    # ── Security & Surveillance ───────────────────────────────────────────
    ("Hikvision 4MP IP Dome Camera",       "CCTV",            "Hikvision",  "DS-2CD2143G",(85000,   150000),   "security", "CAM"),
    ("Dahua 8-Channel NVR",                "CCTV",            "Dahua",      "DHI-NVR2108",(180000,  320000),   "security", "NVR"),
    ("ZKTeco K40 Access Control",          "Access Control",  "ZKTeco",     "K40",        (120000,  250000),   "security", "ACS"),
    ("Honeywell Biometric Reader",         "Access Control",  "Honeywell",  "OmniAssure", (180000,  350000),   "security", "ACS"),

    # ── ICT Equipment ─────────────────────────────────────────────────────
    ("Dell PowerEdge R750 Server",         "Servers",         "Dell",       "R750",       (3500000, 6000000),  "ict", "SRV"),
    ("HP ProLiant DL380 Server",           "Servers",         "HP",         "DL380-G10",  (2800000, 5000000),  "ict", "SRV"),
    ("HP EliteDesk 800 G6 Desktop",        "Desktops",        "HP",         "ED800-G6",   (280000,  450000),   "ict", "DSK"),
    ("Dell OptiPlex 7090 Desktop",         "Desktops",        "Dell",       "OP7090",     (260000,  420000),   "ict", "DSK"),
    ("Canon iR2206N Photocopier",          "Printers",        "Canon",      "iR2206N",    (280000,  480000),   "ict", "PHC"),
    ("Ricoh MP2014 Multifunction Printer", "Printers",        "Ricoh",      "MP2014",     (250000,  420000),   "ict", "PHC"),
    ("Xerox WorkCentre 6515 Printer",      "Printers",        "Xerox",      "WC6515",     (180000,  320000),   "ict", "PHC"),

    # ── Lifts & Vertical Transport ────────────────────────────────────────
    ("Otis 8-Person Passenger Lift",       "Lifts",           "Otis",       "GEN2-8P",    (8000000, 15000000), "mechanical", "LFT"),
    ("Schindler 10-Person Lift",           "Lifts",           "Schindler",  "3300-AP",    (9000000, 16000000), "mechanical", "LFT"),

    # ── Office Furniture ──────────────────────────────────────────────────
    ("Executive Office Desk",              "Office Furniture","Interwood",  "EXD-180",    (85000,   180000),   "general", "DSK"),
    ("Staff Workstation Desk",             "Office Furniture","Interwood",  "SWD-140",    (45000,   90000),    "general", "FRN"),
    ("Ergonomic Executive Chair",          "Office Furniture","Herman Miller","Aeron",     (120000,  280000),   "general", "CHR"),
    ("Staff Office Chair",                 "Office Furniture","Posturite",  "Nia-CH",     (35000,   75000),    "general", "CHR"),
    ("4-Door Steel Filing Cabinet",        "Office Furniture","Rexel",      "FC-4D",      (55000,   110000),   "general", "CAB"),
    ("6-Seater Conference Table",          "Office Furniture","Interwood",  "CT-6S",      (180000,  350000),   "general", "TBL"),
    ("Refrigerator 350L Double Door",      "Office Furniture","LG",         "GC-B399NQCM",(180000,  320000),   "general", "FRG"),
    ("Water Dispenser Hot/Cold",           "Office Furniture","Midea",      "YD1321S",    (45000,   85000),    "general", "WDS"),
    ("Microwave Oven 30L",                 "Office Furniture","Samsung",    "MS30T5018AK",(35000,   65000),    "general", "MWV"),
]

# ── Seed categories into generic.resource.category if it exists ──────────────
resource_cat_map = {}
try:
    RCat = env['generic.resource.category']
    for cat_name in cats:
        existing = RCat.search([('name','=', 'Asset: ' + cat_name)], limit=1)
        if existing:
            resource_cat_map[cat_name] = existing
        else:
            rc = RCat.create({'name': 'Asset: ' + cat_name})
            resource_cat_map[cat_name] = rc
    env.cr.commit()
    print(f"Resource categories created: {len(resource_cat_map)}")
except Exception as e:
    print(f"generic.resource.category not available: {e}")
    resource_cat_map = {}

# ── Find generic.resource.kind for assets ────────────────────────────────────
resource_kind = None
try:
    resource_kind = env['generic.resource.kind'].search(
        [('name','ilike','asset')], limit=1)
    if not resource_kind:
        resource_kind = env['generic.resource.kind'].search([], limit=1)
    print(f"Resource kind: {resource_kind.name if resource_kind else 'None'}")
except Exception as e:
    print(f"generic.resource.kind not available: {e}")

# ── Generate assets ───────────────────────────────────────────────────────────
created = 0
skipped = 0
resource_created = 0
counters = {}  # serial number counters per prefix

def next_serial(prefix):
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"NRS-{prefix}-{counters[prefix]:04d}"

def next_code(prefix):
    return f"AST/{prefix}/{counters.get(prefix,1):04d}"

# Spread assets across locations — aim for ~3-4 per location
loc_cycle = locs * 10  # enough to cover all assets
random.shuffle(loc_cycle)

asset_list = []

# Expand ASSET_TYPES — create multiple instances of common items
QUANTITIES = {
    "Hisense 1.5HP Split AC Unit":        8,
    "LG 2HP Inverter Split AC":           6,
    "Samsung 2.5HP Floor Standing AC":    4,
    "Daikin 3HP Cassette AC":             3,
    "Minimax 6KG CO2 Extinguisher":       10,
    "Amerex 9L Foam Extinguisher":        8,
    "Hochiki Smoke Detector":             8,
    "Hikvision 4MP IP Dome Camera":       8,
    "HP EliteDesk 800 G6 Desktop":        6,
    "Dell OptiPlex 7090 Desktop":         6,
    "Canon iR2206N Photocopier":          5,
    "Ricoh MP2014 Multifunction Printer": 5,
    "Staff Workstation Desk":             8,
    "Staff Office Chair":                 10,
    "Ergonomic Executive Chair":          5,
    "Executive Office Desk":              5,
    "4-Door Steel Filing Cabinet":        6,
    "Refrigerator 350L Double Door":      4,
    "Water Dispenser Hot/Cold":           6,
    "Grundfos CM5 Water Pump":            4,
    "Polytank 10,000L Overhead Tank":     4,
    "Prag 10KVA UPS System":              4,
    "Luminous 5KVA Inverter/UPS":         5,
    "Perkins 100KVA Diesel Generator":    4,
    "Mikano 60KVA Diesel Generator":      3,
    "ZKTeco K40 Access Control":          4,
    "Dahua 8-Channel NVR":                3,
}

for asset_def in ASSET_TYPES:
    name, cat_name, mfr, model, cost_range, domain, prefix = asset_def
    qty = QUANTITIES.get(name, 1)
    for i in range(qty):
        asset_list.append(asset_def)

print(f"\nTotal assets to create: {len(asset_list)}")
print("-" * 50)

loc_idx = 0
batch_size = 20

for idx, asset_def in enumerate(asset_list):
    name, cat_name, mfr, model, cost_range, domain, prefix = asset_def

    cat = cats.get(cat_name)
    if not cat:
        print(f"  SKIP: category '{cat_name}' not found")
        skipped += 1
        continue

    loc = locs[loc_idx % len(locs)]
    loc_idx += 1

    serial = next_serial(prefix)
    code   = next_code(prefix)
    acq_date = rdate(2018, 2024)
    cost   = round(random.uniform(*cost_range), -3)
    curr_val = depreciating(cost, acq_date)

    # Vary condition/state realistically
    condition = random.choices(
        CONDITIONS,
        weights=[5, 40, 30, 15, 10]
    )[0]
    state = 'active'
    if condition == 'critical':
        state = random.choice(['under_maintenance', 'active'])
    elif condition == 'poor':
        state = random.choice(['under_maintenance', 'active', 'active'])

    dept = random.choice(DEPTS)

    try:
        vals = {
            'name':             name,
            'asset_code':       code,
            'serial_number':    serial,
            'category_id':      cat.id,
            'location_id':      loc.id,
            'manufacturer':     mfr,
            'model_number':     model,
            'state':            state,
            'condition':        condition,
            'domain':           domain,
            'department':       dept,
            'acquisition_date': acq_date,
            'acquisition_cost': cost,
            'current_value':    curr_val,
            'is_verified':      random.choice([True, True, False]),
        }
        asset = env['nrs.asset'].create(vals)
        created += 1

        # ── Replicate into generic.resource ──────────────────────────────
        try:
            res_vals = {
                'name': name,
                'resource_number': serial,
            }
            if resource_kind:
                res_vals['kind_id'] = resource_kind.id
            if resource_cat_map.get(cat_name):
                res_vals['category_id'] = resource_cat_map[cat_name].id
            if loc:
                res_vals['location_id'] = loc.id

            env['generic.resource'].create(res_vals)
            resource_created += 1
        except Exception:
            pass  # resource model field mismatch — skip silently

        # Commit in batches
        if created % batch_size == 0:
            env.cr.commit()
            print(f"  ✓ {created} assets committed...")

    except Exception as e:
        print(f"  ERROR creating '{name}': {e}")
        skipped += 1
        env.cr.rollback()

# Final commit
env.cr.commit()

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  SEED COMPLETE")
print("=" * 70)
print(f"  Assets created    : {created}")
print(f"  Resources created : {resource_created}")
print(f"  Skipped           : {skipped}")
print(f"  Locations used    : {min(loc_idx, len(locs))}")
print()

# Breakdown by category
print("  Category breakdown:")
for cat_name, cat in sorted(cats.items()):
    count = env['nrs.asset'].search_count([('category_id','=',cat.id)])
    if count:
        print(f"    {cat_name:35s}: {count}")

print()
total = env['nrs.asset'].search_count([])
print(f"  TOTAL assets in DB: {total}")
print("=" * 70)
