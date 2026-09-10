import time
import socket
import urllib.request
import urllib.error
import urllib.parse
import json
import random

print()
print("=" * 70)
print("  GEOCODE LOCATIONS — OpenStreetMap Nominatim")
print("=" * 70)

STATE_FALLBACK = {
    'Abia': (5.4527, 7.5248), 'Adamawa': (9.3265, 12.3984),
    'Akwa Ibom': (5.0377, 7.9128), 'Anambra': (6.2101, 6.9971),
    'Bauchi': (10.3158, 9.8442), 'Bayelsa': (4.9267, 6.2676),
    'Benue': (7.7337, 8.5374), 'Borno': (11.8333, 13.1500),
    'Cross River': (4.9517, 8.3220), 'Delta': (5.5320, 5.8987),
    'Ebonyi': (6.3249, 8.1137), 'Edo': (6.3350, 5.6037),
    'Ekiti': (7.7190, 5.3110), 'Enugu': (6.4584, 7.5464),
    'FCT': (9.0765, 7.3986), 'Federal Capital Territory': (9.0765, 7.3986),
    'Gombe': (10.2897, 11.1673), 'Imo': (5.4836, 7.0333),
    'Jigawa': (12.2280, 9.5616), 'Kaduna': (10.5105, 7.4165),
    'Kano': (12.0022, 8.5920), 'Katsina': (12.9889, 7.6006),
    'Kebbi': (12.4539, 4.1975), 'Kogi': (7.7337, 6.6906),
    'Kwara': (8.4966, 4.5421), 'Lagos': (6.5244, 3.3792),
    'Nassarawa': (8.5378, 8.3206), 'Nasarawa': (8.5378, 8.3206),
    'Niger': (9.6139, 6.5569), 'Ogun': (7.1603, 3.3480),
    'Ondo': (7.2500, 5.1933), 'Osun': (7.7827, 4.5418),
    'Oyo': (7.3775, 3.9470), 'Plateau': (9.2182, 9.5179),
    'Rivers': (4.8396, 6.9112), 'Sokoto': (13.0059, 5.2476),
    'Taraba': (7.8704, 11.3609), 'Yobe': (12.2939, 11.4390),
    'Zamfara': (12.1704, 6.6616),
}

HEADERS = {
    'User-Agent': 'myservice-nrs-geocoder/1.0 (facilities@nrs.gov.ng)',
    'Accept-Language': 'en',
}

# ── Three outcomes, not two ───────────────────────────────────────────────
#
# The old code had one failure column. Anything that was not a coordinate came
# back as `None`, and `None` meant "write the state capital plus noise and call
# it a fallback". So a 403 rate-limit or a dropped connection — conditions in
# which this script knows NOTHING about where anything is — produced plausible
# coordinates for the entire estate, tallied as fallbacks.
#
# A place that does not exist and a service that did not answer are different
# answers and are kept apart from here on:
#
#   OK          the service answered and had a match.
#   NOT_FOUND   the service answered and had no match (empty list, or 404).
#               The jittered state-capital approximation is honest here, and
#               it now stamps itself in `geocode_source`.
#   UNREACHABLE we did not get an ANSWER — network error, timeout, any other
#               HTTP status, a body that is not JSON, or a JSON body with no
#               usable coordinate in it. Nothing is written. Not the
#               fallback, not anything.
OK = 'ok'
NOT_FOUND = 'not_found'
UNREACHABLE = 'unreachable'

# The value written into `generic.location.geocode_source` when the service
# answered "no such place" and we wrote a state capital instead. Kept in step
# with myservice_nrs_base/models/generic_location.py; the preflight below
# refuses to run if the field or the value is not there.
SOURCE_APPROXIMATE = 'state_capital_approx'

# A run stops after this many locations in a row come back unreachable.
#
# Five, because a single unreachable answer is ordinary — one dropped
# connection, one socket timeout — but this loop sleeps a second between calls
# and makes up to two calls per location, so five consecutive failures is
# fifteen-odd seconds of nothing but errors. That is not a property of the five
# places; it is the service being down or rate-limiting us. Grinding through
# thousands of locations against a 403 writes nothing, takes hours, and buries
# the one line that mattered under thousands that did not.
MAX_CONSECUTIVE_UNREACHABLE = 5


def _classify(exc):
    """Map an exception from the geocoding call onto NOT_FOUND / UNREACHABLE.

    Only one thing here is a real answer: a 404 is the service saying it has no
    such resource. Every other exception means the question was never answered,
    whatever it looks like — a 403 in particular is Nominatim's rate limit, and
    reading it as "no such place" is how an outage used to become coordinates.
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
        # json.JSONDecodeError subclasses ValueError. A body that is not JSON
        # is a proxy error page or a captive portal, not an answer.
        return UNREACHABLE, f'unreadable response: {exc}'
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return UNREACHABLE, f'response had no usable coordinate: {exc!r}'
    return UNREACHABLE, f'{type(exc).__name__}: {exc}'


def nominatim_geocode(name, state_name):
    """Return (status, coords, strategy, reason).

    `coords` is a (lat, lng) pair only when status is OK. `strategy` names the
    query that answered, and is written into `geocode_source` so the database
    records how precisely the question was posed.

    An UNREACHABLE answer to the first query returns immediately rather than
    trying the second: if the service is down, the second query is down too,
    and the only thing another call buys is another second of delay.
    """
    queries = [
        (f"{name}, {state_name}, Nigeria", 'name_state'),
        (f"{name}, Nigeria", 'name_only'),
    ]
    for query, strategy in queries:
        try:
            params = urllib.parse.urlencode({'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'ng'})
            url = f"https://nominatim.openstreetmap.org/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data:
                return OK, (float(data[0]['lat']), float(data[0]['lon'])), strategy, ''
            # An empty list IS an answer: the service looked and found nothing.
        except KeyboardInterrupt:
            raise
        # catch-all: reported — every exception is classified by `_classify()`
        # into NOT_FOUND (only a 404: the service answered) or UNREACHABLE
        # (everything else: no answer), and an UNREACHABLE returns immediately
        # so the caller writes NOTHING. Nothing is swallowed and nothing
        # silently becomes a coordinate — which is the whole point of the
        # change. The net stays broad on purpose: a geocoder that dies on one
        # unanticipated exception halfway through the estate is worse than one
        # that records that location as unreachable and carries on.
        except Exception as exc:
            status, reason = _classify(exc)
            if status == UNREACHABLE:
                return UNREACHABLE, None, strategy, reason
        time.sleep(1)
    return NOT_FOUND, None, '', ''


def get_state_fallback(loc):
    state = loc.state_name or ''
    if state in STATE_FALLBACK:
        return STATE_FALLBACK[state]
    for key, coords in STATE_FALLBACK.items():
        if key.lower() in state.lower() or state.lower() in key.lower():
            return coords
    parent = loc.parent_id
    while parent:
        if parent.state_name in STATE_FALLBACK:
            return STATE_FALLBACK[parent.state_name]
        parent = parent.parent_id
    return None


# ── Preflight ─────────────────────────────────────────────────────────────
#
# The provenance field lives in myservice_nrs_base and reaches a tenant only
# through `odoo -u myservice_nrs_base` on that database. A run against a tenant
# that has not been upgraded would write coordinates with no statement of where
# they came from — which is the state this script exists to stop producing — so
# it refuses to start instead of degrading quietly.
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
    value for value, _label in env['generic.location']
    .fields_get(['geocode_source'])['geocode_source']['selection']
}
# The same refusal `regeocode_runner.py` makes, and for a sharper reason here:
# the fallback branch below writes SOURCE_APPROXIMATE unconditionally, and it
# commits after every single location. If the value has drifted, checking only
# that the FIELD exists means the run dies on an ORM ValueError at the first
# not-found place — partway through an estate it has already half-written,
# leaving the coordinates it did write and no way to tell how far it got
# without reading the log. A preflight that refuses up front costs nothing.
if SOURCE_APPROXIMATE not in _allowed_sources:
    raise SystemExit(
        f"`geocode_source` on this database has no `{SOURCE_APPROXIMATE}` "
        f"value (it has: {sorted(_allowed_sources)}).\n"
        "The approximation would be written with no way to tell it from a "
        "real geocode. Refusing to run."
    )

locations = env['generic.location'].search([])
locations = locations.filtered(lambda l: not l.latitude and not l.longitude)
print(f"\nLocations needing geocoding: {len(locations)}")
print(f"Estimated time: ~{len(locations)//60} min {len(locations)%60} sec\n")

geocoded = fallback = failed = unreachable = 0
by_strategy = {}
consecutive_unreachable = 0
aborted = False
processed = 0

for i, loc in enumerate(locations, 1):
    name = loc.name or ''
    state = loc.state_name or ''
    print(f"[{i:3d}/{len(locations)}] {name[:40]:<40} {state[:12]:<12}", end=' ', flush=True)

    status, coords, strategy, reason = nominatim_geocode(name, state)
    time.sleep(1)
    processed = i

    if status == UNREACHABLE:
        # Nothing is written. We have no information about this location, and a
        # coordinate invented from no information is worse than none at all.
        print(f"! UNREACHABLE — {reason} (nothing written)")
        unreachable += 1
        consecutive_unreachable += 1
        if consecutive_unreachable >= MAX_CONSECUTIVE_UNREACHABLE:
            aborted = True
            break
        continue

    consecutive_unreachable = 0

    if status == OK:
        lat, lng = coords
        source = strategy if strategy in _allowed_sources else False
        loc.sudo().write({'latitude': lat, 'longitude': lng, 'geocode_source': source})
        env.cr.commit()
        print(f"✓ {lat:.4f}, {lng:.4f} [{strategy}]")
        geocoded += 1
        by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
    else:
        fb = get_state_fallback(loc)
        if fb:
            lat = fb[0] + random.uniform(-0.05, 0.05)
            lng = fb[1] + random.uniform(-0.05, 0.05)
            # The approximation stamps itself in the SAME write as the
            # coordinates: a state capital plus noise that does not say so is
            # indistinguishable from a real fix on the building.
            loc.sudo().write({
                'latitude': lat,
                'longitude': lng,
                'geocode_source': SOURCE_APPROXIMATE,
            })
            env.cr.commit()
            print(f"~ approximate (state capital) {lat:.4f}, {lng:.4f}")
            fallback += 1
        else:
            print("✗ NOT FOUND — no state fallback, nothing written")
            failed += 1

if aborted:
    remaining = len(locations) - processed
    print()
    print("!" * 70)
    print(f"  ABORTED — {MAX_CONSECUTIVE_UNREACHABLE} consecutive unreachable "
          f"responses from Nominatim.")
    print(f"  The service is down, rate-limiting us, or unreachable from here.")
    print(f"  NO coordinates were written for the remaining {remaining} "
          f"location(s), and none were guessed.")
    print(f"  Re-run when the service answers; already-geocoded rows are "
          f"skipped.")
    print("!" * 70)

print(f"\n{'='*70}")
print(f"  Geocoded (service found the place): {geocoded}")
for strategy, count in sorted(by_strategy.items()):
    print(f"      {strategy}: {count}")
print(f"  Approximated (no such place — state capital written): {fallback}")
print(f"  Not found, no fallback available (nothing written): {failed}")
print(f"  Unreachable (no answer — nothing written): {unreachable}")
total = env['generic.location'].search_count([('latitude', '!=', 0.0)])
print(f"  Locations with coords: {total} / {env['generic.location'].search_count([])}")
print(f"{'='*70}")
