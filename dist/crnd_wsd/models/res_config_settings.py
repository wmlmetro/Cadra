from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    request_wsd_public_ui_visibility = fields.Selection(
        related='company_id.request_wsd_public_ui_visibility',
        readonly=False,
        string='Website Service Desk (Public Visibility)')
    request_wsd_public_use_author_phone = fields.Selection(
        related='company_id.request_wsd_public_use_author_phone',
        readonly=False,
        string='Website Service Desk (Use Author Phone)')

    request_limit_max_text_size = fields.Integer(
        related='company_id.request_limit_max_text_size', readonly=False)

    request_allowed_upload_file_types = fields.Char(
        related='company_id.request_allowed_upload_file_types',
        readonly=False)
    request_limit_max_upload_file_size = fields.Integer(
        related='company_id.request_limit_max_upload_file_size',
        readonly=False)
    request_limit_max_upload_file_size_uom = fields.Selection(
        related='company_id.request_limit_max_upload_file_size_uom',
        readonly=False)

    request_create_step_layout = fields.Selection(
        related='website_id.request_create_step_layout',
        readonly=False,
        required=True)

    request_on_request_creating_redirect_to = fields.Selection(
        related='website_id.request_redirect_after_created_on_website',
        readonly=False,
        string='Redirect after request created on Website'
    )

    request_mail_link_access = fields.Selection(
        related='company_id.request_mail_link_access',
        readonly=False,
        string='Choose what kind of link to request will be used in emails.')
