#!/usr/bin/env python3
"""
Odoo shell runner for re-geocoding NRS locations.
Run as: sudo -u odoo python3 /opt/odoo/odoo/odoo-bin shell \
    -c /etc/odoo/odoo.conf -d myservice --no-http < regeocode_runner.py
"""
import sys
import time
import re
import json
import urllib.request
import urllib.parse
import random

# ── State capital coordinates ─────────────────────────────────────────
STATE_CAPITALS = {
    'Abia':        (5.4527,  7.5248),  'Adamawa':    (9.3265, 12.3984),
    'Akwa Ibom':   (5.0510,  7.9330),  'Anambra':    (6.2104,  6.9983),
    'Bauchi':      (10.3158, 9.8442),  'Bayelsa':    (4.9267,  6.2676),
    'Benue':       (7.7307,  8.5391),  'Borno':      (11.8333,13.1500),
    'Cross River': (4.9517,  8.3220),  'Delta':      (5.8904,  5.6801),
    'Ebonyi':      (6.3249,  8.1137),  'Edo':        (6.3350,  5.6270),
    'Ekiti':       (7.7190,  5.3110),  'Enugu':      (6.4584,  7.5464),
    'FCT':         (9.0765,  7.3986),  'Abuja':      (9.0765,  7.3986),
    'Gombe':       (10.2897,11.1673),  'Imo':        (5.4966,  7.0262),
    'Jigawa':      (12.1571, 9.3370),  'Kaduna':     (10.5105, 7.4165),
    'Kano':        (11.9964, 8.5167),  'Katsina':    (12.9889, 7.6006),
    'Kebbi':       (12.4539, 4.1975),  'Kogi':       (7.8012,  6.7333),
    'Kwara':       (8.4966,  4.5426),  'Lagos':      (6.5244,  3.3792),
    'Nasarawa':    (8.5378,  8.3206),  'Niger':      (9.6139,  6.5569),
    'Ogun':        (7.1603,  3.3477),  'Ondo':       (7.2500,  5.1950),
    'Osun':        (7.5629,  4.5200),  'Oyo':        (7.3775,  3.9470),
    'Plateau':     (9.8965,  8.8583),  'Rivers':     (4.8156,  7.0498),
    'Sokoto':      (13.0622, 5.2339),  'Taraba':     (8.8938, 11.3608),
    'Yobe':        (11.7480,11.9663),  'Zamfara':    (12.1704, 6.6614),
}

CITY_STATE_MAP = {
    'ABEOKUTA':'Ogun','AKURE':'Ondo','CALABAR':'Cross River','DUTSE':'Jigawa',
    'IBADAN':'Oyo','ILORIN':'Kwara','IWO':'Osun','JOS':'Plateau','LOKOJA':'Kogi',
    'MINNA':'Niger','OSOGBO':'Osun','OSHOGBO':'Osun','OWO':'Ondo','UMUAHIA':'Abia',
    'WARRI':'Delta','YENAGOA':'Bayelsa','YOLA':'Adamawa','GUSAU':'Zamfara',
    'DAMATURU':'Yobe','JALINGO':'Taraba','LAFIA':'Nasarawa','MAKURDI':'Benue',
    'MAIDUGURI':'Borno','UYO':'Akwa Ibom','AWKA':'Anambra','ASABA':'Delta',
    'BENIN CITY':'Edo','ADO-EKITI':'Ekiti','ADO EKITI':'Ekiti','ABAKALIKI':'Ebonyi',
    'OWERRI':'Imo','BIRNIN KEBBI':'Kebbi','SAGAMU':'Ogun','SHAGAMU':'Ogun',
    'ZARIA':'Kaduna','SULEJA':'Niger','PORT HARCOURT':'Rivers','ABA':'Abia',
    'ONITSHA':'Anambra','NNEWI':'Anambra','BONNY':'Rivers','UGHELLI':'Delta',
    'EKET':'Akwa Ibom','IKOT EKPENE':'Akwa Ibom','OGOJA':'Cross River',
    'GBOKO':'Benue','KEFFI':'Nasarawa','FUNTUA':'Katsina','BIDA':'Niger',
    'POTISKUM':'Yobe','MUBI':'Adamawa','WUKARI':'Taraba','SAKI':'Oyo',
    'OGBOMOSHO':'Oyo','ILESA':'Osun','ONITSHA':'Anambra','NSUKKA':'Enugu',
    'ORLU':'Imo','OKIGWE':'Imo','OKENE':'Kogi','ANYIGBA':'Kogi',
    'BADAGRY':'Lagos','IKORODU':'Lagos','EPE':'Lagos','OTA':'Ogun',
    'ORE':'Ondo','IKARE':'Ondo','OFFA':'Kwara','EKITI':'Ekiti',
}

STATES_NG = list(STATE_CAPITALS.keys())

def extract_state(name, street):
    text = f"{name} {street}".upper()
    for s in STATES_NG:
        if s.upper() in text:
            return s
    for city, state in CITY_STATE_MAP.items():
        if city in text:
            return state
    return None

def extract_city(name):
    name_up = name.upper()
    for city in sorted(CITY_STATE_MAP.keys(), key=len, reverse=True):
        if city in name_up:
            return city.title()
    m = re.match(r'^([A-Za-z][A-Za-z\s\-]+?)\s+(MSTO|MTO|STO|GBTO|GBO|SCO|LTO|ETO|MSTA|SMTO|SMTA|RDMO|SAO|SCDMEO)\b',
                 name, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def nominatim(query):
    try:
        params = urllib.parse.urlencode({'q':query,'format':'json','limit':1,'countrycodes':'ng'})
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers={'User-Agent':'NRS-myservice/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            if data:
                return float(data[0]['lat']), float(data[0]['lon']), data[0].get('display_name','')
    # catch-all: reported — returns (None, None, '') so the caller falls
    # through to the next strategy and the run's stats say which strategy
    # answered. Same limit as geocode_locations.py: a Nominatim outage is
    # indistinguishable from "no such place", and both come out as
    # state_capital coordinates in the tally.
    except:
        pass
    return None, None, ''

def geocode(loc):
    name = loc.name or ''
    street = loc.street or ''
    state = extract_state(name, street)
    city = extract_city(name)

    # S1: full address
    if street and state:
        lat,lng,dn = nominatim(f"{name}, {street}, {state}, Nigeria")
        time.sleep(1.1)
        if lat: return lat,lng,'full_address'

    # S2: name + city + state
    if city and state:
        lat,lng,dn = nominatim(f"{name}, {city}, {state}, Nigeria")
        time.sleep(1.1)
        if lat: return lat,lng,'name_city_state'

    # S3: city + state
    if city and state:
        lat,lng,dn = nominatim(f"{city}, {state}, Nigeria")
        time.sleep(1.1)
        if lat: return lat,lng,'city_state'

    # S4: state capital + small random offset
    if state and state in STATE_CAPITALS:
        cap = STATE_CAPITALS[state]
        return (cap[0]+random.uniform(-0.05,0.05),
                cap[1]+random.uniform(-0.05,0.05),
                'state_capital')

    # S5: name only
    lat,lng,dn = nominatim(f"{name}, Nigeria")
    time.sleep(1.1)
    if lat: return lat,lng,'name_only'

    return None,None,'failed'

# ── Main ──────────────────────────────────────────────────────────────
locs = env['generic.location'].search([], order='name asc')
total = len(locs)
print(f"Re-geocoding {total} locations...")

stats = {'full_address':0,'name_city_state':0,'city_state':0,
         'state_capital':0,'name_only':0,'failed':0,'skipped':0}

BATCH = 50  # commit every 50

for i, loc in enumerate(locs):
    lat, lng, method = geocode(loc)

    if lat:
        loc.write({'latitude': lat, 'longitude': lng})
        stats[method] += 1
    else:
        stats['failed'] += 1

    if (i+1) % BATCH == 0:
        env.cr.commit()
        print(f"  [{i+1}/{total}] committed — stats so far: {stats}")

env.cr.commit()
print(f"\n=== COMPLETE ===")
print(f"Total: {total}")
for k,v in stats.items():
    print(f"  {k}: {v}")
