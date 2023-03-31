import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class GenericServiceLine(models.AbstractModel):
    """ Mixin that implements basic service line concept
    """
    _name = 'generic.service.line'
    _description = 'Generic Service Line'
    _order = 'service_id ASC, id ASC'

    service_id = fields.Many2one(
        'generic.service', index=True, ondelete='restrict')
    service_level_id = fields.Many2one(
        'generic.service.level', index=True, ondelete='restrict')

    @api.constrains('service_id', 'service_level_id')
    def _ensure_service_id_or_service_level_id(self):
        for rec in self:
            if not rec.service_id and not rec.service_level_id:
                raise ValidationError(
                    _('If you don`t want to set the service or service level,'
                      ' unlink this row. You can`t save empty row.'))
