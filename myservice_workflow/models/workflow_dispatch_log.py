from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class WorkflowDispatchLog(models.Model):
    """
    Audit log for every interaction with the NRS Workflow system.
    One record per dispatch attempt. Never deleted — permanent audit trail.
    """
    _name = 'workflow.dispatch.log'
    _description = 'Workflow Dispatch Log'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', readonly=True, copy=False)
    request_id = fields.Many2one(
        comodel_name='request.request',
        string='Request',
        ondelete='set null',
        index=True,
        readonly=True,
    )
    direction = fields.Selection([
        ('outbound', 'Outbound (myservice → Workflow)'),
        ('inbound',  'Inbound (Workflow → myservice)'),
    ], string='Direction', required=True, readonly=True)

    status = fields.Selection([
        ('pending',  'Pending'),
        ('sent',     'Sent — Awaiting Response'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('queried',  'Queried / Comments Received'),
        ('error',    'Error'),
    ], string='Status', default='pending', tracking=True, readonly=True)

    workflow_ref = fields.Char(
        string='Workflow Reference No.',
        readonly=True,
        help='Reference number assigned by the Workflow system',
    )
    payment_ref = fields.Char(
        string='Payment / Approval Reference',
        readonly=True,
        help='Payment or approval reference returned by Workflow',
    )
    sent_by = fields.Many2one(
        comodel_name='res.users',
        string='Sent By',
        readonly=True,
        default=lambda self: self.env.user,
    )
    sent_at = fields.Datetime(string='Sent At', readonly=True)
    responded_at = fields.Datetime(string='Response Received At', readonly=True)

    payload_sent = fields.Text(
        string='Payload Sent',
        readonly=True,
        help='JSON payload sent to Workflow system',
    )
    response_received = fields.Text(
        string='Response Received',
        readonly=True,
        help='Raw response from Workflow system',
    )
    workflow_comment = fields.Text(
        string='Comment from Workflow',
        readonly=True,
        help='Comment, query, or rejection reason from the approver',
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
    )
    adapter_type = fields.Char(
        string='Adapter Used',
        readonly=True,
    )

    @api.model
    def create(self, vals):
        if not vals.get('name'):
            seq = self.env['ir.sequence'].next_by_code('workflow.dispatch.log')
            vals['name'] = seq or 'WDL-NEW'
        return super().create(vals)

    def action_view_request(self):
        if self.request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'request.request',
                'res_id': self.request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
