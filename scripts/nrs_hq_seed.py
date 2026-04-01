#!/usr/bin/env python3
"""
nrs_hq_seed.py
═══════════════════════════════════════════════════════════════════════════════
NRS myservice.com.ng — Phase 1 Asset Register Seed Script
NRS New Headquarters Pilot

Deploys:
  • 8 Asset Categories
  • 30 Sub-categories
  • ~110 Asset Types
  • Per-category sequence counters
  • ~950 Furniture asset records from HQ inventory (DRAFT status)

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
#
# Removes ALL records from myservice.asset only.
# Does NOT touch: fleet.vehicle, Odoo stock, or any other model.
# Categories, sub-categories, and asset types are re-seeded fresh below.
#
# Safety check — print count before wiping
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
print()

# Wipe asset records first (child records before parents to avoid FK errors)
if existing_assets:
    # Unlink sub-assets and components first (have parent_id set)
    sub_assets = existing_assets.filtered(lambda a: a.asset_level in ('sub_asset', 'component'))
    if sub_assets:
        sub_assets.unlink()
        print(f'  - Removed {len(sub_assets)} sub-asset / component records')

    # Remove remaining top-level asset records
    remaining = env['myservice.asset'].search([])
    if remaining:
        remaining.unlink()
        print(f'  - Removed {len(remaining)} asset / group records')
else:
    print('  - No asset records found — nothing to wipe')

# Wipe taxonomy (types → subcategories → categories, child before parent)
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
print()
print('  Wipe complete. Odoo fleet.vehicle records untouched.')
print('  Proceeding to seed fresh taxonomy and records...')

# ─── STEP 1: ASSET CATEGORIES ─────────────────────────────────────────────────
separator('STEP 1: ASSET CATEGORIES')

CATEGORIES = [
    # (name,              code, sequence, description)
    ('IT Equipment',      'IT', 10, 'Computers, networking, servers, telecoms and peripherals'),
    ('Furniture & Fittings','FF',20,'Seating, desking, storage, soft furnishings and fittings'),
    ('Plant & Machinery', 'PM', 30, 'Power supply, HVAC, vertical transport, generators and other plant'),
    ('Plumbing',          'PL', 40, 'Water systems, sanitary fittings and fuel storage'),
    ('Fleet / Vehicles',  'FL', 50, 'Executive, administrative, operational vehicles and motorcycles'),
    ('Security Equipment','SE', 60, 'Physical security — speed gates, guard equipment and intrusion detection'),
    ('Fire Fighting',     'FE', 70, 'Detection, suppression, emergency and response equipment'),
    ('ELV Systems',       'EV', 80, 'Fire alarm, CCTV, public address and access control systems'),
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

# ─── STEP 2: SUB-CATEGORIES ───────────────────────────────────────────────────
separator('STEP 2: SUB-CATEGORIES')

# (name, code, parent_cat_code, sequence)
SUBCATEGORIES = [
    # IT Equipment
    ('Computers & Peripherals', 'IT-CMP', 'IT', 10),
    ('Printing & Imaging',      'IT-PRT', 'IT', 20),
    ('Networking',              'IT-NET', 'IT', 30),
    ('Servers & Storage',       'IT-SRV', 'IT', 40),
    ('Telecoms',                'IT-TEL', 'IT', 50),

    # Furniture & Fittings
    ('Seating',                 'FF-SEA', 'FF', 10),
    ('Desking',                 'FF-DSK', 'FF', 20),
    ('Storage',                 'FF-STR', 'FF', 30),
    ('Soft Furnishings',        'FF-SFT', 'FF', 40),
    ('Fittings',                'FF-FIT', 'FF', 50),

    # Plant & Machinery
    ('Power Supply',            'PM-PWR', 'PM', 10),
    ('HVAC',                    'PM-HVC', 'PM', 20),
    ('Vertical Transport',      'PM-VTR', 'PM', 30),
    ('Generators',              'PM-GEN', 'PM', 40),
    ('Other Plant',             'PM-OTH', 'PM', 50),

    # Plumbing
    ('Water Systems',           'PL-WTR', 'PL', 10),
    ('Sanitary Fittings',       'PL-SAN', 'PL', 20),
    ('Fuel Systems',            'PL-FUEL','PL', 30),

    # Fleet
    ('Executive Vehicles',      'FL-EXC', 'FL', 10),
    ('Administrative Vehicles', 'FL-ADM', 'FL', 20),
    ('Operational Vehicles',    'FL-OPS', 'FL', 30),
    ('Motorcycles',             'FL-MCY', 'FL', 40),

    # Security Equipment
    ('Access Control (Physical)','SE-ACC','SE', 10),
    ('Intrusion Detection',     'SE-INT', 'SE', 20),
    ('Guard Equipment',         'SE-GRD', 'SE', 30),

    # Fire Fighting
    ('Detection',               'FE-DET', 'FE', 10),
    ('Suppression',             'FE-SUP', 'FE', 20),
    ('Emergency',               'FE-EMG', 'FE', 30),
    ('Response',                'FE-RSP', 'FE', 40),

    # ELV Systems
    ('Fire Alarm',              'EV-FAL', 'EV', 10),
    ('CCTV & Detection',        'EV-CCT', 'EV', 20),
    ('Public Address',          'EV-PAS', 'EV', 30),
    ('Access Control (ELV)',    'EV-ACC', 'EV', 40),
]

subcategories = {}
for name, code, parent_code, seq in SUBCATEGORIES:
    rec, created = get_or_create(
        'myservice.asset.subcategory', 'code', code,
        {
            'name': name,
            'code': code,
            'sequence': seq,
            'category_id': categories[parent_code].id,
        }
    )
    subcategories[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()

# ─── STEP 3: ASSET TYPES ──────────────────────────────────────────────────────
separator('STEP 3: ASSET TYPES')

# (name, code, subcategory_code)
ASSET_TYPES = [
    # IT — Computers & Peripherals
    ('Desktop Computer',        'IT-CMP-DKT', 'IT-CMP'),
    ('Laptop',                  'IT-CMP-LAP', 'IT-CMP'),
    ('Monitor',                 'IT-CMP-MON', 'IT-CMP'),
    ('Keyboard & Mouse',        'IT-CMP-KBM', 'IT-CMP'),
    ('Docking Station',         'IT-CMP-DCK', 'IT-CMP'),

    # IT — Printing & Imaging
    ('Printer',                 'IT-PRT-PRT', 'IT-PRT'),
    ('Photocopier',             'IT-PRT-CPR', 'IT-PRT'),
    ('Scanner',                 'IT-PRT-SCN', 'IT-PRT'),
    ('Plotter',                 'IT-PRT-PLT', 'IT-PRT'),

    # IT — Networking
    ('Network Switch',          'IT-NET-SWT', 'IT-NET'),
    ('Router',                  'IT-NET-RTR', 'IT-NET'),
    ('Firewall',                'IT-NET-FWL', 'IT-NET'),
    ('Patch Panel',             'IT-NET-PTC', 'IT-NET'),
    ('Wireless Access Point',   'IT-NET-WAP', 'IT-NET'),

    # IT — Servers & Storage
    ('Server',                  'IT-SRV-SVR', 'IT-SRV'),
    ('NAS / Storage Array',     'IT-SRV-NAS', 'IT-SRV'),
    ('UPS Unit',                'IT-SRV-UPS', 'IT-SRV'),
    ('Server Rack',             'IT-SRV-RCK', 'IT-SRV'),

    # IT — Telecoms
    ('IP Phone',                'IT-TEL-IPP', 'IT-TEL'),
    ('PABX System',             'IT-TEL-PBX', 'IT-TEL'),
    ('Conference System',       'IT-TEL-CNF', 'IT-TEL'),
    ('Video Conferencing Unit', 'IT-TEL-VCU', 'IT-TEL'),

    # FF — Seating
    ('Executive Chair',         'FF-SEA-EXC', 'FF-SEA'),
    ('Visitor Chair',           'FF-SEA-VIS', 'FF-SEA'),
    ('Conference Chair',        'FF-SEA-CNF', 'FF-SEA'),
    ('Workstation Chair',       'FF-SEA-WRK', 'FF-SEA'),
    ('Armchair',                'FF-SEA-ARM', 'FF-SEA'),
    ('Dining Chair',            'FF-SEA-DNG', 'FF-SEA'),
    ('1-Seater Sofa',           'FF-SEA-S1',  'FF-SEA'),

    # FF — Desking
    ('Executive Desk',          'FF-DSK-EXC', 'FF-DSK'),
    ('Workstation Desk',        'FF-DSK-WRK', 'FF-DSK'),
    ('Conference Table',        'FF-DSK-CNF', 'FF-DSK'),
    ('Dining Table',            'FF-DSK-DNG', 'FF-DSK'),
    ('Reception Desk',          'FF-DSK-RCP', 'FF-DSK'),
    ('L-Shaped Desk',           'FF-DSK-LSH', 'FF-DSK'),

    # FF — Storage
    ('Filing Cabinet',          'FF-STR-FLC', 'FF-STR'),
    ('Bookshelf',               'FF-STR-BSH', 'FF-STR'),
    ('Locker',                  'FF-STR-LCK', 'FF-STR'),
    ('Credenza',                'FF-STR-CRD', 'FF-STR'),
    ('Side Drawer Unit',        'FF-STR-SDR', 'FF-STR'),
    ('Cabinet',                 'FF-STR-CAB', 'FF-STR'),

    # FF — Soft Furnishings
    ('U-Shaped Sofa',           'FF-SFT-USF', 'FF-SFT'),
    ('L-Shaped Sofa',           'FF-SFT-LSF', 'FF-SFT'),
    ('2-Seater Sofa',           'FF-SFT-S2',  'FF-SFT'),
    ('Curtains / Blinds',       'FF-SFT-CRT', 'FF-SFT'),
    ('Carpet / Rug',            'FF-SFT-CRP', 'FF-SFT'),

    # FF — Fittings
    ('Partition / Cubicle',     'FF-FIT-PRT', 'FF-FIT'),
    ('Servery Counter',         'FF-FIT-SVC', 'FF-FIT'),
    ('Notice Board',            'FF-FIT-NTB', 'FF-FIT'),
    ('Whiteboard',              'FF-FIT-WTB', 'FF-FIT'),
    ('Signage',                 'FF-FIT-SGN', 'FF-FIT'),

    # PM — Power Supply
    ('33KV Switchgear',                 'PM-PWR-SG33',  'PM-PWR'),
    ('11KV Switchgear',                 'PM-PWR-SG11',  'PM-PWR'),
    ('33/11 7.5MVA Transformer',        'PM-PWR-TX33',  'PM-PWR'),
    ('2MVA 11/0.4KV Transformer',       'PM-PWR-TX2M',  'PM-PWR'),
    ('Main Low Voltage Panel',          'PM-PWR-MLVP',  'PM-PWR'),
    ('Synchronising Panel',             'PM-PWR-SYN',   'PM-PWR'),
    ('Busbar Riser (Raw Power)',         'PM-PWR-BBR',   'PM-PWR'),
    ('Busbar Riser (UPS Power)',         'PM-PWR-BBU',   'PM-PWR'),
    ('Tower Low Voltage Panel',         'PM-PWR-TLVP',  'PM-PWR'),
    ('UPS Panel (Essential)',           'PM-PWR-UPSE',  'PM-PWR'),
    ('UPS Panel (Non-Essential)',       'PM-PWR-UPSN',  'PM-PWR'),
    ('Main UPS',                        'PM-PWR-MUPP',  'PM-PWR'),
    ('100KVA Data Centre UPS',          'PM-PWR-UDC',   'PM-PWR'),
    ('60KVA Auditorium UPS',            'PM-PWR-UAU',   'PM-PWR'),
    ('Distribution Board (Raw Power)', 'PM-PWR-DBR',   'PM-PWR'),
    ('Distribution Board (UPS)',        'PM-PWR-DBU',   'PM-PWR'),
    ('Capacitor Bank',                  'PM-PWR-CAP',   'PM-PWR'),
    ('Internal Lighting',               'PM-PWR-LTI',   'PM-PWR'),
    ('External Lighting',               'PM-PWR-LTE',   'PM-PWR'),
    ('ATS Panel',                       'PM-PWR-ATS',   'PM-PWR'),

    # PM — HVAC
    ('Chiller',                 'PM-HVC-CHL', 'PM-HVC'),
    ('Primary Pump',            'PM-HVC-PPM', 'PM-HVC'),
    ('Secondary Pump',          'PM-HVC-SPM', 'PM-HVC'),
    ('Air Handling Unit (AHU)', 'PM-HVC-AHU', 'PM-HVC'),
    ('Fan Coil Unit (FCU)',     'PM-HVC-FCU', 'PM-HVC'),
    ('Cassette Unit',           'PM-HVC-CST', 'PM-HVC'),
    ('Split Unit',              'PM-HVC-SPL', 'PM-HVC'),
    ('Fresh Air Unit (FAU)',    'PM-HVC-FAU', 'PM-HVC'),
    ('Cooling Tower',           'PM-HVC-CLT', 'PM-HVC'),
    ('Exhaust Fan',             'PM-HVC-EXF', 'PM-HVC'),

    # PM — Vertical Transport
    ('Passenger Lift',          'PM-VTR-PLF', 'PM-VTR'),
    ('Service Lift',            'PM-VTR-SLF', 'PM-VTR'),
    ('Escalator',               'PM-VTR-ESC', 'PM-VTR'),

    # PM — Generators
    ('Generator 2MVA 400V',     'PM-GEN-G2M', 'PM-GEN'),
    ('Generator 1.25MVA 400V',  'PM-GEN-G1M', 'PM-GEN'),
    ('Generator 750KVA 400V',   'PM-GEN-G750','PM-GEN'),

    # PM — Other Plant
    ('BMS Controller',          'PM-OTH-BMS', 'PM-OTH'),
    ('Compressor',              'PM-OTH-CMP', 'PM-OTH'),
    ('Intercom System',         'PM-OTH-ICM', 'PM-OTH'),

    # PL — Water Systems
    ('Overhead Water Tank',     'PL-WTR-OHT', 'PL-WTR'),
    ('Underground Water Tank',  'PL-WTR-UGT', 'PL-WTR'),
    ('Transfer Pump',           'PL-WTR-TRP', 'PL-WTR'),
    ('Booster Pump',            'PL-WTR-BOP', 'PL-WTR'),
    ('Water Treatment Plant',   'PL-WTR-WTP', 'PL-WTR'),
    ('Water Heater',            'PL-WTR-WHT', 'PL-WTR'),

    # PL — Sanitary Fittings
    ('WC / Toilet',             'PL-SAN-WCT', 'PL-SAN'),
    ('Wash Hand Basin',         'PL-SAN-WHB', 'PL-SAN'),
    ('Mirror',                  'PL-SAN-MIR', 'PL-SAN'),
    ('Hand Dryer',              'PL-SAN-HDR', 'PL-SAN'),

    # PL — Fuel Systems
    ('Diesel Tank',             'PL-FUEL-DST','PL-FUEL'),
    ('Day Tank',                'PL-FUEL-DAT','PL-FUEL'),

    # FL — Vehicles
    ('Saloon Car',              'FL-EXC-SAL', 'FL-EXC'),
    ('SUV',                     'FL-EXC-SUV', 'FL-EXC'),
    ('Staff Bus',               'FL-ADM-BUS', 'FL-ADM'),
    ('Minivan',                 'FL-ADM-MVN', 'FL-ADM'),
    ('Pickup Truck',            'FL-OPS-PKP', 'FL-OPS'),
    ('Utility Van',             'FL-OPS-UTV', 'FL-OPS'),
    ('Ambulance',               'FL-OPS-AMB', 'FL-OPS'),
    ('Dispatch Bike',           'FL-MCY-DBK', 'FL-MCY'),
    ('Patrol Bike',             'FL-MCY-PBK', 'FL-MCY'),

    # SE — Access Control (Physical)
    ('Speed Gate',              'SE-ACC-SPG', 'SE-ACC'),
    ('Boom Barrier',            'SE-ACC-BBR', 'SE-ACC'),
    ('Turnstile',               'SE-ACC-TRN', 'SE-ACC'),
    ('Guard Booth',             'SE-ACC-GBT', 'SE-ACC'),

    # SE — Intrusion Detection
    ('Motion Sensor',           'SE-INT-MTS', 'SE-INT'),
    ('Glass Break Sensor',      'SE-INT-GBS', 'SE-INT'),
    ('Alarm Panel',             'SE-INT-ALP', 'SE-INT'),
    ('Siren',                   'SE-INT-SRN', 'SE-INT'),
    ('Patrol Wand',             'SE-INT-PWD', 'SE-INT'),

    # SE — Guard Equipment
    ('Walk-Through Metal Detector', 'SE-GRD-WTM', 'SE-GRD'),
    ('Handheld Scanner',        'SE-GRD-HHS', 'SE-GRD'),
    ('X-Ray Baggage Scanner',   'SE-GRD-XRY', 'SE-GRD'),

    # FE — Detection
    ('Smoke Detector',          'FE-DET-SMK', 'FE-DET'),
    ('Heat Detector',           'FE-DET-HET', 'FE-DET'),
    ('Manual Call Point',       'FE-DET-MCP', 'FE-DET'),

    # FE — Suppression
    ('Sprinkler Pump',          'FE-SUP-SKP', 'FE-SUP'),
    ('Hydrant Pump',            'FE-SUP-HDP', 'FE-SUP'),
    ('Hose Reel Pump',          'FE-SUP-HRP', 'FE-SUP'),
    ('Fire-Pro Unit',           'FE-SUP-FPU', 'FE-SUP'),
    ('Foam Bladder Tank',       'FE-SUP-FBT', 'FE-SUP'),
    ('Hose Reel',               'FE-SUP-HSR', 'FE-SUP'),
    ('Sprinkler System',        'FE-SUP-SKS', 'FE-SUP'),
    ('Fire Extinguisher (CO2)', 'FE-SUP-ECO', 'FE-SUP'),
    ('Fire Extinguisher (Dry Powder)', 'FE-SUP-EDP', 'FE-SUP'),
    ('Fire Extinguisher (Foam)','FE-SUP-EFM', 'FE-SUP'),

    # FE — Emergency
    ('Emergency Exit Light',    'FE-EMG-EXL', 'FE-EMG'),
    ('Fire Escape Signage',     'FE-EMG-SGN', 'FE-EMG'),
    ('Fire Door',               'FE-EMG-FDR', 'FE-EMG'),
    ('Evacuation Speaker',      'FE-EMG-EVS', 'FE-EMG'),

    # FE — Response
    ('Fire Hose Cabinet',       'FE-RSP-FHC', 'FE-RSP'),
    ('Hydrant',                 'FE-RSP-HDT', 'FE-RSP'),
    ('Fire Blanket',            'FE-RSP-FBL', 'FE-RSP'),
    ('First Aid Kit',           'FE-RSP-FAK', 'FE-RSP'),

    # EV — Fire Alarm
    ('Fire Alarm Panel',        'EV-FAL-FAP', 'EV-FAL'),
    ('Smoke Detector (ELV)',    'EV-FAL-SMK', 'EV-FAL'),
    ('Heat Detector (ELV)',     'EV-FAL-HET', 'EV-FAL'),
    ('Beam Detector',           'EV-FAL-BDT', 'EV-FAL'),
    ('Breakglass Unit',         'EV-FAL-BGU', 'EV-FAL'),
    ('Sounder',                 'EV-FAL-SND', 'EV-FAL'),

    # EV — CCTV
    ('CCTV Monitor / Screen',   'EV-CCT-MON', 'EV-CCT'),
    ('Dome Camera (Internal)',  'EV-CCT-DCI', 'EV-CCT'),
    ('Dome Camera (External)',  'EV-CCT-DCE', 'EV-CCT'),
    ('DVR / NVR',               'EV-CCT-DVR', 'EV-CCT'),
    ('Video Wall Display',      'EV-CCT-VWD', 'EV-CCT'),

    # EV — Public Address
    ('PA Speaker',              'EV-PAS-SPK', 'EV-PAS'),
    ('Amplifier',               'EV-PAS-AMP', 'EV-PAS'),
    ('PA Rack',                 'EV-PAS-RCK', 'EV-PAS'),

    # EV — Access Control (ELV)
    ('Access Control Panel',    'EV-ACC-ACP', 'EV-ACC'),
    ('Card Reader',             'EV-ACC-CDR', 'EV-ACC'),
    ('Biometric Reader',        'EV-ACC-BIO', 'EV-ACC'),
    ('Electronic Lock',         'EV-ACC-ELK', 'EV-ACC'),
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

# ─── STEP 4: ASSET FIELDS CONFIG ──────────────────────────────────────────────
separator('STEP 4: ASSET STATUS & CONDITION SELECTIONS')
# These are Selection field values — confirmed in the model.
# If your myservice_asset_register module uses ir.config_parameter or a
# separate model for dynamic selections, seed them here.
# Otherwise these are hardcoded in the model as:
#
# status: draft | discovered | pending_verification | active |
#         under_repair | reserved | lost | decommissioned | disposed
#
# condition: new | good | fair | poor | decommissioned
#
# asset_level: group | asset | sub_asset | component
#
print('  Selection fields are hardcoded in myservice.asset model.')
print('  Verify these values exist in your model definition:')
print('  status:     draft, discovered, pending_verification, active,')
print('              under_repair, reserved, lost, decommissioned, disposed')
print('  condition:  new, good, fair, poor, decommissioned')
print('  asset_level: group, asset, sub_asset, component')

# ─── STEP 5: FURNITURE SEED RECORDS ───────────────────────────────────────────
separator('STEP 5: FURNITURE SEED RECORDS FROM HQ INVENTORY')

# Resolve HQ Abuja location
hq_location = env['generic.location'].search([
    ('name', 'ilike', 'Abuja'), ('name', 'ilike', 'HQ')
], limit=1)
if not hq_location:
    hq_location = env['generic.location'].search([
        ('name', 'ilike', 'Federal Inland Revenue'), 
    ], limit=1)
if not hq_location:
    hq_location = env['generic.location'].search([], limit=1)
    print(f'  WARNING: HQ location not found. Defaulting to: {hq_location.name}')
else:
    print(f'  HQ Location resolved to: {hq_location.name}')

def next_asset_code(cat_code, subcat_code):
    """Generate next sequential asset code for a category+subcategory."""
    prefix = f'NRS-{cat_code}-{subcat_code.split("-")[1]}'
    existing = env['myservice.asset'].search([
        ('asset_code', 'like', prefix + '-')
    ], order='asset_code desc', limit=1)
    if existing:
        try:
            last_seq = int(existing.asset_code.split('-')[-1])
        except:
            last_seq = 0
    else:
        last_seq = 0
    return f'{prefix}-{(last_seq + 1):05d}'

def next_tag_code(site, floor, room, cat_code):
    """Generate next sequential physical tag code."""
    prefix = f'{site}-{floor}-{room}-{cat_code}'
    existing = env['myservice.asset'].search([
        ('tag_code', 'like', prefix + '-')
    ], order='tag_code desc', limit=1)
    if existing:
        try:
            last_seq = int(existing.tag_code.split('-')[-1])
        except:
            last_seq = 0
    else:
        last_seq = 0
    return f'{prefix}-{(last_seq + 1):03d}'

def create_furniture_records(floor_code, room_code, type_code, quantity, notes=''):
    """
    Create individual asset records for each unit of furniture.
    Each unit gets its own record, asset code, and tag code.
    """
    type_rec = asset_types.get(type_code)
    if not type_rec:
        print(f'  WARNING: Asset type {type_code} not found — skipping {quantity} records')
        return 0

    subcat = type_rec.subcategory_id
    cat = type_rec.category_id
    created_count = 0

    for i in range(quantity):
        asset_code = next_asset_code(cat.code, subcat.code)
        tag_code   = next_tag_code('HQ', floor_code, room_code, cat.code)
        name = f'{type_rec.name} — {floor_code} {room_code}'

        env['myservice.asset'].create({
            'name':           name,
            'asset_code':     asset_code,
            'tag_code':       tag_code,
            'category_id':    cat.id,
            'subcategory_id': subcat.id,
            'asset_type_id':  type_rec.id,
            'asset_level':    'asset',
            'location_id':    hq_location.id,
            'floor_room':     f'{floor_code} — {room_code}',
            'condition':      'good',
            'status':         'draft',
            'notes':          notes or f'Seeded from HQ Furniture Inventory — {floor_code}',
        })
        created_count += 1

    return created_count

# ─── FURNITURE INVENTORY DATA ─────────────────────────────────────────────────
# Source: FIRS HQ FURNITURE INVENTORY — 11/02/2026
# Format: (floor_code, room_code, asset_type_code, quantity, notes)

FURNITURE_INVENTORY = [
    # ── Entry Floor (Ground Floor) ─────────────────────────────────────────
    # Mail Room
    ('GF', 'MR', 'FF-DSK-WRK',  13, 'Entry Floor — Mail Room — Workstation tables'),
    ('GF', 'MR', 'FF-SEA-WRK',  39, 'Entry Floor — Mail Room — Chairs'),
    ('GF', 'MR', 'FF-STR-SDR',  13, 'Entry Floor — Mail Room — Side drawers'),
    # Dining Room 1
    ('GF', 'DR', 'FF-DSK-DNG',  12, 'Entry Floor — Dining 1 — Dining tables'),
    ('GF', 'DR', 'FF-SEA-DNG',  52, 'Entry Floor — Dining 1 — Dining chairs'),
    ('GF', 'DR', 'FF-SFT-USF',   7, 'Entry Floor — Dining 1 — U-shaped sofas'),
    ('GF', 'DR', 'FF-SFT-LSF',   2, 'Entry Floor — Dining 1 — L-shaped sofas'),
    ('GF', 'DR', 'FF-FIT-SVC',   2, 'Entry Floor — Dining 1 — Servery counters'),

    # ── 1st Floor (Library) ───────────────────────────────────────────────
    ('F1', 'LB', 'FF-DSK-WRK',  22, '1st Floor — Library — Workstation desks'),
    ('F1', 'LB', 'FF-SEA-WRK',  16, '1st Floor — Library — Chairs'),
    ('F1', 'LB', 'FF-STR-SDR',  31, '1st Floor — Library — Side drawers'),
    ('F1', 'LB', 'FF-SEA-EXC',   3, '1st Floor — Library — Executive chairs'),

    # ── 3rd Floor Wing C (Conference Room) ────────────────────────────────
    ('F3C', 'CR', 'FF-DSK-CNF', 13, '3rd Floor Wing C — Conference Room — Tables'),
    ('F3C', 'CR', 'FF-SEA-CNF',104, '3rd Floor Wing C — Conference Room — Chairs'),

    # ── 6th Floor Wing C ──────────────────────────────────────────────────
    ('F6C', 'OA', 'FF-DSK-WRK',  62, '6th Floor Wing C — Open Area — Tables'),
    ('F6C', 'OA', 'FF-SEA-WRK',  62, '6th Floor Wing C — Open Area — Chairs'),
    ('F6C', 'OA', 'FF-SFT-S2',    1, '6th Floor Wing C — 2-seater sofa'),
    ('F6C', 'OA', 'FF-SFT-S2',    2, '6th Floor Wing C — 1-seater sofas'),   # labelled 1-seater in PDF
    ('F6C', 'OA', 'FF-DSK-LSH',   1, '6th Floor Wing C — L-shaped desk'),
    ('F6C', 'OA', 'FF-SEA-EXC',  52, '6th Floor Wing C — Executive chairs'),
    ('F6C', 'OA', 'FF-STR-CAB',   8, '6th Floor Wing C — Cabinets'),
    ('F6C', 'OA', 'FF-SEA-ARM',   3, '6th Floor Wing C — Armchairs'),

    # ── 7th Floor Wing C ──────────────────────────────────────────────────
    ('F7C', 'OA', 'FF-DSK-WRK', 112, '7th Floor Wing C — Tables'),
    ('F7C', 'OA', 'FF-SEA-WRK', 112, '7th Floor Wing C — Chairs'),
    ('F7C', 'OA', 'FF-SFT-S2',    1, '7th Floor Wing C — 2-seater sofa'),
    ('F7C', 'OA', 'FF-SFT-S2',    7, '7th Floor Wing C — 1-seater sofas'),
    ('F7C', 'OA', 'FF-DSK-LSH',   2, '7th Floor Wing C — L-shaped desks'),
    ('F7C', 'OA', 'FF-SEA-EXC',  32, '7th Floor Wing C — Executive chairs'),
    ('F7C', 'OA', 'FF-STR-CAB',   8, '7th Floor Wing C — Cabinets'),
    ('F7C', 'OA', 'FF-SEA-ARM',   6, '7th Floor Wing C — Armchairs'),

    # ── 8th Floor Wing C ──────────────────────────────────────────────────
    ('F8C', 'OA', 'FF-SEA-WRK',  60, '8th Floor Wing C — Chairs'),
    ('F8C', 'OA', 'FF-SFT-S2',    1, '8th Floor Wing C — 2-seater sofa'),
    ('F8C', 'OA', 'FF-SFT-S2',    2, '8th Floor Wing C — 1-seater sofas'),
    ('F8C', 'OA', 'FF-SEA-EXC',  51, '8th Floor Wing C — Executive chairs'),
    ('F8C', 'OA', 'FF-STR-CAB',   8, '8th Floor Wing C — Cabinets'),
    ('F8C', 'OA', 'FF-SEA-ARM',   6, '8th Floor Wing C — Armchairs'),

    # ── 9th Floor Wing C ──────────────────────────────────────────────────
    ('F9C', 'OA', 'FF-DSK-WRK',  60, '9th Floor Wing C — Tables'),
    ('F9C', 'OA', 'FF-SEA-WRK',  60, '9th Floor Wing C — Chairs'),
    ('F9C', 'OA', 'FF-SFT-S2',    1, '9th Floor Wing C — 2-seater sofa'),
    ('F9C', 'OA', 'FF-SFT-S2',    2, '9th Floor Wing C — 1-seater sofas'),
    ('F9C', 'OA', 'FF-DSK-LSH',   2, '9th Floor Wing C — L-shaped desks'),
    ('F9C', 'OA', 'FF-SEA-EXC',  54, '9th Floor Wing C — Executive chairs'),
    ('F9C', 'OA', 'FF-STR-CAB',  16, '9th Floor Wing C — Cabinets'),
    ('F9C', 'OA', 'FF-SEA-ARM',   6, '9th Floor Wing C — Armchairs'),

    # ── 10th Floor Wing C ─────────────────────────────────────────────────
    ('F10C','OA', 'FF-SEA-WRK',  79, '10th Floor Wing C — Chairs'),
    ('F10C','OA', 'FF-SFT-S2',    1, '10th Floor Wing C — 2-seater sofa'),
    ('F10C','OA', 'FF-SFT-S2',    2, '10th Floor Wing C — 1-seater sofas'),
    ('F10C','OA', 'FF-SEA-EXC',  43, '10th Floor Wing C — Executive chairs'),
    ('F10C','OA', 'FF-STR-CAB',  15, '10th Floor Wing C — Cabinets'),
    ('F10C','OA', 'FF-SEA-ARM',   3, '10th Floor Wing C — Armchairs'),
]

total_furniture = 0
for floor_code, room_code, type_code, qty, notes in FURNITURE_INVENTORY:
    n = create_furniture_records(floor_code, room_code, type_code, qty, notes)
    total_furniture += n
    if n > 0:
        print(f'  + {n:4d} records  —  {floor_code}/{room_code}/{type_code}  [{notes[:50]}]')

env.cr.commit()
print(f'\n  Total furniture records seeded: {total_furniture}')

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
separator('SEED COMPLETE — SUMMARY')

cat_count    = env['myservice.asset.category'].search_count([])
subcat_count = env['myservice.asset.subcategory'].search_count([])
type_count   = env['myservice.asset.type'].search_count([])
asset_count  = env['myservice.asset'].search_count([])
draft_count  = env['myservice.asset'].search_count([('status','=','draft')])

print(f'''
  Asset Categories    : {cat_count}
  Sub-Categories      : {subcat_count}
  Asset Types         : {type_count}
  Asset Records       : {asset_count}
    └─ DRAFT (furniture seed) : {draft_count}

  Next steps:
    1. Verify category/subcategory/type hierarchy in myservice UI
    2. Confirm furniture DRAFT records appear on correct floors
    3. Run nrs_itsm_seed_v2.py (Help Desk service catalogue)
    4. Run nrs_sla_seed.py (SLA policies)
    5. Print Zebra label batch for Ground Floor — begin tagging exercise

  Deployment branch: 15.0
  Server: /opt/odoo/myservicenrs/scripts/nrs_asset_seed.py
''')
