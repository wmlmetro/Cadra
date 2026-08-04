from odoo import models, fields


class RequestEventType(models.Model):
    _name = 'request.event.type'
    _description = 'Request Event Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)


class RequestEvent(models.Model):
    """Lightweight audit trail of what happened to a request (stage moves,
    assignment, etc.). The API can embed the last N events per request."""
    _name = 'request.event'
    _description = 'Request Event'
    _order = 'date desc, id desc'

    request_id = fields.Many2one(
        'request.request', string='Request', required=True,
        ondelete='cascade', index=True)
    event_type_id = fields.Many2one('request.event.type', string='Event Type')
    date = fields.Datetime(default=fields.Datetime.now, index=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda s: s.env.user)
    description = fields.Char()


class RequestTag(models.Model):
    _name = 'request.tag'
    _description = 'Request Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
