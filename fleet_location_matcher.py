"""
Fleet vehicle → FIRS location matcher.
Strategy:
1. Parse vehicle.location field (format: "FULL NAME | SHORT NAME")
2. Try exact match against generic.location names
3. Try keyword matching (extract key tokens, find best overlap)
4. Try state-scoped matching using SCO tag (SCO:FCT → only FCT locations)
5. Manual review list for low-confidence matches
"""
import re
import collections

# ── SCO tag → Nigerian state mapping ─────────────────────────────────
SCO_STATE_MAP = {
    'SCO:FCT': ['FCT','Abuja','Garki','Wuse','Maitama','Kubwa','Gwarimpa',
                'Gwagwalada','Lugbe','Central'],
    'SCO:RED': ['Rivers','Port Harcourt','Rumukwurushi','Rumueme','Bonny',
                'Onne','Ahoada'],
    'SCO:IA':  ['Anambra','Enugu','Imo','Abia','Ebonyi','Nnewi','Onitsha',
                'Awka','Owerri','Umuahia','Abakaliki','Nsukka'],
    'SCO:JKK': ['Kaduna','Kano','Katsina','Kogi','Kebbi','Kwara','Zamfara',
                'Sokoto','Jigawa','Zaria','Funtua','Dutse','Birnin'],
    'SCO:KEO': ['Ekiti','Kwara','Ondo','Osun','Oyo','Ogun','Ibadan',
                'Akure','Ado','Ilorin','Abeokuta','Osogbo','Ife'],
    'SCO:LI':  ['Lagos Island','Ikoyi','Victoria','Onikan','Bar Beach',
                'Broadstreet','Ajah','Epe'],
    'SCO:LME': ['Lagos Mainland East','Ikeja','Agege','Ikorodu','Alimosho',
                'Isolo','Mushin','Yaba','Ilupeju'],
    'SCO:LMW': ['Lagos Mainland West','Apapa','Surulere','Festac','Orile',
                'Alaba','Aguda','Badagry'],
    'SCO:BKP': ['Kaduna','Plateau','Nasarawa','Benue','Niger','Abuja',
                'Jos','Makurdi','Minna','Lafia'],
    'SCO:BBY': ['Borno','Bauchi','Yobe','Adamawa','Taraba','Gombe',
                'Maiduguri','Bauchi','Damaturu','Jalingo','Gombe'],
    'SCO:OOO': ['Oyo','Ogun','Osun','Ibadan','Abeokuta','Sagamu','Ota'],
    'SCO:NKN': ['Niger','Kogi','Nasarawa','Kwara','Lokoja','Minna'],
}

def tokenise(text):
    """Extract meaningful tokens from a location string."""
    text = text.upper()
    # Remove common suffixes/prefixes that don't help matching
    stopwords = {'MSTO','MTO','MSTA','SMTO','SMTA','GBTO','GBO','GBA',
                 'SCO','LTO','ETO','ETA','SAO','RDMO','STO','SCDMEO',
                 'AD','DD','TC','HEAD','IRS','FIRS','NRS','POOL',
                 'THE','OF','AND','FOR','IN','AT','II','I','2','1',
                 'UNIT','DEPT','DEPARTMENT','REGIONAL','AREA'}
    tokens = set(re.split(r'[\s/\-,|\.&]+', text))
    tokens = {t for t in tokens if t and len(t) > 2 and t not in stopwords}
    return tokens

def match_score(vehicle_tokens, loc_tokens):
    """Score overlap between vehicle location tokens and FIRS location name."""
    if not vehicle_tokens or not loc_tokens:
        return 0
    overlap = vehicle_tokens & loc_tokens
    return len(overlap) / max(len(vehicle_tokens), 1)

def get_state_hint(tag_name):
    """Return keywords for filtering locations by SCO tag."""
    return SCO_STATE_MAP.get(tag_name, [])

# ── Main matching ─────────────────────────────────────────────────────
vehicles = env['fleet.vehicle'].search([
    ('home_location_id','=', False),
    ('location','!=', False),
    ('location','!=', ''),
], limit=0)

all_locs = env['generic.location'].search([])
print(f"Vehicles to match: {len(vehicles)}")
print(f"FIRS locations available: {len(all_locs)}")

# Pre-tokenise all FIRS locations
loc_tokens = {}
for loc in all_locs:
    loc_tokens[loc.id] = tokenise(loc.name)

matched      = 0
low_conf     = 0
unmatched    = 0
results      = []

for v in vehicles:
    raw_loc = (v.location or '').split('|')[0].strip()
    if not raw_loc or raw_loc in ('NEW SUPPLY','GROUNDED','UNDERGOING REPAIRS',
                                   'Disband office',''):
        results.append((v, None, 0, 'skip'))
        continue

    vtokens = tokenise(raw_loc)
    tag_name = v.tag_ids[0].name if v.tag_ids else ''
    state_hints = get_state_hint(tag_name)

    # Score all locations
    scores = []
    for loc in all_locs:
        # Boost score if location name contains state hint keywords
        base = match_score(vtokens, loc_tokens[loc.id])
        boost = 0
        if state_hints:
            loc_upper = loc.name.upper()
            if any(h.upper() in loc_upper for h in state_hints):
                boost = 0.1
        scores.append((loc, base + boost))

    scores.sort(key=lambda x: -x[1])
    best_loc, best_score = scores[0] if scores else (None, 0)

    if best_score >= 0.4:
        results.append((v, best_loc, best_score, 'high'))
        matched += 1
    elif best_score >= 0.2:
        results.append((v, best_loc, best_score, 'low'))
        low_conf += 1
    else:
        results.append((v, None, best_score, 'none'))
        unmatched += 1

print(f"\nHigh confidence (>=0.4): {matched}")
print(f"Low confidence (0.2-0.4): {low_conf}")
print(f"No match (<0.2):          {unmatched}")

# Apply high confidence matches
applied = 0
for v, loc, score, conf in results:
    if conf == 'high' and loc:
        v.write({'home_location_id': loc.id})
        applied += 1

env.cr.commit()
print(f"\nApplied {applied} high-confidence matches to DB")

# Show sample of low confidence for review
print("\n=== Low confidence — needs review ===")
for v, loc, score, conf in results:
    if conf == 'low' and loc:
        print(f"  {v.license_plate:20} | {(v.location or '').split('|')[0].strip()[:30]:30} "
              f"→ {loc.name[:35]:35} | score={score:.2f} | tag={v.tag_ids[0].name if v.tag_ids else ''}")

# Show sample unmatched
print(f"\n=== Unmatched (first 20) ===")
count = 0
for v, loc, score, conf in results:
    if conf == 'none':
        print(f"  {v.license_plate:20} | {(v.location or '').split('|')[0].strip()[:40]}")
        count += 1
        if count >= 20:
            break

# Summary stats
print(f"\n=== Final state ===")
print(f"Vehicles with location now: {env['fleet.vehicle'].search_count([('home_location_id','!=',False)])}")
print(f"Vehicles still unmatched:   {env['fleet.vehicle'].search_count([('home_location_id','=',False)])}")
