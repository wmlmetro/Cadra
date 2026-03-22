import time
import urllib.request
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

def nominatim_geocode(name, state_name):
    queries = [
        f"{name}, {state_name}, Nigeria",
        f"{name}, Nigeria",
    ]
    for query in queries:
        try:
            params = urllib.parse.urlencode({'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'ng'})
            url = f"https://nominatim.openstreetmap.org/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
        except Exception:
            pass
        time.sleep(1)
    return None

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

locations = env['generic.location'].search([]) 
locations = locations.filtered(lambda l: not l.latitude and not l.longitude)
print(f"\nLocations needing geocoding: {len(locations)}")
print(f"Estimated time: ~{len(locations)//60} min {len(locations)%60} sec\n")

geocoded = fallback = failed = 0

for i, loc in enumerate(locations, 1):
    name = loc.name or ''
    state = loc.state_name or ''
    print(f"[{i:3d}/{len(locations)}] {name[:40]:<40} {state[:12]:<12}", end=' ', flush=True)

    result = nominatim_geocode(name, state)
    time.sleep(1)

    if result:
        lat, lng = result
        loc.sudo().write({'latitude': lat, 'longitude': lng})
        env.cr.commit()
        print(f"✓ {lat:.4f}, {lng:.4f}")
        geocoded += 1
    else:
        fb = get_state_fallback(loc)
        if fb:
            lat = fb[0] + random.uniform(-0.05, 0.05)
            lng = fb[1] + random.uniform(-0.05, 0.05)
            loc.sudo().write({'latitude': lat, 'longitude': lng})
            env.cr.commit()
            print(f"~ fallback {lat:.4f}, {lng:.4f}")
            fallback += 1
        else:
            print("✗ FAILED")
            failed += 1

print(f"\n{'='*70}")
print(f"  Done: {geocoded} geocoded | {fallback} fallback | {failed} failed")
total = env['generic.location'].search_count([('latitude','!=',0.0)])
print(f"  Locations with coords: {total} / {env['generic.location'].search_count([])}")
print(f"{'='*70}")
