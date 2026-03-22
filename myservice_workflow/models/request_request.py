from odoo import models, fields, api
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    # ── Workflow status fields on the request ─────────────────────────
    workflow_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('pending',  'Sent — Awaiting Approval'),
        ('approved', 'Approved by Workflow'),
        ('rejected', 'Rejected by Workflow'),
        ('queried',  'Queried — Response Required'),
    ], string='Workflow Status', default='not_sent',
       tracking=True, readonly=True, copy=False)

    workflow_ref = fields.Char(
        string='Workflow Reference',
        readonly=True, copy=False,
        help='Reference number assigned by the NRS Workflow system',
    )
    workflow_payment_ref = fields.Char(
        string='Payment / Approval Reference',
        readonly=True, copy=False,
        help='Payment or approval reference returned by Workflow on approval',
    )
    workflow_dispatch_ids = fields.One2many(
        comodel_name='workflow.dispatch.log',
        inverse_name='request_id',
        string='Workflow Dispatch Log',
        readonly=True,
    )
    workflow_dispatch_count = fields.Integer(
        string='Workflow Dispatches',
        compute='_compute_workflow_dispatch_count',
    )

    @api.depends('workflow_dispatch_ids')
    def _compute_workflow_dispatch_count(self):
        for rec in self:
            rec.workflow_dispatch_count = len(rec.workflow_dispatch_ids)

    # ── Stage change hook — auto-trigger ──────────────────────────────
    def write(self, vals):
        result = super().write(vals)
        if 'stage_id' in vals:
            self._check_workflow_auto_trigger()
        return result

    def _check_workflow_auto_trigger(self):
        """Fire auto-send if the new stage is in the trigger list."""
        try:
            config = self.env['workflow.config'].get_active_config()
        except UserError:
            return  # No config — silent skip

        trigger_ids = config.trigger_stage_ids.ids
        if not trigger_ids:
            return

        for req in self:
            if (req.stage_id.id in trigger_ids
                    and req.workflow_status == 'not_sent'):
                _logger.info(
                    "Auto-triggering Workflow dispatch for request %s "
                    "(stage: %s)", req.name, req.stage_id.name)
                req._send_to_workflow(triggered_by='auto')

    # ── Core dispatch method ──────────────────────────────────────────
    def _send_to_workflow(self, triggered_by='manual', note=None):
        """
        Build the payload, call the adapter, record the log.
        Returns the dispatch log record.
        """
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        adapter = config._get_adapter()

        payload = self._build_workflow_payload()
        log = self.env['workflow.dispatch.log'].create({
            'request_id':   self.id,
            'direction':    'outbound',
            'status':       'pending',
            'sent_by':      self.env.user.id,
            'sent_at':      fields.Datetime.now(),
            'payload_sent': json.dumps(payload, indent=2, default=str),
            'adapter_type': config.adapter_type,
        })

        result = adapter.submit(payload)

        if result.get('ok'):
            log.write({
                'status':       'sent',
                'workflow_ref': result.get('workflow_ref', ''),
                'response_received': result.get('raw', result.get('message', '')),
            })
            self.write({
                'workflow_status': 'pending',
                'workflow_ref':    result.get('workflow_ref', ''),
            })
            self.message_post(
                body=f"<p>📤 <strong>Sent to NRS Workflow</strong> "
                     f"({triggered_by}) — Ref: <strong>{result.get('workflow_ref','')}</strong></p>"
                     + (f"<p>{note}</p>" if note else ''),
                subtype_xmlid='mail.mt_comment',
            )
        else:
            log.write({
                'status':        'error',
                'error_message': result.get('error', 'Unknown error'),
            })
            self.message_post(
                body=f"<p>❌ <strong>Workflow dispatch failed</strong>: "
                     f"{result.get('error','Unknown error')}</p>",
                subtype_xmlid='mail.mt_comment',
            )
            raise UserError(
                f"Failed to send to Workflow system:\n{result.get('error','Unknown error')}"
            )
        return log

    def _build_workflow_payload(self):
        """
        Build the JSON payload to send to Workflow.
        Structured to be human-readable for email fallback too.
        NRS IT team can request field additions here.
        """
        self.ensure_one()
        req = self

        payload = {
            'source_system':    'NRS myservice',
            'source_url':       f"https://myservice.com.ng/web#id={req.id}&model=request.request&view_type=form",
            'reference':        req.name or '',
            'type':             req.type_id.name if req.type_id else '',
            'category':         req.category_id.name if req.category_id else '',
            'service':          req.service_id.name if req.service_id else '',
            'location':         req.generic_location_id.name if req.generic_location_id else '',
            'stage':            req.stage_id.name if req.stage_id else '',
            'priority':         req.priority if hasattr(req, 'priority') else '',
            'requested_by':     req.author_id.name if req.author_id else '',
            'requested_by_email': req.author_id.email if req.author_id else '',
            'assigned_to':      req.user_id.name if req.user_id else '',
            'description':      req.request_text or '',
            'created_date':     str(req.date_created) if req.date_created else '',
            'submission_date':  str(fields.Datetime.now()),
        }

        # Add vehicle if present (from myservice_request_fields)
        if hasattr(req, 'vehicle_id') and req.vehicle_id:
            payload['vehicle'] = req.vehicle_id.name or ''
            payload['vehicle_plate'] = req.vehicle_id.license_plate or ''

        # Add attachments summary
        config = self.env['workflow.config'].get_active_config()
        if config.include_attachments and req.attachment_ids:
            payload['attachments'] = [
                {'name': a.name, 'size': a.file_size}
                for a in req.attachment_ids
            ]
        return payload

    # ── Manual send button ────────────────────────────────────────────
    def action_send_to_workflow(self):
        """Opens the send wizard for manual dispatch."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send to NRS Workflow',
            'res_model': 'workflow.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_view_workflow_log(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workflow Dispatch Log',
            'res_model': 'workflow.dispatch.log',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'target': 'current',
        }

    # ── Callback handlers — called by the webhook controller ─────────
    def _workflow_callback_approved(self, workflow_ref, payment_ref=None,
                                    comment=None, log=None):
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        vals = {'workflow_status': 'approved'}
        if payment_ref:
            vals['workflow_payment_ref'] = payment_ref
        self.write(vals)

        # Advance to approved stage if configured
        if config.approved_stage_id:
            self.write({'stage_id': config.approved_stage_id.id})

        msg = (f"<p>✅ <strong>Approved by NRS Workflow</strong>"
               f" — Ref: {workflow_ref}</p>")
        if payment_ref:
            msg += f"<p>Payment/Approval Reference: <strong>{payment_ref}</strong></p>"
        if comment:
            msg += f"<p>Comment: {comment}</p>"
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'approved',
                'workflow_ref': workflow_ref,
                'payment_ref': payment_ref or '',
                'workflow_comment': comment or '',
                'responded_at': fields.Datetime.now(),
            })

    def _workflow_callback_rejected(self, workflow_ref, comment=None, log=None):
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        self.write({'workflow_status': 'rejected'})

        # Move back to rejected stage if configured
        if config.rejected_stage_id:
            self.write({'stage_id': config.rejected_stage_id.id})

        msg = (f"<p>❌ <strong>Rejected by NRS Workflow</strong>"
               f" — Ref: {workflow_ref}</p>")
        if comment:
            msg += f"<p>Rejection reason: {comment}</p>"
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'rejected',
                'workflow_ref': workflow_ref,
                'workflow_comment': comment or '',
                'responded_at': fields.Datetime.now(),
            })

    def _workflow_callback_queried(self, workflow_ref, comment, log=None):
        self.ensure_one()
        self.write({'workflow_status': 'queried'})
        msg = (f"<p>💬 <strong>Query from NRS Workflow</strong>"
               f" — Ref: {workflow_ref}</p>"
               f"<p>{comment}</p>")
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'queried',
                'workflow_ref': workflow_ref,
                'workflow_comment': comment,
                'responded_at': fields.Datetime.now(),
            })
