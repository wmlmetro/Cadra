"""Handoff 58 §4: every class gets an identification mode; furniture is
`tag_id` (D11).

The column arrives with its default, `serial`, on every row — vehicles and
electronics are serial by default and nothing needs writing for them. A
furniture class (FM domain `furniture`, or a name that says furniture) is
switched to `tag_id` through the ORM, so the change is on the configuration
record like any other (`cadra.class_identification.<id>`), written by the
upgrade. Nothing defaults to `pool`. Prints the count per tenant.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Category = env['nrs.asset.category'].with_context(active_test=False)
    furniture = Category.search(['|', ('domain', '=', 'furniture'),
                                 ('name', 'ilike', 'furniture')])
    furniture.filtered(
        lambda c: c.identification_mode != 'tag_id').write(
        {'identification_mode': 'tag_id'})
    total = Category.search_count([])
    _logger.warning(
        "handoff 58: identification mode on %s — %s of %s classes tag_id "
        "(%s), the rest serial", cr.dbname, len(furniture), total,
        ', '.join(furniture.mapped('name')) or 'none')
