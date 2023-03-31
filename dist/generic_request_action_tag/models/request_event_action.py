from odoo import models, fields


class RequestEventAction(models.Model):
    _inherit = 'request.event.action'

    act_type = fields.Selection(selection_add=[('tag', 'Tag')],
                                ondelete={'tag': 'cascade'})
    tag_add_tag_ids = fields.Many2many(
        'generic.tag',
        'request_event_action_generic_tag_add_tag_ids_rel',
        'action_id', 'tag_id',
        domain=[('model_id.model', '=', 'request.request')])
    tag_remove_tag_ids = fields.Many2many(
        'generic.tag',
        'request_event_action_generic_tag_remove_tag_ids_rel',
        'action_id', 'tag_id',
        domain=[('model_id.model', '=', 'request.request')])

    def _run_tag(self, request, event):
        request.tag_ids -= self.tag_remove_tag_ids
        request.tag_ids += self.tag_add_tag_ids

    def _dispatch(self, request, event):
        if self.act_type == 'tag':
            return self._run_tag(request, event)
        return super(RequestEventAction, self)._dispatch(request, event)
