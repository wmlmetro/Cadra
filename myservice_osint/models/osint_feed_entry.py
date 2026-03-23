from odoo import models, fields, api


class OsintFeedEntry(models.Model):
    """
    Unified store for all OSINT intelligence entries.
    Every source adapter writes normalised entries here.
    """
    _name = 'osint.feed.entry'
    _description = 'OSINT Feed Entry'
    _order = 'event_date desc, create_date desc'
    _rec_name = 'title'

    source_config_id = fields.Many2one(
        'osint.source.config', string='Source', ondelete='set null')
    source_type = fields.Selection([
        ('acled',      'ACLED'),
        ('gdelt',      'GDELT'),
        ('rss',        'RSS / News'),
        ('reliefweb',  'ReliefWeb / OCHA'),
        ('twitter',    'Twitter/X'),
        ('telegram',   'Telegram'),
        ('manual',     'Manual / Analyst'),
        ('watchlist',  'Watchlist Activity'),
        ('ai_pattern', 'AI Pattern Detection'),
        ('state',      'State Threat Alert'),
    ], string='Source Type', required=True)
    source_name = fields.Char(string='Source')

    title       = fields.Char(string='Title', required=True)
    summary     = fields.Text(string='Summary')
    state_name  = fields.Char(string='State', index=True)
    event_date  = fields.Datetime(string='Event Date')
    latitude    = fields.Float(digits=(10, 6))
    longitude   = fields.Float(digits=(10, 6))

    threat_level = fields.Selection([
        ('critical',  'Critical'),
        ('high',      'High'),
        ('elevated',  'Elevated'),
        ('medium',    'Medium'),
        ('low',       'Low'),
        ('info',      'Info'),
    ], string='Threat Level', default='info', index=True)

    event_type   = fields.Char(string='Event Type')
    fatalities   = fields.Integer(string='Fatalities', default=0)
    raw_score    = fields.Integer(string='Raw Score', default=0)
    source_url   = fields.Char(string='Source URL')
    is_verified  = fields.Boolean(string='Verified', default=False)
    duplicate_hash = fields.Char(string='Dedup Hash', index=True)

    linked_incident_id = fields.Many2one(
        'security.incident', string='Linked Incident')
    linked_watchlist_id = fields.Many2one(
        'security.watchlist', string='Linked Watchlist Subject')

    added_by = fields.Many2one('res.users', string='Added By',
                               default=lambda self: self.env.user)

    threat_color = fields.Char(
        string='Colour', compute='_compute_threat_color')

    @api.depends('threat_level')
    def _compute_threat_color(self):
        colors = {
            'critical': '#dc3545',
            'high':     '#E85426',
            'elevated': '#fd7e14',
            'medium':   '#ffc107',
            'low':      '#28a745',
            'info':     '#17a2b8',
        }
        for rec in self:
            rec.threat_color = colors.get(rec.threat_level, '#888')
