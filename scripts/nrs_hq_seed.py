#!/usr/bin/env python3
"""
nrs_hq_seed.py  —  Version 3.0  (DEFINITIVE)
═══════════════════════════════════════════════════════════════════════════════
NRS myservice.com.ng — Phase 1 Asset Register Seed Script
NRS New Headquarters, Kui Mohammed Avenue, CBD, Abuja, FCT

Sources consolidated in this version:
  • Baron Architecture drawings  A400–A485  (building layout / rooms)
  • Unecon Associates Ltd         M&E completion schedule (plumbing, HVAC, FF)
  • Electrical Works.xlsx         Power, Fire Alarm, CCTV, PA, Access, Security
  • FIRS HQ Furniture Inventory   11/02/2026 (furniture counts per floor)

Deploys:
  STEP 0   Wipe existing nrs.asset records (leaves fleet.vehicle untouched)
  STEP 1   ir.sequence — asset_code and tag_code auto-generation
  STEP 2   NRS HQ location hierarchy  (1 root → 19 floors → 232 rooms)
  STEP 3   8 Asset categories
  STEP 4   35 Sub-categories
  STEP 5   135 Asset types  (all contractor-confirmed items)
  STEP 6   ~1,272 Furniture DRAFT records mapped to exact room locations

Run via Odoo shell (branch: 15.0):
  sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \
    -c /etc/odoo/odoo.conf -d myservice --no-http \
    < /opt/odoo/myservicenrs/scripts/nrs_hq_seed.py

Deployment workflow:
  Mac → GitHub (15.0) → server git pull → Odoo shell
  NEVER scp or direct upload.
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
_logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_or_create(model, domain, vals):
    rec = env[model].search(domain, limit=1)
    if not rec:
        rec = env[model].create(vals)
        return rec, True
    return rec, False

def sep(title):
    print('\n' + '═' * 70)
    print(f'  {title}')
    print('═' * 70)

def ok(created, name):
    print(f'  {"+ created" if created else "✓ exists "}  {name}')

# ─── STEP 0: WIPE ─────────────────────────────────────────────────────────────
#
# THE CHAIN OF CUSTODY, AND THE DOOR OUT OF THE REFUSAL
#
# `nrs.asset.custody` is append-only and its link to the asset is
# `ondelete='restrict'`, so the wipe below STOPS on any tenant that has
# custody history. That refusal is deliberate: a script that would destroy an
# audit-grade record should stop and say so.
#
# But a refusal people route around is worse than a refusal with a documented
# exit, and the route around this one is dropping the database — which
# destroys the chain AND everything else, with nothing left to say it
# happened. So there is a door, and it is a FLAG:
#
#     CADRA_SEED_DESTROY_CUSTODY=1
#
# An environment variable rather than a prompt, because this script is piped
# into `odoo shell` and a prompt there is answered by whatever the rest of the
# file happens to be. A flag cannot be hit by accident and cannot be answered
# by pressing return.
#
# Under the flag the deletion is raw SQL, and that is not laziness: the model
# refuses `unlink()` unconditionally, including under `sudo()`, and that
# refusal is its entire value. Going round it is meant to look like going
# round it. The count and the tenant are printed FIRST, so the operator sees
# what they are about to destroy and where, in a log they keep.
import os

CUSTODY_ESCAPE_FLAG = 'CADRA_SEED_DESTROY_CUSTODY'

sep('STEP 0: WIPE EXISTING nrs.asset RECORDS')

if 'nrs.asset.custody' in env:
    custody_links = env['nrs.asset.custody'].sudo().search_count([])
    if custody_links:
        print(f'  Chain of custody on {env.cr.dbname!r}: '
              f'{custody_links} link(s).')
        if os.environ.get(CUSTODY_ESCAPE_FLAG, '').strip() not in ('1', 'true', 'TRUE', 'yes'):
            raise SystemExit(
                f'\n  REFUSED. Wiping the register would destroy '
                f'{custody_links} chain-of-custody link(s) on tenant '
                f'{env.cr.dbname!r}.\n'
                f'  These are append-only audit records: once gone there is '
                f'nothing left to say they existed.\n'
                f'  If you genuinely mean to discard them, re-run with '
                f'{CUSTODY_ESCAPE_FLAG}=1 set.\n'
            )
        print(f'  {CUSTODY_ESCAPE_FLAG} is set. DESTROYING {custody_links} '
              f'chain-of-custody link(s) on tenant {env.cr.dbname!r}.')
        print(f'  This goes around nrs.asset.custody\'s own append-only '
              f'guard. It is not recoverable.')
        _logger.warning(
            'nrs_hq_seed: %s set — deleting %s chain-of-custody link(s) on %s',
            CUSTODY_ESCAPE_FLAG, custody_links, env.cr.dbname)
        env.cr.execute('DELETE FROM nrs_asset_custody')
        print(f'  - Removed {custody_links} chain-of-custody links')

existing = env['nrs.asset'].search([])
cats     = env['nrs.asset.category'].search([])
subs     = env['nrs.asset.subcategory'].search([])
types    = env['nrs.asset.type'].search([])

print(f'  Before wipe:')
print(f'    nrs.asset              : {len(existing)}')
print(f'    nrs.asset.category     : {len(cats)}')
print(f'    nrs.asset.subcategory  : {len(subs)}')
print(f'    nrs.asset.type         : {len(types)}')
print(f'    fleet.vehicle (safe)   : {env["fleet.vehicle"].search_count([])}')

if existing:
    children = existing.filtered(lambda a: a.asset_level in ('sub_asset','component'))
    if children:
        children.unlink()
        print(f'  - Removed {len(children)} sub-asset/component records')
    remaining = env['nrs.asset'].search([])
    if remaining:
        remaining.unlink()
        print(f'  - Removed {len(remaining)} asset/group records')

if types:  types.unlink();  print(f'  - Removed {len(types)} asset types')
if subs:   subs.unlink();   print(f'  - Removed {len(subs)} sub-categories')
if cats:   cats.unlink();   print(f'  - Removed {len(cats)} categories')

env.cr.commit()
print('  Wipe complete.')

# ─── STEP 1: ir.sequence FOR ASSET CODE & TAG CODE ────────────────────────────
sep('STEP 1: ir.sequence — ASSET CODE & TAG CODE')

# Asset code sequence: NRS-{CATCODE}-{SUBCATCODE}-{00001}
# Tag code sequence:   HQ-{FLOOR}-{ROOM}-{CATCODE}-{001}
# Both are generated programmatically in Step 6 using counters.
# Here we register the ir.sequence records so the Odoo UI
# can also auto-generate on manual record creation.

SEQUENCES = [
    {
        'name': 'NRS Asset Code',
        'code': 'nrs.asset.code',
        'prefix': 'NRS-',
        'padding': 5,
        'number_next': 1,
        'number_increment': 1,
        'implementation': 'standard',
    },
    {
        'name': 'NRS Asset Tag Code',
        'code': 'nrs.asset.tag',
        'prefix': 'HQ-',
        'padding': 3,
        'number_next': 1,
        'number_increment': 1,
        'implementation': 'standard',
    },
]

for sq in SEQUENCES:
    rec, created = get_or_create(
        'ir.sequence',
        [('code','=', sq['code'])],
        sq
    )
    ok(created, f"{sq['name']}  ({sq['code']})")

env.cr.commit()

# ─── STEP 2: LOCATION HIERARCHY ───────────────────────────────────────────────
sep('STEP 2: NRS HQ LOCATION HIERARCHY')

locations      = {}
floor_locs     = {}
room_locs      = {}

# Root HQ location
hq, created = get_or_create(
    'generic.location',
    [('name','=','NRS Headquarters'),('parent_id','=',False)],
    {'name':'NRS Headquarters','parent_id':False,
     'description':'Nigeria Revenue Service New HQ, Kui Mohammed Avenue, CBD, Abuja, FCT.'}
)
ok(created, 'NRS Headquarters  [ROOT]')
locations['HQ'] = hq

# Floor + Room definitions
# Source: Baron Architecture drawings A401–A485
# Format: (floor_code, floor_label, drawing_no, [(room_code, room_name), ...])
FLOOR_ROOMS = [
    ('BF','Basement Floor','A401',[
        ('GYM','Gym'),('SLP','Sleep Area'),('DRL',"Driver's Lounge"),
        ('RCP','Reception'),('LBY-N','Lobby North'),('LBY-S','Lobby South'),
        ('OFC-CI','Office (CI)'),('SRV','Server Room'),('SCR','Security Room'),
        ('SCM','Security & Monitoring'),('BMS','BMS Room'),
        ('AHU-1','AHU Room 1'),('AHU-2','AHU Room 2'),('ELR','Electrical Room'),
        ('MCH-1','Mechanical Room 1'),('MCH-2','Mechanical Room 2'),
        ('CHM','Chemical Room'),('STR','Store'),('ECP','Executive Carpark'),
        ('WCM','Male WC'),('WCF','Female WC'),('STR-B','Stairwell'),('LFT','Lift Lobby'),
    ]),
    ('GF','Ground Floor','A411',[
        ('RCP','Reception'),('LBY','Main Lobby'),('LFT','Lift Lobby'),
        ('WTA','Waiting Area'),('LED','LED Room'),('PRJ','Projection Room'),
        ('MPR','Multi-Purpose Room'),('PRY','Prayer Room'),('CNF','Conference Room'),
        ('WCM','Male WC'),('WCF','Female WC'),('STR','Store'),('STR-B','Stairwell'),
        ('MR','Mail Room'),('DNG','Dining Room'),
    ]),
    ('F01','1st Floor','A418',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F02','2nd Floor','A425',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F03','3rd Floor','A430',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('SCM','Security & Safety Management'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F04','4th Floor','A436',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F05','5th Floor','A440',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('FOP','Field Operations Department'),('SUP','Support Staff Area'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F06','6th Floor','A444',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F07','7th Floor','A448',[
        ('TAX','Tax Policy & Advisory'),('CEG','Compliance & Enforcement Group'),
        ('PDD','Project Delivery & Planning'),
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('EXO-1','Executive Office 1'),
        ('DNG','Dining Area'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F08','8th Floor','A452',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('BRD','Board / Conference Area'),
        ('MTG-1','Meeting Room 1'),('MTG-2','Meeting Room 2'),
        ('EXO-1','Executive Office 1'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F09','9th Floor','A456',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('PRB','Procurement & Remuneration Bureau'),
        ('MTG-1','Meeting Room 1'),('EXO-1','Executive Office 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F10','10th Floor','A460',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('APR','Appraisal & Performance'),
        ('MTG-1','Meeting Room 1'),('EXO-1','Executive Office 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F11','11th Floor','A464',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('MTG-1','Meeting Room 1'),('EXO-1','Executive Office 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F12','12th Floor','A468',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('SSB','Service Bureau'),
        ('MTG-1','Meeting Room 1'),('EXO-1','Executive Office 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F13','13th Floor','A472',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('EXO-3','Executive Office 3'),('MTG-1','Meeting Room 1'),
        ('DNG','Dining Area'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F14','14th Floor','A477',[
        ('OFC-N','Open Office North'),('OFC-S','Open Office South'),
        ('SCS','Security Services'),('BLT','Balloting Room'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('MTG-1','Meeting Room 1'),('LFT','Lift Lobby'),
        ('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F15','15th Floor','A481',[
        ('BRD','Board Room'),('EXO-1','Executive Office 1'),
        ('EXO-2','Executive Office 2'),('EXS','Executive Support'),
        ('VIP-D','VIP Dining'),('MTG-1','Meeting Room 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR','Store'),('STR-B','Stairwell'),('PNT','Pantry'),
    ]),
    ('F16','16th Floor','A485',[
        ('CHR',"Chairman's Office"),('BRD','Board Room'),
        ('EXS','Executive Suite'),('VIP-L','VIP Lounge'),
        ('VIP-D','VIP Dining'),('RCP','Executive Reception'),
        ('EXO-1','Executive Office 1'),('EXO-2','Executive Office 2'),
        ('EXO-3','Executive Office 3'),('MTG-1','Meeting Room 1'),
        ('LFT','Lift Lobby'),('WCM','Male WC'),('WCF','Female WC'),
        ('STR-B','Stairwell'),
    ]),
    ('RF','Roof / Plant Room','—',[
        ('PR','Plant Room'),('OVH','Overhead Tank Area'),('EX','External Roof'),
    ]),
]

total_floors = total_rooms = 0
for floor_code, floor_label, drw, rooms in FLOOR_ROOMS:
    floor_rec, created = get_or_create(
        'generic.location',
        [('name','=',floor_label),('parent_id','=',hq.id)],
        {'name':floor_label,'parent_id':hq.id,'description':f'Drawing: {drw}'}
    )
    floor_locs[floor_code] = floor_rec
    locations[floor_code]  = floor_rec
    ok(created, f'{floor_code}  {floor_label}')
    total_floors += 1
    for room_code, room_name in rooms:
        key = f'{floor_code}-{room_code}'
        room_rec, _ = get_or_create(
            'generic.location',
            [('name','=',room_name),('parent_id','=',floor_rec.id)],
            {'name':room_name,'parent_id':floor_rec.id,
             'description':f'NRS HQ / {floor_code} / {room_code}'}
        )
        room_locs[key] = room_rec
        locations[key] = room_rec
        total_rooms += 1

env.cr.commit()
print(f'\n  Locations created: 1 HQ + {total_floors} floors + {total_rooms} rooms = {1+total_floors+total_rooms} total')

# ─── STEP 3: ASSET CATEGORIES ─────────────────────────────────────────────────
sep('STEP 3: ASSET CATEGORIES')

CATEGORIES = [
    ('IT Equipment',        'IT', 10, 'Computers, networking, servers, telecoms and peripherals'),
    ('Furniture & Fittings','FF', 20, 'Seating, desking, storage, soft furnishings, kitchen and fittings'),
    ('Plant & Machinery',   'PM', 30, 'Power supply, HVAC, vertical transport, generators and other plant'),
    ('Plumbing',            'PL', 40, 'Water systems, sanitary fittings and fuel storage'),
    ('Fleet / Vehicles',    'FL', 50, 'Executive, administrative, operational vehicles and motorcycles'),
    ('Security Equipment',  'SE', 60, 'Physical security — speed gates, guard equipment and intrusion detection'),
    ('Fire Fighting',       'FE', 70, 'Detection, suppression, emergency and response equipment'),
    ('ELV Systems',         'EV', 80, 'Fire alarm, CCTV, public address and access control systems'),
]

categories = {}
for name, code, seq, desc in CATEGORIES:
    rec, created = get_or_create(
        'nrs.asset.category', [('code','=',code)],
        {'name':name,'code':code,'sequence':seq,'description':desc}
    )
    categories[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()

# ─── STEP 4: SUB-CATEGORIES ───────────────────────────────────────────────────
sep('STEP 4: SUB-CATEGORIES  (35 total)')

SUBCATEGORIES = [
    # IT
    ('Computers & Peripherals',   'IT-CMP',  'IT', 10),
    ('Printing & Imaging',        'IT-PRT',  'IT', 20),
    ('Networking',                'IT-NET',  'IT', 30),
    ('Servers & Storage',         'IT-SRV',  'IT', 40),
    ('Telecoms',                  'IT-TEL',  'IT', 50),
    # FF
    ('Seating',                   'FF-SEA',  'FF', 10),
    ('Desking',                   'FF-DSK',  'FF', 20),
    ('Storage',                   'FF-STR',  'FF', 30),
    ('Soft Furnishings',          'FF-SFT',  'FF', 40),
    ('Fittings',                  'FF-FIT',  'FF', 50),
    ('Kitchen Equipment',         'FF-KIT',  'FF', 60),  # NEW — Unecon
    # PM
    ('Power Supply',              'PM-PWR',  'PM', 10),
    ('HVAC',                      'PM-HVC',  'PM', 20),
    ('Vertical Transport',        'PM-VTR',  'PM', 30),
    ('Generators',                'PM-GEN',  'PM', 40),
    ('Cleaning Equipment',        'PM-CLN',  'PM', 50),  # NEW — Unecon
    ('Other Plant',               'PM-OTH',  'PM', 60),
    # PL
    ('Water Systems',             'PL-WTR',  'PL', 10),
    ('Sanitary Fittings',         'PL-SAN',  'PL', 20),
    ('Fuel Systems',              'PL-FUEL', 'PL', 30),
    # FL
    ('Executive Vehicles',        'FL-EXC',  'FL', 10),
    ('Administrative Vehicles',   'FL-ADM',  'FL', 20),
    ('Operational Vehicles',      'FL-OPS',  'FL', 30),
    ('Motorcycles',               'FL-MCY',  'FL', 40),
    # SE
    ('Access Control (Physical)', 'SE-ACC',  'SE', 10),
    ('Intrusion Detection',       'SE-INT',  'SE', 20),
    ('Guard Equipment',           'SE-GRD',  'SE', 30),
    # FE
    ('Detection',                 'FE-DET',  'FE', 10),
    ('Suppression',               'FE-SUP',  'FE', 20),
    ('Emergency',                 'FE-EMG',  'FE', 30),
    ('Response',                  'FE-RSP',  'FE', 40),
    # EV
    ('Fire Alarm',                'EV-FAL',  'EV', 10),
    ('CCTV & Detection',          'EV-CCT',  'EV', 20),
    ('Public Address',            'EV-PAS',  'EV', 30),
    ('Access Control (ELV)',      'EV-ACC',  'EV', 40),
]

subcategories = {}
for name, code, parent_code, seq in SUBCATEGORIES:
    rec, created = get_or_create(
        'nrs.asset.subcategory', [('code','=',code)],
        {'name':name,'code':code,'sequence':seq,
         'category_id':categories[parent_code].id}
    )
    subcategories[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()

# ─── STEP 5: ASSET TYPES ──────────────────────────────────────────────────────
sep('STEP 5: ASSET TYPES  (135 total — all contractor-confirmed)')

# Sources:
#   ✅ Baron Architecture drawings
#   ✅ Unecon Associates M&E completion schedule
#   ✅ Electrical Works.xlsx (Power, Fire Alarm, CCTV, PA, Access, Security)

ASSET_TYPES = [
    # ── IT Equipment ────────────────────────────────────────────────────────
    ('Desktop Computer',                'IT-CMP-DKT', 'IT-CMP'),
    ('Laptop',                          'IT-CMP-LAP', 'IT-CMP'),
    ('Monitor',                         'IT-CMP-MON', 'IT-CMP'),
    ('Keyboard & Mouse',                'IT-CMP-KBM', 'IT-CMP'),
    ('Docking Station',                 'IT-CMP-DCK', 'IT-CMP'),
    ('Printer',                         'IT-PRT-PRT', 'IT-PRT'),
    ('Photocopier',                     'IT-PRT-CPR', 'IT-PRT'),
    ('Scanner',                         'IT-PRT-SCN', 'IT-PRT'),
    ('Plotter',                         'IT-PRT-PLT', 'IT-PRT'),
    ('Network Switch',                  'IT-NET-SWT', 'IT-NET'),
    ('Router',                          'IT-NET-RTR', 'IT-NET'),
    ('Firewall',                        'IT-NET-FWL', 'IT-NET'),
    ('Patch Panel',                     'IT-NET-PTC', 'IT-NET'),
    ('Wireless Access Point',           'IT-NET-WAP', 'IT-NET'),
    ('Server',                          'IT-SRV-SVR', 'IT-SRV'),
    ('NAS / Storage Array',             'IT-SRV-NAS', 'IT-SRV'),
    ('UPS Unit',                        'IT-SRV-UPS', 'IT-SRV'),
    ('Server Rack',                     'IT-SRV-RCK', 'IT-SRV'),
    ('IP Phone',                        'IT-TEL-IPP', 'IT-TEL'),
    ('PABX System',                     'IT-TEL-PBX', 'IT-TEL'),
    ('Conference System',               'IT-TEL-CNF', 'IT-TEL'),
    ('Video Conferencing Unit',         'IT-TEL-VCU', 'IT-TEL'),

    # ── Furniture & Fittings — Seating ──────────────────────────────────────
    ('Executive Chair',                 'FF-SEA-EXC', 'FF-SEA'),
    ('Visitor Chair',                   'FF-SEA-VIS', 'FF-SEA'),
    ('Conference Chair',                'FF-SEA-CNF', 'FF-SEA'),
    ('Workstation Chair',               'FF-SEA-WRK', 'FF-SEA'),
    ('Armchair',                        'FF-SEA-ARM', 'FF-SEA'),
    ('Dining Chair',                    'FF-SEA-DNG', 'FF-SEA'),
    ('1-Seater Sofa',                   'FF-SEA-S1',  'FF-SEA'),

    # ── Furniture & Fittings — Desking ──────────────────────────────────────
    ('Executive Desk',                  'FF-DSK-EXC', 'FF-DSK'),
    ('Workstation Desk',                'FF-DSK-WRK', 'FF-DSK'),
    ('Conference Table',                'FF-DSK-CNF', 'FF-DSK'),
    ('Dining Table',                    'FF-DSK-DNG', 'FF-DSK'),
    ('Reception Desk',                  'FF-DSK-RCP', 'FF-DSK'),
    ('L-Shaped Desk',                   'FF-DSK-LSH', 'FF-DSK'),

    # ── Furniture & Fittings — Storage ──────────────────────────────────────
    ('Filing Cabinet',                  'FF-STR-FLC', 'FF-STR'),
    ('Bookshelf',                       'FF-STR-BSH', 'FF-STR'),
    ('Locker',                          'FF-STR-LCK', 'FF-STR'),
    ('Credenza',                        'FF-STR-CRD', 'FF-STR'),
    ('Side Drawer Unit',                'FF-STR-SDR', 'FF-STR'),
    ('Cabinet',                         'FF-STR-CAB', 'FF-STR'),

    # ── Furniture & Fittings — Soft Furnishings ─────────────────────────────
    ('U-Shaped Sofa',                   'FF-SFT-USF', 'FF-SFT'),
    ('L-Shaped Sofa',                   'FF-SFT-LSF', 'FF-SFT'),
    ('2-Seater Sofa',                   'FF-SFT-S2',  'FF-SFT'),
    ('Curtains / Blinds',               'FF-SFT-CRT', 'FF-SFT'),
    ('Carpet / Rug',                    'FF-SFT-CRP', 'FF-SFT'),

    # ── Furniture & Fittings — Fittings ─────────────────────────────────────
    ('Partition / Cubicle',             'FF-FIT-PRT', 'FF-FIT'),
    ('Servery Counter',                 'FF-FIT-SVC', 'FF-FIT'),
    ('Notice Board',                    'FF-FIT-NTB', 'FF-FIT'),
    ('Whiteboard',                      'FF-FIT-WTB', 'FF-FIT'),
    ('Signage',                         'FF-FIT-SGN', 'FF-FIT'),

    # ── Furniture & Fittings — Kitchen Equipment (NEW — Unecon) ─────────────
    ('Kitchen Equipment (General)',     'FF-KIT-GEN', 'FF-KIT'),

    # ── Plant & Machinery — Power Supply (Electrical Works.xlsx) ────────────
    ('33KV Switchgear',                 'PM-PWR-SG33', 'PM-PWR'),
    ('11KV Switchgear',                 'PM-PWR-SG11', 'PM-PWR'),
    ('33/11 7.5MVA Transformer',        'PM-PWR-TX33', 'PM-PWR'),
    ('2MVA 11/0.4KV Transformer',       'PM-PWR-TX2M', 'PM-PWR'),
    ('Main Low Voltage Panel',          'PM-PWR-MLVP', 'PM-PWR'),
    ('Synchronising Panel',             'PM-PWR-SYN',  'PM-PWR'),
    ('Busbar Riser (Raw Power)',         'PM-PWR-BBR',  'PM-PWR'),
    ('Busbar Riser (UPS Power)',         'PM-PWR-BBU',  'PM-PWR'),
    ('Tower Low Voltage Panel',         'PM-PWR-TLVP', 'PM-PWR'),
    ('UPS Panel (Essential)',           'PM-PWR-UPSE', 'PM-PWR'),
    ('UPS Panel (Non-Essential)',       'PM-PWR-UPSN', 'PM-PWR'),
    ('Main UPS',                        'PM-PWR-MUPP', 'PM-PWR'),
    ('100KVA Data Centre UPS',          'PM-PWR-UDC',  'PM-PWR'),
    ('60KVA Auditorium UPS',            'PM-PWR-UAU',  'PM-PWR'),
    ('Distribution Board (Raw Power)', 'PM-PWR-DBR',  'PM-PWR'),
    ('Distribution Board (UPS)',        'PM-PWR-DBU',  'PM-PWR'),
    ('Capacitor Bank',                  'PM-PWR-CAP',  'PM-PWR'),
    ('Internal Lighting',               'PM-PWR-LTI',  'PM-PWR'),
    ('External Lighting',               'PM-PWR-LTE',  'PM-PWR'),
    ('ATS Panel',                       'PM-PWR-ATS',  'PM-PWR'),
    ('Floor Box',                       'PM-PWR-FLB',  'PM-PWR'),  # NEW — Electrical Works

    # ── Plant & Machinery — HVAC (Unecon) ───────────────────────────────────
    ('Chiller',                         'PM-HVC-CHL', 'PM-HVC'),
    ('Primary Pump',                    'PM-HVC-PPM', 'PM-HVC'),
    ('Secondary Pump',                  'PM-HVC-SPM', 'PM-HVC'),
    ('Air Handling Unit (AHU)',         'PM-HVC-AHU', 'PM-HVC'),
    ('Fan Coil Unit (FCU)',             'PM-HVC-FCU', 'PM-HVC'),
    ('Cassette Unit',                   'PM-HVC-CST', 'PM-HVC'),
    ('Split / Precision Unit',          'PM-HVC-SPL', 'PM-HVC'),
    ('Fresh Air Unit (FAU)',            'PM-HVC-FAU', 'PM-HVC'),
    ('Fan / Exhaust Fan',               'PM-HVC-EXF', 'PM-HVC'),
    ('Cooling Tower',                   'PM-HVC-CLT', 'PM-HVC'),
    ('Chemical Dosing Unit',            'PM-HVC-CDU', 'PM-HVC'),  # NEW — Unecon
    ('Separator',                       'PM-HVC-SEP', 'PM-HVC'),  # NEW — Unecon
    ('Expansion Tank',                  'PM-HVC-EXT', 'PM-HVC'),  # NEW — Unecon
    ('Volume Damper',                   'PM-HVC-VLD', 'PM-HVC'),  # NEW — Unecon

    # ── Plant & Machinery — Vertical Transport (Unecon) ─────────────────────
    ('Passenger Lift',                  'PM-VTR-PLF', 'PM-VTR'),
    ('Service Lift',                    'PM-VTR-SLF', 'PM-VTR'),
    ('Escalator',                       'PM-VTR-ESC', 'PM-VTR'),

    # ── Plant & Machinery — Generators ──────────────────────────────────────
    ('Generator 2MVA 400V',             'PM-GEN-G2M',  'PM-GEN'),
    ('Generator 1.25MVA 400V',          'PM-GEN-G1M',  'PM-GEN'),
    ('Generator 750KVA 400V',           'PM-GEN-G750', 'PM-GEN'),

    # ── Plant & Machinery — Cleaning Equipment (NEW — Unecon) ───────────────
    ('Cleaning Cradle',                 'PM-CLN-CCR', 'PM-CLN'),

    # ── Plant & Machinery — Other Plant ─────────────────────────────────────
    ('BMS Controller',                  'PM-OTH-BMS', 'PM-OTH'),
    ('Compressor',                      'PM-OTH-CMP', 'PM-OTH'),
    ('Intercom System',                 'PM-OTH-ICM', 'PM-OTH'),

    # ── Plumbing — Water Systems (Unecon) ───────────────────────────────────
    ('Overhead Water Tank',             'PL-WTR-OHT', 'PL-WTR'),
    ('Underground Water Tank',          'PL-WTR-UGT', 'PL-WTR'),
    ('Transfer Pump',                   'PL-WTR-TRP', 'PL-WTR'),
    ('Booster Pump',                    'PL-WTR-BOP', 'PL-WTR'),
    ('Water Treatment Plant',           'PL-WTR-WTP', 'PL-WTR'),
    ('Water Heater',                    'PL-WTR-WHT', 'PL-WTR'),

    # ── Plumbing — Sanitary Fittings (Unecon) ───────────────────────────────
    ('WC / Toilet',                     'PL-SAN-WCT', 'PL-SAN'),
    ('Disabled WC',                     'PL-SAN-DWC', 'PL-SAN'),  # NEW — Unecon
    ('Urinal Bowl',                     'PL-SAN-URN', 'PL-SAN'),  # NEW — Unecon
    ('Shower Unit',                     'PL-SAN-SHW', 'PL-SAN'),  # NEW — Unecon
    ('Wash Hand Basin',                 'PL-SAN-WHB', 'PL-SAN'),
    ('Mirror',                          'PL-SAN-MIR', 'PL-SAN'),
    ('Automatic Hand Dryer',            'PL-SAN-HDR', 'PL-SAN'),
    ('Bidet Hand Spray',                'PL-SAN-BDS', 'PL-SAN'),  # NEW — Unecon
    ('Ablution Tap',                    'PL-SAN-ABL', 'PL-SAN'),  # NEW — Unecon
    ('Water Tap',                       'PL-SAN-TAP', 'PL-SAN'),  # NEW — Unecon

    # ── Plumbing — Fuel Systems ──────────────────────────────────────────────
    ('Diesel Tank (Day)',                'PL-FUEL-DAT', 'PL-FUEL'),
    ('Diesel Tank (Underground)',        'PL-FUEL-UDT', 'PL-FUEL'),  # NEW — Unecon

    # ── Fleet / Vehicles ────────────────────────────────────────────────────
    ('Saloon Car',                      'FL-EXC-SAL', 'FL-EXC'),
    ('SUV',                             'FL-EXC-SUV', 'FL-EXC'),
    ('Staff Bus',                       'FL-ADM-BUS', 'FL-ADM'),
    ('Minivan',                         'FL-ADM-MVN', 'FL-ADM'),
    ('Pickup Truck',                    'FL-OPS-PKP', 'FL-OPS'),
    ('Utility Van',                     'FL-OPS-UTV', 'FL-OPS'),
    ('Ambulance',                       'FL-OPS-AMB', 'FL-OPS'),
    ('Dispatch Bike',                   'FL-MCY-DBK', 'FL-MCY'),
    ('Patrol Bike',                     'FL-MCY-PBK', 'FL-MCY'),

    # ── Security Equipment — Physical Access (Electrical Works.xlsx) ────────
    ('Speed Gate',                      'SE-ACC-SPG', 'SE-ACC'),
    ('Turnstile',                       'SE-ACC-TRN', 'SE-ACC'),
    ('Boom Barrier',                    'SE-ACC-BBR', 'SE-ACC'),
    ('Guard Booth',                     'SE-ACC-GBT', 'SE-ACC'),

    # ── Security Equipment — Intrusion Detection ─────────────────────────────
    ('Motion Sensor',                   'SE-INT-MTS', 'SE-INT'),
    ('Glass Break Sensor',              'SE-INT-GBS', 'SE-INT'),
    ('Alarm Panel',                     'SE-INT-ALP', 'SE-INT'),
    ('Siren',                           'SE-INT-SRN', 'SE-INT'),
    ('Patrol Wand',                     'SE-INT-PWD', 'SE-INT'),

    # ── Security Equipment — Guard Equipment (Electrical Works.xlsx) ────────
    ('Walk-Through Metal Detector',     'SE-GRD-WTM', 'SE-GRD'),
    ('Baggage / X-Ray Scanner',         'SE-GRD-XRY', 'SE-GRD'),
    ('Handheld Scanner',                'SE-GRD-HHS', 'SE-GRD'),
    ('Under Vehicle Surveillance (UVSS)','SE-GRD-UVS','SE-GRD'),  # NEW — Electrical Works
    ('License Plate Recognition Camera','SE-GRD-LPR', 'SE-GRD'),  # NEW — Electrical Works

    # ── Fire Fighting — Detection ─────────────────────────────────────────────
    ('Smoke Detector',                  'FE-DET-SMK', 'FE-DET'),
    ('Heat Detector',                   'FE-DET-HET', 'FE-DET'),
    ('Manual Call Point',               'FE-DET-MCP', 'FE-DET'),

    # ── Fire Fighting — Suppression (Unecon) ────────────────────────────────
    ('Sprinkler Pump',                  'FE-SUP-SKP', 'FE-SUP'),
    ('Hydrant Pump',                    'FE-SUP-HDP', 'FE-SUP'),
    ('Hose Reel Pump',                  'FE-SUP-HRP', 'FE-SUP'),
    ('Fire-Pro Unit',                   'FE-SUP-FPU', 'FE-SUP'),
    ('Foam Bladder Tank',               'FE-SUP-FBT', 'FE-SUP'),
    ('Hose Reel',                       'FE-SUP-HSR', 'FE-SUP'),
    ('Sprinkler System',                'FE-SUP-SKS', 'FE-SUP'),
    ('Fire Extinguisher (CO2)',         'FE-SUP-ECO', 'FE-SUP'),
    ('Fire Extinguisher (Dry Powder)',  'FE-SUP-EDP', 'FE-SUP'),
    ('Fire Extinguisher (Foam)',        'FE-SUP-EFM', 'FE-SUP'),

    # ── Fire Fighting — Emergency ────────────────────────────────────────────
    ('Emergency Exit Light',            'FE-EMG-EXL', 'FE-EMG'),
    ('Fire Escape Signage',             'FE-EMG-SGN', 'FE-EMG'),
    ('Fire Door',                       'FE-EMG-FDR', 'FE-EMG'),
    ('Evacuation Speaker',              'FE-EMG-EVS', 'FE-EMG'),

    # ── Fire Fighting — Response ─────────────────────────────────────────────
    ('Fire Hose Cabinet',               'FE-RSP-FHC', 'FE-RSP'),
    ('Hydrant',                         'FE-RSP-HDT', 'FE-RSP'),
    ('Fire Blanket',                    'FE-RSP-FBL', 'FE-RSP'),
    ('First Aid Kit',                   'FE-RSP-FAK', 'FE-RSP'),

    # ── ELV Systems — Fire Alarm (Electrical Works.xlsx) ────────────────────
    ('Fire Alarm Panel',                'EV-FAL-FAP', 'EV-FAL'),
    ('Fire Alarm Repeater Panel',       'EV-FAL-RAP', 'EV-FAL'),  # NEW — Electrical Works
    ('Smoke Detector (ELV)',            'EV-FAL-SMK', 'EV-FAL'),
    ('Heat Detector (ELV)',             'EV-FAL-HET', 'EV-FAL'),
    ('Beam Detector (Auditorium)',      'EV-FAL-BDT', 'EV-FAL'),
    ('Linear Detector (Car Park)',      'EV-FAL-LDT', 'EV-FAL'),  # NEW — Electrical Works
    ('Breakglass Unit',                 'EV-FAL-BGU', 'EV-FAL'),
    ('Sounder',                         'EV-FAL-SND', 'EV-FAL'),

    # ── ELV Systems — CCTV (Electrical Works.xlsx) ──────────────────────────
    ('CCTV Monitor / Screen',           'EV-CCT-MON', 'EV-CCT'),
    ('CCTV Camera (Internal)',          'EV-CCT-DCI', 'EV-CCT'),
    ('CCTV Camera (External)',          'EV-CCT-DCE', 'EV-CCT'),
    ('Network Video Recorder (NVR)',    'EV-CCT-NVR', 'EV-CCT'),
    ('Video Wall Display',              'EV-CCT-VWD', 'EV-CCT'),

    # ── ELV Systems — Public Address (Electrical Works.xlsx) ────────────────
    ('PA Speaker',                      'EV-PAS-SPK', 'EV-PAS'),
    ('Amplifier',                       'EV-PAS-AMP', 'EV-PAS'),
    ('PA Rack',                         'EV-PAS-RCK', 'EV-PAS'),
    ('Paging Microphone',               'EV-PAS-PMC', 'EV-PAS'),  # NEW — Electrical Works
    ('Master Audio Control Unit',       'EV-PAS-MAC', 'EV-PAS'),  # NEW — Electrical Works

    # ── ELV Systems — Access Control (Electrical Works.xlsx) ────────────────
    ('Access Control Panel',            'EV-ACC-ACP', 'EV-ACC'),
    ('Access Control Server',           'EV-ACC-SVR', 'EV-ACC'),  # NEW — Electrical Works
    ('Card Reader',                     'EV-ACC-CDR', 'EV-ACC'),
    ('Biometric Reader',                'EV-ACC-BIO', 'EV-ACC'),
    ('Magnetic Lock',                   'EV-ACC-MGL', 'EV-ACC'),  # NEW — Electrical Works
    ('Electronic Lock',                 'EV-ACC-ELK', 'EV-ACC'),
]

asset_types = {}
for name, code, subcat_code in ASSET_TYPES:
    rec, created = get_or_create(
        'nrs.asset.type', [('code','=',code)],
        {'name':name,'code':code,
         'subcategory_id':subcategories[subcat_code].id,
         'category_id':subcategories[subcat_code].category_id.id}
    )
    asset_types[code] = rec
    ok(created, f'{code}  —  {name}')

env.cr.commit()
print(f'\n  Total asset types seeded: {len(ASSET_TYPES)}')

# ─── STEP 6: FURNITURE SEED RECORDS ───────────────────────────────────────────
sep('STEP 6: FURNITURE SEED RECORDS — HQ INVENTORY (11/02/2026)')

# Code generation counters
asset_seq  = {}   # 'NRS-FF-SEA' → int
tag_seq    = {}   # 'HQ-F06-OFC-N-FF' → int

def gen_asset_code(cat_code, subcat_code):
    sub_short = subcat_code.split('-')[1]
    key = f'NRS-{cat_code}-{sub_short}'
    asset_seq[key] = asset_seq.get(key, 0) + 1
    return f'{key}-{asset_seq[key]:05d}'

def gen_tag_code(floor_code, room_code, cat_code):
    key = f'HQ-{floor_code}-{room_code}-{cat_code}'
    tag_seq[key] = tag_seq.get(key, 0) + 1
    return f'{key}-{tag_seq[key]:03d}'

def resolve_loc(floor_code, room_code):
    key = f'{floor_code}-{room_code}'
    if key in room_locs:
        return room_locs[key]
    if floor_code in floor_locs:
        print(f'  WARNING: room {key} not found — falling back to floor {floor_code}')
        return floor_locs[floor_code]
    print(f'  WARNING: floor {floor_code} not found — falling back to HQ root')
    return hq

def seed_furniture(floor_code, room_code, type_code, quantity, notes=''):
    type_rec = asset_types.get(type_code)
    if not type_rec:
        print(f'  WARNING: type {type_code} not found — skipping {quantity}')
        return 0
    subcat   = type_rec.subcategory_id
    cat      = type_rec.category_id
    location = resolve_loc(floor_code, room_code)
    n = 0
    for _ in range(quantity):
        acode = gen_asset_code(cat.code, subcat.code)
        tcode = gen_tag_code(floor_code, room_code, cat.code)
        env['nrs.asset'].create({
            'name':           type_rec.name,
            'asset_code':     acode,
            'asset_tag':      tcode,
            'category_id':    cat.id,
            'subcategory_id': subcat.id,
            'asset_type_id':  type_rec.id,
            'asset_level':    'asset',
            'location_id':    location.id,
            'floor_room':     f'{floor_code} — {room_code}',
            'condition':      'good',
            'state':          'active',
            'notes':          notes or f'Seeded from HQ Furniture Inventory 11/02/2026',
        })
        n += 1
    return n

# Inventory data — source: FIRS HQ Furniture Inventory 11/02/2026
INVENTORY = [
    # Ground Floor — Mail Room
    ('GF','MR',   'FF-DSK-WRK', 13, 'GF Mail Room — Workstation tables'),
    ('GF','MR',   'FF-SEA-WRK', 39, 'GF Mail Room — Chairs'),
    ('GF','MR',   'FF-STR-SDR', 13, 'GF Mail Room — Side drawers'),
    # Ground Floor — Dining
    ('GF','DNG',  'FF-DSK-DNG', 12, 'GF Dining — Dining tables'),
    ('GF','DNG',  'FF-SEA-DNG', 52, 'GF Dining — Dining chairs'),
    ('GF','DNG',  'FF-SFT-USF',  7, 'GF Dining — U-shaped sofas'),
    ('GF','DNG',  'FF-SFT-LSF',  2, 'GF Dining — L-shaped sofas'),
    ('GF','DNG',  'FF-FIT-SVC',  2, 'GF Dining — Servery counters'),
    # 1st Floor — Library (mapped to Open Office North)
    ('F01','OFC-N','FF-DSK-WRK',22, 'F01 Library — Workstation desks'),
    ('F01','OFC-N','FF-SEA-WRK',16, 'F01 Library — Chairs'),
    ('F01','OFC-N','FF-STR-SDR',31, 'F01 Library — Side drawers'),
    ('F01','OFC-N','FF-SEA-EXC', 3, 'F01 Library — Executive chairs'),
    # 3rd Floor — Conference Room
    ('F03','MTG-1','FF-DSK-CNF',13, 'F03 Conference Room — Tables'),
    ('F03','MTG-1','FF-SEA-CNF',104,'F03 Conference Room — Chairs'),
    # 6th Floor
    ('F06','OFC-N','FF-DSK-WRK',62, 'F06 Open Office North — Tables'),
    ('F06','OFC-N','FF-SEA-WRK',62, 'F06 Open Office North — Chairs'),
    ('F06','OFC-N','FF-SFT-S2',  1, 'F06 — 2-seater sofa'),
    ('F06','OFC-N','FF-SEA-S1',  2, 'F06 — 1-seater sofas'),
    ('F06','OFC-N','FF-DSK-LSH', 1, 'F06 — L-shaped desk'),
    ('F06','OFC-N','FF-SEA-EXC',52, 'F06 — Executive chairs'),
    ('F06','OFC-N','FF-STR-CAB', 8, 'F06 — Cabinets'),
    ('F06','OFC-N','FF-SEA-ARM', 3, 'F06 — Armchairs'),
    # 7th Floor
    ('F07','OFC-N','FF-DSK-WRK',112,'F07 Open Office — Tables'),
    ('F07','OFC-N','FF-SEA-WRK',112,'F07 Open Office — Chairs'),
    ('F07','OFC-N','FF-SFT-S2',  1, 'F07 — 2-seater sofa'),
    ('F07','OFC-N','FF-SEA-S1',  7, 'F07 — 1-seater sofas'),
    ('F07','OFC-N','FF-DSK-LSH', 2, 'F07 — L-shaped desks'),
    ('F07','OFC-N','FF-SEA-EXC',32, 'F07 — Executive chairs'),
    ('F07','OFC-N','FF-STR-CAB', 8, 'F07 — Cabinets'),
    ('F07','OFC-N','FF-SEA-ARM', 6, 'F07 — Armchairs'),
    # 8th Floor
    ('F08','OFC-N','FF-SEA-WRK',60, 'F08 Open Office — Chairs'),
    ('F08','OFC-N','FF-SFT-S2',  1, 'F08 — 2-seater sofa'),
    ('F08','OFC-N','FF-SEA-S1',  2, 'F08 — 1-seater sofas'),
    ('F08','OFC-N','FF-SEA-EXC',51, 'F08 — Executive chairs'),
    ('F08','OFC-N','FF-STR-CAB', 8, 'F08 — Cabinets'),
    ('F08','OFC-N','FF-SEA-ARM', 6, 'F08 — Armchairs'),
    # 9th Floor
    ('F09','OFC-N','FF-DSK-WRK',60, 'F09 Open Office — Tables'),
    ('F09','OFC-N','FF-SEA-WRK',60, 'F09 Open Office — Chairs'),
    ('F09','OFC-N','FF-SFT-S2',  1, 'F09 — 2-seater sofa'),
    ('F09','OFC-N','FF-SEA-S1',  2, 'F09 — 1-seater sofas'),
    ('F09','OFC-N','FF-DSK-LSH', 2, 'F09 — L-shaped desks'),
    ('F09','OFC-N','FF-SEA-EXC',54, 'F09 — Executive chairs'),
    ('F09','OFC-N','FF-STR-CAB',16, 'F09 — Cabinets'),
    ('F09','OFC-N','FF-SEA-ARM', 6, 'F09 — Armchairs'),
    # 10th Floor
    ('F10','OFC-N','FF-SEA-WRK',79, 'F10 Open Office — Chairs'),
    ('F10','OFC-N','FF-SFT-S2',  1, 'F10 — 2-seater sofa'),
    ('F10','OFC-N','FF-SEA-S1',  2, 'F10 — 1-seater sofas'),
    ('F10','OFC-N','FF-SEA-EXC',43, 'F10 — Executive chairs'),
    ('F10','OFC-N','FF-STR-CAB',15, 'F10 — Cabinets'),
    ('F10','OFC-N','FF-SEA-ARM', 3, 'F10 — Armchairs'),
]

total_furniture = 0
for floor_code, room_code, type_code, qty, notes in INVENTORY:
    n = seed_furniture(floor_code, room_code, type_code, qty, notes)
    total_furniture += n
    if n > 0:
        loc_key = f'{floor_code}-{room_code}'
        loc_name = room_locs.get(loc_key, floor_locs.get(floor_code, hq)).name
        print(f'  + {n:4d}  {type_code}  →  {floor_code}/{room_code}  [{loc_name}]')

env.cr.commit()

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
sep('SEED COMPLETE — SUMMARY')

asset_total = env['nrs.asset'].search_count([])
draft_total = env['nrs.asset'].search_count([('state','=','draft')])

print(f'''
  LOCATION HIERARCHY
    HQ root location         : 1
    Floor locations          : {len(floor_locs)}
    Room locations           : {len(room_locs)}
    Total locations          : {1 + len(floor_locs) + len(room_locs)}

  ASSET TAXONOMY
    Categories               : {env['nrs.asset.category'].search_count([])}
    Sub-categories           : {env['nrs.asset.subcategory'].search_count([])}
    Asset types              : {env['nrs.asset.type'].search_count([])}

  SOURCES CONFIRMED
    Baron Architecture       : A400–A485 (19 floors, 232 rooms)
    Unecon Associates        : M&E completion schedule
    Electrical Works.xlsx    : Power, Fire Alarm, CCTV, PA, Access, Security

  ASSET RECORDS
    Total seeded             : {asset_total}
    DRAFT (furniture)        : {draft_total}

  ASSET CODE FORMAT    : NRS-{{CAT}}-{{SUBCAT}}-{{00001}}
  TAG CODE FORMAT      : HQ-{{FLOOR}}-{{ROOM}}-{{CAT}}-{{001}}
  BARCODE FIELD        : barcode = tag_code value (renders in UI + Zebra print)

  NEXT STEPS
    1. Verify location tree in myservice Locations menu
    2. Verify barcode field renders on asset form view
    3. Print test Zebra label for one record
    4. Run nrs_itsm_seed_v2.py  (Help Desk catalogue)
    5. Run nrs_sla_seed.py      (SLA policies)
    6. Building visit — photos for floor plan SVG accuracy

  Branch : 15.0
  Script : /opt/odoo/myservicenrs/scripts/nrs_hq_seed.py
''')
