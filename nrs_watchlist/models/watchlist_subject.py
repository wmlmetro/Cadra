from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WatchlistSubject(models.Model):
    _name = 'nrs.watchlist.subject'
    _description = 'NRS SOC Watchlist Subject'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'threat_tier, name'
    _rec_name = 'name'

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Full Name', required=True, tracking=True,
        help='Full legal name of the subject')
    alias = fields.Char(
        string='Alias / Handle', tracking=True,
        help='Known alias, nickname, or operational handle')
    reference = fields.Char(
        string='Watchlist ID', readonly=True, copy=False,
        default='New', help='Auto-generated watchlist reference')

    # ── Photo / Mugshot ───────────────────────────────────────────────────────
    photo = fields.Binary(
        string='Mugshot / Photo', attachment=True,
        help='Upload from Odoo — JPEG/PNG passport-style photo')
    photo_url = fields.Char(
        string='External Photo URL',
        help='URL to photo from external mugshot system or API feed')
    photo_source = fields.Selection([
        ('upload', 'Odoo Upload'),
        ('url', 'External URL'),
        ('api', 'API Feed (Auto)'),
        ('none', 'No Photo'),
    ], string='Photo Source', default='none', tracking=True)

    # ── Threat Classification ─────────────────────────────────────────────────
    threat_tier = fields.Selection([
        ('delta', 'DELTA — Extreme Threat'),
        ('charlie', 'CHARLIE — High Threat'),
        ('bravo', 'BRAVO — Medium Threat'),
    ], string='Threat Tier', required=True, default='bravo', tracking=True,
        help='DELTA=extreme/armed, CHARLIE=high/fraud, BRAVO=medium/surveillance')

    status = fields.Selection([
        ('active', 'Active — At Large'),
        ('detained', 'Detained — In Custody'),
        ('cleared', 'Cleared — Case Closed'),
        ('pending', 'Pending — Under Review'),
    ], string='Status', required=True, default='active', tracking=True)

    # ── Charge / Reason ───────────────────────────────────────────────────────
    charge = fields.Text(
        string='Wanted Reason / Charge', required=True,
        help='Describe the reason for listing — offence, suspicion, or charge')
    charge_category = fields.Selection([
        ('tax_fraud', 'Tax Fraud / Evasion'),
        ('identity', 'Identity Forgery / Impersonation'),
        ('intrusion', 'Physical Intrusion / Armed'),
        ('cyber', 'Cyber / IT Intrusion'),
        ('procurement', 'Procurement Fraud'),
        ('bribery', 'Bribery / Corruption'),
        ('smuggling', 'Smuggling / Contraband'),
        ('surveillance', 'Suspicious Surveillance'),
        ('other', 'Other'),
    ], string='Charge Category', required=True, default='other')

    # ── Location ──────────────────────────────────────────────────────────────
    last_known_location = fields.Char(
        string='Last Known Location', tracking=True)
    last_seen_date = fields.Datetime(
        string='Last Seen', tracking=True)
    custody_location = fields.Char(
        string='Custody / Detention Location',
        help='Filled when status = Detained')
    state_id = fields.Many2one(
        'res.country.state', string='State',
        domain="[('country_id.name','=','Nigeria')]")

    # ── Source / API Feed ─────────────────────────────────────────────────────
    data_source = fields.Selection([
        ('internal', 'Internal / Odoo'),
        ('dss', 'DSS Feed'),
        ('npf', 'NPF Feed'),
        ('interpol', 'INTERPOL Feed'),
        ('efcc', 'EFCC Feed'),
        ('manual', 'Manual Entry'),
    ], string='Data Source', default='manual', tracking=True)
    api_record_id = fields.Char(
        string='API Record ID',
        help='Original ID from external feed — for dedup and sync')
    last_api_sync = fields.Datetime(
        string='Last API Sync', readonly=True)

    # ── Intelligence Notes ────────────────────────────────────────────────────
    intelligence_notes = fields.Html(
        string='Intelligence Notes',
        help='Classified intelligence notes — restricted access')
    risk_score = fields.Integer(
        string='Risk Score (0–100)', default=50,
        help='Composite risk score for ranking in the board')

    # ── Linked Records ────────────────────────────────────────────────────────
    linked_incident_ids = fields.Many2many(
        'generic.request', string='Linked Incidents',
        help='ITSM incidents linked to this subject')
    alert_count = fields.Integer(
        string='Alerts Raised', default=0, readonly=True)

    # ── Computed ──────────────────────────────────────────────────────────────
    display_photo = fields.Boolean(
        compute='_compute_display_photo', store=False)
    tier_color = fields.Integer(
        compute='_compute_tier_color', store=False)

    @api.depends('photo', 'photo_url', 'photo_source')
    def _compute_display_photo(self):
        for rec in self:
            rec.display_photo = bool(rec.photo or rec.photo_url)

    @api.depends('threat_tier')
    def _compute_tier_color(self):
        colors = {'delta': 1, 'charlie': 3, 'bravo': 4}
        for rec in self:
            rec.tier_color = colors.get(rec.threat_tier, 0)

    # ── Sequence / Reference ──────────────────────────────────────────────────
    @api.model
    def create(self, vals):
        if vals.get('reference', 'New') == 'New':
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'nrs.watchlist.subject') or 'WL-NEW'
        return super().create(vals)

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains('risk_score')
    def _check_risk_score(self):
        for rec in self:
            if not (0 <= rec.risk_score <= 100):
                raise ValidationError('Risk score must be between 0 and 100.')

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_flag_active(self):
        self.ensure_one()
        self.write({'status': 'active'})
        self.message_post(body='Subject flagged as ACTIVE by SOC operator.')
        return True

    def action_mark_detained(self):
        self.ensure_one()
        self.write({'status': 'detained'})
        self.message_post(body='Subject status updated to DETAINED.')
        return True

    def action_mark_cleared(self):
        self.ensure_one()
        self.write({'status': 'cleared'})
        self.message_post(body='Subject CLEARED — case closed.')
        return True

    def action_raise_alert(self):
        self.ensure_one()
        self.alert_count += 1
        self.message_post(
            body=f'SECURITY ALERT raised for {self.name} ({self.reference}). '
                 f'Threat tier: {self.threat_tier.upper()}. '
                 f'Last known: {self.last_known_location or "Unknown"}')
        return True

    @api.model
    def get_board_data(self):
        """JSON-serialisable data for the SOC watchlist board JS widget."""
        subjects = self.search([('status', '!=', 'cleared')], order='threat_tier, risk_score desc')
        result = []
        for s in subjects:
            result.append({
                'id': s.id,
                'reference': s.reference,
                'name': s.name,
                'alias': s.alias or '',
                'tier': s.threat_tier,
                'status': s.status,
                'charge': s.charge,
                'charge_category': s.charge_category,
                'location': s.last_known_location or '',
                'source': dict(s._fields['data_source'].selection).get(s.data_source, ''),
                'photo_url': s.photo_url or '',
                'has_photo': bool(s.photo),
                'photo_endpoint': f'/web/image/nrs.watchlist.subject/{s.id}/photo' if s.photo else '',
                'risk_score': s.risk_score,
                'last_seen': s.last_seen_date.isoformat() if s.last_seen_date else '',
            })
        return result
