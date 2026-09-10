#!/usr/bin/env python3
"""
Odoo shell runner for re-geocoding NRS locations.
Run as: sudo -u odoo python3 /opt/odoo/odoo/odoo-bin shell \
    -c /etc/odoo/odoo.conf -d myservice --no-http < regeocode_runner.py

Every coordinate this script writes also records HOW it was obtained, in
`generic.location.geocode_source` (myservice_nrs_base). A jittered state
capital and a real fix on the building look identical on a map, and a reader
who cannot tell them apart reconciles against the wrong one — see the module
docstring in myservice_nrs_base/models/generic_location.py.

And a geocoder that cannot REACH its service writes nothing at all: an outage
or a 403 rate-limit used to be indistinguishable from "no such place", so a
total outage produced plausible coordinates for the whole estate, reported as
state_capital fallbacks.
"""
import sys
import time
import re
import json
import socket
import urllib.request
import urllib.error
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

# ── Three outcomes from the service, not two ──────────────────────────
#
#   OK          it answered and had a match.
#   NOT_FOUND   it answered and had no match — an empty result list, or a 404.
#               Falling through to the next strategy, and ultimately to the
#               state-capital approximation, is honest here.
#   UNREACHABLE we did not get an ANSWER: network error, timeout, any other
#               HTTP status (403 rate-limit above all), a body that is not
#               JSON, or a JSON body with no usable coordinate. NOTHING is
#               written for that location and the state-capital fallback is
#               NOT reached — an outage tells us nothing about where a
#               building is, and a coordinate invented from nothing is the
#               defect this classification exists to remove.
OK = 'ok'
NOT_FOUND = 'not_found'
UNREACHABLE = 'unreachable'

# Written into `generic.location.geocode_source` when the service answered "no
# such place" and a jittered state capital was written instead. Must match
# myservice_nrs_base/models/generic_location.py; the preflight below refuses to
# run if it does not.
SOURCE_APPROXIMATE = 'state_capital_approx'

# Stop the run after this many locations in a row come back unreachable.
#
# Five. One unreachable answer is ordinary — a dropped connection, a slow DNS
# lookup — and the loop already sleeps 1.1s between calls and may make four
# calls per location, so five consecutive failures is the best part of a minute
# in which the service answered nothing at all. That is the service, not those
# five places. The alternative is walking 11,000 locations against a 403,
# writing nothing, for hours, printing thousands of lines nobody will read.
MAX_CONSECUTIVE_UNREACHABLE = 5


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

def _classify(exc):
    """Map an exception from the HTTP call onto NOT_FOUND / UNREACHABLE.

    A 404 is the only status that is an answer about the PLACE; everything else
    is an answer about the service, or no answer at all. A 403 is Nominatim's
    rate limit and reading it as "no such place" is precisely how an outage
    used to turn into state-capital coordinates for the whole estate.
    """
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return NOT_FOUND, 'HTTP 404'
        return UNREACHABLE, f'HTTP {exc.code} {exc.reason}'
    if isinstance(exc, urllib.error.URLError):
        return UNREACHABLE, f'network error: {exc.reason}'
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return UNREACHABLE, 'timed out'
    if isinstance(exc, ValueError):
        # json.JSONDecodeError subclasses ValueError: a body that is not JSON
        # is a proxy error page, not an answer.
        return UNREACHABLE, f'unreadable response: {exc}'
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return UNREACHABLE, f'response had no usable coordinate: {exc!r}'
    return UNREACHABLE, f'{type(exc).__name__}: {exc}'


def nominatim(query):
    """Return (status, coords, reason). `coords` is (lat, lng) only when OK.

    This used to be a bare `except:` returning `(None, None, '')`. Two things
    were wrong with it: it swallowed KeyboardInterrupt, so the only way to stop
    a long run was to kill the process; and it collapsed "no such place" and "no
    answer" into one value that the caller read as the former.
    """
    try:
        params = urllib.parse.urlencode({'q':query,'format':'json','limit':1,'countrycodes':'ng'})
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers={'User-Agent':'NRS-myservice/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data:
            return OK, (float(data[0]['lat']), float(data[0]['lon'])), ''
        # An empty list is an ANSWER: the service looked and found nothing.
        return NOT_FOUND, None, ''
    except KeyboardInterrupt:
        raise
    # catch-all: reported — `_classify()` sorts every exception into NOT_FOUND
    # (a 404, the one status that is an answer about the place) or UNREACHABLE
    # (everything else: no answer at all). The status is returned, counted in
    # `stats`, printed with its reason, and an UNREACHABLE writes nothing and
    # never reaches the state-capital fallback. Nothing is swallowed and no
    # error becomes a coordinate. Deliberately broad, with a fall-through in
    # `_classify` for the unanticipated: dying mid-estate on one strange
    # exception is worse than recording that location as unreachable.
    except Exception as exc:
        status, reason = _classify(exc)
        return status, None, reason


def geocode(loc):
    """Return (status, coords, method, reason).

    `method` is the value written into `geocode_source`: one of the strategy
    names when the service found the place, or `state_capital_approx` when it
    answered "no such place" and a jittered capital was substituted.

    **The service is asked at least one real question before anything is
    approximated.** The three precise strategies can only be built from a
    street or a recognised city, so a location with neither — a name carrying
    a state and nothing else — fell through an EMPTY ladder straight to the
    state-capital fallback and was stamped `state_capital_approx`, a value
    whose published meaning is "the service was reachable, answered, and had
    no such place". It had not been asked anything. Zero HTTP calls, and a
    provenance statement that was not true. The name-only query is now the
    ladder's last rung whenever no stronger question can be posed, so every
    approximation is preceded by an actual answer.

    The ORDER is otherwise unchanged, including S4 (state capital) coming
    before a bare name match: where a PRECISE question was asked and came back
    "no such place", an approximation in the right state beats a name match
    that could land anywhere in Nigeria — the approximation announces itself in
    `geocode_source` and a wrong name match does not. The weakest question is
    asked only when it is the only question available.

    And ANY unreachable answer stops the ladder immediately and returns
    UNREACHABLE — the next strategy would be asking a service that is not
    answering, and the fallback at the bottom of the ladder must not be
    reached by an outage.
    """
    name = loc.name or ''
    street = loc.street or ''
    state = extract_state(name, street)
    city = extract_city(name)

    # S1: full address / S2: name + city + state / S3: city + state
    ladder = []
    if street and state:
        ladder.append((f"{name}, {street}, {state}, Nigeria", 'full_address'))
    if city and state:
        ladder.append((f"{name}, {city}, {state}, Nigeria", 'name_city_state'))
        ladder.append((f"{city}, {state}, Nigeria", 'city_state'))
    if not ladder:
        # S5, as the ladder's last rung rather than as code below the
        # fallback that a location with a state could never reach. Nothing
        # else can be asked about this location, and asking the weak question
        # is strictly better than approximating without asking any.
        ladder.append((f"{name}, Nigeria", 'name_only'))

    for query, method in ladder:
        status, coords, reason = nominatim(query)
        time.sleep(1.1)
        if status == UNREACHABLE:
            return UNREACHABLE, None, '', reason
        if status == OK:
            return OK, coords, method, ''

    # S4: state capital + small random offset. Reached only because the service
    # ANSWERED every question that could be posed about this location and had
    # nothing — never because it failed to answer, and never without asking.
    if state and state in STATE_CAPITALS:
        cap = STATE_CAPITALS[state]
        return (NOT_FOUND,
                (cap[0]+random.uniform(-0.05,0.05),
                 cap[1]+random.uniform(-0.05,0.05)),
                'state_capital', '')

    return NOT_FOUND, None, 'failed', ''

# ── Preflight ─────────────────────────────────────────────────────────
#
# `geocode_source` reaches a tenant only via `odoo -u myservice_nrs_base` on
# that database. Running against a tenant that has not been upgraded would
# write coordinates carrying no statement of where they came from — the state
# this script exists to stop producing — so it refuses to start rather than
# degrade quietly.
_loc_fields = env['generic.location']._fields
if 'geocode_source' not in _loc_fields:
    raise SystemExit(
        "generic.location has no `geocode_source` field on this database.\n"
        "Upgrade myservice_nrs_base on this tenant first:\n"
        "  odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_nrs_base "
        "--stop-after-init --http-port=8099 --gevent-port=8098\n"
        "Refusing to write coordinates that cannot say where they came from."
    )
# `fields_get`, not `dict(field.selection)` — see the handoff 05 ruling:
# `.selection` is a callable on a related Selection and dict() of it raises.
_allowed_sources = {
    v for v, _l in env['generic.location']
    .fields_get(['geocode_source'])['geocode_source']['selection']
}
if SOURCE_APPROXIMATE not in _allowed_sources:
    raise SystemExit(
        f"`geocode_source` on this database has no `{SOURCE_APPROXIMATE}` "
        f"value (it has: {sorted(_allowed_sources)}).\n"
        "The approximation would be written with no way to tell it from a "
        "real geocode. Refusing to run."
    )

# ── Main ──────────────────────────────────────────────────────────────
locs = env['generic.location'].search([], order='name asc')
total = len(locs)
print(f"Re-geocoding {total} locations...")

# `state_capital` counts APPROXIMATIONS — the service answered and had no such
# place. `failed` counts a not-found with no fallback available, so nothing was
# written. `unreachable` counts locations we got no answer about at all;
# nothing was written for those either, and crucially they were NOT quietly
# turned into state_capital rows, which is what used to happen.
stats = {'full_address':0,'name_city_state':0,'city_state':0,
         'state_capital':0,'name_only':0,'failed':0,'skipped':0,
         'unreachable':0}

BATCH = 50  # commit every 50

consecutive_unreachable = 0
aborted = False
last_reason = ''
processed = 0

for i, loc in enumerate(locs):
    status, coords, method, reason = geocode(loc)
    processed = i + 1

    if status == UNREACHABLE:
        # Nothing written. No coordinate, no source, no fallback.
        stats['unreachable'] += 1
        consecutive_unreachable += 1
        last_reason = reason
        print(f"  [{i+1}/{total}] {(loc.name or '')[:40]} — UNREACHABLE: "
              f"{reason} (nothing written)")
        if consecutive_unreachable >= MAX_CONSECUTIVE_UNREACHABLE:
            aborted = True
            break
        continue

    consecutive_unreachable = 0

    if coords:
        source = method if method in _allowed_sources else (
            SOURCE_APPROXIMATE if method == 'state_capital' else False)
        # The source is stamped in the SAME write as the coordinates. A pair of
        # floats that arrives without its provenance is exactly the ambiguity
        # the field exists to remove, and a second write could fail alone.
        loc.write({'latitude': coords[0], 'longitude': coords[1],
                   'geocode_source': source})
        stats[method] += 1
    else:
        stats['failed'] += 1

    if (i+1) % BATCH == 0:
        env.cr.commit()
        print(f"  [{i+1}/{total}] committed — stats so far: {stats}")

env.cr.commit()

if aborted:
    remaining = total - processed
    print()
    print("!" * 70)
    print(f"  ABORTED after {MAX_CONSECUTIVE_UNREACHABLE} consecutive "
          f"unreachable responses (last: {last_reason}).")
    print(f"  Nominatim is down, rate-limiting us, or unreachable from here.")
    print(f"  NO coordinates were written for the remaining {remaining} "
          f"location(s), and none were guessed.")
    print(f"  Everything written before the abort is committed; re-run when "
          f"the service answers.")
    print("!" * 70)

print(f"\n=== {'ABORTED' if aborted else 'COMPLETE'} ===")
print(f"Total locations: {total} (attempted: {processed})")
print("  Geocoded — the service found the place:")
for k in ('full_address','name_city_state','city_state','name_only'):
    print(f"      {k}: {stats[k]}")
print(f"  Approximated — no such place, state capital written: "
      f"{stats['state_capital']}")
print(f"  Not found, no fallback available (nothing written): {stats['failed']}")
print(f"  Unreachable — no answer, nothing written: {stats['unreachable']}")
print(f"  Skipped: {stats['skipped']}")
