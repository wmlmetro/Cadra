import json
import logging

from odoo import models, fields, api

from ..tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)


class RequestWizardClose(models.TransientModel):
    _inherit = 'request.wizard.close'

    value_ids = fields.One2many(
        'request.wizard.close.field.value', 'wizard_id', string='Values',
        readonly=False, copy=False)

    # Technical fields used to display values in user-friendly way.
    # The data structure is described in method `fields_data()`
    # of class FieldsUIHelper
    wizard_fields_json_top = fields.Text(
        "Fields Info (JSON) [ALL]",
        compute='_compute_wizard_fields_json',
        inverse='_inverse_wizard_fields_json')
    wizard_fields_json_bottom = fields.Text(
        "Fields Info (JSON) [ALL]",
        compute='_compute_wizard_fields_json',
        inverse='_inverse_wizard_fields_json')
    wizard_has_fields_top = fields.Boolean(
        compute='_compute_wizard_fields_json', readonly=True)
    wizard_has_fields_bottom = fields.Boolean(
        compute='_compute_wizard_fields_json', readonly=True)

    @api.depends('value_ids')
    def _compute_wizard_fields_json(self):
        for record in self:
            values_top = record.value_ids.filtered(
                lambda r: r.field_id.position == 'before')
            values_bottom = record.value_ids.filtered(
                lambda r: r.field_id.position == 'after')
            record.wizard_fields_json_top = json.dumps(
                values_top.convert_to_fields_info())
            record.wizard_fields_json_bottom = json.dumps(
                values_bottom.convert_to_fields_info())
            record.wizard_has_fields_top = bool(values_top)
            record.wizard_has_fields_bottom = bool(values_bottom)

    def _inverse_wizard_fields_json(self):
        """ Handle writes in `wizard_fields_json_top` and
            `wizard_fields_json_bottom`
        """
        for record in self:
            new_req = self.env['request.request'].new(
                record._reopen_prepare_data())

            fields_top = FieldsUIHelper(self.env)
            fields_top.from_json(record.wizard_fields_json_top)
            fields_top.enforce_fields(
                new_req._request_fields__get_fields(position='before'))

            fields_bottom = FieldsUIHelper(self.env)
            fields_bottom.from_json(record.wizard_fields_json_bottom)
            fields_bottom.enforce_fields(
                new_req._request_fields__get_fields(position='after'))

            values = self.env['request.wizard.close.field.value'].browse([])
            values += fields_top.to_values_wizard()
            values += fields_bottom.to_values_wizard()
            record.value_ids = values

    @api.onchange('request_id',
                  'new_request_type_id',
                  'new_request_category_id',
                  'new_request_service_id',
                  'wizard_fields_json_top', 'wizard_fields_json_bottom')
    def _onchange_wizard_fields(self):
        for record in self:
            new_req = self.env['request.request'].new(
                record._reopen_prepare_data())

            # Custom default values for fields from original request
            # This dict will be provided to 'enforce_fields'
            # method of UI helper
            custom_defaults = {
                v.field_id.code: v.value
                for v in record.request_id.value_ids
                if v.value
            }

            fields_top = FieldsUIHelper(self.env)
            fields_top.from_json(record.wizard_fields_json_top)
            fields_top.enforce_fields(
                new_req._request_fields__get_fields(position='before'),
                custom_defaults=custom_defaults)

            fields_bottom = FieldsUIHelper(self.env)
            fields_bottom.from_json(record.wizard_fields_json_bottom)
            fields_bottom.enforce_fields(
                new_req._request_fields__get_fields(position='after'),
                custom_defaults=custom_defaults)

            values = self.env['request.wizard.close.field.value'].browse([])
            values += fields_top.to_values_wizard()
            values += fields_bottom.to_values_wizard()
            record.value_ids = values

    def _reopen_prepare_data(self):
        res = super(RequestWizardClose, self)._reopen_prepare_data()

        res.update({
            'request_fields_json_top': self.wizard_fields_json_top,
            'request_fields_json_bottom': self.wizard_fields_json_bottom,
        })
        return res


class RequestWizardCloseFieldValue(models.TransientModel):
    _name = 'request.wizard.close.field.value'
    _description = 'Request Wizard: Close (field value)'
    _order = 'sequence'

    wizard_id = fields.Many2one(
        'request.wizard.close', 'Wizard', ondelete='cascade', required=True)
    request_id = fields.Many2one(
        related='wizard_id.request_id', readonly=True)

    field_id = fields.Many2one(
        'request.field', 'Field', ondelete='cascade', required=True)
    sequence = fields.Integer(
        related='field_id.sequence', readonly=True)
    field_name = fields.Char(
        related='field_id.name', readonly=True)
    field_mandatory = fields.Boolean(
        'Mandatory', related='field_id.mandatory', readonly=True)
    value = fields.Char()

    def _get_request_field_info(self):
        """ Field infor to be provided for JS widget
        """
        self.ensure_one()
        return self.field_id._get_request_field_info(value=self.value)

    def convert_to_fields_info(self):
        # We have to use string keys here,
        # because json supports only string dict keys
        fields_info = {
            str(v.field_id.id): v._get_request_field_info() for v in self}
        fields_order = [
            str(v.field_id.id)
            for v in sorted(self, key=lambda x: x.sequence)
        ]
        res = {
            'fields_info': fields_info,
            'fields_order': fields_order,
        }
        return res
