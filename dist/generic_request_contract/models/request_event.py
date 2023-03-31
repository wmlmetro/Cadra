from odoo import models, fields


class RequestEvent(models.Model):
    _inherit = 'request.event'

    old_contract_id = fields.Many2one('generic.contract', readonly=True)
    new_contract_id = fields.Many2one('generic.contract', readonly=True)
