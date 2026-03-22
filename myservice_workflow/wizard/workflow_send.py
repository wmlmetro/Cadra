from odoo import models, fields, api
from odoo.exceptions import UserError


class WorkflowSendWizard(models.TransientModel):
    """
    Manual send wizard — lets staff add a note before dispatching
    to Workflow, and shows the payload that will be sent.
    """
    _name = 'workflow.send.wizard'
    _description = 'Send to NRS Workflow'

    request_id = fields.Many2one(
        comodel_name='request.request',
        string='Request',
        required=True,
        readonly=True,
    )
    request_name = fields.Char(related='request_id.name', readonly=True)
    request_type = fields.Char(
        related='request_id.type_id.name', string='Type', readonly=True)
    request_stage = fields.Char(
        related='request_id.stage_id.name', string='Current Stage', readonly=True)
    workflow_status = fields.Selection(
        related='request_id.workflow_status', readonly=True)
    note = fields.Text(
        string='Note to Approver',
        placeholder='Optional — add context for the executive approver...',
    )
    resend = fields.Boolean(
        string='Force Resend',
        default=False,
        help='Check to resend even if already sent to Workflow',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        req_id = ctx.get('default_request_id')
        if req_id:
            req = self.env['request.request'].browse(req_id)
            if req.workflow_status == 'pending':
                res['resend'] = False
        return res

    def action_send(self):
        self.ensure_one()
        req = self.request_id

        if req.workflow_status == 'pending' and not self.resend:
            raise UserError(
                f"This request has already been sent to Workflow "
                f"(Ref: {req.workflow_ref}). "
                f"Tick 'Force Resend' if you want to send again."
            )

        req._send_to_workflow(
            triggered_by='manual',
            note=self.note or None,
        )
        return {'type': 'ir.actions.act_window_close'}
