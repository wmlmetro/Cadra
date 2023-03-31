from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    request_invoice_line_description_tmpl = fields.Text(
        related='company_id.request_invoice_line_description_tmpl',
        readonly=False,
        string='Request Invoice Line Description Template',
        help="You can use jinja2 placeholders in this field",
    )
