# Read-only measurement for handoff 65 §6.1/§6.6/§7 on nrs19. Every write
# below is inside this shell's transaction and is ROLLED BACK at the end.
import time, json, collections
Sap = env['nrs.sap.asset'].sudo()
out = {}
t = time.time(); targets = Sap._confident_targets(); out['targets_seconds'] = round(time.time() - t, 2)
claims = targets['claims']
unc = [(aid, sid, b) for aid, (sid, b) in targets['target'].items() if len(claims[sid]) == 1]
out['confident'] = Sap._confident_links()
out['uncontested_pairs'] = len(unc)
out['contested_groups'] = sum(1 for v in claims.values() if len(v) > 1)
recs = {r.id: r for r in Sap.browse({s for _a, s, _b in unc})}
out['uncontested_by_office_top10'] = collections.Counter(recs[s].office_code for _a, s, _b in unc).most_common(10)
out['uncontested_by_sap_class'] = collections.Counter(recs[s].asset_class for _a, s, _b in unc).most_common()
cov0 = Sap._coverage()
def held(cov):
    act = sum(v[0] for v in cov['sap_by_class'].values()); lk = sum(v[1] for v in cov['sap_by_class'].values())
    return lk, act
out['before'] = held(cov0)
# §7: link the uncontested pairs INSIDE this transaction, as the approval writes them.
cr = env.cr
for aid, sid, b in unc:
    r = recs[sid]
    cr.execute("UPDATE nrs_asset SET sap_asset_number=%s, sap_company_code=%s, sap_code_source='linked_from_sap_mirror' WHERE id=%s",
               (r.asset_number_norm, r.company_code, aid))
env.invalidate_all()
cov1 = Sap._coverage()
out['after'] = held(cov1)
out['after_confident'] = cov1['confident']
ev = Sap._class_evidence()
cats = {c.id: c.name for c in env['nrs.asset.category'].sudo().browse([e[0] for e in ev if e[0]])}
rows = collections.defaultdict(lambda: {'configured': None, 'classes': {}})
for cat, conf, cls, n, via in ev:
    rows[cats.get(cat, 'none')]['configured'] = conf
    rows[cats.get(cat, 'none')]['classes'][cls] = n
out['class_evidence_after'] = sorted(((k, v['configured'], sorted(v['classes'].items(), key=lambda x: -x[1]), sum(v['classes'].values())) for k, v in rows.items()), key=lambda r: -r[3])
# §7 estimate: the assets left with no SAP number and no confident match.
cr.execute("""SELECT a.id, a.name, a.legacy_asset_code FROM nrs_asset a
              WHERE a.register_state='registered' AND coalesce(btrim(a.sap_asset_number),'')=''""")
left = cr.fetchall()
contested_ids = {a for v in claims.values() if len(v) > 1 for a in v}
out['left_without_sap_number'] = len(left)
out['left_of_which_contested'] = sum(1 for a in left if a[0] in contested_ids)
from odoo.addons.myservice_asset_register.models.sap_mirror import norm_tag, query_words, LINKED_EXISTS
out['left_with_old_tag'] = sum(1 for a in left if norm_tag(a[2]))
names = collections.Counter(tuple(query_words(a[1])) for a in left if a[0] not in contested_ids)
out['left_distinct_descriptions'] = len(names)
# SAP's active, unlinked records with an office vs without (office from the tag today).
cr.execute("SELECT count(*) FILTER (WHERE office_code IS NOT NULL), count(*) FROM nrs_sap_asset s WHERE sap_active AND in_latest_export AND NOT " + LINKED_EXISTS)
out['sap_unlinked_with_office_of_all'] = cr.fetchone()
cr.execute("SELECT count(DISTINCT office_code) FROM nrs_sap_asset WHERE office_code IS NOT NULL")
out['sap_offices'] = cr.fetchone()[0]
# Nationwide pool per description (whole words, the matcher's rule).
t = time.time()
pool = {}
for words in names:
    if not words:
        pool[words] = None; continue
    clause = ' AND '.join(["s.desc_words LIKE %s"] * len(words))
    cr.execute("SELECT count(*) FROM nrs_sap_asset s WHERE s.sap_active AND s.in_latest_export AND " + clause + " AND NOT " + LINKED_EXISTS,
               ['%% %s %%' % w for w in words])
    pool[words] = cr.fetchone()[0]
out['pool_seconds'] = round(time.time() - t, 1)
dist = collections.Counter()
for words, n in names.items():
    p = pool[words]
    key = 'no words' if p is None else '0' if p == 0 else '1' if p == 1 else '2-10' if p <= 10 else '11-100' if p <= 100 else '101-1000' if p <= 1000 else '>1000'
    dist[key] += n
out['left_by_nationwide_description_pool'] = dict(dist)
out['pools'] = {' '.join(w): (pool[w], n) for w, n in names.most_common(25)}
env.cr.rollback()
print("MEASURE " + json.dumps(out, default=str))
