#!/usr/bin/env python3
"""
load_offices_v2.py — FIRS Offices Nationwide
=============================================
415 FIRS offices loaded into generic.location

Hierarchy (4 levels):
  Geo Zone → State → Coordination Group → Office

Location Types created:
  HQ / Coordination / MSTO / GBTO / Satellite / Department / Other

Source: 2025 LIST OF FIRS OFFICES NATIONWIDE
Run:
    sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \\
        -c /etc/odoo/odoo.conf -d myservice --no-http < load_offices_v2.py
"""

import traceback

print()
print("=" * 70)
print("  FIRS OFFICES — LOCATION SEED v2")
print("  4-level hierarchy | 415 offices | 6 geo zones")
print("=" * 70)

# ── STEP 0: Probe model & get Nigeria country id ──────────────────────
print("\n  Probing generic.location model...")
# Find the related model for type_id
type_field = env['generic.location']._fields.get('type_id')
type_model = type_field.comodel_name if type_field else None
print(f"  type_id → model: {type_model}")

nigeria = env['res.country'].search([('name', 'ilike', 'Nigeria')], limit=1)
NIGERIA_ID = nigeria.id if nigeria else None
print(f"  Nigeria country id: {NIGERIA_ID}")

# ── STEP 1: Create location types ─────────────────────────────────────
print("\n  Creating location types...")

LOCATION_TYPES = [
    ('HQ',           'FIRS Headquarters'),
    ('Coordination', 'State/Zone Coordination Office'),
    ('MSTO',         'Medium Scale Taxpayers Office'),
    ('GBTO',         'Government Business Tax Office'),
    ('Satellite',    'Satellite Tax Office'),
    ('Department',   'FIRS Department / Unit'),
    ('LTO',          'Large Taxpayers Office'),
    ('MTO',          'Medium Tax Office'),
    ('Training',     'Training School'),
    ('Other',        'Other Office'),
]

type_map = {}
for code, name in LOCATION_TYPES:
    try:
        existing = env[type_model].search([('name', '=', name)], limit=1) if type_model else None
        if not existing:
            rec = env[type_model].create({'name': name}) if type_model else None
            type_map[code] = rec.id
            print(f"  + Type: {name}")
        else:
            type_map[code] = existing.id
            print(f"  o Type: {name}")
    except Exception as e:
        print(f"  ! Type {name} skipped — {e}")
        type_map[code] = None

env.cr.commit()


def get_type_id(office_name):
    """Infer location type from office name."""
    n = office_name.upper()
    if any(x in n for x in ['HEADQUARTERS', 'EXECUTIVE CHAIRMAN', 'HQ']):
        return type_map.get('HQ')
    if any(x in n for x in ['COORDINATOR', 'COORDINATION', 'STATE ADMIN', 'STATE ADMINISTRATOR']):
        return type_map.get('Coordination')
    if 'MSTO' in n or 'SMTO' in n:
        return type_map.get('MSTO')
    if 'GBTO' in n:
        return type_map.get('GBTO')
    if 'SATELLITE' in n:
        return type_map.get('Satellite')
    if 'LTO' in n:
        return type_map.get('LTO')
    if 'MTO' in n:
        return type_map.get('MTO')
    if 'TRAINING' in n or 'SCHOOL' in n:
        return type_map.get('Training')
    if any(x in n for x in ['DEPARTMENT', 'DEPT', 'UNIT', 'GROUP', 'DIVISION', 'OFFICE OF',
                              'AUDIT', 'ENFORCEMENT', 'ACCOUNTING', 'SECRETARIAT', 'REGISTRY',
                              'RESEARCH', 'PROCUREMENT', 'MANAGEMENT', 'BOARD', 'LIAISON',
                              'INVESTIGATION', 'POLICY', 'SERVICOM', 'COOPERATIVE', 'PMO',
                              'EDRMS', 'WATAF', 'SCDMEO', 'DMEO', 'MSTA', 'MSTD',
                              'BA & ESD', 'CD/', 'CALL CENTRE', 'TREASURY', 'STORE']):
        return type_map.get('Department')
    return type_map.get('Other')


# ── STEP 2: Geo Zones ─────────────────────────────────────────────────
print("\n  Creating geo zones...")

GEO_ZONES = [
    'North Central', 'North East', 'North West',
    'South East', 'South South', 'South West',
]

zone_map = {}
for zone in GEO_ZONES:
    existing = env['generic.location'].search([('name', '=', zone), ('parent_id', '=', False)], limit=1)
    if not existing:
        rec = env['generic.location'].create({'name': zone})
        zone_map[zone] = rec.id
        print(f"  + Zone: {zone}")
    else:
        zone_map[zone] = existing.id
        print(f"  o Zone: {zone}")

env.cr.commit()


# ── STEP 3: States ────────────────────────────────────────────────────
print("\n  Creating states...")

STATE_ZONE = {
    'FCT':          'North Central',
    'Kogi':         'North Central',
    'Benue':        'North Central',
    'Nasarawa':     'North Central',
    'Niger':        'North Central',
    'Plateau':      'North Central',
    'Kwara':        'North Central',
    'Adamawa':      'North East',
    'Bauchi':       'North East',
    'Borno':        'North East',
    'Gombe':        'North East',
    'Taraba':       'North East',
    'Yobe':         'North East',
    'Jigawa':       'North West',
    'Kaduna':       'North West',
    'Kano':         'North West',
    'Katsina':      'North West',
    'Kebbi':        'North West',
    'Sokoto':       'North West',
    'Zamfara':      'North West',
    'Abia':         'South East',
    'Anambra':      'South East',
    'Ebonyi':       'South East',
    'Enugu':        'South East',
    'Imo':          'South East',
    'Akwa Ibom':    'South South',
    'Bayelsa':      'South South',
    'Cross River':  'South South',
    'Delta':        'South South',
    'Edo':          'South South',
    'Rivers':       'South South',
    'Ekiti':        'South West',
    'Lagos':        'South West',
    'Ogun':         'South West',
    'Ondo':         'South West',
    'Osun':         'South West',
    'Oyo':          'South West',
}

state_map = {}
for state, geo_zone in sorted(STATE_ZONE.items()):
    parent_id = zone_map[geo_zone]
    existing = env['generic.location'].search([('name', '=', state), ('parent_id', '=', parent_id)], limit=1)
    if not existing:
        rec = env['generic.location'].create({'name': state, 'parent_id': parent_id})
        state_map[state] = rec.id
        print(f"  + State: {state}")
    else:
        state_map[state] = existing.id
        print(f"  o State: {state}")

env.cr.commit()


# ── STEP 4: Coordination Groups ───────────────────────────────────────
print("\n  Creating coordination groups...")

# (name, primary_state, address, other_states)
COORD_GROUPS = [
    ('Kwara, Ekiti & Ondo Coordination',    'Ondo',       'Alfred Rewane Road, GRA Akure',                                    ['Kwara', 'Ekiti']),
    ('Ogun, Oyo & Osun Coordination',        'Oyo',        'No 43 Molete-Challenge Road, Opposite Genesis Hotel, Ibadan',      ['Ogun', 'Osun']),
    ('Jigawa, Kano & Katsina Coordination',  'Kano',       'No.55 Sani Marshal Road, Kano',                                    ['Jigawa', 'Katsina']),
    ('Sokoto, Kebbi & Zamfara Coordination', 'Sokoto',     'No.2 Alhassan Avenue along Gusau Road, Sokoto',                    ['Kebbi', 'Zamfara']),
    ('Benue, Kaduna & Plateau Coordination', 'Kaduna',     'No.2A Buba Yero Road, Off Dendo Road, Kaduna State',               ['Benue', 'Plateau']),
    ('FIRS Headquarters',                    'FCT',        'Revenue House, 15 Sokode Crescent, Wuse Zone 5, Abuja',            []),
    ('FCT Abuja Coordination',               'FCT',        'Plot 251, Katampe Extension, Abuja',                               []),
    ('Kogi, Nasarawa & Niger Coordination',  'Kogi',       'A41 Mohammed Muazu Road, Adjacent NACB Building, Minna',           ['Nasarawa', 'Niger']),
    ('Borno, Bauchi & Yobe Coordination',    'Borno',      'No.32 & 33 Yakubun Bauchi Road, Opposite State Secretariat',       ['Bauchi', 'Yobe']),
    ('Gombe, Taraba & Adamawa Coordination', 'Gombe',      'Off Bauchi Road, Adjacent INEC Office, Gombe',                     ['Taraba', 'Adamawa']),
    ('Akwa Ibom, Bayelsa & C/River Coord',  'Akwa Ibom',  'Plot 5 Along Udo Udoma Avenue, Opposite Ibom Mall, Uyo',           ['Bayelsa', 'Cross River']),
    ('Rivers, Edo & Delta Coordination',     'Rivers',     'Plot 465A, Trans-Amadi Industrial Layout, Port Harcourt',          ['Edo', 'Delta']),
    ('Ebonyi, Enugu & Abia Coordination',    'Enugu',      'No. 4 Nwodo Close, GRA Enugu, Enugu State',                       ['Ebonyi', 'Abia']),
    ('Imo & Anambra Coordination',           'Imo',        'No 68 World Bank Area A, New Owerri, Imo State',                   ['Anambra']),
    ('Lagos Mainland East Coordination',     'Lagos',      '2b Lateef Jakande Road, Agidingbi, Lagos',                         []),
    ('Lagos Mainland West Coordination',     'Lagos',      'No 33 Imam Dauda Street, Off Eric Moore Road, Surulere, Lagos',    []),
    ('Lagos Island Coordination',            'Lagos',      '17b Awolowo Road, Ikoyi, Lagos',                                   []),
]

coord_map = {}  # name -> id
coord_type_id = type_map.get('Coordination')

for cname, primary_state, address, other_states in COORD_GROUPS:
    parent_id = state_map.get(primary_state)
    if not parent_id:
        print(f"  ! No state found for {cname}")
        continue
    existing = env['generic.location'].search([('name', '=', cname), ('parent_id', '=', parent_id)], limit=1)
    if not existing:
        vals = {'name': cname, 'parent_id': parent_id, 'street': address}
        if NIGERIA_ID:
            vals['country_id'] = NIGERIA_ID
        if coord_type_id:
            try: vals['type_id'] = coord_type_id
            except: pass
        rec = env['generic.location'].create(vals)
        coord_map[cname] = (rec.id, address)
        print(f"  + Coord: {cname}")
    else:
        coord_map[cname] = (existing.id, address)
        print(f"  o Coord: {cname}")

env.cr.commit()


# ── STEP 5: All 415 Offices ───────────────────────────────────────────
print("\n  Loading offices...")

# Format: (num, name, address, ownership, coord_group)
OFFICES = [
    # ── Kwara, Ekiti & Ondo ───────────────────────────────────────────
    (1,   'Ilorin MSTO',                          'No 1 Obbo Road, Off Unity Road, Ilorin',                                       'Owned',  'Kwara, Ekiti & Ondo Coordination'),
    (2,   'Kwara GBTO',                           '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (3,   'Ilorin Stamp Duty',                    '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (4,   'MSTA, Kwara',                          '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (5,   'Ado-Ekiti MSTO',                       'Secretariat Road, Opposite CBN, Ado-Ekiti',                                     'Owned',  'Kwara, Ekiti & Ondo Coordination'),
    (6,   'Ekiti GBTO',                           '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (7,   'MSTA, Ekiti',                          '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (8,   'Kwara, Ekiti & Ondo State Coordinator Office', 'Alfred Rewane Road, GRA Akure',                                         'Owned',  'Kwara, Ekiti & Ondo Coordination'),
    (9,   'Akure MSTO',                           '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (10,  'Akure SCDMEO',                         '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (11,  'Ondo GBTO',                            '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (12,  'MSTA, Ondo',                           '',                                                                               '',       'Kwara, Ekiti & Ondo Coordination'),
    (13,  'Owo MSTO',                             'No 1 Idowu Salame Street, Owo GRA, Ondo State',                                 'Rented', 'Kwara, Ekiti & Ondo Coordination'),
    (14,  'Ore MSTO',                             'No 63 Okitipupa Road, Ore',                                                     'Rented', 'Kwara, Ekiti & Ondo Coordination'),
    (15,  'Offa Satellite Tax Office',            'Suite 3, Ijakadi Shopping Mall, Beside Ibolo Microfinance Bank, Olofa Way, Offa, Kwara State', 'Rented', 'Kwara, Ekiti & Ondo Coordination'),
    # ── Ogun, Oyo & Osun ─────────────────────────────────────────────
    (16,  'Abeokuta MSTO',                        "Opposite Governor's Office, Along IBB Boulevard Oke Mosan, Abeokuta",           'Owned',  'Ogun, Oyo & Osun Coordination'),
    (17,  'Ogun GBTO',                            '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (18,  'MSTA, Ogun',                           '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (19,  'Ota MSTO',                             'Km 37, Lagos-Abeokuta Express Way',                                             'Rented', 'Ogun, Oyo & Osun Coordination'),
    (20,  'MSTA, Ota',                            '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (21,  'Sagamu MSTO',                          'No 4, Obafemi Awolowo Avenue, Before Red Gate, GRA Quarters, Sagamu, Ogun State', 'Rented', 'Ogun, Oyo & Osun Coordination'),
    (22,  "State Coordinator's Office (Ogun, Oyo & Osun)", 'No 43 Molete-Challenge Road, Opposite Genesis Hotel, Police Post, Ibadan', 'Owned', 'Ogun, Oyo & Osun Coordination'),
    (23,  'Ibadan SCDMEO',                        'No.1 Bishop Akinyele Road, Opposite Union Bank, Agodi GRA, Ibadan',             'Rented', 'Ogun, Oyo & Osun Coordination'),
    (24,  'MTO Ibadan',                           '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (25,  'Iwo Road MSTO',                        '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (26,  'Training School',                      '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (27,  'Large Tax Audit, Ibadan',              '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (28,  'MSTA, Oyo II',                         '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (29,  'Medium Tax Audit, Ibadan',             '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (30,  'South West VAT Coordination',          '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (31,  'Oyo MSTO',                             'Beside Zenith Bank, Akunlemu Area, Ogbomosho Road',                             'Owned',  'Ogun, Oyo & Osun Coordination'),
    (32,  'LTO Ibadan',                           'Plot 17, I.C.C Liberty Stadium Layout, Ring Road, Ibadan, Oyo State',           'Rented', 'Ogun, Oyo & Osun Coordination'),
    (33,  'Oyo GBTO',                             '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (34,  'Adeoyo MSTO',                          'No 45, New Adeoyo Hospital Road, Ibadan',                                       'Owned',  'Ogun, Oyo & Osun Coordination'),
    (35,  'MSTA, Adeoyo',                         '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (36,  'MSTA, Oyo',                            '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (37,  'Oshogbo MSTO',                         'Behind INEC Office, KM 4 Gbongan-Oshogbo Road',                                 'Owned',  'Ogun, Oyo & Osun Coordination'),
    (38,  'Osun GBTO',                            '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (39,  'Osogbo MSTA',                          '',                                                                               '',       'Ogun, Oyo & Osun Coordination'),
    (40,  'Ijebu Ode Satellite Tax Office',       'No.1 Jogbo Street, Ibadan Road, Ijebu Ode, Ogun State',                        'Rented', 'Ogun, Oyo & Osun Coordination'),
    (41,  'Ilesha Satellite Tax Office',          'No.2 Kajola Lane, Abiola Avenue, Beside Drjay Hotel, Ilesa, Osun State',        'Rented', 'Ogun, Oyo & Osun Coordination'),
    (42,  'Ogbomosho Satellite Tax Office',       "Alhaji Muri's House, Beside Kara Sabo, Masidi Idi-Araba, Ogbomosho, Oyo State",'Rented', 'Ogun, Oyo & Osun Coordination'),
    (43,  'Saki Satellite Tax Office',            'Samson Koleoso House, Oje-Owode Road, Ajegunle, Saki, Oyo State',               'Rented', 'Ogun, Oyo & Osun Coordination'),
    (44,  'Agbara Satellite Tax Office',          '914 Road, Area 8 Off Diya Gate, OPIC Estate, Agbara, Ogun State',               'Rented', 'Ogun, Oyo & Osun Coordination'),
    (45,  'Ile-Ife Satellite Tax Office',         '28 Ibadan-Ife Road, Mayfair, Ile Ife, Osun State',                              'Rented', 'Ogun, Oyo & Osun Coordination'),
    # ── Jigawa, Kano & Katsina ────────────────────────────────────────
    (46,  'ECFIRS Office Kano',                   'No.55 Sani Marshal Road, Kano (formerly Club Road)',                            'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (47,  "State Administrator's Office (Kano, Jigawa & Katsina)", '', '',                                                                   'Jigawa, Kano & Katsina Coordination'),
    (48,  'MTO Kano',                             '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (49,  'Kano SCDMEO',                          '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (50,  'GBTO Kano',                            '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (51,  'Large Tax Audit, Kano',                '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (52,  'NPF Enforcement Unit, Kano',           '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (53,  'Kano I MSTO (Club Road)',              '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (54,  'Medium Tax Audit, Kano',               '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (55,  'LTO Kano',                             'No.14 Guda Abdullahi Street, Farm House, Kano',                                 'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (56,  'MSTA, Kano II',                        'No.1 Zaria Road, Kano',                                                         'Rented', 'Jigawa, Kano & Katsina Coordination'),
    (57,  'Kano MSTO 3',                          '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (58,  'Kano II MSTO',                         'No.6, Zaria Road, Gyadi Gyadi, Kano',                                           'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (59,  'MSTA, Kano I',                         '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (60,  'Dutse MSTO',                           'No.52 Opposite Saminu Turaki Tower, Kiyawa Road, Dutse',                        'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (61,  'Jigawa GBTO',                          '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (62,  'MSTA, Jigawa',                         '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (63,  'Katsina MSTO',                         'Plot 3 & 5 Commercial Layout, Gidan Dawa Off IBB Way, Katsina',                 'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (64,  'Katsina GBTO',                         '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (65,  'MSTA, Katsina',                        '',                                                                               '',       'Jigawa, Kano & Katsina Coordination'),
    (66,  'Training School Centre, Katsina',      'Opposite Muhammadu Dikko Stadium, Mani Road, Katsina',                          'Owned',  'Jigawa, Kano & Katsina Coordination'),
    (67,  'Funtua MSTO',                          'No. 157 Sokoto Road, Funtua, Katsina State',                                    'Rented', 'Jigawa, Kano & Katsina Coordination'),
    # ── Sokoto, Kebbi & Zamfara ───────────────────────────────────────
    (68,  'State Administration Office, Zamfara', 'Olusegun Obasanjo Drive, Opp J B Secretariat, Gusau, Zamfara State',            'Owned',  'Sokoto, Kebbi & Zamfara Coordination'),
    (69,  'Gusau MSTO',                           '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (70,  'Zamfara GBTO',                         '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (71,  'MSTA, Zamfara',                        '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (72,  'Sokoto MSTO',                          'No.2 Alhassan Avenue along Gusau Road, Sokoto',                                  'Rented', 'Sokoto, Kebbi & Zamfara Coordination'),
    (73,  'Sokoto GBTO',                          '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (74,  'MSTA, Sokoto',                         '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (75,  'Sokoto SCDMEO',                        '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (76,  'Birnin Kebbi MSTO',                    'No.5 Olusegun Obasanjo Avenue, Opp Muhammad Adamu Aliero Memorial Poly, Birnin Kebbi', 'Owned', 'Sokoto, Kebbi & Zamfara Coordination'),
    (77,  'Kebbi GBTO',                           '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (78,  'MSTA, Kebbi',                          '',                                                                               '',       'Sokoto, Kebbi & Zamfara Coordination'),
    (79,  'Talata Mafara Satellite Tax Office',   'Jangebe Plaza, Beside Police Divisional Force, Along Gusau-Sokoto Road, Talata Mafara', 'Rented', 'Sokoto, Kebbi & Zamfara Coordination'),
    # ── Benue, Kaduna & Plateau ───────────────────────────────────────
    (80,  'State Administrators Office (Benue, Kaduna & Plateau)', 'No.2A Buba Yero Road, Off Dendo Road, Kaduna State', 'Owned', 'Benue, Kaduna & Plateau Coordination'),
    (81,  'Kaduna GBTO',                          '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (82,  'Medium Tax Audit, Kaduna',             '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (83,  'Kaduna SCDMEO',                        '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (84,  'MSTA, Kaduna',                         '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (85,  'Kaduna III MSTO',                      'No 11B Ali Akilu Road, Kaduna State',                                           'Rented', 'Benue, Kaduna & Plateau Coordination'),
    (86,  'Kaduna I MSTO',                        'No.3 Broadcasting Road, Kaduna',                                                'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (87,  'MTO Kaduna',                           'No. 7 Katsina Road, Kaduna',                                                    'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (88,  'Kaduna II MSTO',                       'No.12 Kachia Road, Kaduna',                                                     'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (89,  'Zaria MSTO',                           'No 1, Kofar Kibo by Barewa Junction Shagalinku, Kaduna State',                  'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (90,  'Makurdi MSTO',                         'No. 25, Jonah Jang Crescent, Makurdi, Benue State',                             'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (91,  'Benue GBTO',                           '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (92,  'MSTA, Benue',                          '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (93,  'Jos MSTO',                             'Adjacent Federal Secretariat Complex, Tudun Wada, Jos',                         'Owned',  'Benue, Kaduna & Plateau Coordination'),
    (94,  'Plateau GBTO',                         '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (95,  'Jos SCDMEO',                           '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (96,  'MSTA, Plateau',                        '',                                                                               '',       'Benue, Kaduna & Plateau Coordination'),
    (97,  'Shendam Satellite Tax Office',         'No.10 Hubert Shaldas Way, Lafia Road, Shendam, Plateau State',                  'Rented', 'Benue, Kaduna & Plateau Coordination'),
    (98,  'Otukpo Satellite Tax Office',          'Along Double K Resort, Otukpo, Benue State',                                    'Rented', 'Benue, Kaduna & Plateau Coordination'),
    (99,  'Gboko Satellite Tax Office',           'No.2 Makir Dzakpe Way, Gboko, Benue State',                                     'Rented', 'Benue, Kaduna & Plateau Coordination'),
    # ── FIRS Headquarters ─────────────────────────────────────────────
    (100, 'CD/People Support Group',             'No.15, Sokode Crescent, Wuse Zone 5, Abuja',                                     'Owned',  'FIRS Headquarters'),
    (101, 'Human Capital Department',            '',                                                                                '',       'FIRS Headquarters'),
    (102, "Taxpayer's Services Department",      '',                                                                                '',       'FIRS Headquarters'),
    (103, 'Communication & Liaison Department',  '',                                                                                '',       'FIRS Headquarters'),
    (104, 'Information Communications Technology (ICT)', '',                                                                       '',       'FIRS Headquarters'),
    (105, 'Board Secretary',                     '',                                                                                '',       'FIRS Headquarters'),
    (106, 'Tax Audit Department',                '',                                                                                '',       'FIRS Headquarters'),
    (107, 'Director, Special Tax Audit',         '',                                                                                '',       'FIRS Headquarters'),
    (108, 'Vendor Processing Unit',              '',                                                                                '',       'FIRS Headquarters'),
    (109, 'Change Management Department',        '',                                                                                '',       'FIRS Headquarters'),
    (110, 'Project Delivery Department',         'No.16 Sokode Crescent, Wuse Zone 5, Abuja',                                      'Owned',  'FIRS Headquarters'),
    (111, 'Revenue Accounting Department',       '',                                                                                '',       'FIRS Headquarters'),
    (112, 'BA & ESD',                            '',                                                                                '',       'FIRS Headquarters'),
    (113, 'Records/Document Management Archive', '',                                                                                '',       'FIRS Headquarters'),
    (114, 'Internal Affairs Department',         '',                                                                                '',       'FIRS Headquarters'),
    (115, 'Research & Statistics',               '',                                                                                '',       'FIRS Headquarters'),
    (116, 'Procurement Department',              'No.14 Sokode Crescent, Wuse Zone 5, Abuja',                                      'Owned',  'FIRS Headquarters'),
    (117, 'Large Infrastructure Development Office', '',                                                                            '',       'FIRS Headquarters'),
    (118, 'Facility Management Department',      '',                                                                                '',       'FIRS Headquarters'),
    (119, 'Office of the Executive Chairman',    'No.20 Sokode Crescent, Wuse Zone 5, Abuja',                                      'Owned',  'FIRS Headquarters'),
    (120, 'Office of the CSO',                   '',                                                                                '',       'FIRS Headquarters'),
    (121, "Offices of EC's Special Advisers",    '',                                                                                '',       'FIRS Headquarters'),
    (122, 'CD/Support Services Group',           '',                                                                                '',       'FIRS Headquarters'),
    (123, 'Coordinating Director Emerging Tax Operation Group', '',                                                                 '',       'FIRS Headquarters'),
    (124, 'CD/Compliance Support Group',         '',                                                                                '',       'FIRS Headquarters'),
    (125, 'CD/Enforcement Support Group',        '',                                                                                '',       'FIRS Headquarters'),
    (126, 'CD/Medium Tax Group',                 '',                                                                                '',       'FIRS Headquarters'),
    (127, 'CD/Special Duties',                   '',                                                                                '',       'FIRS Headquarters'),
    (128, 'CD/Large Tax Group',                  '',                                                                                '',       'FIRS Headquarters'),
    (129, 'Finance and Accounts Department',     '',                                                                                '',       'FIRS Headquarters'),
    (130, 'Legal and Management Services Department', '',                                                                           '',       'FIRS Headquarters'),
    (131, 'EC FIRS Registry',                    '',                                                                                '',       'FIRS Headquarters'),
    (132, 'Management Secretariat',              '',                                                                                '',       'FIRS Headquarters'),
    (133, 'Liaison with Antigraft & Law Enforcement Agency', '',                                                                    '',       'FIRS Headquarters'),
    (134, 'Call Centre',                         '',                                                                                '',       'FIRS Headquarters'),
    (135, 'Treasury Department',                 '',                                                                                '',       'FIRS Headquarters'),
    (136, 'Store',                               '',                                                                                '',       'FIRS Headquarters'),
    (137, "Taxpayers Department",                '',                                                                                '',       'FIRS Headquarters'),
    (138, 'Communication Department (Annex)',    'No.12 Sokode Crescent, Wuse Zone 5, Abuja',                                       'Owned',  'FIRS Headquarters'),
    (139, 'MSTD',                                '',                                                                                '',       'FIRS Headquarters'),
    (140, "Federal Auditor's Office",            '',                                                                                '',       'FIRS Headquarters'),
    (141, 'Debt Management Department',          '',                                                                                '',       'FIRS Headquarters'),
    (142, 'Medium Tax Department',               '',                                                                                '',       'FIRS Headquarters'),
    (143, 'Security & Safety Department',        '',                                                                                '',       'FIRS Headquarters'),
    (144, 'Risk Management Department',          '',                                                                                '',       'FIRS Headquarters'),
    (145, 'Planning & Coordination Department',  '',                                                                                '',       'FIRS Headquarters'),
    (146, 'Tax Investigation Department',        'No.26 Sokode Crescent, Wuse Zone 5, Abuja',                                       'Rented', 'FIRS Headquarters'),
    (147, 'Liaison Office — Director International Tax', '',                                                                        '',       'FIRS Headquarters'),
    (148, 'Liaison Office — Director Oil & Gas', '',                                                                                '',       'FIRS Headquarters'),
    (149, 'Servicom Department',                 '',                                                                                '',       'FIRS Headquarters'),
    (150, 'Tax-Data Management',                 '',                                                                                '',       'FIRS Headquarters'),
    (151, 'Tax Policy Department',               '',                                                                                '',       'FIRS Headquarters'),
    (152, 'Joint Tax Board',                     '',                                                                                '',       'FIRS Headquarters'),
    (153, 'WATAF',                               '',                                                                                '',       'FIRS Headquarters'),
    (154, 'PMO (SAP)',                           '',                                                                                '',       'FIRS Headquarters'),
    (155, 'Career & Skill Department / FIRS Training School', 'Durumi, Abuja',                                                     'Owned',  'FIRS Headquarters'),
    (156, 'Special Enforcement Department',      'No.39, Njamena Crescent, Wuse II, Abuja',                                        'Owned',  'FIRS Headquarters'),
    (157, 'Exchange of Information Headquarters','Plot 1863, Lee Kwan Yew, Asokoro, Abuja',                                        'Owned',  'FIRS Headquarters'),
    (158, 'EDRMS',                               'No.34 Sokode Crescent, Wuse Zone 5, Abuja',                                       'Rented', 'FIRS Headquarters'),
    # ── FCT Abuja Coordination ────────────────────────────────────────
    (159, 'Special Tax Audit (Northern Division)', '',                                                                              '',       'FCT Abuja Coordination'),
    (160, 'MSTA, Maitama',                       '',                                                                                '',       'FCT Abuja Coordination'),
    (161, 'Asokoro MSTO',                        'No.70 Yakubu Gowon Street, Asokoro, Abuja',                                      'Owned',  'FCT Abuja Coordination'),
    (162, 'MSTA, Asokoro',                       '',                                                                                '',       'FCT Abuja Coordination'),
    (163, 'Tax Investigation — Northern Region', 'No.1A & B Udo-Udoma Street, Asokoro, Abuja',                                     'Rented', 'FCT Abuja Coordination'),
    (164, 'Central Area MSTO',                   'Yobe Investment House, Plot 1332, Cadastral Zone A0, Central Business District, Abuja', 'Rented', 'FCT Abuja Coordination'),
    (165, 'Utako MSTO',                          'Plot 35A A.E Ekukinam Street, Utako, Abuja',                                     'Owned',  'FCT Abuja Coordination'),
    (166, 'Utako MSTA',                          '',                                                                                '',       'FCT Abuja Coordination'),
    (167, 'Utako MSTO II (Mabushi)',             "Plot 1209 Yar'adua Expressway, Mabushi, Abuja",                                   'Rented', 'FCT Abuja Coordination'),
    (168, 'Garki MSTO',                          'No.12 Port Harcourt Crescent, Area 11, Garki, Abuja',                            'Owned',  'FCT Abuja Coordination'),
    (169, 'Garki MSTO II',                       '',                                                                                '',       'FCT Abuja Coordination'),
    (170, 'MTO Abuja',                           '',                                                                                '',       'FCT Abuja Coordination'),
    (171, 'Medium Tax Audit, Abuja',             '',                                                                                '',       'FCT Abuja Coordination'),
    (172, 'Garki MSTA/Central Area MSTA',        '',                                                                                '',       'FCT Abuja Coordination'),
    (173, 'Wuse MSTO I',                         'No.28 Sudan Street, Wuse Zone 6, Abuja',                                         'Owned',  'FCT Abuja Coordination'),
    (174, 'Wuse MSTA',                           '',                                                                                '',       'FCT Abuja Coordination'),
    (175, 'GBTO Abuja',                          '',                                                                                '',       'FCT Abuja Coordination'),
    (176, 'Wuse MSTO II',                        'Plot 11-5 (Block A), Daressalam Street, Off Aminu Kano Crescent, Wuse II, Abuja', 'Rented', 'FCT Abuja Coordination'),
    (177, 'Maitama MSTO',                        'Plot 61, Usuma Street, Maitama, Abuja',                                          'Owned',  'FCT Abuja Coordination'),
    (178, 'FCT SCO Office',                      'Plot 251, Katampe Extension, Abuja',                                             'Owned',  'FCT Abuja Coordination'),
    (179, 'Medium Tax Audit 2, Abuja',           '',                                                                                '',       'FCT Abuja Coordination'),
    (180, 'Large Tax Audit, Abuja',              'No.10 Sapele Street, Garki, Abuja',                                              'Rented', 'FCT Abuja Coordination'),
    (181, 'Large Tax Office, Abuja',             '',                                                                                '',       'FCT Abuja Coordination'),
    (182, 'FCT Debt Management Office',          '',                                                                                '',       'FCT Abuja Coordination'),
    (183, 'Gwagwalada MSTO',                     'Plot 77 Old Kutunku Road After Jimrose Hotel, Gwagwalada, Abuja',                 'Owned',  'FCT Abuja Coordination'),
    (184, 'Lugbe MSTO',                          'MF 484 Cadastral Zone 07-07 Sabon Lugbe, Along Airport Road, Abuja',             'Owned',  'FCT Abuja Coordination'),
    (185, 'Lugbe MSTA',                          '',                                                                                '',       'FCT Abuja Coordination'),
    (186, 'Kubwa MSTO',                          'Plot CM4, Kubwa Extension III FCDA Scheme, Murtala Mohammed Expressway, Abuja',  'Rented', 'FCT Abuja Coordination'),
    (187, 'MSTA, Kubwa',                         '',                                                                                '',       'FCT Abuja Coordination'),
    (188, 'FIRS Multipurpose Cooperative',       'Feb 04 Plaza, Plot 2027 Dalaba Street, Wuse Zone 5, Abuja',                      'Rented', 'FCT Abuja Coordination'),
    (189, 'FIRS Retired Officers Association (Abuja)', 'MKK Plaza, Suite 211, No.2, I.T Igbani Street Off Ademola Adetokunbo, Wuse II', 'Rented', 'FCT Abuja Coordination'),
    (190, 'Gwarimpa SMTO',                       'No 10, Mamman Shata Street, Off Third Avenue, Gwarimpa, Abuja',                  'Rented', 'FCT Abuja Coordination'),
    (191, 'Gwarimpa SMTA',                       'No 10, Akure Street, War College Estate, Off Third Avenue, Gwarimpa, Abuja',     'Rented', 'FCT Abuja Coordination'),
    (192, 'New Karu MSTO',                       'No.1 Oladipo Diya Street, Off Abacha Road, Karu, Abuja',                        'Rented', 'FCT Abuja Coordination'),
    # ── Kogi, Nasarawa & Niger ────────────────────────────────────────
    (193, 'Lafia MSTO',                          'Markurdi Road, Behind Labour House, Lafia, Nasarawa State',                      'Owned',  'Kogi, Nasarawa & Niger Coordination'),
    (194, 'Nasarawa GBTO',                       '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (195, 'MSTA, Nasarawa',                      '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (196, 'Keffi MSTO',                          'Halibiz Mall, No.21 Maizabo Road, Keffi, Nasarawa State',                        'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    (197, 'Lokoja MSTO',                         'Lokogoma Phase II, IBB Way, Lokoja, Kogi State',                                 'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    (198, 'Kogi GBTO',                           '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (199, 'MSTA, Kogi',                          '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (200, 'Anyigba Satellite Tax Office',        'Km 1, Anyigba-Ankpa Road, Anyigba, Kogi State',                                  'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    (201, 'State Coordinator KNN',               'A41 Mohammed Muazu Road, Adjacent NACB Building, Minna, Niger State',            'Owned',  'Kogi, Nasarawa & Niger Coordination'),
    (202, 'Minna MSTO',                          '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (203, 'GBTO, Niger',                         '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (204, 'MSTA, Niger',                         '',                                                                                '',       'Kogi, Nasarawa & Niger Coordination'),
    (205, 'Suleja MSTO',                         'No.32 Suleman Barau Road, Suleja, Niger State',                                  'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    (206, 'Bida MSTO',                           'Along Ilorin Road, Bida, Niger State',                                           'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    (207, 'Kontagora MSTO',                      'Lagos-Kaduna Road, Adjacent B Division By BCGA, Kontagora, Niger State',         'Rented', 'Kogi, Nasarawa & Niger Coordination'),
    # ── Borno, Bauchi & Yobe ──────────────────────────────────────────
    (208, 'State Coordinator BBY',               'No.32 & 33 Yakubun Bauchi Road, Opposite State Secretariat, Bauchi',             'Owned',  'Borno, Bauchi & Yobe Coordination'),
    (209, 'Bauchi MSTO',                         '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (210, 'Bauchi GBTO',                         '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (211, 'MSTA, Bauchi',                        '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (212, 'Bauchi SCDMEO',                       '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (213, 'FIRS Training School, Bauchi',        'Federal Low Cost Housing, PMB 0265, Bauchi',                                     'Owned',  'Borno, Bauchi & Yobe Coordination'),
    (214, 'Azare MSTO',                          'No.1454 Old Kano Road, Azare, Bauchi State',                                     'Rented', 'Borno, Bauchi & Yobe Coordination'),
    (215, 'Damaturu MSTO',                       'Potiskum Road, Opposite NTA, PMB 1095, Damaturu, Yobe State',                    'Owned',  'Borno, Bauchi & Yobe Coordination'),
    (216, 'MSTA, Yobe',                          '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (217, 'Yobe GBTO',                           '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (218, 'Maiduguri MSTO',                      'Airport Road, Opposite Borno Express Terminus, Maiduguri',                       'Owned',  'Borno, Bauchi & Yobe Coordination'),
    (219, 'MSTA, Borno',                         '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    (220, 'Maiduguri GBTO',                      '',                                                                                '',       'Borno, Bauchi & Yobe Coordination'),
    # ── Gombe, Taraba & Adamawa ───────────────────────────────────────
    (221, 'State Coordination Office, Gombe',    'Off Bauchi Road, Adjacent INEC Office, Gombe',                                   'Owned',  'Gombe, Taraba & Adamawa Coordination'),
    (222, 'Gombe MSTO',                          '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (223, 'Gombe GBTO',                          '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (224, 'MSTA, Gombe',                         '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (225, 'Gombe SCDMEO',                        '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (226, 'Yola MSTO',                           'Galadima Aminu Way, Opposite NRC LTD, PMB 2115, Jimeta, Yola, Adamawa State',    'Owned',  'Gombe, Taraba & Adamawa Coordination'),
    (227, 'MSTA, Adamawa',                       '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (228, 'Adamawa GBTO',                        '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (229, 'Yola SMTO',                           'Plot No 3 Jaura Road, Off Galadima Aminu Way, Yola, Adamawa State',              'Rented', 'Gombe, Taraba & Adamawa Coordination'),
    (230, 'Jalingo MSTO',                        'Abuja Phase 1, State Secretariat Road, Jalingo, Taraba State',                   'Owned',  'Gombe, Taraba & Adamawa Coordination'),
    (231, 'Taraba GBTO',                         '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (232, 'MSTA, Taraba',                        '',                                                                                '',       'Gombe, Taraba & Adamawa Coordination'),
    (233, 'Mubi Satellite Tax Office',           'Near Mubi 1 Primary School, Behind Mubi Prison, Lamisula Road, Mubi, Adamawa State', 'Rented', 'Gombe, Taraba & Adamawa Coordination'),
    (234, 'Kaltungo Satellite Tax Office',       'Along Gombe-Yola Road, Kaltungo LGA, Gombe State',                               'Rented', 'Gombe, Taraba & Adamawa Coordination'),
    (235, 'Wukari Satellite Tax Office',         'T Junction, Former BECO Lab, General Hospital, Wukari, Taraba State',            'Rented', 'Gombe, Taraba & Adamawa Coordination'),
    # ── Akwa Ibom, Bayelsa & Cross River ─────────────────────────────
    (236, 'State Coordination Office, Uyo',      'Plot 5 Along Udo Udoma Avenue, Opposite Ibom Mall, Uyo, Akwa Ibom State',        'Owned',  'Akwa Ibom, Bayelsa & C/River Coord'),
    (237, 'Uyo MSTO',                            '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (238, 'Akwa Ibom GBTO',                      '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (239, 'MSTA, Akwa Ibom',                     '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (240, 'SCDMEO, Akwa Ibom',                   '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (241, 'Yenagoa MSTO',                        'No.1 Okologba Street, Akenpai, Yenagoa, Bayelsa State',                          'Owned',  'Akwa Ibom, Bayelsa & C/River Coord'),
    (242, 'Bayelsa GBTO',                        '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (243, 'MSTA, Bayelsa',                       '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (244, 'GBTO Calabar',                        'Plot 1 IBB Way, Calabar, Cross River State',                                     'Owned',  'Akwa Ibom, Bayelsa & C/River Coord'),
    (245, 'Calabar MSTO',                        '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (246, 'MSTA, Cross River',                   '',                                                                                '',       'Akwa Ibom, Bayelsa & C/River Coord'),
    (247, 'Ikom MSTO',                           'No 13 Okim Osabor Street, Ikom, Cross River State',                              'Rented', 'Akwa Ibom, Bayelsa & C/River Coord'),
    (248, 'Eket Satellite Tax Office',           'No.12 Uqua Road, Eket, Akwa Ibom State',                                        'Rented', 'Akwa Ibom, Bayelsa & C/River Coord'),
    (249, 'Ikot Ekpene Satellite Tax Office',    'No.3 Etok Eren Road, Ikot Ekpene, Akwa Ibom State',                              'Rented', 'Akwa Ibom, Bayelsa & C/River Coord'),
    # ── Rivers, Edo & Delta ───────────────────────────────────────────
    (250, 'State Coordination Office, Port Harcourt', 'Plot 465A, Trans-Amadi Industrial Layout, Port Harcourt, Rivers State',    'Owned',  'Rivers, Edo & Delta Coordination'),
    (251, 'Port Harcourt SC & DMEO',             '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (252, 'Port Harcourt MSTO',                  'No.10 Moscow Road, Port Harcourt, Rivers State',                                 'Owned',  'Rivers, Edo & Delta Coordination'),
    (253, 'Rivers GBTO',                         '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (254, 'Tax Incentive Department, Port Harcourt', '',                                                                            '',       'Rivers, Edo & Delta Coordination'),
    (255, 'MSTA, Port Harcourt 1',               'Divinity House, 213 Woji Road, GRA Phase 2, Port Harcourt',                      'Rented', 'Rivers, Edo & Delta Coordination'),
    (256, 'MSTA, Port Harcourt 2',               '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (257, 'Large Tax Audit, Port Harcourt',      '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (258, 'Medium Tax Audit, Port Harcourt',     '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (259, 'Special Tax Audit, Port Harcourt',    '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (260, 'MSTA, Rumukurushi',                   '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (261, 'Tax Investigation, Port Harcourt',    '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (262, 'Rumueme MSTO',                        'No.8 Sani Abacha Road, GRA Phase III, Port Harcourt',                            'Rented', 'Rivers, Edo & Delta Coordination'),
    (263, 'Port Harcourt MSTO 2',                '21 Aba Road, Port Harcourt, Rivers State',                                       'Rented', 'Rivers, Edo & Delta Coordination'),
    (264, 'Port Harcourt MSTO 3',                '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (265, 'Rumukwurushi MSTO 2',                 '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (266, 'Rumukwurushi MSTO 3',                 '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (267, 'MTO Port Harcourt',                   'No 78, Stadium Road, Port Harcourt, Rivers State',                               'Rented', 'Rivers, Edo & Delta Coordination'),
    (268, 'Rumukwurushi MSTO',                   'No.301 Port Harcourt-Aba Road, Rumukushi Junction, Rivers State',                'Owned',  'Rivers, Edo & Delta Coordination'),
    (269, 'Port Harcourt LTO',                   '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (270, 'Asaba MSTO',                          'Plot 4, Govt. House/Anwai Road, Asaba, Delta State',                             'Owned',  'Rivers, Edo & Delta Coordination'),
    (271, 'Delta GBTO',                          '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (272, 'MSTA, Asaba',                         '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (273, 'Warri MSTO',                          'No 143 Refinery Road, Uvwie LGA, Warri, Delta State',                            'Owned',  'Rivers, Edo & Delta Coordination'),
    (274, 'MSTA, Warri',                         '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (275, 'Medium Tax Audit, Warri',             '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (276, 'MTO Warri',                           '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (277, 'Benin MSTO',                          'No.53, Airport Road, Benin City, Edo State',                                     'Owned',  'Rivers, Edo & Delta Coordination'),
    (278, 'Edo GBTO',                            '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (279, 'MSTA, Edo',                           '',                                                                                '',       'Rivers, Edo & Delta Coordination'),
    (280, 'Sapele MSTO',                         '205 New Ogorode Road, Sapele, Delta State',                                      'Owned',  'Rivers, Edo & Delta Coordination'),
    (281, 'Auchi MSTO',                          'Plot 49A Block Old GRA Auchi, No.1 Prince Adaka Momodu Street, Auchi, Edo State','Owned',  'Rivers, Edo & Delta Coordination'),
    (282, 'Yenagoa SMTO',                        'Otiotio Street, Yenagoa, Bayelsa State',                                         'Owned',  'Rivers, Edo & Delta Coordination'),
    (283, 'Bonny Island Satellite Tax Office',   'Along Bonny/Bodo Road, Adjacent UBA, Bonny Island, Rivers State',                'Rented', 'Rivers, Edo & Delta Coordination'),
    (284, 'Ahoada Satellite Tax Office',         'No.54, Omoku Road, Ahoada, Rivers State',                                        'Rented', 'Rivers, Edo & Delta Coordination'),
    (285, 'Agbor Satellite Tax Office',          'No.2 Deaper Life Road, AgborObi, Off Benin-Asaba Expressway, Delta State',       'Rented', 'Rivers, Edo & Delta Coordination'),
    (286, 'Onne Satellite Tax Office',           'No.103, Harbour Road, Oil & Gas Free Zone Area, Onne, Rivers State',             'Rented', 'Rivers, Edo & Delta Coordination'),
    (287, 'Ughelli Satellite Tax Office',        'Warri-Ughelli Road, Beside St Theresa Secondary School, Ughelli, Delta State',   'Rented', 'Rivers, Edo & Delta Coordination'),
    # ── Ebonyi, Enugu & Abia ─────────────────────────────────────────
    (288, 'State Coordination Office, Enugu',    'No. 4 Nwodo Close, GRA, Enugu State',                                            'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (289, 'Medium Tax Audit, Enugu',             '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (290, 'MSTA, Enugu',                         '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (291, 'Debt Management & Enforcement, Enugu','',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (292, 'Enugu MSTO',                          'No.7 Ridge Way, GRA, Enugu',                                                     'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (293, 'Enugu GBTO',                          '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (294, 'MTO Enugu',                           'No.2 Ridge Way Road, GRA, Enugu',                                                 'Rented', 'Ebonyi, Enugu & Abia Coordination'),
    (295, 'Aba MSTO',                            'No 1 Aba-Ikot Ekpene Road, Abia State',                                          'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (296, 'Umuahia MSTO',                        'No.4, Ojike Street, Umuahia, Abia State',                                        'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (297, 'Abia GBTO',                           '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (298, 'MSTA, Abia',                          '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (299, 'Osisioma MSTO',                       'No.161 Aba-Owerri Road, Osisioma, Aba',                                          'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (300, 'Abakaliki MSTO',                      'Mile 50 Old Enugu Road, Abakaliki, Ebonyi State',                                 'Owned',  'Ebonyi, Enugu & Abia Coordination'),
    (301, 'Ebonyi GBTO',                         '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (302, 'MSTA, Ebonyi',                        '',                                                                                '',       'Ebonyi, Enugu & Abia Coordination'),
    (303, '9th Mile Satellite Tax Office',       'No.2 Divine Estate, 9th Mile Corner Ngwo, Enugu State',                          'Rented', 'Ebonyi, Enugu & Abia Coordination'),
    (304, 'Afikpo Satellite Tax Office',         'No.31 Eke Market Road, Afikpo, Ebonyi State',                                    'Rented', 'Ebonyi, Enugu & Abia Coordination'),
    # ── Imo & Anambra ─────────────────────────────────────────────────
    (305, 'State Coordinator, Imo & Anambra',    'No 68 World Bank Area A, New Owerri, Imo State',                                  'Rented', 'Imo & Anambra Coordination'),
    (306, 'Owerri MSTO',                         'Km 3 Owerri-Onitsha Road, Owerri, Imo State',                                    'Owned',  'Imo & Anambra Coordination'),
    (307, 'Owerri SCDMEO',                       '',                                                                                '',       'Imo & Anambra Coordination'),
    (308, 'Imo GBTO',                            '',                                                                                '',       'Imo & Anambra Coordination'),
    (309, 'MSTA, Imo',                           '',                                                                                '',       'Imo & Anambra Coordination'),
    (310, 'Police Enforcement Unit, Owerri',     '',                                                                                '',       'Imo & Anambra Coordination'),
    (311, 'Orlu MSTO',                           'No.10 Ihioma Road, Orlu, Imo State',                                             'Rented', 'Imo & Anambra Coordination'),
    (312, 'Awka MSTO',                           'Plot 4, Abuja Estate, Glass House, Along Onitsha/Enugu Expressway, Awka',        'Owned',  'Imo & Anambra Coordination'),
    (313, 'Anambra GBTO',                        '',                                                                                '',       'Imo & Anambra Coordination'),
    (314, 'Awka LTO',                            'No 9/11 Onwubuya Street, Off Arthur Eze Avenue/Coastal Road, Awka, Anambra State','Rented', 'Imo & Anambra Coordination'),
    (315, 'Onitsha MSTO',                        'No.6 Ridge Road, Near NEPA Building, GRA, Onitsha, Anambra State',               'Owned',  'Imo & Anambra Coordination'),
    (316, 'MSTA, Anambra',                       '',                                                                                '',       'Imo & Anambra Coordination'),
    (317, 'Nnewi MSTO 1',                        'No.74, Onitsha Road, Nnewi, Anambra State',                                      'Owned',  'Imo & Anambra Coordination'),
    (318, 'Nnewi MSTO 2',                        '20 Nnobi Road, Nnewi, Anambra State',                                            'Rented', 'Imo & Anambra Coordination'),
    (319, 'Okigwe Satellite Tax Office',         'No.179 Owerri Road, Okigwe Uturu Plaza, Okigwe, Imo State',                      'Rented', 'Imo & Anambra Coordination'),
    (320, 'Nkpor Satellite Tax Office',          'No.64 Limca Road, Opp MTN Onitsha, Anambra State',                               'Rented', 'Imo & Anambra Coordination'),
    # ── Lagos Mainland East ───────────────────────────────────────────
    (321, 'Lagos Mainland East Coordination Office', '2b Lateef Jakande Road, Agidingbi, Lagos',                                   'Owned',  'Lagos Mainland East Coordination'),
    (322, 'Large Tax Office (Non-Oil) Manufacturing', '',                                                                           '',       'Lagos Mainland East Coordination'),
    (323, 'MTO Lagos Mainland East',             '',                                                                                '',       'Lagos Mainland East Coordination'),
    (324, 'Lagos GBTO',                          '',                                                                                '',       'Lagos Mainland East Coordination'),
    (325, 'Large Tax Audit Manufacturing & Others', '',                                                                             '',       'Lagos Mainland East Coordination'),
    (326, 'Medium Tax Audit LME I',              '',                                                                                '',       'Lagos Mainland East Coordination'),
    (327, 'LME SCDMEO',                          '',                                                                                '',       'Lagos Mainland East Coordination'),
    (328, 'Tax Incentive Department, Lagos',     '',                                                                                '',       'Lagos Mainland East Coordination'),
    (329, 'LME FIRS Training School',            '',                                                                                '',       'Lagos Mainland East Coordination'),
    (330, 'Ikeja 2 MSTO',                        'No.76 Allen Avenue, Ikeja, Lagos',                                               'Owned',  'Lagos Mainland East Coordination'),
    (331, 'Ikeja MSTA',                          '',                                                                                '',       'Lagos Mainland East Coordination'),
    (332, 'Ikeja 3 SMTO',                        'AHCN Towers, CIPM Road, Alausa, Lagos',                                          'Rented', 'Lagos Mainland East Coordination'),
    (333, 'Ikeja 1 ETA, GBA & DMO',              'Tax Investigation Office, No 60 Kudirat Abiola Way, Ikeja, Lagos',               'Rented', 'Lagos Mainland East Coordination'),
    (334, 'Ikeja 1 MSTO',                        '',                                                                                '',       'Lagos Mainland East Coordination'),
    (335, 'Agege MSTO',                          'No 1 Adigun Street, Off Iju Road, Agege, Lagos State',                           'Rented', 'Lagos Mainland East Coordination'),
    (336, 'MSTA, Agege',                         '',                                                                                '',       'Lagos Mainland East Coordination'),
    (337, 'Alimosho MSTO 1',                     'No.26 Shasha Road, Akowonjo Roundabout, Lagos',                                  'Owned',  'Lagos Mainland East Coordination'),
    (338, 'Alimosho MSTO 2',                     '',                                                                                '',       'Lagos Mainland East Coordination'),
    (339, 'Ilupeju 1, 2, 3 SMTO',               'No 3 Olusoji Idowu Street, Ilupeju, Lagos',                                      'Owned',  'Lagos Mainland East Coordination'),
    (340, 'Ilupeju 1 MSTO',                      'No 6 Ilupeju Bypass, Lagos',                                                     'Rented', 'Lagos Mainland East Coordination'),
    (341, 'Ilupeju 2 MSTO',                      '',                                                                                '',       'Lagos Mainland East Coordination'),
    (342, 'Ilupeju 3 MSTO',                      '',                                                                                '',       'Lagos Mainland East Coordination'),
    (343, 'Medium Tax Audit LME II',             '',                                                                                '',       'Lagos Mainland East Coordination'),
    (344, 'Ilupeju MSTA',                        '',                                                                                '',       'Lagos Mainland East Coordination'),
    (345, 'Yaba MSTO',                           'No 356 Murtala Mohammed Street, Yaba, Lagos',                                    'Owned',  'Lagos Mainland East Coordination'),
    (346, 'Yaba MSTA',                           '',                                                                                '',       'Lagos Mainland East Coordination'),
    (347, 'FIRS Training School, Yaba',          'Plot 225 Herbert Macauley Way, Yaba, Lagos',                                     'Owned',  'Lagos Mainland East Coordination'),
    (348, 'Onigbongbo MSTO',                     'No.24A Isaac Johnson Street, GRA, Lagos',                                        'Rented', 'Lagos Mainland East Coordination'),
    (349, 'Onigbongbo MSTA',                     '',                                                                                '',       'Lagos Mainland East Coordination'),
    (350, 'Ikorodu MSTO 1',                      'No 110 Lagos-Ikorodu Road, Lagos',                                               'Rented', 'Lagos Mainland East Coordination'),
    (351, 'Ikorodu MSTO 2',                      '',                                                                                '',       'Lagos Mainland East Coordination'),
    (352, 'FIRS Retired Officers Association (Lagos)', '2nd Floor, NIS Building, Elephant House Road, Alausa, Lagos',              'Rented', 'Lagos Mainland East Coordination'),
    (353, 'Ojodu Berger MSTO',                   'Providence House, No.1 Babatunde Ladega Street, Omole, Ikeja, Lagos',            'Rented', 'Lagos Mainland East Coordination'),
    (354, 'Imota MSTO',                          'Adeniyi Street, Imota, Lagos State',                                             'Rented', 'Lagos Mainland East Coordination'),
    # ── Lagos Mainland West ───────────────────────────────────────────
    (355, 'Medium Tax Audit LMW',                '7 Afric Road, Off Funsho Williams Avenue, Iponri, Lagos',                        'Rented', 'Lagos Mainland West Coordination'),
    (356, 'MSTA, Surulere',                      '',                                                                                '',       'Lagos Mainland West Coordination'),
    (357, 'Surulere MSTO',                       '',                                                                                '',       'Lagos Mainland West Coordination'),
    (358, 'Lagos Mainland West VAT Coordination','',                                                                                '',       'Lagos Mainland West Coordination'),
    (359, 'Alaba MSTO',                          '1 Olarewaju Street, Off Badagry Expressway, Tipper Garage, Alaba, Lagos',        'Owned',  'Lagos Mainland West Coordination'),
    (360, 'MSTA, Alaba',                         '',                                                                                '',       'Lagos Mainland West Coordination'),
    (361, 'MSTA, Festac',                        '1st Avenue, Ice Plaza Building, Near Big Treat, Festac Town, Lagos',             'Owned',  'Lagos Mainland West Coordination'),
    (362, 'Festac MSTO',                         '',                                                                                '',       'Lagos Mainland West Coordination'),
    (363, 'Apapa MSTO',                          'No 22 Warehouse Road, Apapa, Lagos State',                                       'Owned',  'Lagos Mainland West Coordination'),
    (364, 'LMW SCDMEO',                          '',                                                                                '',       'Lagos Mainland West Coordination'),
    (365, 'MSTA, Apapa',                         '',                                                                                '',       'Lagos Mainland West Coordination'),
    (366, 'LTO (Non-Oil Aviation and Construction)', '',                                                                            '',       'Lagos Mainland West Coordination'),
    (367, 'Isolo MSTO',                          '22 Osolo Way, Off MM International Airport Road, Lagos State',                   'Rented', 'Lagos Mainland West Coordination'),
    (368, 'MSTA, Isolo',                         '',                                                                                '',       'Lagos Mainland West Coordination'),
    (369, 'Surulere/LMW',                        '63 Imam Dauda Street, Surulere, Lagos',                                          'Owned',  'Lagos Mainland West Coordination'),
    (370, 'LMW State Coordination Office',       'No 33 Imam Dauda Street, Off Eric Moore Road, Surulere, Lagos State',            'Rented', 'Lagos Mainland West Coordination'),
    (371, 'Aguda MSTO',                          '',                                                                                '',       'Lagos Mainland West Coordination'),
    (372, 'MTO Lagos Mainland West',             '',                                                                                '',       'Lagos Mainland West Coordination'),
    (373, 'MSTA, Aguda',                         '',                                                                                '',       'Lagos Mainland West Coordination'),
    (374, 'MSTA, Orile Iganmu',                  'Sunny Motors House, KM 2, Badagry Expressway, Alaba Suru, Lagos State',          'Rented', 'Lagos Mainland West Coordination'),
    (375, 'Orile Iganmu MSTO',                   '',                                                                                '',       'Lagos Mainland West Coordination'),
    (376, 'Badagry Satellite Tax Office',        'No.3 Oke-Owo Close, Off Ansarudeen Road, Oropo, Badagry, Lagos State',           'Rented', 'Lagos Mainland West Coordination'),
    # ── Lagos Island ──────────────────────────────────────────────────
    (377, 'Ajah 1 MSTO',                         'AVM Building, KM 14, Lekki-Epe Expressway, Agungi, Lagos State',                 'Rented', 'Lagos Island Coordination'),
    (378, 'MSTA, Ajah',                          '',                                                                                '',       'Lagos Island Coordination'),
    (379, 'Lagos Island State Coordination',     '17b Awolowo Road, Ikoyi, Lagos',                                                 'Owned',  'Lagos Island Coordination'),
    (380, 'Oil & Gas Department',                '',                                                                                '',       'Lagos Island Coordination'),
    (381, 'Oil & Gas Downstream Audit',          '',                                                                                '',       'Lagos Island Coordination'),
    (382, 'Oil & Gas Upstream Audit',            '',                                                                                '',       'Lagos Island Coordination'),
    (383, 'LTO (Oil & Gas) Downstream',          '',                                                                                '',       'Lagos Island Coordination'),
    (384, 'LTO (Oil & Gas) Oil Servicing',       '',                                                                                '',       'Lagos Island Coordination'),
    (385, 'LTO Oil & Gas Upstream',              '',                                                                                '',       'Lagos Island Coordination'),
    (386, 'Special Enforcement Unit, Lagos',     '',                                                                                '',       'Lagos Island Coordination'),
    (387, 'Tax Investigation, Lagos Island',     '',                                                                                '',       'Lagos Island Coordination'),
    (388, 'Lagos Island SCDMEO',                 '',                                                                                '',       'Lagos Island Coordination'),
    (389, 'Ikoyi 1 MSTO',                        '',                                                                                '',       'Lagos Island Coordination'),
    (390, 'Special Tax Audit, Lagos Island',     '',                                                                                '',       'Lagos Island Coordination'),
    (391, 'International Taxation Department',   '',                                                                                '',       'Lagos Island Coordination'),
    (392, 'Non-Resident Taxpayers Department',   '',                                                                                '',       'Lagos Island Coordination'),
    (393, 'MSTA, Ikoyi',                         '',                                                                                '',       'Lagos Island Coordination'),
    (394, 'Large Tax Audit (Non-Oil) Financial', '',                                                                                '',       'Lagos Island Coordination'),
    (395, 'LTO Non-Oil Financial',               '',                                                                                '',       'Lagos Island Coordination'),
    (396, 'Lagos Island VAT Coordination',       '',                                                                                '',       'Lagos Island Coordination'),
    (397, 'Oil & Gas Servicing Audit',           '',                                                                                '',       'Lagos Island Coordination'),
    (398, 'Ajah 2 MSTO',                         'ADAMAS PLAZA, Km14, Lekki-Epe Expressway, Ikota, Lagos',                        'Rented', 'Lagos Island Coordination'),
    (399, 'Broad Street MSTO',                   'Sterling Towers, 20 Marina Road, Lagos',                                         'Rented', 'Lagos Island Coordination'),
    (400, 'Medium Tax Audit 1, Lagos Island',    '',                                                                                '',       'Lagos Island Coordination'),
    (401, 'MTO Lagos Island',                    'Afriland Towers, 97/105 Broad Street, Lagos',                                    'Rented', 'Lagos Island Coordination'),
    (402, 'Medium Tax Audit 2, Lagos Island',    '',                                                                                '',       'Lagos Island Coordination'),
    (403, 'MSTA, Onikan/Broad Street',           '',                                                                                '',       'Lagos Island Coordination'),
    (404, 'Onikan MSTO',                         '',                                                                                '',       'Lagos Island Coordination'),
    (405, 'Bar-Beach MSTO',                      'The Ark Towers, 17 Ligali Ayorinde Street, Victoria Island, Lagos',              'Rented', 'Lagos Island Coordination'),
    (406, 'MSTA, Bar Beach',                     '',                                                                                '',       'Lagos Island Coordination'),
    (407, 'LTO Telecoms & Broadcasting',         '',                                                                                '',       'Lagos Island Coordination'),
    (408, 'Victoria Island MSTO',                '33 Ahmadu Bello Way, Adjacent NTA, Victoria Island, Lagos',                      'Owned',  'Lagos Island Coordination'),
    (409, 'MSTA, Victoria Island',               '',                                                                                '',       'Lagos Island Coordination'),
    (410, 'Victoria Island II MSTO',             'Okoi Arikpo House, No.5 Idowu Tailor Street, Victoria Island, Lagos',            'Rented', 'Lagos Island Coordination'),
    (411, 'Ikoyi (Bella Vista Towers)',          'Block C, Bella Vista Towers, Plot 1, Zone 1, Banana Island, Lagos',              'Owned',  'Lagos Island Coordination'),
    (412, 'Ikoyi (Cameron Road)',                'No 28 Cameron Road, Ikoyi, Lagos',                                               'Owned',  'Lagos Island Coordination'),
    (413, 'Ikoyi 2 MSTO',                        'Golden Gate Complex, 25b Glover Road, Ikoyi, Lagos',                             'Rented', 'Lagos Island Coordination'),
    (414, 'Epe MSTO',                            'Ehisville Building, Ibeju Lekki, Lagos',                                         'Rented', 'Lagos Island Coordination'),
]

# ── Load offices with address inheritance ────────────────────────────
created = 0
skipped = 0
errors  = 0
BATCH   = 50

for i, (num, name, address, ownership, coord_name) in enumerate(OFFICES, 1):
    try:
        coord_data = coord_map.get(coord_name)
        if not coord_data:
            print(f"  ! [{num}] No coord group '{coord_name}' for: {name}")
            errors += 1
            continue

        coord_id, coord_addr = coord_data

        # Inherit parent address if blank
        effective_address = address if address else coord_addr

        # Avoid duplicates
        existing = env['generic.location'].search([
            ('name', '=', name),
            ('parent_id', '=', coord_id),
        ], limit=1)

        if not existing:
            vals = {
                'name':      name,
                'parent_id': coord_id,
            }
            if effective_address:
                vals['street'] = effective_address
            if NIGERIA_ID:
                vals['country_id'] = NIGERIA_ID
            # Try location type
            type_id = get_type_id(name)
            if type_id:
                try:
                    vals['type_id'] = type_id
                except Exception:
                    pass
            env['generic.location'].create(vals)
            created += 1
            if created <= 30 or created % 50 == 0:
                print(f"  + [{num:3d}] {name[:55]}")
        else:
            skipped += 1

        if i % BATCH == 0:
            env.cr.commit()
            print(f"  [committed batch {i}/{len(OFFICES)}]")

    except Exception as e:
        errors += 1
        print(f"  ✗ [{num}] {name[:50]} — {e}")
        traceback.print_exc()

env.cr.commit()

total = env['generic.location'].search_count([])
print()
print("=" * 70)
print("  FIRS OFFICES — LOAD COMPLETE")
print("=" * 70)
print(f"  Offices created  : {created}")
print(f"  Already existed  : {skipped}")
print(f"  Errors           : {errors}")
print(f"  Total locations  : {total}")
print()
print("  Hierarchy: Geo Zone → State → Coordination Group → Office")
print("=" * 70)
