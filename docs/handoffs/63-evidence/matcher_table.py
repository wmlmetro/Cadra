"""Handoff 63 §5.3 and §6 — report 61 §12's table, reprinted FROM THE MATCHER.

Run in an Odoo shell on a tenant whose SAP mirror is loaded (counts only;
no row of SAP's export is printed):

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo shell -c /etc/odoo/odoo.conf -d nrs19 --no-http \\
      < docs/handoffs/63-evidence/matcher_table.py

Report 61 §12 measured, from the export with a script, how often an old FIRS
tag finds one SAP record. This asks the MATCHER the same questions, record
by record — every active furniture (2000) and office-equipment (4000)
record, put to `SapMatcher.match` as if it were the item found:

* by its own old tag and description — does the matcher rank IT first, and
  is it alone at the top (`tied_at_top == 1`)?
* a shared tag by its office and description, tag ignored;
* an untagged record by its description and class, nationwide.

`candidates` is `tied_at_top`: how many records the matcher cannot tell
apart at its best score. Then §6: every Cadra asset with no SAP number put
to the matcher by its legacy asset code and serial, counting the ones
ranked first by `old_tag_unique` or `serial_unique` — the cross-check of
`GET /reports/sap-coverage`'s `reconcilable_today`, which computes the same
thing in one query.
"""
import statistics
import time

from odoo.addons.myservice_asset_register.models.sap_mirror import SapMatcher

M = SapMatcher(env)  # noqa: F821 — odoo shell
cr = env.cr  # noqa: F821
t0 = time.time()
_memo = {}


def ask(**query):
    """`M.match`, asked once per distinct question: the matcher's answer to
    the same query is the same answer (a nationwide description search is a
    scan of the class, ~190 ms on `nrs19`, and 19,000 untagged records share
    far fewer descriptions)."""
    key = tuple(sorted(query.items()))
    if key not in _memo:
        _memo[key] = M.match(**query)
    return _memo[key]


def stats(values):
    if not values:
        return "—"
    return "mean %.2f, median %s, max %d" % (
        statistics.mean(values), statistics.median(values), max(values))


def words(*texts):
    return " ".join(t for t in texts if t)


print("SAP mirror on %s: %d records" % (cr.dbname, env["nrs.sap.asset"].search_count([])))  # noqa: F821
rows = {}
for cls in ("2000", "4000"):
    cr.execute("""SELECT id, old_tag_norm, office_code, description,
                         description_2
                    FROM nrs_sap_asset
                   WHERE sap_active AND in_latest_export AND asset_class = %s
                   ORDER BY id""", [cls])
    recs = cr.fetchall()
    tagged = [r for r in recs if r[1]]
    cr.execute("""SELECT old_tag_norm, count(*) FROM nrs_sap_asset
                   WHERE sap_active AND in_latest_export
                     AND old_tag_norm IS NOT NULL GROUP BY 1""")
    share = dict(cr.fetchall())
    unique = [r for r in tagged if share[r[1]] == 1]
    shared = [r for r in tagged if share[r[1]] > 1]
    firs = [r for r in tagged if r[2]]
    ends_on_one, tag_desc, office_desc, untagged = 0, [], [], []
    one_left = 0
    reasons = {}
    for sid, tag, office, d1, d2 in tagged:
        a = M.match(old_tag=tag, description=words(d1, d2))
        top = a["results"][0] if a["results"] else None
        if top:
            reasons[top["reason_code"]] = reasons.get(top["reason_code"], 0) + 1
        if top and top["id"] == sid and a["tied_at_top"] == 1:
            ends_on_one += 1
        if share[tag] > 1:
            tag_desc.append(a["tied_at_top"])
            if a["tied_at_top"] == 1:
                one_left += 1
            if office:
                b = ask(description=words(d1, d2), asset_class=cls,
                        office=office)
                office_desc.append(b["tied_at_top"])
    for sid, tag, office, d1, d2 in recs:
        if not tag:
            c = ask(description=words(d1, d2), asset_class=cls)
            untagged.append(c["tied_at_top"])
    # A shared tag made unique by the office: records sharing a whole tag
    # share its office, by construction (the office is inside the tag).
    by_tag_office = {}
    for r in shared:
        by_tag_office.setdefault(r[1], set()).add(r[2])
    made_unique = sum(1 for offices in by_tag_office.values()
                      if len(offices) > 1)
    rows[cls] = {
        "active records": len(recs),
        "has an old tag": "%d of %d (%.1f%%)" % (
            len(tagged), len(recs), 100.0 * len(tagged) / len(recs)),
        "tag unique among active records (matcher: old_tag_unique)":
            "%d of %d tagged (%.1f%%) — %.1f%% of active" % (
                len(unique), len(tagged), 100.0 * len(unique) / len(tagged),
                100.0 * len(unique) / len(recs)),
        "tag follows FIRS/<office>/…": "%d of %d (%.1f%%)" % (
            len(firs), len(tagged), 100.0 * len(firs) / len(tagged)),
        "a shared tag made unique by the office":
            "%d of %d shared tags" % (made_unique, len(by_tag_office)),
        "shared tag: candidates by tag + description (tied_at_top)":
            "%s; one left for %d of %d (%.1f%%)" % (
                stats(tag_desc), one_left, len(shared),
                100.0 * one_left / len(shared) if shared else 0),
        "shared tag: candidates by office + description, tag ignored":
            stats(office_desc),
        "no tag: candidates by description and class, nationwide":
            "%d records: %s" % (len(untagged), stats(untagged)),
        "ends on one record by tag (+ description)": "%d of %d (%.1f%%)" % (
            ends_on_one, len(recs), 100.0 * ends_on_one / len(recs)),
        "first result's reason (tagged records)": reasons,
    }
    print("class %s done in %.0f s" % (cls, time.time() - t0), flush=True)

print()
print("%-62s | %s | %s" % ("", "Furniture (2000)", "Office equipment (4000)"))
for key in rows["2000"]:
    print("%-62s | %s | %s" % (key, rows["2000"][key], rows["4000"][key]))

# §6 — the Cadra assets with no SAP number, one matcher call each.
cr.execute("""SELECT id, legacy_asset_code, serial_number FROM nrs_asset
               WHERE register_state = 'registered'
                 AND coalesce(btrim(sap_asset_number), '') = ''""")
assets = cr.fetchall()
first = {}
target = {}
for aid, legacy, serial in assets:
    if not (legacy or serial):
        continue
    a = M.match(old_tag=legacy, serial=serial)
    top = a["results"][0] if a["results"] else None
    if top and top["reason_code"] in ("old_tag_unique", "serial_unique"):
        first[top["reason_code"]] = first.get(top["reason_code"], 0) + 1
        target.setdefault(top["id"], []).append(aid)
contested = sum(len(v) for v in target.values() if len(v) > 1)
print()
print("§6: %d Cadra assets on the register with no SAP number; the matcher "
      "ranks %d first by old_tag_unique and %d by serial_unique (%d), onto "
      "%d SAP records; %d of them share their SAP record with another Cadra "
      "asset; %d uncontested." % (
          len(assets), first.get("old_tag_unique", 0),
          first.get("serial_unique", 0), sum(first.values()), len(target),
          contested, sum(first.values()) - contested))
print("coverage report says: %s" % env["nrs.sap.asset"]._confident_links())  # noqa: F821
print("total %.0f s" % (time.time() - t0))
