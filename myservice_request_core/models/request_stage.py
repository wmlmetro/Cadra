from odoo import models, fields


class RequestStageType(models.Model):
    """The kind of a stage (new / in-progress / done ...). Exposed to the API
    as ``stage.type_code`` so the frontend can reason about lifecycle position
    independent of a stage's display name."""
    _name = 'request.stage.type'
    _description = 'Request Stage Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help='Stable machine code, e.g. new / in_progress / done.')
    sequence = fields.Integer(default=10)


class RequestStage(models.Model):
    _name = 'request.stage'
    _description = 'Request Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help='Stable machine code for API/integration use.')
    sequence = fields.Integer(default=10)
    stage_type_id = fields.Many2one('request.stage.type', string='Stage Type')
    closed = fields.Boolean(
        string='Closing Stage',
        help='Requests in this stage are considered closed/resolved.')
    fold = fields.Boolean(string='Folded in Kanban')
    active = fields.Boolean(default=True)

    # Outbound transitions allowed from this stage.
    route_out_ids = fields.One2many(
        'request.stage.route', 'stage_from_id', string='Outbound Routes')


class RequestStageRoute(models.Model):
    """A permitted transition between two stages. The API embeds these as the
    ``available_routes`` for a request's current stage."""
    _name = 'request.stage.route'
    _description = 'Request Stage Route'
    _order = 'sequence, id'
    _rec_name = 'name'

    name = fields.Char()
    sequence = fields.Integer(default=10)
    stage_from_id = fields.Many2one(
        'request.stage', string='From Stage', required=True, ondelete='cascade')
    stage_to_id = fields.Many2one(
        'request.stage', string='To Stage', required=True, ondelete='cascade')
