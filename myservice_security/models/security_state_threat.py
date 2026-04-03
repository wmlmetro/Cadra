from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


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
