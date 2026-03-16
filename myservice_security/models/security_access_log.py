from odoo import models, fields, api


class SecurityAccessLog(models.Model):
    _name = 'security.access.log'
    _description = 'Security Access Log'
    _order = 'datetime desc'

    location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Location',
        required=True,
        index=True,
    )
    person_name = fields.Char(string='Person Name', required=True)
    id_number    = fields.Char(string='ID / NIN Number')
    id_type = fields.Selection(
        selection=[
            ('nin',       'NIN'),
            ('passport',  'Passport'),
            ('drivers',   'Driver\'s Licence'),
            ('staff_id',  'Staff ID'),
            ('other',     'Other'),
        ],
        string='ID Type',
        default='staff_id',
    )
    direction = fields.Selection(
        selection=[('in', 'Entry'), ('out', 'Exit')],
        string='Direction',
        required=True,
        default='in',
    )
    datetime = fields.Datetime(
        string='Date & Time',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    purpose = fields.Char(string='Purpose of Visit')
    host_name = fields.Char(string='Host / Staff Name')
    vehicle_plate = fields.Char(string='Vehicle Plate')
    authorized = fields.Boolean(
        string='Authorized',
        default=True,
        tracking=True,
    )
    guard_id = fields.Many2one(
        comodel_name='security.guard',
        string='Guard on Duty',
    )
    photo = fields.Binary(string='Visitor Photo')
    notes = fields.Text(string='Notes')
    flagged = fields.Boolean(
        string='Flagged',
        default=False,
        help='Flag if person matches watchlist or is suspicious',
    )
    watchlist_match_id = fields.Many2one(
        comodel_name='security.watchlist',
        string='Watchlist Match',
    )
