#!/usr/bin/env python3
"""
nrs_hq_seed_v4.py  —  Version 4.0
═══════════════════════════════════════════════════════════════════════════════
NRS myservice.com.ng — Location Metadata Seed
Populates location_type, zone_code, floor_number, address, lat/lon
on existing NRS HQ location hierarchy created by v3.

Run AFTER upgrading generic_location and myservice_asset_register modules.

Run via Odoo shell (branch: 15.0):
  sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo-bin shell \
    -c /etc/odoo/odoo.conf -d myservice --no-http \
    < /opt/odoo/myservicenrs/scripts/nrs_hq_seed_v4.py
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
_logger = logging.getLogger(__name__)

Location = env['generic.location']
Asset = env['nrs.asset']

def sep(title):
    print('\n' + '=' * 70)
    print(f'  {title}')
    print('=' * 70)

# ─── STEP 1: TAG THE HQ ROOT AS A BUILDING ───────────────────────────────────
sep('STEP 1: SET BUILDING METADATA ON NRS HEADQUARTERS')

hq = Location.search([('name', '=', 'NRS Headquarters'), ('parent_id', '=', False)], limit=1)
if not hq:
    print('  ERROR: NRS Headquarters root location not found. Run v3 seed first.')
else:
    hq.write({
        'location_type': 'building',
        'zone_code': 'HQ',
        'floor_number': 0,
        '_street': 'Kui Mohammed Avenue',
        '_street2': 'Central Business District',
        '_city': 'Abuja',
        '_country_id': env.ref('base.ng').id,
        'street_use_parent': False,
        'street2_use_parent': False,
        'city_use_parent': False,
        'country_id_use_parent': False,
        'latitude': 9.0579,
        'longitude': 7.4951,
    })
    # Try to set state (FCT)
    fct = env['res.country.state'].search([
        ('country_id', '=', env.ref('base.ng').id),
        ('code', '=', 'FC'),
    ], limit=1)
    if not fct:
        fct = env['res.country.state'].search([
            ('country_id', '=', env.ref('base.ng').id),
            ('name', 'ilike', 'Federal Capital'),
        ], limit=1)
    if fct:
        hq.write({
            '_state_id': fct.id,
            'state_id_use_parent': False,
        })
    print(f'  + NRS Headquarters: building, zone_code=HQ, lat=9.0579, lon=7.4951')

env.cr.commit()

# ─── STEP 2: TAG ALL FLOORS ──────────────────────────────────────────────────
sep('STEP 2: SET FLOOR METADATA')

# Map floor name/code to floor_number
FLOOR_META = {
    'BF':  ('Basement Floor',  -1),
    'GF':  ('Ground Floor',     0),
    'F01': ('1st Floor',        1),
    'F02': ('2nd Floor',        2),
    'F03': ('3rd Floor',        3),
    'F04': ('4th Floor',        4),
    'F05': ('5th Floor',        5),
    'F06': ('6th Floor',        6),
    'F07': ('7th Floor',        7),
    'F08': ('8th Floor',        8),
    'F09': ('9th Floor',        9),
    'F10': ('10th Floor',      10),
    'F11': ('11th Floor',      11),
    'F12': ('12th Floor',      12),
    'F13': ('13th Floor',      13),
    'F14': ('14th Floor',      14),
    'F15': ('15th Floor',      15),
    'F16': ('16th Floor',      16),
    'RF':  ('Roof / Plant Room', 99),
}

floor_count = 0
floor_recs = {}
for code, (label, fnum) in FLOOR_META.items():
    floor = Location.search([
        ('name', '=', label),
        ('parent_id', '=', hq.id),
    ], limit=1)
    if floor:
        floor.write({
            'location_type': 'floor',
            'zone_code': code,
            'floor_number': fnum,
            'street_use_parent': True,
            'street2_use_parent': True,
            'city_use_parent': True,
            'state_id_use_parent': True,
            'country_id_use_parent': True,
            'zip_use_parent': True,
        })
        floor_recs[code] = floor
        floor_count += 1
        print(f'  + {code}  {label:25s}  floor_number={fnum}')
    else:
        print(f'  SKIP: floor "{label}" not found under HQ')

env.cr.commit()
print(f'\n  Floors updated: {floor_count}')

# ─── STEP 3: TAG ALL ROOMS ───────────────────────────────────────────────────
sep('STEP 3: SET ROOM METADATA')

# Room code mapping from v3 FLOOR_ROOMS structure
FLOOR_ROOMS = [
    ('BF', [
        'GYM','SLP','DRL','RCP','LBY-N','LBY-S','OFC-CI','SRV','SCR',
        'SCM','BMS','AHU-1','AHU-2','ELR','MCH-1','MCH-2','CHM','STR',
        'ECP','WCM','WCF','STR-B','LFT',
    ]),
    ('GF', [
        'RCP','LBY','LFT','WTA','LED','PRJ','MPR','PRY','CNF',
        'WCM','WCF','STR','STR-B','MR','DNG',
    ]),
    ('F01', ['OFC-N','OFC-S','MTG-1','MTG-2','EXO-1','EXO-2','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F02', ['OFC-N','OFC-S','MTG-1','MTG-2','EXO-1','EXO-2','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F03', ['OFC-N','OFC-S','MTG-1','MTG-2','EXO-1','SCM','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F04', ['OFC-N','OFC-S','MTG-1','MTG-2','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F05', ['OFC-N','OFC-S','FOP','SUP','MTG-1','MTG-2','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F06', ['OFC-N','OFC-S','MTG-1','MTG-2','EXO-1','EXO-2','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F07', ['TAX','CEG','PDD','OFC-N','OFC-S','MTG-1','EXO-1','DNG','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F08', ['OFC-N','OFC-S','BRD','MTG-1','MTG-2','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F09', ['OFC-N','OFC-S','PRB','MTG-1','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F10', ['OFC-N','OFC-S','APR','MTG-1','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F11', ['OFC-N','OFC-S','MTG-1','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F12', ['OFC-N','OFC-S','SSB','MTG-1','EXO-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F13', ['OFC-N','OFC-S','EXO-1','EXO-2','EXO-3','MTG-1','DNG','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F14', ['OFC-N','OFC-S','SCS','BLT','EXO-1','EXO-2','MTG-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F15', ['BRD','EXO-1','EXO-2','EXS','VIP-D','MTG-1','LFT','WCM','WCF','STR','STR-B','PNT']),
    ('F16', ['CHR','BRD','EXS','VIP-L','VIP-D','RCP','EXO-1','EXO-2','EXO-3','MTG-1','LFT','WCM','WCF','STR-B']),
    ('RF',  ['PR','OVH','EX']),
]

room_count = 0
for floor_code, room_codes in FLOOR_ROOMS:
    floor_rec = floor_recs.get(floor_code)
    if not floor_rec:
        print(f'  SKIP: floor {floor_code} not found')
        continue
    # Get all rooms under this floor
    rooms = Location.search([('parent_id', '=', floor_rec.id)])
    # Build a name->room mapping for matching
    # The v3 seed used room names, so we match by position/description
    room_by_desc = {}
    for room in rooms:
        # Extract room code from description field "NRS HQ / F01 / OFC-N"
        if room.description:
            parts = room.description.split(' / ')
            if len(parts) >= 3:
                room_by_desc[parts[2].strip()] = room

    for room_code in room_codes:
        room_rec = room_by_desc.get(room_code)
        if room_rec:
            room_rec.write({
                'location_type': 'room',
                'zone_code': room_code,
                'street_use_parent': True,
                'street2_use_parent': True,
                'city_use_parent': True,
                'state_id_use_parent': True,
                'country_id_use_parent': True,
                'zip_use_parent': True,
            })
            room_count += 1
        else:
            # Try matching by room name directly under this floor
            # This is a fallback
            pass

env.cr.commit()
print(f'\n  Rooms updated: {room_count}')

# ─── STEP 4: BACKFILL building_id, floor_id, room_id ON EXISTING ASSETS ──────
sep('STEP 4: BACKFILL ASSET LOCATION HIERARCHY')

assets = Asset.search([('location_id', '!=', False)])
updated = 0
for asset in assets:
    loc = asset.location_id
    vals = {}

    # Determine building, floor, room from current location_id
    if loc.location_type == 'room':
        vals['room_id'] = loc.id
        # Parent should be the floor
        if loc.parent_id and loc.parent_id.location_type == 'floor':
            vals['floor_id'] = loc.parent_id.id
            # Grandparent should be building
            if loc.parent_id.parent_id and loc.parent_id.parent_id.location_type == 'building':
                vals['building_id'] = loc.parent_id.parent_id.id
    elif loc.location_type == 'floor':
        vals['floor_id'] = loc.id
        if loc.parent_id and loc.parent_id.location_type == 'building':
            vals['building_id'] = loc.parent_id.id
    elif loc.location_type == 'building':
        vals['building_id'] = loc.id

    # If no location_type set yet, try building_id from computed field
    if not vals and loc.building_id:
        vals['building_id'] = loc.building_id.id

    if vals:
        asset.write(vals)
        updated += 1

env.cr.commit()
print(f'  Assets backfilled: {updated} / {len(assets)}')

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
sep('SEED V4 COMPLETE — SUMMARY')

building_count = Location.search_count([('location_type', '=', 'building')])
floor_total = Location.search_count([('location_type', '=', 'floor')])
room_total = Location.search_count([('location_type', '=', 'room')])
assets_with_building = Asset.search_count([('building_id', '!=', False)])

print(f'''
  LOCATION METADATA
    Buildings tagged          : {building_count}
    Floors tagged             : {floor_total}
    Rooms tagged              : {room_total}

  ASSET BACKFILL
    Assets with building_id   : {assets_with_building}

  HQ ADDRESS
    Street  : Kui Mohammed Avenue
    City    : Abuja, FCT
    Country : Nigeria
    Lat/Lon : 9.0579 N, 7.4951 E

  Branch : 15.0
  Script : /opt/odoo/myservicenrs/scripts/nrs_hq_seed_v4.py
''')
