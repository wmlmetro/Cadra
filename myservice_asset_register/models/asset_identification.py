# -*- coding: utf-8 -*-
"""How a received unit is identified — Addendum A Section 12 (handoff 58 §4).

The owner's ruling (evaluation §7/4.1): *no serial, no receipt* stays for
serialised items; an item with no manufacturer serial — furniture — is
identified by its tag and a set of attributes instead. The CLASS decides
which, and the unit remembers the mode it arrived under:

* `serial` — a manufacturer serial is mandatory, and the class's mandatory
  attributes (by default make and model) with it.
* `tag_id` — no serial; the class's mandatory attributes (AD-32: description,
  make or brand, model or catalogue reference, colour, material, dimensions)
  are the unit's identity until its label is on it, and the asset code is
  its identity after.
* `pool` — declared, and REFUSED at receipt: pool holdings are Addendum A
  Phase E and nothing here pretends to hold one.

Every rule here applies to a GATED receipt only (`register_state =
'captured'` at creation): with a tenant's switch off, nothing a receipt
sends is checked that was not checked before handoff 58 (§7).

A change of a class's mode affects NEW receipts only (AD-31): the unit's
`identification_mode` is stamped at receipt and never recomputed, so a
candidate already in the chain keeps the check it arrived with.

A change of a class's mode or schema is a CONFIGURATION change, and the
configuration record (`GET /reports/configuration-changes`) reads
`ir.config_parameter` and nothing else. So the change writes one parameter
per class, `cadra.class_identification.<category id>`, whose value says the
mode, the mandatory attributes and the class's name — the row the report
shows, with the person who made the change and when. Nothing reads that
parameter back; the category's own fields are the truth.
"""
import json

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

MODE_SERIAL = 'serial'
MODE_TAG_ID = 'tag_id'
MODE_POOL = 'pool'
IDENTIFICATION_MODES = [
    (MODE_SERIAL, 'Serial number'),
    (MODE_TAG_ID, 'Tag ID (attributes, no serial)'),
    (MODE_POOL, 'Pool (not built yet)'),
]

#: The fields a class may make mandatory at receipt — the `POST /assets`
#: names, so a receiving system reads the schema and knows what to send.
CAPTURABLE_FIELDS = {
    'name': 'description',
    'make': 'make or brand',
    'model_name': 'model or catalogue reference',
    'manufacturer': 'manufacturer',
    'colour': 'colour',
    'material': 'material',
    'dimensions': 'dimensions',
}
#: The schema each mode has until somebody sets one for the class.
DEFAULT_MANDATORY = {
    MODE_SERIAL: ('make', 'model_name'),
    MODE_TAG_ID: ('name', 'make', 'model_name', 'colour', 'material',
                  'dimensions'),
    MODE_POOL: (),
}

CONFIG_KEY = 'cadra.class_identification.%d'


def parse_schema(value):
    """`{"mandatory": [...]}` → the tuple of field names, or raise
    ValueError with the sentence. Accepts a dict or its JSON text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError('`class_attributes_schema` is not valid JSON.')
    if not isinstance(value, dict) or set(value) != {'mandatory'} \
            or not isinstance(value['mandatory'], list):
        raise ValueError(
            '`class_attributes_schema` must be {"mandatory": [field, ...]} '
            'and nothing else.')
    names = value['mandatory']
    unknown = [n for n in names if n not in CAPTURABLE_FIELDS]
    if unknown or not all(isinstance(n, str) for n in names):
        raise ValueError(
            '`class_attributes_schema` names a field a receipt cannot carry '
            '(%s); the capturable fields are: %s.' % (
                ', '.join(map(str, unknown)) or '?',
                ', '.join(CAPTURABLE_FIELDS)))
    if len(set(names)) != len(names):
        raise ValueError('`class_attributes_schema` names a field twice.')
    return tuple(names)


def _words(names):
    parts = ['its %s (`%s`)' % (CAPTURABLE_FIELDS[n], n) for n in names]
    if len(parts) == 1:
        return parts[0]
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


class NRSAssetCategoryIdentification(models.Model):
    _inherit = 'nrs.asset.category'

    identification_mode = fields.Selection(
        IDENTIFICATION_MODES, string='Identification', required=True,
        default=MODE_SERIAL,
        help='How a received unit of this class is identified (Addendum A '
             'Section 12). Applies to units received from the moment it is '
             'changed; units already received keep the mode they arrived '
             'with.')
    # JSON text, `{"mandatory": [...]}`. Empty means "the mode's default",
    # so a class nobody configured follows the default if it is ever changed.
    class_attributes_schema = fields.Text(
        'Mandatory Attributes (JSON)',
        help='{"mandatory": [field, ...]} — what a receipt of this class must '
             'carry. Empty: the identification mode\'s default.')

    def _mandatory_attributes(self):
        self.ensure_one()
        if self.class_attributes_schema:
            try:
                return parse_schema(self.class_attributes_schema)
            except ValueError:
                pass
        return DEFAULT_MANDATORY.get(self.identification_mode or MODE_SERIAL,
                                     ())

    def _effective_schema(self):
        """What `GET /asset-categories` publishes — always a schema, never
        null, and the same shape `PATCH` accepts back."""
        return {'mandatory': list(self._mandatory_attributes())}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalise_schema(vals)
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if {'identification_mode', 'class_attributes_schema'} & set(vals) \
                    and (rec.identification_mode != MODE_SERIAL
                         or rec.class_attributes_schema):
                rec._record_identification()
        return records

    def write(self, vals):
        self._normalise_schema(vals)
        watched = {'identification_mode', 'class_attributes_schema'} & set(vals)
        before = {r.id: (r.identification_mode, r._mandatory_attributes())
                  for r in self} if watched else {}
        result = super().write(vals)
        for rec in self:
            if watched and before[rec.id] != (rec.identification_mode,
                                              rec._mandatory_attributes()):
                rec._record_identification()
        return result

    @api.model
    def _normalise_schema(self, vals):
        if vals.get('class_attributes_schema') not in (None, False, ''):
            try:
                names = parse_schema(vals['class_attributes_schema'])
            except ValueError as e:
                raise ValidationError(str(e))
            vals['class_attributes_schema'] = json.dumps({'mandatory':
                                                          list(names)})

    def _record_identification(self):
        """The configuration record's row for this class (module docstring)."""
        self.ensure_one()
        value = '%s; mandatory: %s; class: %s' % (
            self.identification_mode,
            ', '.join(self._mandatory_attributes()) or '(none)',
            self.name)
        self.env['ir.config_parameter'].sudo().set_param(
            CONFIG_KEY % self.id, value)


class NRSAssetIdentification(models.Model):
    _inherit = 'nrs.asset'

    # The attributes a `tag_id` unit is identified by (AD-32) that the
    # register had nowhere to hold. Make, model and manufacturer were already
    # fields; the description is the asset's `name`.
    # Not tracked, like `make` and `model_name` beside them: the register
    # snapshot rolls back every tracked field (test_snapshot_rollback), and
    # an attribute of the unit is not a fact that changes over its life.
    colour = fields.Char('Colour')
    material = fields.Char('Material')
    dimensions = fields.Char('Dimensions')
    identification_mode = fields.Selection(
        [(MODE_SERIAL, 'Serial number'),
         (MODE_TAG_ID, 'Tag ID (attributes, no serial)')],
        string='Received As', readonly=True, copy=False,
        help='The identification mode of this unit\'s class when it was '
             'RECEIVED through the receipt gates. Fixed at receipt (AD-31). '
             'Empty for anything received with the gates off.')

    @api.model
    def _check_receipt_identity(self, vals):
        """Refuse a gated receipt its class cannot accept. Returns the
        values to stamp on the new unit. Raises a `GateRefused` (400
        `validation_failed`, the missing fields named in `details`)."""
        from .asset_gates import GateRefused
        category = self.env['nrs.asset.category'].sudo().browse(
            vals.get('category_id') or ()).exists()
        if not category:
            # `category_id` is required on the model, which says so.
            return {}
        mode = category.identification_mode or MODE_SERIAL
        if mode == MODE_POOL:
            raise GateRefused(
                _('Pool identification is not built yet (Addendum A Phase '
                  'E).'), 'validation_failed',
                {'identification_mode': mode, 'category_id': category.id})
        serial = (vals.get('serial_number') or '').strip()
        if mode == MODE_SERIAL and not serial:
            # Vendra's own sentence for the same refusal, for one unit.
            raise GateRefused(
                _('%(cls)s: 0 of 1 serial numbers captured. Capture one '
                  'serial number per accepted unit.', cls=category.name),
                'validation_failed',
                {'field': 'serial_number', 'identification_mode': mode,
                 'category_id': category.id})
        missing = [f for f in category._mandatory_attributes()
                   if not str(vals.get(f) or '').strip()]
        if missing:
            raise GateRefused(
                _('%(cls)s is identified by %(how)s, so a unit of it must '
                  'arrive with %(what)s.', cls=category.name,
                  how=_('serial number') if mode == MODE_SERIAL
                  else _('tag and attributes'), what=_words(missing)),
                'validation_failed',
                {'missing_fields': missing, 'identification_mode': mode,
                 'category_id': category.id})
        if serial:
            # Serial uniqueness, for a gated receipt (defence in depth — the
            # receiving system already refuses it). EMPTY serials are never
            # compared: a `tag_id` unit has none, and a hundred chairs must
            # not collide with each other. Raw SQL, so a candidate and an
            # archived record are found too; compared stripped and
            # case-insensitively, the scan box's rule (handoff 38). Not a
            # constraint: `nrs19` holds 1,291 serials on more than one
            # asset, and a constraint would refuse the register it describes.
            self.env.cr.execute(
                "SELECT asset_code FROM nrs_asset "
                "WHERE serial_number IS NOT NULL "
                "AND btrim(serial_number) <> '' "
                "AND lower(btrim(serial_number)) = lower(%s) "
                "ORDER BY id LIMIT 1", (serial,))
            clash = self.env.cr.fetchone()
            if clash:
                raise GateRefused(
                    _('Serial number %(serial)s is already registered as an '
                      'asset in Cadra (%(code)s).', serial=serial,
                      code=clash[0]),
                    'validation_failed',
                    {'field': 'serial_number', 'asset_code': clash[0]})
        return {'identification_mode': mode}
