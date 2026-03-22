from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class WorkflowConfig(models.Model):
    """
    Stores the connection configuration for the NRS WorkSpace.
    One active config at a time. Adapter type is swappable here.
    """
    _name = 'workflow.config'
    _description = 'NRS WorkSpace Integration Configuration'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True,
                       default='NRS WorkSpace')
    active = fields.Boolean(default=True)

    # ── Adapter type ──────────────────────────────────────────────────
    adapter_type = fields.Selection([
        ('rest',  'REST API (HTTP/JSON)'),
        ('soap',  'SOAP / XML Web Service'),
        ('email', 'Email-based (structured email)'),
        ('stub',  'Stub / Test mode (no real send)'),
    ], string='Adapter Type', required=True, default='stub',
       help='Select once the NRS IT team confirms the NRS WorkSpace interface.')

    # ── REST adapter settings ─────────────────────────────────────────
    rest_base_url = fields.Char(
        string='Workflow API Base URL',
        help='e.g. https://workflow.nrs.gov.ng/api/v1')
    rest_endpoint_submit = fields.Char(
        string='Submit Endpoint',
        default='/requests/submit',
        help='Appended to base URL for new request submissions')
    rest_auth_type = fields.Selection([
        ('none',   'No authentication'),
        ('apikey', 'API Key (header)'),
        ('bearer', 'Bearer Token'),
        ('basic',  'Basic Auth (username/password)'),
    ], string='Auth Type', default='apikey')
    rest_api_key = fields.Char(string='API Key / Token')
    rest_api_key_header = fields.Char(
        string='API Key Header Name', default='X-API-Key')
    rest_username = fields.Char(string='Username')
    rest_password = fields.Char(string='Password')
    rest_timeout = fields.Integer(string='Timeout (seconds)', default=30)

    # ── Email adapter settings ────────────────────────────────────────
    email_to = fields.Char(
        string='Workflow Email Address',
        help='Email address Workflow monitors for incoming requests')
    email_subject_prefix = fields.Char(
        string='Subject Prefix', default='[NRS-WORKFLOW]')

    # ── Callback / webhook settings ───────────────────────────────────
    callback_enabled = fields.Boolean(
        string='Enable Webhook Callback',
        default=True,
        help='Allow Workflow to POST approval outcomes back to myservice')
    callback_token = fields.Char(
        string='Callback Security Token',
        help='Shared secret Workflow must send in X-Callback-Token header')
    callback_url_hint = fields.Char(
        string='Callback URL (read-only)',
        compute='_compute_callback_url')

    # ── Stage mapping ─────────────────────────────────────────────────
    trigger_stage_ids = fields.Many2many(
        comodel_name='request.stage',
        relation='workflow_config_trigger_stage_rel',
        string='Auto-trigger Stages',
        help='Requests entering these stages are automatically sent to WorkSpace')
    approved_stage_id = fields.Many2one(
        comodel_name='request.stage',
        string='Approved → Move to Stage',
        help='Stage to advance request to when Workflow returns Approved')
    rejected_stage_id = fields.Many2one(
        comodel_name='request.stage',
        string='Rejected → Move to Stage',
        help='Stage to move request back to when Workflow returns Rejected')

    # ── Payload options ───────────────────────────────────────────────
    include_attachments = fields.Boolean(
        string='Include Attachments in Payload', default=True)
    payload_template = fields.Text(
        string='Custom Payload Template (JSON)',
        help='Optional Jinja2/JSON template override for the request payload. '
             'Leave blank to use default.')
    notes = fields.Text(string='Integration Notes',
                        help='Internal notes for the integration team')

    @api.depends('callback_enabled')
    def _compute_callback_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', 'https://myservice.com.ng')
        for rec in self:
            rec.callback_url_hint = f"{base}/myservice/workflow/callback"

    def action_test_connection(self):
        """Test the connection to the NRS WorkSpace."""
        self.ensure_one()
        if self.adapter_type == 'stub':
            return self._notify('Stub mode — no real connection. Change adapter type when ready.')
        adapter = self._get_adapter()
        result = adapter.ping()
        if result.get('ok'):
            return self._notify(f"Connection successful: {result.get('message','OK')}")
        raise UserError(f"Connection failed: {result.get('error','Unknown error')}")

    def _get_adapter(self):
        """Factory — returns the correct adapter based on config."""
        self.ensure_one()
        if self.adapter_type == 'rest':
            return WorkflowRestAdapter(self)
        elif self.adapter_type == 'email':
            return WorkflowEmailAdapter(self)
        else:
            return WorkflowStubAdapter(self)

    def _notify(self, msg):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'WorkSpace Integration',
                'message': msg,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def get_active_config(self):
        cfg = self.search([('active', '=', True)], limit=1)
        if not cfg:
            raise UserError(
                'No active Workflow integration configuration found. '
                'Please configure one under Settings → WorkSpace Integration.')
        return cfg


# ══════════════════════════════════════════════════════════════════════
# ADAPTERS
# ══════════════════════════════════════════════════════════════════════

class WorkflowStubAdapter:
    """
    Stub adapter — simulates a successful send without contacting
    any external system. Use during development and testing.
    """
    def __init__(self, config):
        self.config = config

    def ping(self):
        return {'ok': True, 'message': 'Stub adapter — always succeeds'}

    def submit(self, payload):
        import uuid
        ref = f"WF-STUB-{uuid.uuid4().hex[:8].upper()}"
        _logger.info("STUB: Would send payload to Workflow — ref: %s", ref)
        _logger.info("STUB payload: %s", json.dumps(payload, indent=2, default=str))
        return {
            'ok': True,
            'workspace_ref': ref,
            'message': 'Stub — simulated submission accepted',
        }


class WorkflowRestAdapter:
    """
    REST/JSON adapter. Connects to the Workflow API endpoint.
    NRS IT team to provide: base URL, auth credentials, endpoint paths.
    """
    def __init__(self, config):
        self.config = config

    def _get_headers(self):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.config.rest_auth_type == 'apikey':
            headers[self.config.rest_api_key_header or 'X-API-Key'] = \
                self.config.rest_api_key or ''
        elif self.config.rest_auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {self.config.rest_api_key or ''}"
        return headers

    def _get_auth(self):
        if self.config.rest_auth_type == 'basic':
            return (self.config.rest_username or '',
                    self.config.rest_password or '')
        return None

    def ping(self):
        import requests as req
        try:
            url = (self.config.rest_base_url or '').rstrip('/') + '/ping'
            r = req.get(url, headers=self._get_headers(),
                        auth=self._get_auth(),
                        timeout=self.config.rest_timeout or 10)
            if r.status_code < 400:
                return {'ok': True, 'message': f"HTTP {r.status_code}"}
            return {'ok': False, 'error': f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def submit(self, payload):
        import requests as req
        try:
            base = (self.config.rest_base_url or '').rstrip('/')
            endpoint = (self.config.rest_endpoint_submit or '/requests/submit').lstrip('/')
            url = f"{base}/{endpoint}"
            r = req.post(
                url,
                headers=self._get_headers(),
                auth=self._get_auth(),
                json=payload,
                timeout=self.config.rest_timeout or 30,
            )
            _logger.info("Workflow REST submit → %s  status=%s", url, r.status_code)
            if r.status_code in (200, 201, 202):
                try:
                    data = r.json()
                except Exception:
                    data = {}
                return {
                    'ok': True,
                    'workspace_ref': data.get('reference') or data.get('ref')
                                    or data.get('id') or f"WF-{r.status_code}",
                    'message': data.get('message', 'Submitted'),
                    'raw': r.text[:500],
                }
            return {
                'ok': False,
                'error': f"HTTP {r.status_code}: {r.text[:300]}",
            }
        except Exception as e:
            _logger.error("Workflow REST submit error: %s", e, exc_info=True)
            return {'ok': False, 'error': str(e)}


class WorkflowEmailAdapter:
    """
    Email adapter — sends a structured email to the NRS WorkSpace's
    monitored inbox. Used when Workflow has no API but monitors email.
    """
    def __init__(self, config):
        self.config = config

    def ping(self):
        if not self.config.email_to:
            return {'ok': False, 'error': 'No Workflow email address configured'}
        return {'ok': True, 'message': f"Email adapter ready → {self.config.email_to}"}

    def submit(self, payload):
        import uuid
        ref = f"WF-EMAIL-{uuid.uuid4().hex[:8].upper()}"
        try:
            subject = (
                f"{self.config.email_subject_prefix or '[NRS-WORKFLOW]'} "
                f"Approval Request: {payload.get('reference','N/A')} — "
                f"{payload.get('type','Request')}"
            )
            body = self._build_email_body(payload, ref)
            mail = self.config.env['mail.mail'].sudo().create({
                'subject': subject,
                'email_to': self.config.email_to,
                'body_html': body,
                'state': 'outgoing',
            })
            mail.send()
            _logger.info("Workflow email sent to %s ref=%s", self.config.email_to, ref)
            return {'ok': True, 'workspace_ref': ref, 'message': f"Email sent to {self.config.email_to}"}
        except Exception as e:
            _logger.error("Workflow email error: %s", e, exc_info=True)
            return {'ok': False, 'error': str(e)}

    def _build_email_body(self, payload, ref):
        rows = ''.join(
            f"<tr><td style='padding:6px 12px;font-weight:600;background:#f5f5f5'>{k}</td>"
            f"<td style='padding:6px 12px'>{v}</td></tr>"
            for k, v in payload.items()
            if k not in ('attachments', 'raw_text')
        )
        return f"""
<div style='font-family:Arial,sans-serif;max-width:640px'>
  <div style='background:#1A1A1A;padding:16px 24px;border-bottom:3px solid #E85426'>
    <h2 style='color:#fff;margin:0;font-size:16px'>NRS myservice — Workflow Approval Request</h2>
    <p style='color:rgba(255,255,255,0.6);margin:4px 0 0;font-size:12px'>Ref: {ref}</p>
  </div>
  <table style='width:100%;border-collapse:collapse;margin:16px 0'>{rows}</table>
  <p style='font-size:12px;color:#888'>
    This request was submitted from NRS myservice.com.ng.<br>
    To respond, use your NRS WorkSpace or reply to this email with:
    APPROVED / REJECTED / QUERY: [your comment]
  </p>
</div>"""
