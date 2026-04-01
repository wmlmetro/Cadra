#!/usr/bin/env python3
"""
nrs_hq_seed.py
═══════════════════════════════════════════════════════════════════════════════
NRS myservice.com.ng — Phase 1 Asset Register Seed Script
NRS New Headquarters Pilot

Deploys:
  STEP 0  Wipe existing myservice.asset records (leaves fleet untouched)
  STEP 1  NRS HQ Location hierarchy in generic.location
            NRS Headquarters (parent)
            └── Basement / Ground / Floors 01–16 / Roof  (floor locations)
                └── Individual rooms per floor             (room locations)
  STEP 2  8 Asset Categories
  STEP 3  30 Sub-categories
  STEP 4  113 Asset Types
  STEP 5  ~950 Furniture asset records (DRAFT) mapped to exact room locations

Source drawings: Baron Architecture
  NRS All Floors-compressed-1-10.pdf   (A400–A448, Basement–7th Floor)
  NRS All Floors-compressed-11-19.pdf  (A452–A485, 8th–16th Floor)
Building: Kui Mohammed Avenue, Central Business District, Abuja, FCT

Run via Odoo shell (branch: 15.0):
  sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \
    -c /opt/odoo/conf/odoo.conf -d myservice.com.ng --no-http \
    < /opt/odoo/myservicenrs/scripts/nrs_hq_seed.py

Deployment workflow:
  Mac → GitHub (15.0) → server git pull → Odoo shell
  NEVER scp or direct upload.
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
_logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_or_create(model, search_field, search_val, vals):
    rec = env[model].search([(search_field, '=', search_val)], limit=1)
    if not rec:
        rec = env[model].create(vals)
        return rec, True
    return rec, False

def separator(title):
    print('\n' + '═' * 70)
    print(f'  {title}')
    print('═' * 70)

def ok(created, name):
    mark = '+ created' if created else '✓ exists '
    print(f'  {mark}  {name}')

# ─── STEP 0: WIPE EXISTING ASSET RECORDS ─────────────────────────────────────
separator('STEP 0: WIPE EXISTING myservice.asset RECORDS')

existing_assets = env['myservice.asset'].search([])
existing_cats   = env['myservice.asset.category'].search([])
existing_sub    = env['myservice.asset.subcategory'].search([])
existing_types  = env['myservice.asset.type'].search([])

print(f'  Records found before wipe:')
print(f'    myservice.asset              : {len(existing_assets)}')
print(f'    myservice.asset.category     : {len(existing_cats)}')
print(f'    myservice.asset.subcategory  : {len(existing_sub)}')
print(f'    myservice.asset.type         : {len(existing_types)}')
print(f'    fleet.vehicle (untouched)    : {env["fleet.vehicle"].search_count([])}')

if existing_assets:
    sub_assets = existing_assets.filtered(lambda a: a.asset_level in ('sub_asset', 'component'))
    if sub_assets:
        sub_assets.unlink()
        print(f'  - Removed {len(sub_assets)} sub-asset / component records')
    remaining = env['myservice.asset'].search([])
    if remaining:
        remaining.unlink()
        print(f'  - Removed {len(remaining)} asset / group records')
else:
    print('  - No asset records found — nothing to wipe')

if existing_types:
    existing_types.unlink()
    print(f'  - Removed {len(existing_types)} asset type records')
if existing_sub:
    existing_sub.unlink()
    print(f'  - Removed {len(existing_sub)} sub-category records')
if existing_cats:
    existing_cats.unlink()
    print(f'  - Removed {len(existing_cats)} category records')

env.cr.commit()
print('  Wipe complete. Proceeding to seed...')

# ─── STEP 1: LOCATION HIERARCHY ───────────────────────────────────────────────
separator('STEP 1: NRS HQ LOCATION HIERARCHY')
#
# Structure:
#   NRS Headquarters  (parent — top level)
#   └── [Floor]       (child of HQ)
#       └── [Room]    (child of Floor)
#
# Location names follow: "NRS HQ / F06 / Open Office North"
# Location codes follow: "NRS-HQ-F06-OFC-N"
#
# We store all location records in a dict keyed by our internal code
# so furniture seed (Step 5) can look them up precisely.

locations = {}   # key → generic.location record

# ── Find or create the HQ parent ──────────────────────────────────────────────
hq_parent, created = get_or_create(
    'generic.location', 'complete_name', 'NRS Headquarters',
    {
        'name': 'NRS Headquarters',
        'parent_id': False,
        'usage': 'internal',
        'comment': 'Nigeria Revenue Service New Headquarters, Kui Mohammed Avenue, '
                   'Central Business District, Abuja, FCT. '
                   'Drawing set: Baron Architecture A400–A485.',
    }
)
ok(created, 'NRS Headquarters  [ROOT]')
locations['HQ'] = hq_parent

# ── Floor + Room data ─────────────────────────────────────────────────────────
# Format: (floor_code, floor_label, drawing_no, [(room_code, room_name), ...])
#
# Room codes are suffixed to floor code to form the location dict key:
#   key = f'{floor_code}-{room_code}'  e.g. 'BF-SRV', 'GF-RCP', 'F06-OFC-N'
#
# Sources: Baron Architecture drawings A401, A411, A418–A485
# Room names taken directly from drawing labels where legible;
# generic labels (Open Office North/South) used where rooms are unnamed.

FLOOR_ROOMS = [
    # ── BASEMENT (A401) ───────────────────────────────────────────────────────
    ('BF', 'Basement Floor', 'A401', [
        ('GYM',   'Gym'),
        ('SLP',   'Sleep Area'),
        ('DRL',   'Drivers Lounge'),
        ('RCP',   'Reception'),
        ('LBY-N', 'Lobby North'),
        ('LBY-S', 'Lobby South'),
        ('OFC-CI','Office (CI)'),
        ('SRV',   'Server Room'),
        ('SCR',   'Security Room'),
        ('SCM',   'Security & Monitoring'),
        ('BMS',   'BMS Room'),
        ('AHU-1', 'AHU Room 1'),
        ('AHU-2', 'AHU Room 2'),
        ('ELR',   'Electrical Room'),
        ('MCH-1', 'Mechanical Room 1'),
        ('MCH-2', 'Mechanical Room 2'),
        ('CHM',   'Chemical Room'),
        ('STR',   'Store'),
        ('ECP',   'Executive Carpark'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR-B', 'Stairwell'),
        ('LFT',   'Lift Lobby'),
    ]),

    # ── GROUND FLOOR (A411) ───────────────────────────────────────────────────
    ('GF', 'Ground Floor', 'A411', [
        ('RCP',   'Reception'),
        ('LBY',   'Main Lobby'),
        ('LFT',   'Lift Lobby'),
        ('WTA',   'Waiting Area'),
        ('LED',   'LED Room'),
        ('PRJ',   'Projection Room'),
        ('MPR',   'Multi-Purpose Room'),
        ('PRY',   'Prayer Room'),
        ('CNF',   'Conference Room'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
    ]),

    # ── 1ST FLOOR (A418) ──────────────────────────────────────────────────────
    ('F01', '1st Floor', 'A418', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 2ND FLOOR (A425) ──────────────────────────────────────────────────────
    ('F02', '2nd Floor', 'A425', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 3RD FLOOR (A430) ──────────────────────────────────────────────────────
    ('F03', '3rd Floor', 'A430', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('SCM',   'Security & Safety Management'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 4TH FLOOR (A436) ──────────────────────────────────────────────────────
    ('F04', '4th Floor', 'A436', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 5TH FLOOR (A440) ──────────────────────────────────────────────────────
    ('F05', '5th Floor', 'A440', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('FOP',   'Field Operations Department'),
        ('SUP',   'Support Staff Area'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 6TH FLOOR (A444) ──────────────────────────────────────────────────────
    ('F06', '6th Floor', 'A444', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 7TH FLOOR (A448) ──────────────────────────────────────────────────────
    ('F07', '7th Floor', 'A448', [
        ('TAX',   'Tax Policy & Advisory Department'),
        ('CEG',   'Compliance & Enforcement Group'),
        ('PDD',   'Project Delivery & Planning'),
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('EXO-1', 'Executive Office 1'),
        ('DNG',   'Dining Area'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 8TH FLOOR (A452) ──────────────────────────────────────────────────────
    ('F08', '8th Floor', 'A452', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('BRD',   'Board / Conference Area'),
        ('MTG-1', 'Meeting Room 1'),
        ('MTG-2', 'Meeting Room 2'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 9TH FLOOR (A456) ──────────────────────────────────────────────────────
    ('F09', '9th Floor', 'A456', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('PRB',   'Procurement & Remuneration Bureau'),
        ('MTG-1', 'Meeting Room 1'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 10TH FLOOR (A460) ─────────────────────────────────────────────────────
    ('F10', '10th Floor', 'A460', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('APR',   'Appraisal & Performance'),
        ('MTG-1', 'Meeting Room 1'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 11TH FLOOR (A464) ─────────────────────────────────────────────────────
    ('F11', '11th Floor', 'A464', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('MTG-1', 'Meeting Room 1'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 12TH FLOOR (A468) ─────────────────────────────────────────────────────
    ('F12', '12th Floor', 'A468', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('SSB',   'Somewhere Service Bureau'),
        ('MTG-1', 'Meeting Room 1'),
        ('EXO-1', 'Executive Office 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 13TH FLOOR (A472) ─────────────────────────────────────────────────────
    ('F13', '13th Floor', 'A472', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('EXO-3', 'Executive Office 3'),
        ('MTG-1', 'Meeting Room 1'),
        ('DNG',   'Dining Area'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 14TH FLOOR (A477) ─────────────────────────────────────────────────────
    ('F14', '14th Floor', 'A477', [
        ('OFC-N', 'Open Office North'),
        ('OFC-S', 'Open Office South'),
        ('SCS',   'Security Services'),
        ('BLT',   'Balloting Room'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('MTG-1', 'Meeting Room 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 15TH FLOOR (A481) ─────────────────────────────────────────────────────
    ('F15', '15th Floor', 'A481', [
        ('BRD',   'Board Room'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('EXS',   'Executive Support'),
        ('VIP-D', 'VIP Dining'),
        ('MTG-1', 'Meeting Room 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR',   'Store'),
        ('STR-B', 'Stairwell'),
        ('PNT',   'Pantry'),
    ]),

    # ── 16TH FLOOR (A485) — EXECUTIVE FLOOR ──────────────────────────────────
    ('F16', '16th Floor', 'A485', [
        ('CHR',   'Chairman\'s Office'),
        ('BRD',   'Board Room'),
        ('EXS',   'Executive Suite'),
        ('VIP-L', 'VIP Lounge'),
        ('VIP-D', 'VIP Dining'),
        ('RCP',   'Executive Reception'),
        ('EXO-1', 'Executive Office 1'),
        ('EXO-2', 'Executive Office 2'),
        ('EXO-3', 'Executive Office 3'),
        ('MTG-1', 'Meeting Room 1'),
        ('LFT',   'Lift Lobby'),
        ('WCM',   'Male WC'),
        ('WCF',   'Female WC'),
        ('STR-B', 'Stairwell'),
    ]),

    # ── ROOF ──────────────────────────────────────────────────────────────────
    ('RF', 'Roof / Plant Room', '—', [
        ('PR',    'Plant Room'),
        ('OVH',   'Overhead Tank Area'),
        ('EX',    'External Roof Area'),
    ]),
]

# ── Create floor and room locations ───────────────────────────────────────────
floor_locations = {}   # floor_code → generic.location record
room_locations  = {}   # 'F06-OFC-N' → generic.location record

total_floors = 0
total_rooms  = 0

for floor_code, floor_label, drawing_no, rooms in FLOOR_ROOMS:
    # Create floor location (child of HQ)
    floor_name = f'NRS HQ — {floor_label}'
    floor_rec, created = get_or_create(
        'generic.location', 'complete_name', floor_name,
        {
            'name': floor_label,
            'parent_id': hq_parent.id,
            'usage': 'internal',
            'comment': f'Drawing: {drawing_no}',
        }
    )
    floor_locations[floor_code] = floor_rec
    locations[floor_code] = floor_rec
    ok(created, f'{floor_code}  {floor_label}  (Drawing {drawing_no})')
    total_floors += 1

    # Create room locations (children of floor)
    for room_code, room_name in rooms:
        room_full_name = f'{floor_label} — {room_name}'
        loc_key = f'{floor_code}-{room_code}'
        room_rec, r_created = get_or_create(
            'generic.location', 'complete_name',
            f'NRS HQ — {room_full_name}',
            {
                'name': room_name,
                'parent_id': floor_rec.id,
                'usage': 'internal',
                'comment': f'NRS HQ / {floor_code} / {room_code}',
            }
        )
        room_locations[loc_key] = room_rec
        locations[loc_key] = room_rec
        total_rooms += 1

env.cr.commit()
print(f'\n  Location hierarchy created:')
print(f'    1 HQ parent location')
print(f'    {total_floors} floor locations')
print(f'    {total_rooms} room locations')
print(f'    Total: {1 + total_floors + total_rooms} location records')

# ─── STEP 2: ASSET CATEGORIES ─────────────────────────────────────────────────
separator('STEP 2: ASSET CATEGORIES')

CATEGORIES = [
    ('IT Equipment',       'IT', 10, 'Computers, networking, servers, telecoms and peripherals'),
    ('Furniture & Fittings','FF',20, 'Seating, desking, storage, soft furnishings and fittings'),
    ('Plant & Machinery',  'PM', 30, 'Power supply, HVAC, vertical transport, generators and other plant'),
    ('Plumbing',           'PL', 40, 'Water systems, sanitary fittings and fuel storage'),
    ('Fleet / Vehicles',   'FL', 50, 'Executive, administrative, operational vehicles and motorcycles'),
    ('Security Equipment', 'SE', 60, 'Physical security — speed gates, guard equipment and intrusion detection'),
    ('Fire Fighting',      'FE', 70, 'Detection, suppression, emergency and response equipment'),
    ('ELV Systems',        'EV', 80, 'Fire alarm, CCTV, public address and access control systems'),
]

categories = {}
for name, code, seq, desc in CATEGORIES:
    rec, created = get_or_create(
        'myservice.asset.category', 'code', code,
        {'name': name, 'code': code, 'sequence': seq, 'description': desc}
    )
    categories[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()

# ─── STEP 3: SUB-CATEGORIES ───────────────────────────────────────────────────
separator('STEP 3: SUB-CATEGORIES')

SUBCATEGORIES = [
    ('Computers & Peripherals',  'IT-CMP',  'IT', 10),
    ('Printing & Imaging',       'IT-PRT',  'IT', 20),
    ('Networking',               'IT-NET',  'IT', 30),
    ('Servers & Storage',        'IT-SRV',  'IT', 40),
    ('Telecoms',                 'IT-TEL',  'IT', 50),
    ('Seating',                  'FF-SEA',  'FF', 10),
    ('Desking',                  'FF-DSK',  'FF', 20),
    ('Storage',                  'FF-STR',  'FF', 30),
    ('Soft Furnishings',         'FF-SFT',  'FF', 40),
    ('Fittings',                 'FF-FIT',  'FF', 50),
    ('Power Supply',             'PM-PWR',  'PM', 10),
    ('HVAC',                     'PM-HVC',  'PM', 20),
    ('Vertical Transport',       'PM-VTR',  'PM', 30),
    ('Generators',               'PM-GEN',  'PM', 40),
    ('Other Plant',              'PM-OTH',  'PM', 50),
    ('Water Systems',            'PL-WTR',  'PL', 10),
    ('Sanitary Fittings',        'PL-SAN',  'PL', 20),
    ('Fuel Systems',             'PL-FUEL', 'PL', 30),
    ('Executive Vehicles',       'FL-EXC',  'FL', 10),
    ('Administrative Vehicles',  'FL-ADM',  'FL', 20),
    ('Operational Vehicles',     'FL-OPS',  'FL', 30),
    ('Motorcycles',              'FL-MCY',  'FL', 40),
    ('Access Control (Physical)','SE-ACC',  'SE', 10),
    ('Intrusion Detection',      'SE-INT',  'SE', 20),
    ('Guard Equipment',          'SE-GRD',  'SE', 30),
    ('Detection',                'FE-DET',  'FE', 10),
    ('Suppression',              'FE-SUP',  'FE', 20),
    ('Emergency',                'FE-EMG',  'FE', 30),
    ('Response',                 'FE-RSP',  'FE', 40),
    ('Fire Alarm',               'EV-FAL',  'EV', 10),
    ('CCTV & Detection',         'EV-CCT',  'EV', 20),
    ('Public Address',           'EV-PAS',  'EV', 30),
    ('Access Control (ELV)',     'EV-ACC',  'EV', 40),
]

subcategories = {}
for name, code, parent_code, seq in SUBCATEGORIES:
    rec, created = get_or_create(
        'myservice.asset.subcategory', 'code', code,
        {'name': name, 'code': code, 'sequence': seq,
         'category_id': categories[parent_code].id}
    )
    subcategories[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()

# ─── STEP 4: ASSET TYPES ──────────────────────────────────────────────────────
separator('STEP 4: ASSET TYPES')

ASSET_TYPES = [
    # IT
    ('Desktop Computer',           'IT-CMP-DKT', 'IT-CMP'),
    ('Laptop',                     'IT-CMP-LAP', 'IT-CMP'),
    ('Monitor',                    'IT-CMP-MON', 'IT-CMP'),
    ('Keyboard & Mouse',           'IT-CMP-KBM', 'IT-CMP'),
    ('Docking Station',            'IT-CMP-DCK', 'IT-CMP'),
    ('Printer',                    'IT-PRT-PRT', 'IT-PRT'),
    ('Photocopier',                'IT-PRT-CPR', 'IT-PRT'),
    ('Scanner',                    'IT-PRT-SCN', 'IT-PRT'),
    ('Plotter',                    'IT-PRT-PLT', 'IT-PRT'),
    ('Network Switch',             'IT-NET-SWT', 'IT-NET'),
    ('Router',                     'IT-NET-RTR', 'IT-NET'),
    ('Firewall',                   'IT-NET-FWL', 'IT-NET'),
    ('Patch Panel',                'IT-NET-PTC', 'IT-NET'),
    ('Wireless Access Point',      'IT-NET-WAP', 'IT-NET'),
    ('Server',                     'IT-SRV-SVR', 'IT-SRV'),
    ('NAS / Storage Array',        'IT-SRV-NAS', 'IT-SRV'),
    ('UPS Unit',                   'IT-SRV-UPS', 'IT-SRV'),
    ('Server Rack',                'IT-SRV-RCK', 'IT-SRV'),
    ('IP Phone',                   'IT-TEL-IPP', 'IT-TEL'),
    ('PABX System',                'IT-TEL-PBX', 'IT-TEL'),
    ('Conference System',          'IT-TEL-CNF', 'IT-TEL'),
    ('Video Conferencing Unit',    'IT-TEL-VCU', 'IT-TEL'),
    # FF — Seating
    ('Executive Chair',            'FF-SEA-EXC', 'FF-SEA'),
    ('Visitor Chair',              'FF-SEA-VIS', 'FF-SEA'),
    ('Conference Chair',           'FF-SEA-CNF', 'FF-SEA'),
    ('Workstation Chair',          'FF-SEA-WRK', 'FF-SEA'),
    ('Armchair',                   'FF-SEA-ARM', 'FF-SEA'),
    ('Dining Chair',               'FF-SEA-DNG', 'FF-SEA'),
    ('1-Seater Sofa',              'FF-SEA-S1',  'FF-SEA'),
    # FF — Desking
    ('Executive Desk',             'FF-DSK-EXC', 'FF-DSK'),
    ('Workstation Desk',           'FF-DSK-WRK', 'FF-DSK'),
    ('Conference Table',           'FF-DSK-CNF', 'FF-DSK'),
    ('Dining Table',               'FF-DSK-DNG', 'FF-DSK'),
    ('Reception Desk',             'FF-DSK-RCP', 'FF-DSK'),
    ('L-Shaped Desk',              'FF-DSK-LSH', 'FF-DSK'),
    # FF — Storage
    ('Filing Cabinet',             'FF-STR-FLC', 'FF-STR'),
    ('Bookshelf',                  'FF-STR-BSH', 'FF-STR'),
    ('Locker',                     'FF-STR-LCK', 'FF-STR'),
    ('Credenza',                   'FF-STR-CRD', 'FF-STR'),
    ('Side Drawer Unit',           'FF-STR-SDR', 'FF-STR'),
    ('Cabinet',                    'FF-STR-CAB', 'FF-STR'),
    # FF — Soft Furnishings
    ('U-Shaped Sofa',              'FF-SFT-USF', 'FF-SFT'),
    ('L-Shaped Sofa',              'FF-SFT-LSF', 'FF-SFT'),
    ('2-Seater Sofa',              'FF-SFT-S2',  'FF-SFT'),
    ('Curtains / Blinds',          'FF-SFT-CRT', 'FF-SFT'),
    ('Carpet / Rug',               'FF-SFT-CRP', 'FF-SFT'),
    # FF — Fittings
    ('Partition / Cubicle',        'FF-FIT-PRT', 'FF-FIT'),
    ('Servery Counter',            'FF-FIT-SVC', 'FF-FIT'),
    ('Notice Board',               'FF-FIT-NTB', 'FF-FIT'),
    ('Whiteboard',                 'FF-FIT-WTB', 'FF-FIT'),
    ('Signage',                    'FF-FIT-SGN', 'FF-FIT'),
    # PM — Power
    ('33KV Switchgear',            'PM-PWR-SG33',  'PM-PWR'),
    ('11KV Switchgear',            'PM-PWR-SG11',  'PM-PWR'),
    ('33/11 7.5MVA Transformer',   'PM-PWR-TX33',  'PM-PWR'),
    ('2MVA 11/0.4KV Transformer',  'PM-PWR-TX2M',  'PM-PWR'),
    ('Main Low Voltage Panel',     'PM-PWR-MLVP',  'PM-PWR'),
    ('Synchronising Panel',        'PM-PWR-SYN',   'PM-PWR'),
    ('Busbar Riser (Raw Power)',    'PM-PWR-BBR',   'PM-PWR'),
    ('Busbar Riser (UPS Power)',    'PM-PWR-BBU',   'PM-PWR'),
    ('Tower Low Voltage Panel',    'PM-PWR-TLVP',  'PM-PWR'),
    ('UPS Panel (Essential)',      'PM-PWR-UPSE',  'PM-PWR'),
    ('UPS Panel (Non-Essential)',  'PM-PWR-UPSN',  'PM-PWR'),
    ('Main UPS',                   'PM-PWR-MUPP',  'PM-PWR'),
    ('100KVA Data Centre UPS',     'PM-PWR-UDC',   'PM-PWR'),
    ('60KVA Auditorium UPS',       'PM-PWR-UAU',   'PM-PWR'),
    ('Distribution Board (Raw)',   'PM-PWR-DBR',   'PM-PWR'),
    ('Distribution Board (UPS)',   'PM-PWR-DBU',   'PM-PWR'),
    ('Capacitor Bank',             'PM-PWR-CAP',   'PM-PWR'),
    ('Internal Lighting',          'PM-PWR-LTI',   'PM-PWR'),
    ('External Lighting',          'PM-PWR-LTE',   'PM-PWR'),
    ('ATS Panel',                  'PM-PWR-ATS',   'PM-PWR'),
    # PM — HVAC
    ('Chiller',                    'PM-HVC-CHL', 'PM-HVC'),
    ('Primary Pump',               'PM-HVC-PPM', 'PM-HVC'),
    ('Secondary Pump',             'PM-HVC-SPM', 'PM-HVC'),
    ('Air Handling Unit (AHU)',    'PM-HVC-AHU', 'PM-HVC'),
    ('Fan Coil Unit (FCU)',        'PM-HVC-FCU', 'PM-HVC'),
    ('Cassette Unit',              'PM-HVC-CST', 'PM-HVC'),
    ('Split Unit',                 'PM-HVC-SPL', 'PM-HVC'),
    ('Fresh Air Unit (FAU)',       'PM-HVC-FAU', 'PM-HVC'),
    ('Cooling Tower',              'PM-HVC-CLT', 'PM-HVC'),
    ('Exhaust Fan',                'PM-HVC-EXF', 'PM-HVC'),
    # PM — Vertical Transport
    ('Passenger Lift',             'PM-VTR-PLF', 'PM-VTR'),
    ('Service Lift',               'PM-VTR-SLF', 'PM-VTR'),
    ('Escalator',                  'PM-VTR-ESC', 'PM-VTR'),
    # PM — Generators
    ('Generator 2MVA 400V',        'PM-GEN-G2M',  'PM-GEN'),
    ('Generator 1.25MVA 400V',     'PM-GEN-G1M',  'PM-GEN'),
    ('Generator 750KVA 400V',      'PM-GEN-G750', 'PM-GEN'),
    # PM — Other Plant
    ('BMS Controller',             'PM-OTH-BMS', 'PM-OTH'),
    ('Compressor',                 'PM-OTH-CMP', 'PM-OTH'),
    ('Intercom System',            'PM-OTH-ICM', 'PM-OTH'),
    # PL
    ('Overhead Water Tank',        'PL-WTR-OHT',  'PL-WTR'),
    ('Underground Water Tank',     'PL-WTR-UGT',  'PL-WTR'),
    ('Transfer Pump',              'PL-WTR-TRP',  'PL-WTR'),
    ('Booster Pump',               'PL-WTR-BOP',  'PL-WTR'),
    ('Water Treatment Plant',      'PL-WTR-WTP',  'PL-WTR'),
    ('Water Heater',               'PL-WTR-WHT',  'PL-WTR'),
    ('WC / Toilet',                'PL-SAN-WCT',  'PL-SAN'),
    ('Wash Hand Basin',            'PL-SAN-WHB',  'PL-SAN'),
    ('Mirror',                     'PL-SAN-MIR',  'PL-SAN'),
    ('Hand Dryer',                 'PL-SAN-HDR',  'PL-SAN'),
    ('Diesel Tank',                'PL-FUEL-DST', 'PL-FUEL'),
    ('Day Tank',                   'PL-FUEL-DAT', 'PL-FUEL'),
    # FL
    ('Saloon Car',                 'FL-EXC-SAL', 'FL-EXC'),
    ('SUV',                        'FL-EXC-SUV', 'FL-EXC'),
    ('Staff Bus',                  'FL-ADM-BUS', 'FL-ADM'),
    ('Minivan',                    'FL-ADM-MVN', 'FL-ADM'),
    ('Pickup Truck',               'FL-OPS-PKP', 'FL-OPS'),
    ('Utility Van',                'FL-OPS-UTV', 'FL-OPS'),
    ('Ambulance',                  'FL-OPS-AMB', 'FL-OPS'),
    ('Dispatch Bike',              'FL-MCY-DBK', 'FL-MCY'),
    ('Patrol Bike',                'FL-MCY-PBK', 'FL-MCY'),
    # SE
    ('Speed Gate',                 'SE-ACC-SPG', 'SE-ACC'),
    ('Boom Barrier',               'SE-ACC-BBR', 'SE-ACC'),
    ('Turnstile',                  'SE-ACC-TRN', 'SE-ACC'),
    ('Guard Booth',                'SE-ACC-GBT', 'SE-ACC'),
    ('Motion Sensor',              'SE-INT-MTS', 'SE-INT'),
    ('Glass Break Sensor',         'SE-INT-GBS', 'SE-INT'),
    ('Alarm Panel',                'SE-INT-ALP', 'SE-INT'),
    ('Siren',                      'SE-INT-SRN', 'SE-INT'),
    ('Patrol Wand',                'SE-INT-PWD', 'SE-INT'),
    ('Walk-Through Metal Detector','SE-GRD-WTM', 'SE-GRD'),
    ('Handheld Scanner',           'SE-GRD-HHS', 'SE-GRD'),
    ('X-Ray Baggage Scanner',      'SE-GRD-XRY', 'SE-GRD'),
    # FE
    ('Smoke Detector',             'FE-DET-SMK', 'FE-DET'),
    ('Heat Detector',              'FE-DET-HET', 'FE-DET'),
    ('Manual Call Point',          'FE-DET-MCP', 'FE-DET'),
    ('Sprinkler Pump',             'FE-SUP-SKP', 'FE-SUP'),
    ('Hydrant Pump',               'FE-SUP-HDP', 'FE-SUP'),
    ('Hose Reel Pump',             'FE-SUP-HRP', 'FE-SUP'),
    ('Fire-Pro Unit',              'FE-SUP-FPU', 'FE-SUP'),
    ('Foam Bladder Tank',          'FE-SUP-FBT', 'FE-SUP'),
    ('Hose Reel',                  'FE-SUP-HSR', 'FE-SUP'),
    ('Sprinkler System',           'FE-SUP-SKS', 'FE-SUP'),
    ('Fire Extinguisher (CO2)',    'FE-SUP-ECO', 'FE-SUP'),
    ('Fire Extinguisher (Dry Powder)','FE-SUP-EDP','FE-SUP'),
    ('Fire Extinguisher (Foam)',   'FE-SUP-EFM', 'FE-SUP'),
    ('Emergency Exit Light',       'FE-EMG-EXL', 'FE-EMG'),
    ('Fire Escape Signage',        'FE-EMG-SGN', 'FE-EMG'),
    ('Fire Door',                  'FE-EMG-FDR', 'FE-EMG'),
    ('Evacuation Speaker',         'FE-EMG-EVS', 'FE-EMG'),
    ('Fire Hose Cabinet',          'FE-RSP-FHC', 'FE-RSP'),
    ('Hydrant',                    'FE-RSP-HDT', 'FE-RSP'),
    ('Fire Blanket',               'FE-RSP-FBL', 'FE-RSP'),
    ('First Aid Kit',              'FE-RSP-FAK', 'FE-RSP'),
    # EV
    ('Fire Alarm Panel',           'EV-FAL-FAP', 'EV-FAL'),
    ('Smoke Detector (ELV)',       'EV-FAL-SMK', 'EV-FAL'),
    ('Heat Detector (ELV)',        'EV-FAL-HET', 'EV-FAL'),
    ('Beam Detector',              'EV-FAL-BDT', 'EV-FAL'),
    ('Breakglass Unit',            'EV-FAL-BGU', 'EV-FAL'),
    ('Sounder',                    'EV-FAL-SND', 'EV-FAL'),
    ('CCTV Monitor / Screen',      'EV-CCT-MON', 'EV-CCT'),
    ('Dome Camera (Internal)',     'EV-CCT-DCI', 'EV-CCT'),
    ('Dome Camera (External)',     'EV-CCT-DCE', 'EV-CCT'),
    ('DVR / NVR',                  'EV-CCT-DVR', 'EV-CCT'),
    ('Video Wall Display',         'EV-CCT-VWD', 'EV-CCT'),
    ('PA Speaker',                 'EV-PAS-SPK', 'EV-PAS'),
    ('Amplifier',                  'EV-PAS-AMP', 'EV-PAS'),
    ('PA Rack',                    'EV-PAS-RCK', 'EV-PAS'),
    ('Access Control Panel',       'EV-ACC-ACP', 'EV-ACC'),
    ('Card Reader',                'EV-ACC-CDR', 'EV-ACC'),
    ('Biometric Reader',           'EV-ACC-BIO', 'EV-ACC'),
    ('Electronic Lock',            'EV-ACC-ELK', 'EV-ACC'),
]

asset_types = {}
for name, code, subcat_code in ASSET_TYPES:
    rec, created = get_or_create(
        'myservice.asset.type', 'code', code,
        {
            'name': name,
            'code': code,
            'subcategory_id': subcategories[subcat_code].id,
            'category_id': subcategories[subcat_code].category_id.id,
        }
    )
    asset_types[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()
print(f'\n  Total asset types: {len(ASSET_TYPES)}')

# ─── STEP 5: FURNITURE SEED RECORDS ───────────────────────────────────────────
separator('STEP 5: FURNITURE SEED RECORDS — HQ INVENTORY')
#
# Source: FIRS HQ FURNITURE INVENTORY — 11/02/2026
# Each row produces individual asset records (one per unit).
# Location is resolved to the exact room location from Step 1.
# Floor mapping from inventory → drawing floor codes:
#   Entry floor   → GF (Ground Floor)
#   1st floor     → F01
#   3rd floor     → F03
#   6th floor     → F06
#   7th floor     → F07
#   8th floor     → F08
#   9th floor     → F09
#   10th floor    → F10
#
# Sequence counters are per category+subcategory combination.

seq_counters = {}   # 'NRS-FF-SEA' → current sequence int

def next_asset_code(cat_code, subcat_short):
    key = f'NRS-{cat_code}-{subcat_short}'
    seq_counters[key] = seq_counters.get(key, 0) + 1
    return f'{key}-{seq_counters[key]:05d}'

tag_counters = {}   # 'HQ-F06-OFC-N-FF' → current tag seq int

def next_tag_code(floor_code, room_code, cat_code):
    key = f'HQ-{floor_code}-{room_code}-{cat_code}'
    tag_counters[key] = tag_counters.get(key, 0) + 1
    return f'{key}-{tag_counters[key]:03d}'

def resolve_location(floor_code, room_code):
    """Return the generic.location record for a floor+room. Falls back to floor."""
    loc_key = f'{floor_code}-{room_code}'
    if loc_key in room_locations:
        return room_locations[loc_key]
    if floor_code in floor_locations:
        print(f'  WARNING: room {loc_key} not found — using floor {floor_code}')
        return floor_locations[floor_code]
    print(f'  WARNING: floor {floor_code} not found — using HQ parent')
    return hq_parent

def seed_furniture(floor_code, room_code, type_code, quantity, notes=''):
    type_rec = asset_types.get(type_code)
    if not type_rec:
        print(f'  WARNING: type {type_code} not found — skipping {quantity} records')
        return 0
    subcat     = type_rec.subcategory_id
    cat        = type_rec.category_id
    location   = resolve_location(floor_code, room_code)
    subcat_short = subcat.code.split('-')[1]
    created_n  = 0
    for _ in range(quantity):
        asset_code = next_asset_code(cat.code, subcat_short)
        tag_code   = next_tag_code(floor_code, room_code, cat.code)
        env['myservice.asset'].create({
            'name':           f'{type_rec.name}',
            'asset_code':     asset_code,
            'tag_code':       tag_code,
            'category_id':    cat.id,
            'subcategory_id': subcat.id,
            'asset_type_id':  type_rec.id,
            'asset_level':    'asset',
            'location_id':    location.id,
            'floor_room':     f'{floor_code} — {room_code}',
            'condition':      'good',
            'status':         'draft',
            'notes':          notes or f'Seeded from HQ Furniture Inventory',
        })
        created_n += 1
    return created_n

# ── Inventory data ─────────────────────────────────────────────────────────────
# (floor_code, room_code, asset_type_code, quantity, notes)
# Room codes match exactly what was created in FLOOR_ROOMS above.

FURNITURE_INVENTORY = [
    # Ground Floor — Mail Room
    ('GF', 'MR',   'FF-DSK-WRK',  13, 'GF Mail Room — Workstation tables'),
    ('GF', 'MR',   'FF-SEA-WRK',  39, 'GF Mail Room — Chairs'),
    ('GF', 'MR',   'FF-STR-SDR',  13, 'GF Mail Room — Side drawers'),
    # Ground Floor — Dining
    ('GF', 'DNG',  'FF-DSK-DNG',  12, 'GF Dining — Dining tables'),
    ('GF', 'DNG',  'FF-SEA-DNG',  52, 'GF Dining — Dining chairs'),
    ('GF', 'DNG',  'FF-SFT-USF',   7, 'GF Dining — U-shaped sofas'),
    ('GF', 'DNG',  'FF-SFT-LSF',   2, 'GF Dining — L-shaped sofas'),
    ('GF', 'DNG',  'FF-FIT-SVC',   2, 'GF Dining — Servery counters'),

    # 1st Floor — Library (mapped to F01-OFC-N as library is open office)
    ('F01', 'OFC-N', 'FF-DSK-WRK', 22, 'F01 Library — Workstation desks'),
    ('F01', 'OFC-N', 'FF-SEA-WRK', 16, 'F01 Library — Chairs'),
    ('F01', 'OFC-N', 'FF-STR-SDR', 31, 'F01 Library — Side drawers'),
    ('F01', 'OFC-N', 'FF-SEA-EXC',  3, 'F01 Library — Executive chairs'),

    # 3rd Floor — Conference Room
    ('F03', 'MTG-1', 'FF-DSK-CNF', 13, 'F03 Conference Room — Tables'),
    ('F03', 'MTG-1', 'FF-SEA-CNF',104, 'F03 Conference Room — Chairs'),

    # 6th Floor — Open Office
    ('F06', 'OFC-N', 'FF-DSK-WRK',  62, 'F06 Open Office — Tables'),
    ('F06', 'OFC-N', 'FF-SEA-WRK',  62, 'F06 Open Office — Chairs'),
    ('F06', 'OFC-N', 'FF-SFT-S2',    1, 'F06 — 2-seater sofa'),
    ('F06', 'OFC-N', 'FF-SEA-S1',    2, 'F06 — 1-seater sofas'),
    ('F06', 'OFC-N', 'FF-DSK-LSH',   1, 'F06 — L-shaped desk'),
    ('F06', 'OFC-N', 'FF-SEA-EXC',  52, 'F06 — Executive chairs'),
    ('F06', 'OFC-N', 'FF-STR-CAB',   8, 'F06 — Cabinets'),
    ('F06', 'OFC-N', 'FF-SEA-ARM',   3, 'F06 — Armchairs'),

    # 7th Floor — Open Office
    ('F07', 'OFC-N', 'FF-DSK-WRK', 112, 'F07 Open Office — Tables'),
    ('F07', 'OFC-N', 'FF-SEA-WRK', 112, 'F07 Open Office — Chairs'),
    ('F07', 'OFC-N', 'FF-SFT-S2',    1, 'F07 — 2-seater sofa'),
    ('F07', 'OFC-N', 'FF-SEA-S1',    7, 'F07 — 1-seater sofas'),
    ('F07', 'OFC-N', 'FF-DSK-LSH',   2, 'F07 — L-shaped desks'),
    ('F07', 'OFC-N', 'FF-SEA-EXC',  32, 'F07 — Executive chairs'),
    ('F07', 'OFC-N', 'FF-STR-CAB',   8, 'F07 — Cabinets'),
    ('F07', 'OFC-N', 'FF-SEA-ARM',   6, 'F07 — Armchairs'),

    # 8th Floor
    ('F08', 'OFC-N', 'FF-SEA-WRK',  60, 'F08 Open Office — Chairs'),
    ('F08', 'OFC-N', 'FF-SFT-S2',    1, 'F08 — 2-seater sofa'),
    ('F08', 'OFC-N', 'FF-SEA-S1',    2, 'F08 — 1-seater sofas'),
    ('F08', 'OFC-N', 'FF-SEA-EXC',  51, 'F08 — Executive chairs'),
    ('F08', 'OFC-N', 'FF-STR-CAB',   8, 'F08 — Cabinets'),
    ('F08', 'OFC-N', 'FF-SEA-ARM',   6, 'F08 — Armchairs'),

    # 9th Floor
    ('F09', 'OFC-N', 'FF-DSK-WRK',  60, 'F09 Open Office — Tables'),
    ('F09', 'OFC-N', 'FF-SEA-WRK',  60, 'F09 Open Office — Chairs'),
    ('F09', 'OFC-N', 'FF-SFT-S2',    1, 'F09 — 2-seater sofa'),
    ('F09', 'OFC-N', 'FF-SEA-S1',    2, 'F09 — 1-seater sofas'),
    ('F09', 'OFC-N', 'FF-DSK-LSH',   2, 'F09 — L-shaped desks'),
    ('F09', 'OFC-N', 'FF-SEA-EXC',  54, 'F09 — Executive chairs'),
    ('F09', 'OFC-N', 'FF-STR-CAB',  16, 'F09 — Cabinets'),
    ('F09', 'OFC-N', 'FF-SEA-ARM',   6, 'F09 — Armchairs'),

    # 10th Floor
    ('F10', 'OFC-N', 'FF-SEA-WRK',  79, 'F10 Open Office — Chairs'),
    ('F10', 'OFC-N', 'FF-SFT-S2',    1, 'F10 — 2-seater sofa'),
    ('F10', 'OFC-N', 'FF-SEA-S1',    2, 'F10 — 1-seater sofas'),
    ('F10', 'OFC-N', 'FF-SEA-EXC',  43, 'F10 — Executive chairs'),
    ('F10', 'OFC-N', 'FF-STR-CAB',  15, 'F10 — Cabinets'),
    ('F10', 'OFC-N', 'FF-SEA-ARM',   3, 'F10 — Armchairs'),
]

total_furniture = 0
for floor_code, room_code, type_code, qty, notes in FURNITURE_INVENTORY:
    n = seed_furniture(floor_code, room_code, type_code, qty, notes)
    total_furniture += n
    if n > 0:
        loc_key = f'{floor_code}-{room_code}'
        loc_name = room_locations.get(loc_key, floor_locations.get(floor_code))
        loc_label = loc_name.name if loc_name else '?'
        print(f'  + {n:4d}  {type_code}  →  {floor_code}/{room_code}  [{loc_label}]')

env.cr.commit()
print(f'\n  Total furniture records seeded: {total_furniture}')

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
separator('SEED COMPLETE — SUMMARY')

print(f'''
  Location Hierarchy:
    HQ parent location       : 1
    Floor locations          : {len(floor_locations)}
    Room locations           : {len(room_locations)}
    Total location records   : {1 + len(floor_locations) + len(room_locations)}

  Asset Taxonomy:
    Categories               : {env['myservice.asset.category'].search_count([])}
    Sub-categories           : {env['myservice.asset.subcategory'].search_count([])}
    Asset Types              : {env['myservice.asset.type'].search_count([])}

  Asset Records:
    Total                    : {env['myservice.asset'].search_count([])}
    DRAFT (furniture seed)   : {env['myservice.asset'].search_count([('status','=','draft')])}

  Next steps:
    1. Verify location tree in myservice Locations menu
    2. Verify furniture DRAFT records on correct floor/room locations
    3. Run nrs_itsm_seed_v2.py  (Help Desk service catalogue)
    4. Run nrs_sla_seed.py      (SLA policies)
    5. Print Zebra label batch for Ground Floor — begin tagging

  Branch: 15.0
  Script: /opt/odoo/myservicenrs/scripts/nrs_hq_seed.py
''')
