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

# `active_test=False`, because the question here is EXISTENCE, not visibility.
# `generic.location` carries an `active` field (crnd-19/generic_location/models/
# generic_location.py:54) and Odoo's default search silently excludes archived
# records — so an archived HQ would be reported as missing and this seed would
# have gone looking for a building it had just been told about. That is the
# exact failure mark_test_fixtures.py hit on `jaizbankplc`: a plain search for
# an ARCHIVED credential returned empty, the loop never ran, and the script
# printed nothing whatsoever about it (docs/DECISIONS.md, 2026-09-15,
# handoff 25 B).
hq = Location.with_context(active_test=False).search(
    [('name', '=', 'NRS Headquarters'), ('parent_id', '=', False)], limit=1)
if not hq:
    # STOP. This used to print an ERROR line and carry straight on. `hq.id` on
    # an empty recordset is `False`, so the floor search in STEP 2 became
    # ('parent_id', '=', False) — which matches every unrelated TOP-LEVEL
    # location in the tenant. A miss here did not do nothing; it rewrote
    # whatever else sat at the root as floors of a building that is not there.
    #
    # Raised rather than `SystemExit`: scripts/bootstrap.py `exec`s this file
    # from run_seeds() inside `try/except Exception`, where one seed failing is
    # logged with its label and the rest of provisioning continues. SystemExit
    # is a BaseException, would escape that handler and both of main()'s, and
    # would kill the whole bootstrap without even rolling back — a louder
    # failure than the one being fixed, in the wrong place.
    raise RuntimeError(
        "nrs_hq_seed_v4: no generic.location named 'NRS Headquarters' with "
        "parent_id = False in database %r. Searched with active_test=False, "
        "so an archived one would have counted. This seed only ADDS metadata "
        "to the hierarchy scripts/nrs_hq_seed.py (v3) creates — run that first."
        % env.cr.dbname)
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
#: Floors named in FLOOR_META that no location under HQ answers to. Collected
#: rather than only printed, so the summary can state the run's own shortfall
#: instead of a register-wide total that hides it.
floors_not_found = []
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
        floors_not_found.append((code, label))
        print(f'  SKIP: floor "{label}" ({code}) not found under HQ')

env.cr.commit()
print(f'\n  Floors updated: {floor_count} of {len(FLOOR_META)} expected'
      f'  ({len(floors_not_found)} not found)')

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

#: Every room code FLOOR_ROOMS names, so "tagged N" can be read against what
#: was asked for rather than against nothing.
rooms_expected = sum(len(codes) for _, codes in FLOOR_ROOMS)

room_count = 0
#: (floor_code, room_code) for every room this run asked for and could not
#: find. See the else-branch below — these used to vanish entirely.
rooms_not_matched = []
#: Floors STEP 3 could not work on because STEP 2 never found them.
floors_skipped_in_rooms = []
#: Locations that exist under the floors this run did reach, matched or not.
#: Printed as the denominator: "tagged M of N present" is a fact about this
#: run, where a bare M is a number with nothing to be wrong against.
rooms_seen_under_floors = 0

for floor_code, room_codes in FLOOR_ROOMS:
    floor_rec = floor_recs.get(floor_code)
    if not floor_rec:
        floors_skipped_in_rooms.append(floor_code)
        print(f'  SKIP: floor {floor_code} not found — its '
              f'{len(room_codes)} rooms cannot be tagged')
        continue
    # Get all rooms under this floor
    rooms = Location.search([('parent_id', '=', floor_rec.id)])
    rooms_seen_under_floors += len(rooms)
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
            # There is NO fallback, and there never was one. What used to sit
            # here was the comment "Try matching by room name directly under
            # this floor / This is a fallback" over a bare `pass` — a comment
            # describing code nobody wrote. An unmatched room was therefore
            # neither tagged, counted nor mentioned anywhere, while the summary
            # went on printing a number that read as completeness.
            #
            # A room reaches this branch when no location under this floor has
            # a `description` whose third ' / ' segment is this code: either v3
            # never created it, or its description is shaped differently. Both
            # are worth a person seeing. Neither is guessed at here — inventing
            # a name-based match now would make a wrong tagging look confident,
            # which is worse than the silence it replaces.
            rooms_not_matched.append((floor_code, room_code))

env.cr.commit()
print(f'\n  Rooms updated: {room_count} of {rooms_expected} expected'
      f'  ({rooms_seen_under_floors} locations seen under the floors reached)')
if rooms_not_matched:
    print(f'  Rooms NOT matched: {len(rooms_not_matched)}')
    for floor_code, room_code in rooms_not_matched:
        print(f'    - {floor_code} / {room_code}')

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

# WHAT THIS RUN DID, and separately what the register holds.
#
# These headings used to read "Buildings tagged / Floors tagged / Rooms
# tagged" over four Location.search_count(...) calls taken across the whole
# tenant. They measured the WORLD, not the RUN: a pass that matched nothing
# still printed `1 / 19 / 232` — the previous run's work, read back as though
# it were this one's, under a heading that says "tagged". The global figures
# are kept because "the register now holds N floors" is genuinely useful
# beside "this run touched M of them", but they are now labelled as what they
# are and they are no longer the first thing the reader sees.
building_count = Location.search_count([('location_type', '=', 'building')])
floor_total = Location.search_count([('location_type', '=', 'floor')])
room_total = Location.search_count([('location_type', '=', 'room')])
assets_with_building = Asset.search_count([('building_id', '!=', False)])

# Built outside the f-string deliberately: an expression spanning two lines
# inside an f-string is a 3.12+ feature, and this file is run by whatever
# Python the Odoo image ships.
missing_floors = ' — ' + ', '.join(c for c, _ in floors_not_found) if floors_not_found else ''
skipped_floors = ' — ' + ', '.join(floors_skipped_in_rooms) if floors_skipped_in_rooms else ''

print(f'''
  THIS RUN
    HQ building tagged        : 1 ({hq.name}, id={hq.id})
    Floors tagged             : {floor_count} of {len(FLOOR_META)} expected
    Floors not found under HQ : {len(floors_not_found)}{missing_floors}
    Rooms tagged              : {room_count} of {rooms_expected} expected
    Rooms not matched         : {len(rooms_not_matched)}
    Floors skipped in STEP 3  : {len(floors_skipped_in_rooms)}{skipped_floors}
    Locations seen under those floors : {rooms_seen_under_floors}
    Assets backfilled         : {updated} of {len(assets)} that have a location

  WHOLE REGISTER — context, NOT this run's work
    Locations typed building  : {building_count}
    Locations typed floor     : {floor_total}
    Locations typed room      : {room_total}
    Assets with building_id   : {assets_with_building}

  HQ ADDRESS
    Street  : Kui Mohammed Avenue
    City    : Abuja, FCT
    Country : Nigeria
    Lat/Lon : 9.0579 N, 7.4951 E

  Branch : 15.0
  Script : /opt/odoo/myservicenrs/scripts/nrs_hq_seed_v4.py
''')
