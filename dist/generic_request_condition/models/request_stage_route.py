from odoo import models, fields, exceptions, _


class RequestStageRoute(models.Model):
    _inherit = "request.stage.route"

    condition_ids = fields.Many2many(
        'generic.condition', string='Conditions',
        help="List here conditions that request shouds satisfy "
             "to be able to use this route")
    condition_operator = fields.Selection(
        selection=[
            ('and', 'AND'),
            ('or', 'OR')
        ],
        default='and',
        required=True
    )

    def _ensure_can_move(self, request):
        res = super(RequestStageRoute, self)._ensure_can_move(request)

        if not self.condition_ids.check(
                request, operator=self.condition_operator):
            raise exceptions.AccessError(_(
                "This stage change '%(route)s' restricted by "
                "route conditions.\n"
                "Request: %(request)s\n"
                "Request Type: %(request_type)s\n"
                "Request Category: %(request_category)s\n"
            ) % {
                'route': self.display_name,
                'request': request.sudo().display_name,
                'request_type': request.sudo().type_id.display_name,
                'request_category': request.sudo().category_id.display_name,
            })
        return res
