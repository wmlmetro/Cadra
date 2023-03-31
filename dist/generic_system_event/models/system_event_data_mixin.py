import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericSystemEventDataMixin(models.AbstractModel):
    _name = 'generic.system.event.data.mixin'
    _inherit = 'generic.mixin.delegation.implementation'
    _order = 'event_date DESC, id DESC'
    _description = 'Generic System Event Data Mixin'
    _log_access = False

    event_id = fields.Many2one(
        'generic.system.event', required=True, index=True,
        readonly=True, delegate=True, auto_join=True, ondelete="cascade")

    def name_get(self):
        res = []
        for record in self:
            res += [(record.id, record.event_id.display_name)]
        return res
