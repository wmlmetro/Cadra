"""Handoff 59: measure, write nothing.

Three measurements per tenant, printed on the upgrade's log so the fan-out
is the evidence (report 59):

* placeholder serials already on the register (§3) — nothing is rewritten;
  cleaning legacy serials is NRS's call (GO-LIVE §29 item 8);
* categories whose names suggest a class that carries no label (§2) —
  NOTHING is switched to `record_only`: which Cadra categories are land,
  buildings, software or works in progress is NRS's to say;
* how many categories carry a SAP asset class (§1), and how many SAP asset
  numbers would collide once compared stripped and upper-cased (§4).

The placeholder list itself is seeded by `data/serial_placeholders.xml`.
"""
import logging
import re

from odoo import SUPERUSER_ID, api

from odoo.addons.myservice_asset_register.models import serial_placeholders

_logger = logging.getLogger(__name__)

_LABEL_LESS = re.compile(
    r'\b(land|building|buildings|renovation|software|licen[cs]e|licen[cs]es|'
    r'work[s]? in progress|wip|construction|project|projects)\b', re.I)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    m = serial_placeholders.measure(env)
    top = ', '.join('%s ×%d' % (t['value'], t['count']) for t in m['top'])
    _logger.warning(
        "handoff 59: placeholder serials on %s — %s of %s assets with a "
        "serial (of %s assets) carry a placeholder; top: %s",
        cr.dbname, m['placeholders'], m['with_serial'], m['assets'],
        top or 'none')
    Category = env['nrs.asset.category'].with_context(active_test=False)
    cats = Category.search([])
    hinted = cats.filtered(lambda c: _LABEL_LESS.search(c.name or ''))
    _logger.warning(
        "handoff 59: categories on %s whose names suggest a label-less "
        "class — %s of %s (%s); none switched to record_only",
        cr.dbname, len(hinted), len(cats),
        ', '.join(hinted.mapped('name')) or 'none')
    with_class = cats.filtered('sap_asset_class')
    cr.execute(
        "SELECT count(*) FROM (SELECT upper(btrim(sap_asset_number)) "
        "FROM nrs_asset WHERE coalesce(btrim(sap_asset_number), '') <> '' "
        "GROUP BY 1 HAVING count(*) > 1) d")
    dup = cr.fetchone()[0]
    cr.execute("SELECT count(*) FROM nrs_asset "
               "WHERE coalesce(btrim(sap_asset_number), '') <> ''")
    numbered = cr.fetchone()[0]
    _logger.warning(
        "handoff 59: SAP on %s — %s of %s categories carry a SAP asset "
        "class; %s SAP asset numbers shared once stripped and upper-cased "
        "(of %s assets with one)",
        cr.dbname, len(with_class), len(cats), dup, numbered)
