from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AiPatternAlert(models.Model):
    """
    Stores each AI-detected security pattern.
    Created automatically by the pattern engine.
    Analyst reviews and confirms or dismisses.
    """
    _name = 'ai.pattern.alert'
    _description = 'AI Pattern Alert'
    _order = 'create_date desc'
    _rec_name = 'title'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference', readonly=True, copy=False)
    title = fields.Char(
        string='Alert Title', required=True, tracking=True)

    pattern_type = fields.Selection([
        ('cluster',    'Incident Cluster'),
        ('escalation', 'Escalation Pattern'),
        ('actor',      'Actor Pattern'),
        ('temporal',   'Temporal Anomaly'),
        ('route',      'Route Risk'),
        ('watchlist',  'Watchlist Proximity'),
    ], string='Pattern Type', required=True, tracking=True)

    severity = fields.Selection([
        ('critical', 'Critical'),
        ('high',     'High'),
        ('medium',   'Medium'),
        ('low',      'Low'),
    ], string='Severity', default='medium', tracking=True)

    state = fields.Selection([
        ('new',       'New — Unreviewed'),
        ('confirmed', 'Confirmed'),
        ('dismissed', 'Dismissed'),
        ('actioned',  'Actioned'),
    ], string='Status', default='new', tracking=True)

    confidence = fields.Float(
        string='AI Confidence', digits=(4, 2),
        help='0.0 to 1.0 — how confident the AI is in this pattern')

    # ── AI output ─────────────────────────────────────────────────────
    ai_summary = fields.Text(
        string='AI Summary',
        help='Plain English assessment from Claude')
    ai_recommended_actions = fields.Text(
        string='Recommended Actions',
        help='AI-generated response recommendations')
    ai_raw_response = fields.Text(
        string='Raw AI Response', readonly=True)

    # ── Affected data ─────────────────────────────────────────────────
    affected_states = fields.Char(string='Affected States')
    affected_locations = fields.Char(string='Affected Locations')
    incident_count = fields.Integer(string='Incidents in Pattern')
    date_range_start = fields.Datetime(string='Pattern Start')
    date_range_end = fields.Datetime(string='Pattern End')

    # ── Links ─────────────────────────────────────────────────────────
    linked_incident_ids = fields.Many2many(
        'security.incident',
        'ai_alert_incident_rel',
        'alert_id', 'incident_id',
        string='Linked Incidents')
    linked_osint_ids = fields.Many2many(
        'osint.feed.entry',
        'ai_alert_osint_rel',
        'alert_id', 'osint_id',
        string='Linked OSINT Entries')
    auto_created_incident_id = fields.Many2one(
        'security.incident',
        string='Auto-Created Incident',
        readonly=True)

    # ── Route risk specific ───────────────────────────────────────────
    route_origin = fields.Char(string='Route Origin')
    route_destination = fields.Char(string='Route Destination')
    route_risk_score = fields.Float(string='Route Risk Score (0–100)')

    # ── Notification tracking ─────────────────────────────────────────
    whatsapp_sent = fields.Boolean(string='WhatsApp Sent', readonly=True)
    email_sent = fields.Boolean(string='Email Sent', readonly=True)
    dashboard_shown = fields.Boolean(string='On Dashboard', default=True)

    analyst_note = fields.Text(string='Analyst Note')
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    reviewed_at = fields.Datetime(string='Reviewed At', readonly=True)

    @api.model
    def create(self, vals):
        if not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'ai.pattern.alert') or 'APA-NEW'
        return super().create(vals)

    def action_confirm(self):
        self.ensure_one()
        self.write({
            'state': 'confirmed',
            'reviewed_by': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
        })
        self.message_post(
            body=f'<p>✅ Pattern confirmed by {self.env.user.name}</p>',
            subtype_xmlid='mail.mt_comment')

    def action_dismiss(self):
        self.ensure_one()
        self.write({
            'state': 'dismissed',
            'reviewed_by': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
            'dashboard_shown': False,
        })
        self.message_post(
            body=f'<p>❌ Pattern dismissed by {self.env.user.name}</p>',
            subtype_xmlid='mail.mt_comment')

    def action_mark_actioned(self):
        self.ensure_one()
        self.write({'state': 'actioned'})
        self.message_post(
            body=f'<p>⚡ Actions taken by {self.env.user.name}</p>',
            subtype_xmlid='mail.mt_comment')

    def action_view_incidents(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Linked Incidents',
            'res_model': 'security.incident',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.linked_incident_ids.ids)],
            'target': 'current',
        }
