"""Handoff 60, ruling 7: the asset's `reference` becomes `record_reference`.

Handoff 59 added `nrs.asset.reference` (what identifies a `record_only`
unit: a title or plot number, a licence key, a contract) and published it
as a top-level `reference` beside two other published `reference` keys with
other meanings. Renamed before anything outside Cadra read it (handoff 37's
one-name rule), the field and the key together.

Before the registry loads, so the ORM finds the column it expects and no
value is lost: the column, the field's `ir.model.fields` row and its
external id are renamed, and a class schema naming `reference` among its
mandatory attributes is rewritten to the new name. Idempotent.
"""
import json
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'nrs_asset'
                     AND column_name = 'reference'""")
    if cr.fetchone():
        cr.execute("""SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'nrs_asset'
                         AND column_name = 'record_reference'""")
        if cr.fetchone():
            # A registry load already created the new column empty.
            cr.execute("UPDATE nrs_asset SET record_reference = reference "
                       "WHERE record_reference IS NULL")
            cr.execute("ALTER TABLE nrs_asset DROP COLUMN reference")
        else:
            cr.execute("ALTER TABLE nrs_asset "
                       "RENAME COLUMN reference TO record_reference")
        cr.execute("""UPDATE ir_model_fields SET name = 'record_reference'
                       WHERE model = 'nrs.asset' AND name = 'reference'
                         AND NOT EXISTS (
                           SELECT 1 FROM ir_model_fields
                            WHERE model = 'nrs.asset'
                              AND name = 'record_reference')""")
        cr.execute("""UPDATE ir_model_data
                         SET name = 'field_nrs_asset__record_reference'
                       WHERE model = 'ir.model.fields'
                         AND name = 'field_nrs_asset__reference'
                         AND NOT EXISTS (
                           SELECT 1 FROM ir_model_data
                            WHERE model = 'ir.model.fields'
                              AND name = 'field_nrs_asset__record_reference')""")
    cr.execute("SELECT count(*) FROM nrs_asset WHERE coalesce("
               "record_reference, '') <> ''" if _has(cr, 'record_reference')
               else "SELECT 0")
    carried = cr.fetchone()[0]
    rewritten = 0
    cr.execute("SELECT id, class_attributes_schema FROM nrs_asset_category "
               "WHERE class_attributes_schema LIKE %s", ('%"reference"%',))
    for cid, raw in cr.fetchall():
        try:
            schema = json.loads(raw)
        except ValueError:
            continue
        mandatory = schema.get('mandatory') if isinstance(schema, dict) \
            else None
        if isinstance(mandatory, list) and 'reference' in mandatory:
            schema['mandatory'] = ['record_reference' if f == 'reference'
                                   else f for f in mandatory]
            cr.execute("UPDATE nrs_asset_category "
                       "SET class_attributes_schema = %s WHERE id = %s",
                       (json.dumps(schema), cid))
            rewritten += 1
    _logger.warning(
        "handoff 60: %s — `reference` renamed `record_reference`: %d assets "
        "carry one; %d class schemas rewritten", cr.dbname, carried,
        rewritten)


def _has(cr, column):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'nrs_asset' AND column_name = %s""",
               (column,))
    return bool(cr.fetchone())
