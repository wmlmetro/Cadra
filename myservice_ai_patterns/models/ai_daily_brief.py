# -*- coding: utf-8 -*-
"""
models/ai_daily_brief.py
NRS myservice — AI Daily Intelligence Brief
Enhanced with Nigerian government classification tiers,
three brief formats, download logging, and approval workflow.
"""

from odoo import models, fields, api
from odoo.exceptions import AccessError, UserError
import logging
import requests
import json

_logger = logging.getLogger(__name__)

# ── Classification colours (used in PDF banner) ──────────────────────────────
CLASSIFICATION_COLOURS = {
    'restricted':   '#1565C0',   # Blue
    'confidential': '#E65100',   # Amber
    'secret':       '#B71C1C',   # Red
    'top_secret':   '#0D0D0D',   # Black
}

CLASSIFICATION_LABELS = {
    'restricted':   'RESTRICTED',
    'confidential': 'CONFIDENTIAL',
    'secret':       'SECRET',
    'top_secret':   'TOP SECRET',
}

THREAT_COLOURS = {
    'low':      '#27500A',
    'moderate': '#633806',
    'high':     '#B71C1C',
    'critical': '#0D0D0D',
}


class AiDailyBrief(models.Model):
    _name        = 'ai.daily.brief'
    _description = 'AI Daily Intelligence Brief'
    _order       = 'date desc, brief_format asc'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Brief Title', required=True,
        default=lambda self: self._default_name())
    ref = fields.Char(
        string='Reference Number', readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('nrs.intel.brief'))
    date = fields.Date(
        string='Brief Date', required=True, default=fields.Date.today)
    time_of_issue = fields.Char(
        string='Time of Issue', default='08:00')

    # ── Format ────────────────────────────────────────────────────────────────
    brief_format = fields.Selection([
        ('tactical',    'Tactical Brief (1 page — field teams)'),
        ('operational', 'Operational Brief (2 pages — security officers)'),
        ('strategic',   'Strategic Brief (4–6 pages — management)'),
    ], string='Brief Format', required=True, default='operational')

    # ── Classification ────────────────────────────────────────────────────────
    classification = fields.Selection([
        ('restricted',   'RESTRICTED'),
        ('confidential', 'CONFIDENTIAL'),
        ('secret',       'SECRET'),
        ('top_secret',   'TOP SECRET'),
    ], string='Classification', required=True, default='restricted')

    distribution_caveat = fields.Selection([
        ('internal',       'NRS INTERNAL ONLY'),
        ('need_to_know',   'NEED TO KNOW'),
        ('no_foreign',     'NO FOREIGN NATIONALS'),
        ('limited',        'LIMITED DISTRIBUTION'),
        ('eyes_only',      'EYES ONLY'),
    ], string='Distribution Caveat', default='internal')

    distribution_list = fields.Many2many(
        'res.users', 'brief_distribution_rel', 'brief_id', 'user_id',
        string='Named Recipients',
        help='Required when Distribution Caveat is NEED TO KNOW or EYES ONLY')

    # ── Threat Assessment ─────────────────────────────────────────────────────
    threat_level = fields.Selection([
        ('low',      'LOW'),
        ('moderate', 'MODERATE'),
        ('high',     'HIGH'),
        ('critical', 'CRITICAL'),
    ], string='Overall Threat Level', required=True, default='low')

    # ── Content Sections ──────────────────────────────────────────────────────
    exec_summary = fields.Text(
        string='Executive Summary',
        help='AI-generated. 3–5 bullet points covering the key intelligence picture.')
    threat_landscape = fields.Text(
        string='Threat Landscape',
        help='AI-generated. Regional analysis based on OSINT and ACLED data.')
    intel_entries_summary = fields.Text(
        string='Intelligence Entries Summary',
        help='AI-generated summary of contributing OSINT entries.')
    watchlist_summary = fields.Text(
        string='Watchlist Summary',
        help='AI-generated. Active POIs, new additions, status changes.')
    recommendations = fields.Text(
        string='Recommendations',
        help='AI-generated action items for the security team.')
    handling_instructions = fields.Text(
        string='Handling Instructions',
        help='Classification authority, declassification date, disposal instructions.')

    # ── Sources ───────────────────────────────────────────────────────────────
    osint_entry_ids = fields.Many2many(
        'osint.feed.entry', 'brief_osint_rel', 'brief_id', 'entry_id',
        string='Source OSINT Entries')
    watchlist_ids = fields.Many2many(
        'security.watchlist', 'brief_watchlist_rel', 'brief_id', 'watchlist_id',
        string='Active Watchlist Entries')
    incident_ids = fields.Many2many(
        'security.incident', 'brief_incident_rel', 'brief_id', 'incident_id',
        string='Contributing Incidents')
    acled_entry_count = fields.Integer(
        string='ACLED Entries Analysed', default=0)

    # ── Approval Workflow ─────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',            'Draft'),
        ('ai_generating',    'AI Generating'),
        ('pending_approval', 'Pending Approval'),
        ('approved',         'Approved'),
        ('released',         'Released'),
        ('recalled',         'Recalled'),
    ], string='Status', default='draft', tracking=True)

    prepared_by     = fields.Many2one('res.users', string='Prepared By',
                                       default=lambda self: self.env.user)
    approved_by     = fields.Many2one('res.users', string='Approved By',
                                       readonly=True)
    approved_date   = fields.Datetime(string='Approval Date/Time', readonly=True)
    released_by     = fields.Many2one('res.users', string='Released By',
                                       readonly=True)
    released_date   = fields.Datetime(string='Release Date/Time', readonly=True)
    recall_reason   = fields.Text(string='Recall Reason')

    # ── Download Tracking ─────────────────────────────────────────────────────
    download_log_ids = fields.One2many(
        'ai.brief.download.log', 'brief_id', string='Download Log')
    download_count = fields.Integer(
        string='Downloads', compute='_compute_download_count', store=True)

    # ── Computed display fields ────────────────────────────────────────────────
    classification_colour = fields.Char(
        compute='_compute_classification_display', string='Classification Colour')
    classification_label = fields.Char(
        compute='_compute_classification_display', string='Classification Label')
    threat_colour = fields.Char(
        compute='_compute_threat_colour', string='Threat Colour')

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _default_name(self):
        fmt = self.env.context.get('default_brief_format', 'operational')
        labels = {
            'tactical':    'Tactical Intelligence Brief',
            'operational': 'Operational Intelligence Brief',
            'strategic':   'Strategic Intelligence Brief',
        }
        return f"NRS {labels.get(fmt, 'Intelligence Brief')} — {fields.Date.today()}"

    @api.depends('download_log_ids')
    def _compute_download_count(self):
        for r in self:
            r.download_count = len(r.download_log_ids)

    @api.depends('classification')
    def _compute_classification_display(self):
        for r in self:
            r.classification_colour = CLASSIFICATION_COLOURS.get(r.classification, '#333')
            r.classification_label  = CLASSIFICATION_LABELS.get(r.classification, 'RESTRICTED')

    @api.depends('threat_level')
    def _compute_threat_colour(self):
        for r in self:
            r.threat_colour = THREAT_COLOURS.get(r.threat_level, '#333')

    # ── AI Generation ─────────────────────────────────────────────────────────
    def action_generate_ai(self):
        """Trigger AI generation for this brief."""
        self.ensure_one()
        self.state = 'ai_generating'
        try:
            self._run_ai_generation()
            self.state = 'pending_approval'
        except Exception as e:
            self.state = 'draft'
            raise UserError(f'AI generation failed: {e}')

    def _run_ai_generation(self):
        """Call Claude API to generate all brief sections."""
        self.ensure_one()

        # Gather context
        osint_entries = self.env['osint.feed.entry'].search(
            [('event_date', '>=', fields.Date.today())],
            order='threat_level desc', limit=50)
        watchlist = self.env['security.watchlist'].search(
            [('state', 'in', ['active', 'alert'])], limit=20)
        incidents = self.env['security.incident'].search(
            [('state', 'not in', ['closed', 'cancelled'])], limit=20)

        # Build context string
        osint_context = '\n'.join([
            f"- [{e.threat_level.upper()}] {e.title} | {e.state_name} | {e.source_name}"
            for e in osint_entries[:30]
        ]) or "No OSINT entries for today."

        watchlist_context = '\n'.join([
            f"- {w.name} | Threat: {w.threat_tier} | Status: {w.state}"
            for w in watchlist[:10]
        ]) or "No active watchlist entries."

        incident_context = '\n'.join([
            f"- {i.name} | {i.severity} | {i.state}"
            for i in incidents[:10]
        ]) or "No open incidents."

        format_instructions = {
            'tactical': (
                "Generate a TACTICAL BRIEF — maximum 1 page equivalent. "
                "Executive summary: 3 bullets max. No detailed sections. "
                "Recommendations: 3 immediate actions only. Concise military-style language."
            ),
            'operational': (
                "Generate an OPERATIONAL BRIEF — 2 page equivalent. "
                "Executive summary: 4–5 bullets. Include threat landscape and watchlist. "
                "Recommendations: 5–7 actionable items. Professional security language."
            ),
            'strategic': (
                "Generate a STRATEGIC BRIEF — full intelligence report format. "
                "Executive summary: 5 bullets. Full threat landscape analysis. "
                "Detailed intelligence entries. Watchlist. 8–10 recommendations. "
                "Senior management language."
            ),
        }

        system_prompt = """You are an AI intelligence analyst for the Nigeria Revenue Service (NRS) 
Security Intelligence Unit. You generate classified intelligence briefs based on OSINT data, 
watchlist entries, and incident reports. Write in formal intelligence report style. 
Be factual, concise, and professional. Do not fabricate specific details not in the data."""

        user_prompt = f"""Generate a {self.brief_format.upper()} intelligence brief for NRS Security.

{format_instructions.get(self.brief_format, '')}

DATE: {self.date}
THREAT LEVEL: {self.threat_level.upper()}
CLASSIFICATION: {self.classification_label}

TODAY'S OSINT ENTRIES:
{osint_context}

ACTIVE WATCHLIST:
{watchlist_context}

OPEN INCIDENTS:
{incident_context}

Respond ONLY with a JSON object — no markdown, no code fences:
{{
  "exec_summary": "bullet1\\nbullet2\\nbullet3",
  "threat_landscape": "regional analysis text",
  "intel_entries_summary": "summary of key intelligence entries",
  "watchlist_summary": "watchlist analysis",
  "recommendations": "action1\\naction2\\naction3",
  "handling_instructions": "Classification: {self.classification_label}\\nDeclassification: Review after 30 days\\nDisposal: Secure destruction after 90 days",
  "suggested_threat_level": "low|moderate|high|critical",
  "suggested_classification": "restricted|confidential|secret|top_secret"
}}"""

        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.env['ir.config_parameter'].sudo().get_param(
                        'anthropic.api_key', ''),
                    'anthropic-version': '2023-06-01',
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 2000,
                    'system': system_prompt,
                    'messages': [{'role': 'user', 'content': user_prompt}],
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            text = data['content'][0]['text'].strip()

            # Strip any accidental markdown fences
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            result = json.loads(text)

            # Apply generated content
            self.write({
                'exec_summary':          result.get('exec_summary', ''),
                'threat_landscape':      result.get('threat_landscape', ''),
                'intel_entries_summary': result.get('intel_entries_summary', ''),
                'watchlist_summary':     result.get('watchlist_summary', ''),
                'recommendations':       result.get('recommendations', ''),
                'handling_instructions': result.get('handling_instructions', ''),
                'osint_entry_ids':       [(6, 0, osint_entries.ids)],
                'watchlist_ids':         [(6, 0, watchlist.ids)],
                'incident_ids':          [(6, 0, incidents.ids)],
                'acled_entry_count':     len(osint_entries),
            })

            # Accept AI threat/classification suggestions if more severe than current
            suggested_threat = result.get('suggested_threat_level', self.threat_level)
            threat_order = ['low', 'moderate', 'high', 'critical']
            if threat_order.index(suggested_threat) > threat_order.index(self.threat_level):
                self.threat_level = suggested_threat

        except requests.exceptions.RequestException as e:
            _logger.error('Claude API request failed: %s', e)
            raise
        except json.JSONDecodeError as e:
            _logger.error('Claude API response not valid JSON: %s', e)
            raise UserError('AI returned invalid response. Please retry.')

    # ── Approval Workflow Actions ──────────────────────────────────────────────
    def action_submit_for_approval(self):
        self.ensure_one()
        if self.state not in ('draft', 'ai_generating'):
            raise UserError('Only draft briefs can be submitted for approval.')
        self.state = 'pending_approval'

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('myservice_security.group_security_manager'):
            raise AccessError('Only Security Managers can approve intelligence briefs.')
        self.write({
            'state':         'approved',
            'approved_by':   self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })

    def action_release(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('Only approved briefs can be released.')
        self.write({
            'state':         'released',
            'released_by':   self.env.user.id,
            'released_date': fields.Datetime.now(),
        })

    def action_recall(self):
        self.ensure_one()
        self.state = 'recalled'

    def action_reset_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    # ── Cron methods ──────────────────────────────────────────────────────────
    @api.model
    def cron_generate_tactical(self):
        self._cron_generate_format('tactical', 'restricted')

    @api.model
    def cron_generate_operational(self):
        self._cron_generate_format('operational', 'confidential')

    @api.model
    def cron_generate_strategic(self):
        self._cron_generate_format('strategic', 'secret')

    @api.model
    def _cron_generate_format(self, brief_format, classification):
        today = fields.Date.today()
        existing = self.search([
            ('date', '=', today),
            ('brief_format', '=', brief_format),
        ])
        if existing:
            _logger.info('Brief %s for %s already exists — skipping cron', brief_format, today)
            return

        format_names = {
            'tactical':    'Tactical Intelligence Brief',
            'operational': 'Operational Intelligence Brief',
            'strategic':   'Strategic Intelligence Brief',
        }
        brief = self.create({
            'name':          f"NRS {format_names[brief_format]} — {today}",
            'date':          today,
            'brief_format':  brief_format,
            'classification': classification,
            'state':         'draft',
        })
        try:
            brief.action_generate_ai()
            _logger.info('Brief %s generated successfully for %s', brief_format, today)
        except Exception as e:
            _logger.error('Cron brief generation failed for %s: %s', brief_format, e)


class AiBriefDownloadLog(models.Model):
    _name        = 'ai.brief.download.log'
    _description = 'Intelligence Brief Download Log'
    _order       = 'download_datetime desc'
    _rec_name    = 'download_ref'

    brief_id          = fields.Many2one('ai.daily.brief', string='Brief',
                                         required=True, ondelete='restrict')
    user_id           = fields.Many2one('res.users', string='Downloaded By',
                                         required=True, default=lambda self: self.env.user)
    download_ref      = fields.Char(string='Download Reference', readonly=True, copy=False,
                                     default=lambda self: self.env['ir.sequence'].next_by_code(
                                         'nrs.brief.download'))
    download_datetime = fields.Datetime(string='Date/Time', required=True,
                                         default=fields.Datetime.now)
    ip_address        = fields.Char(string='IP Address')
    brief_format      = fields.Char(string='Format')
    classification    = fields.Char(string='Classification at Download')
    watermark_text    = fields.Text(string='Watermark Applied')
