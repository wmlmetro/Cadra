import logging

from odoo import models, fields
from odoo.addons.generic_mixin.tools.generic_m2o import generic_m2o_get

_logger = logging.getLogger(__name__)


class GenericSystemEvent(models.Model):
    _name = 'generic.system.event'
    _inherit = 'generic.mixin.delegation.interface'
    _order = 'event_date DESC, id DESC'
    _description = 'Generic System Event'
    _log_access = False

    _generic_mixin_implementation_model_field = 'event_data_model_name'
    _generic_mixin_implementation_id_field = 'event_data_id'

    event_date = fields.Datetime(
        readonly=True, required=True, index=True, default=fields.Datetime.now)
    event_type_id = fields.Many2one(
        'generic.system.event.type',
        required=True, readonly=True, index=True, ondelete='cascade')
    event_code = fields.Char(
        related='event_type_id.code', readonly=True)

    # Event source
    event_source_id = fields.Many2one(
        'generic.system.event.source',
        required=True, index=True, readonly=True, ondelete='cascade')
    event_source_model_id = fields.Many2one(
        related='event_source_id.model_id',
        string="Event Source Model",
        readonly=True)
    event_source_model_name = fields.Char(
        related='event_source_id.model_id.model',
        string="Event Source Model (Name)",
        readonly=True)
    event_source_record_id = fields.Integer(
        readonly=True, required=True, index=True)

    # Event Data Info
    event_data_id = fields.Integer(
        readonly=True, required=True, index=True)
    event_data_model_name = fields.Char(
        related='event_source_id.event_data_model_id.model', readonly=True)

    user_id = fields.Many2one(
        'res.users', readonly=True, required=False, index=True,
        default=lambda self: self.env.user,
        ondelete='set null',
        help="User that triggered this event.")

    def get_event_source_record(self):
        """ Return recordset that represents object that triggered this event.
        """
        return generic_m2o_get(
            self,
            field_res_model='event_source_model_name',
            field_res_id='event_source_record_id')

    def name_get(self):
        res = []
        for record in self:
            res += [
                (record.id,
                 "%s %s (%s)" % (record.event_type_id.name,
                                 record.event_date,  # TODO: handle timezone
                                 record.user_id.display_name)),
            ]
        return res
