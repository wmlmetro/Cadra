from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    request_default_mail_source_id = fields.Many2one(
        'request.mail.source',
        config_parameter='generic_request_mail.default_mail_source_id',
        help='Use this mail source for all requests. '
             'Enabling this option will enforce using aliase related to mail '
             'source for all requests.')
    request_incoming_mail_validator_ids = fields.Many2many(
        related='company_id.request_incoming_mail_validator_ids',
        readonly=False)
    request_attach_messages_to_request_by_subject = fields.Boolean(
        related='company_id.request_attach_messages_to_request_by_subject',
        readonly=False)
