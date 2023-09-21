from odoo import models, fields


class RequestType(models.Model):
    _inherit = "request.type"

    website_comments_closed = fields.Boolean(
        'Are comments not available?', default=False,
        help="Disable website comments on closed requests")

    # Help message for request text
    website_request_text_help = fields.Text()
    # Custom title for request
    website_request_title = fields.Char()
    # Custom label for request text editor
    website_custom_label_editor = fields.Char()
    website_custom_congratulation_note = fields.Html()

    selection_priority_view = fields.Selection(
        [('selection', 'Selection'),
         ('star', 'Star bar')], default='selection', required=True)
