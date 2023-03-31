from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    request_incoming_mail_validator_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='res_company_request_incoming_mail_validator_rel',
        column1='company_id',
        column2='condition_id')
    request_attach_messages_to_request_by_subject = fields.Boolean(
        string='Automatically attach messages to request, '
               'mentioned in mail subject',
        default=False)
