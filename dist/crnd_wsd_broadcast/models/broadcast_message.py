from odoo import models, fields


class BroadcastMessage(models.Model):
    _name = 'crnd.wsd.broadcast.message'
    _description = "Website Broadcast Message"
    _order = 'date_beg desc'

    name = fields.Char(required=True)
    message_text = fields.Html(required=True)
    message_style = fields.Selection([
        ('alert-primary', 'Primary'),
        ('alert-secondary', 'Secondary'),
        ('alert-success', 'Success'),
        ('alert-danger', 'Danger'),
        ('alert-warning', 'Warning'),
        ('alert-info', 'Info'),
        ('alert-light', 'Light'),
        ('alert-dark', 'Dark'),
    ], default='alert-info', required=True)
    date_beg = fields.Datetime(required=True, index=True)
    date_end = fields.Datetime(required=True, index=True)
    active = fields.Boolean(default=True, index=True)
    website_ids = fields.Many2many('website')
