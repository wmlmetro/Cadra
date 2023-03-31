from odoo import models, fields, api, _

CREATE_VIEW_REQUESTS_SERVER_ACT = """
action = env.ref(
    'generic_request.action_request_window'
).read()[0]
action['context'] = {
    'default_related_doc_ids': [
        (0, 0, {
            'doc_type_id': %(doc_type_id)s,
            'doc_id': record.id,
        }),
    ],
}
search_doc = "%(doc_type_id)s,%%(doc_id)s" %% {
    'doc_id': record.id,
}
action['domain'] = [
   ('related_doc_search', '=', search_doc),
]
"""


class RequestRelatedDocumentType(models.Model):
    _name = 'request.related.document.type'
    _description = 'Request Related Document Type'

    name = fields.Char(translate=True)
    model_id = fields.Many2one(
        'ir.model', delegate=True, required=True, index=True,
        domain=[('transient', '=', False)], ondelete='cascade',
        string="Document Model")
    active = fields.Boolean(default=True, index=True)
    request_action_id = fields.Many2one(
        'ir.actions.server')
    request_action_name = fields.Char(
        related='request_action_id.name', readonly=False)
    request_action_toggle = fields.Boolean(
        compute='_compute_request_action_toggle',
        inverse='_inverse_request_action_toggle',
        string="Has Context Action",
        help="Show/Hide context action to create requests related to document."
             " To see new context action, please reload the page."
    )

    _sql_constraints = [
        ('model_id_uniq',
         'UNIQUE (model_id)',
         'Model must be unique.'),
    ]

    @api.depends('request_action_id')
    def _compute_request_action_toggle(self):
        for record in self:
            record.request_action_toggle = bool(record.request_action_id)

    def _inverse_request_action_toggle(self):
        for record in self:
            if record.request_action_toggle:
                record.request_action_id = record._create_request_action()
            else:
                record.request_action_id.unlink()

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for record in self:
            record.name = record.model_id.name

    @api.model
    @api.returns('self', lambda value: value.id)
    def create(self, vals):
        # Try to find already created document type.
        # This is required to bypass errors during migration
        model_id = vals.get(
            'model_id',
            self.env.context.get(
                'default_model_id',
                False))
        if model_id:
            doc_type = self.search([('model_id', '=', model_id)], limit=1)
            if doc_type:
                return doc_type
        return super(RequestRelatedDocumentType, self).create(vals)

    def _create_request_action(self):
        return self.env['ir.actions.server'].create({
            'name': _("View / create requests"),
            'type': 'ir.actions.server',
            'binding_type': 'action',
            'binding_model_id': self.model_id.id,
            'model_id': self.model_id.id,
            'state': 'code',
            'code': CREATE_VIEW_REQUESTS_SERVER_ACT % {
                'doc_type_id': self.id,
            },
        }).id
