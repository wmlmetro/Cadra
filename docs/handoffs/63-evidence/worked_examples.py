"""Handoff 63 §5.3 — five worked examples, one per ranking reason, DESCRIBED
BY SHAPE, never by value (59's rule: no identifier of NRS's register enters
the repository). Run in an Odoo shell on a tenant whose mirror is loaded:

    ... odoo shell -c /etc/odoo/odoo.conf -d nrs19 --no-http \\
        < docs/handoffs/63-evidence/worked_examples.py

For each reason it picks the first active furniture record (by id) whose own
old tag / serial / description produces that reason, asks the matcher, and
prints the query's SHAPE (letters as X, digits as n), the pool, the ties and
each result's reason. Numbers and descriptions are never printed.
"""
import re

from odoo.addons.myservice_asset_register.models.sap_mirror import SapMatcher

M = SapMatcher(env)  # noqa: F821
cr = env.cr  # noqa: F821


def shape(v):
    return re.sub(r'[A-Z]', 'X', re.sub(r'[0-9]', 'n', (v or '').upper()))


def show(title, query, answer):
    q = {k: (shape(v) if k in ('old_tag', 'serial', 'office') else
             '%d word(s)' % len((v or '').split())) for k, v in query.items()}
    print('== %s' % title)
    print('   asked: %s' % q)
    print('   basis=%s pool=%s tied_at_top=%s already_linked=%s office_from=%s'
          % (answer['basis'], answer['pool'], answer['tied_at_top'],
             answer['already_linked'], answer['office_from']))
    for r in answer['results']:
        print('   #%d %s — "%s"' % (r['rank'], r['reason_code'],
              re.sub(r'office [A-Z0-9]+', 'office XXXX', r['reason'])))


def words(d1, d2):
    return ' '.join(x for x in (d1, d2) if x)


cr.execute("""SELECT old_tag_norm, description, description_2 FROM nrs_sap_asset
               WHERE sap_active AND asset_class = '2000' AND old_tag_norm IN (
                 SELECT old_tag_norm FROM nrs_sap_asset WHERE sap_active
                  GROUP BY 1 HAVING count(*) = 1) ORDER BY id LIMIT 1""")
tag, d1, d2 = cr.fetchone()
q = {'old_tag': tag}
show('1. old tag, unique', q, M.match(**q))

cr.execute("""SELECT old_tag_norm, description, description_2 FROM nrs_sap_asset
               WHERE sap_active AND asset_class = '2000' AND old_tag_norm IN (
                 SELECT old_tag_norm FROM nrs_sap_asset WHERE sap_active
                  GROUP BY 1 HAVING count(*) BETWEEN 3 AND 8
                     AND count(DISTINCT description) > 1)
               ORDER BY id LIMIT 1""")
tag, d1, d2 = cr.fetchone()
q = {'old_tag': tag, 'description': words(d1, d2)}
show('2. old tag shared; the description settles it', q, M.match(**q))

cr.execute("""SELECT serial_norm, description FROM nrs_sap_asset
               WHERE sap_active AND serial_kind = 'real' AND serial_norm IN (
                 SELECT serial_norm FROM nrs_sap_asset WHERE sap_active
                    AND serial_kind = 'real' GROUP BY 1 HAVING count(*) = 1)
               ORDER BY id LIMIT 1""")
ser, d1 = cr.fetchone()
q = {'old_tag': 'FIRS/NONE/0000', 'serial': ser}
show('3. no record carries the tag; a unique serial', q, M.match(**q))

cr.execute("""SELECT office_code, description, description_2 FROM nrs_sap_asset
               WHERE sap_active AND asset_class = '2000' AND office_code IS NOT NULL
               ORDER BY id LIMIT 1""")
office, d1, d2 = cr.fetchone()
q = {'old_tag': 'FIRS/%s/99999999' % office, 'description': words(d1, d2)}
show('4. tag not in SAP; description within the office inside the tag', q,
     M.match(**q))

cr.execute("""SELECT description, description_2 FROM nrs_sap_asset
               WHERE sap_active AND asset_class = '2000' AND old_tag_norm IS NULL
               ORDER BY id LIMIT 1""")
d1, d2 = cr.fetchone()
q = {'description': words(d1, d2), 'asset_class': '2000'}
show('5. untagged; description and class, nationwide', q, M.match(**q))
