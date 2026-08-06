from odoo import models, fields


class RequestCategory(models.Model):
    _name = 'request.category'
    _description = 'Request Category'
    _order = 'sequence, name'
    _parent_store = True
    _parent_name = 'parent_id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one(
        'request.category', string='Parent Category', ondelete='cascade')
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many('request.category', 'parent_id', string='Sub-categories')


class RequestKind(models.Model):
    """Broad kind of request (e.g. Service / Incident / Change). Part of the
    generic_request field surface the seed + classifiers expect."""
    _name = 'request.kind'
    _description = 'Request Kind'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class RequestClassifier(models.Model):
    """Maps (service, category) -> default type. Part of the generic_request
    surface the seed builds; a lightweight rule record for classification."""
    _name = 'request.classifier'
    _description = 'Request Classifier'

    service_id = fields.Many2one('generic.service', string='Service')
    category_id = fields.Many2one('request.category', string='Category')
    type_id = fields.Many2one('request.type', string='Type')
    active = fields.Boolean(default=True)


class RequestType(models.Model):
    _name = 'request.type'
    _description = 'Request Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind_id = fields.Many2one('request.kind', string='Kind')
    category_id = fields.Many2one('request.category', string='Default Category')

    # Stage flow.
    start_stage_id = fields.Many2one(
        'request.stage', string='Start Stage',
        help='Stage a new request of this type opens in.')
    stage_ids = fields.Many2many(
        'request.stage', string='Allowed Stages',
        help='Stages a request of this type may move through. Empty = all stages.')
