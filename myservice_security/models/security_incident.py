from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SecurityIncident(models.Model):
    _name = 'security.incident'
    _description = 'Security Incident'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_incident desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Incident Reference',
        readonly=True,
        default='New',
        copy=False,
        tracking=True,
    )
    incident_type = fields.Selection(
        selection=[
            ('theft',               'Theft'),
            ('vandalism',           'Vandalism'),
            ('assault',             'Assault'),
            ('trespass',            'Trespass / Unauthorized Entry'),
            ('fire',                'Fire / Explosion'),
            ('medical',             'Medical Emergency'),
            ('suspicious_activity', 'Suspicious Activity'),
            ('data_breach',         'Data / Document Breach'),
            ('armed_robbery',       'Armed Robbery'),
            ('bomb_threat',         'Bomb Threat'),
            ('other',               'Other'),
        ],
        string='Incident Type',
        required=True,
        tracking=True,
    )
    severity = fields.Selection(
        selection=[
            ('low',      'Low'),
            ('medium',   'Medium'),
            ('high',     'High'),
            ('critical', 'Critical'),
        ],
        string='Severity',
        required=True,
        default='medium',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('new',          'New'),
            ('investigating', 'Under Investigation'),
            ('escalated',    'Escalated'),
            ('resolved',     'Resolved'),
            ('closed',       'Closed'),
        ],
        string='Status',
        default='new',
        tracking=True,
        index=True,
    )
    location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Location',
        required=True,
        tracking=True,
        index=True,
    )
    date_incident = fields.Datetime(
        string='Date & Time of Incident',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    date_reported = fields.Datetime(
        string='Date Reported',
        default=fields.Datetime.now,
        readonly=True,
    )
    reported_by = fields.Many2one(
        comodel_name='res.partner',
        string='Reported By',
        tracking=True,
    )
    assigned_to = fields.Many2one(
        comodel_name='res.users',
        string='Assigned To',
        tracking=True,
    )
    description = fields.Html(
        string='Incident Description',
        required=True,
    )
    witness_ids = fields.Many2many(
        comodel_name='res.partner',
        relation='security_incident_witness_rel',
        column1='incident_id',
        column2='partner_id',
        string='Witnesses',
    )
    suspect_description = fields.Text(
        string='Suspect Description',
        help='Physical description, clothing, vehicle, etc.',
    )
    items_stolen = fields.Text(
        string='Items Stolen / Damaged',
    )
    police_report_number = fields.Char(
        string='Police Report Number',
        tracking=True,
    )
    police_station = fields.Char(
        string='Police Station',
    )
    resolution_notes = fields.Html(
        string='Resolution Notes',
    )
    date_resolved = fields.Datetime(
        string='Date Resolved',
        tracking=True,
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='security_incident_attachment_rel',
        column1='incident_id',
        column2='attachment_id',
        string='Evidence / Attachments',
    )
    guard_id = fields.Many2one(
        comodel_name='security.guard',
        string='Responding Guard',
        tracking=True,
    )
    is_portal_report = fields.Boolean(
        string='Portal Report',
        default=False,
        help='Reported via staff portal',
    )
    # Computed
    location_lat = fields.Float(related='location_id.latitude', store=False)
    location_lng = fields.Float(related='location_id.longitude', store=False)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('security.incident') or 'New'
        return super().create(vals)

    def action_investigate(self):
        self.write({'state': 'investigating'})

    def action_escalate(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Escalate Incident',
            'res_model': 'security.incident.escalate',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_incident_id': self.id},
        }

    def action_resolve(self):
        self.write({
            'state': 'resolved',
            'date_resolved': fields.Datetime.now(),
        })

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reopen(self):
        self.write({'state': 'investigating'})
