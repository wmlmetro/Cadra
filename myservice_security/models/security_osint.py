from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


class SecurityOsintFeed(models.Model):
    _name = 'security.osint.feed'
    _description = 'Security OSINT Intelligence Feed'
    _order = 'date desc, id desc'

    title = fields.Char(string='Headline', required=True)
    summary = fields.Text(string='Summary')
    source_type = fields.Selection([
        ('manual',    'Manual Intel'),
        ('rss',       'RSS / External Feed'),
        ('watchlist', 'Watchlist Activity'),
        ('ai_pattern','AI Pattern Alert'),
        ('state',     'State Threat Alert'),
    ], string='Source Type', required=True, default='manual')
    source_name = fields.Char(string='Source Name')
    threat_level = fields.Selection([
        ('info',     'Info'),
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ], string='Threat Level', default='info', required=True)
    location_id = fields.Many2one(
        comodel_name='generic.location', string='Related Location')
    state_name = fields.Char(string='State / Region')
    url = fields.Char(string='Source URL')
    date = fields.Datetime(
        string='Date', default=fields.Datetime.now, required=True)
    active = fields.Boolean(default=True)
    is_verified = fields.Boolean(string='Verified', default=False)
    added_by = fields.Many2one(
        comodel_name='res.users', string='Added By',
        default=lambda self: self.env.user)


class SecurityStateThreat(models.Model):
    _name = 'security.state.threat'
    _description = 'State-level Threat Assessment'

    name = fields.Char(string='State', required=True)
    threat_level = fields.Selection([
        ('green',  'Low / Normal'),
        ('yellow', 'Elevated'),
        ('orange', 'High'),
        ('red',    'Critical'),
    ], string='Threat Level', default='green', required=True)
    notes = fields.Text(string='Notes')
    last_updated = fields.Datetime(
        string='Last Updated', default=fields.Datetime.now)

    @api.model
    def _seed_states(self):
        states = [
            'Abia','Adamawa','Akwa Ibom','Anambra','Bauchi','Bayelsa',
            'Benue','Borno','Cross River','Delta','Ebonyi','Edo','Ekiti',
            'Enugu','FCT','Gombe','Imo','Jigawa','Kaduna','Kano','Katsina',
            'Kebbi','Kogi','Kwara','Lagos','Nasarawa','Niger','Ogun','Ondo',
            'Osun','Oyo','Plateau','Rivers','Sokoto','Taraba','Yobe','Zamfara'
        ]
        for s in states:
            if not self.search([('name','=',s)], limit=1):
                self.create({'name': s, 'threat_level': 'green'})
