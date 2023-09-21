import logging

from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('assign_by_policy', 'Assign by Policy')],
        ondelete={'assign_by_policy': 'cascade'}
    )
    assign_policy_id = fields.Many2one(
        'generic.assign.policy', 'Assign Policy')

    @api.model
    def _run_action_assign_by_policy(self, eval_context=None):
        model_name = self.model_id.sudo().model
        Model = self.env[model_name]
        records = Model.browse()
        if (self.env.context.get('active_model') == model_name and
                self.env.context.get('active_id')):
            records += Model.browse(self.env.context['active_id'])
        if (self.env.context.get('active_model') == model_name and
                self.env.context.get('active_ids')):
            records += Model.browse(self.env.context['active_ids'])
        for rec in records:
            self.assign_policy_id.do_assign(rec)
