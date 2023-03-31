from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    request_invoice_line_description_tmpl = fields.Text(
        default=(
            "\nActivity: {{ tline.activity_id.display_name }}"
            "\nDate: {{ tline.date }}"
            "\nUser: {{ tline.user_id.display_name }}"
            "\n---"
            "\n{{ tline.description }}"
        ))
