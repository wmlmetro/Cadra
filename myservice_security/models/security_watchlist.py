from odoo import models, fields, api


class SecurityWatchlist(models.Model):
    _name = 'security.watchlist'
    _description = 'Security Watchlist / OSINT'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'threat_level desc, name asc'

    name = fields.Char(
        string='Primary Name',
        required=True,
        tracking=True,
    )
    alias_ids = fields.One2many(
        comodel_name='security.watchlist.alias',
        inverse_name='watchlist_id',
        string='Known Aliases',
    )
    photo = fields.Binary(string='Photo')
    id_number = fields.Char(string='ID / NIN Number', tracking=True)
    id_type = fields.Selection(
        selection=[
            ('nin', 'NIN'), ('passport', 'Passport'),
            ('drivers', "Driver's Licence"), ('other', 'Other'),
        ],
        string='ID Type',
    )
    date_of_birth = fields.Date(string='Date of Birth')
    nationality = fields.Char(string='Nationality', default='Nigerian')
    phone = fields.Char(string='Phone Number')
    address = fields.Text(string='Last Known Address')

    threat_level = fields.Selection(
        selection=[
            ('low',      'Low — Monitor'),
            ('medium',   'Medium — Alert'),
            ('high',     'High — Detain & Report'),
            ('critical', 'Critical — Do Not Engage / Call Police'),
        ],
        string='Threat Level',
        required=True,
        default='medium',
        tracking=True,
    )
    category = fields.Selection(
        selection=[
            ('theft',      'Theft / Robbery'),
            ('fraud',      'Fraud / Impersonation'),
            ('violence',   'Violence / Assault'),
            ('espionage',  'Espionage / Intelligence Risk'),
            ('terrorism',  'Terrorism / Extremism'),
            ('trespass',   'Repeat Trespasser'),
            ('other',      'Other'),
        ],
        string='Category',
        required=True,
        tracking=True,
    )
    reason = fields.Html(
        string='Reason for Listing',
        required=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    date_added = fields.Date(
        string='Date Added',
        default=fields.Date.today,
        readonly=True,
    )
    added_by = fields.Many2one(
        comodel_name='res.users',
        string='Added By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    approved_by = fields.Many2one(
        comodel_name='res.users',
        string='Approved By',
        tracking=True,
    )
    approval_state = fields.Selection(
        selection=[
            ('pending',  'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval Status',
        default='pending',
        tracking=True,
    )

    # ── Vehicle information ───────────────────────────────────────────
    vehicle_description = fields.Char(
        string='Vehicle Description',
        help='Make, model, colour',
    )
    vehicle_plate = fields.Char(string='Vehicle Plate Number')
    vehicle_notes = fields.Text(string='Vehicle Notes')

    # ── Associate network ─────────────────────────────────────────────
    associate_ids = fields.Many2many(
        comodel_name='security.watchlist',
        relation='security_watchlist_associate_rel',
        column1='watchlist_id',
        column2='associate_id',
        string='Known Associates',
    )

    # ── Location flags ────────────────────────────────────────────────
    location_ids = fields.Many2many(
        comodel_name='generic.location',
        relation='security_watchlist_location_rel',
        column1='watchlist_id',
        column2='location_id',
        string='Flagged Locations',
        help='FIRS offices where this person has been sighted or poses a risk',
    )

    # ── Incident history ──────────────────────────────────────────────
    incident_ids = fields.Many2many(
        comodel_name='security.incident',
        relation='security_incident_watchlist_rel',
        column1='watchlist_id',
        column2='incident_id',
        string='Related Incidents',
    )
    incident_count = fields.Integer(
        string='Incidents',
        compute='_compute_incident_count',
    )

    # ── OSINT notes ───────────────────────────────────────────────────
    osint_notes = fields.Html(
        string='OSINT / Intelligence Notes',
        help='Open source intelligence gathered on this subject',
    )
    social_media = fields.Text(
        string='Social Media Handles',
    )
    last_sighted = fields.Datetime(
        string='Last Sighted',
        tracking=True,
    )
    last_sighted_location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Last Sighted Location',
    )

    @api.depends('incident_ids')
    def _compute_incident_count(self):
        for rec in self:
            rec.incident_count = len(rec.incident_ids)

    def action_approve(self):
        self.write({
            'approval_state': 'approved',
            'approved_by': self.env.user.id,
        })

    def action_reject(self):
        self.write({'approval_state': 'rejected'})

    def action_view_incidents(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Related Incidents',
            'res_model': 'security.incident',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.incident_ids.ids)],
        }


class SecurityWatchlistAlias(models.Model):
    _name = 'security.watchlist.alias'
    _description = 'Watchlist Alias'

    watchlist_id = fields.Many2one(
        comodel_name='security.watchlist',
        string='Watchlist Entry',
        ondelete='cascade',
        required=True,
    )
    alias = fields.Char(string='Alias / Known Name', required=True)
    notes = fields.Char(string='Notes')
