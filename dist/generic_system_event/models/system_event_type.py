from odoo import models, fields, api, tools


class GenericSystemEventType(models.Model):
    _name = 'generic.system.event.type'
    _inherit = [
        'generic.mixin.name_with_code',
        'generic.mixin.namesearch.by.fields',
    ]
    _order = 'name ASC'
    _description = 'Generic System Event'

    _generic_namesearch_fields = [
        'name',
        'code',
    ]

    event_category_id = fields.Many2one(
        'generic.system.event.category',
        required=True, index=True, readonly=True,
        ondelete='restrict')
    event_source_id = fields.Many2one(
        'generic.system.event.source',
        required=False, index=True, readonly=True, ondelete='cascade')
    event_source_model_id = fields.Many2one(
        related='event_source_id.model_id',
        string="Event Source Model",
        index=True, readonly=True, store=True, ondelete='cascade')
    event_source_model_name = fields.Char(
        related='event_source_id.model_id.model',
        string="Event Source Model (Name)",
        index=True, readonly=True, store=True)
    event_data_model_id = fields.Many2one(
        related='event_source_id.event_data_model_id',
        string="Event Data Model",
        readonly=True, store=True, ondelete='cascade')
    event_data_model_name = fields.Char(
        related='event_source_id.event_data_model_id.model',
        string="Event Data Model (Name)",
        readonly=True, store=True)

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (event_source_id, name)',
         'Name must be unique per event source.'),
        ('code_uniq',
         'UNIQUE (event_source_id, code)',
         'Code must be unique per event source.'),
    ]

    def name_get(self):
        return [(rec.id, '%s / %s' % (
            rec.event_category_id.name, rec.name)) for rec in self]

    @api.model
    @tools.ormcache('code', 'source_id')
    def _get_event_type_id(self, code, source_id):
        return self.sudo().search([
            ('code', '=', code),
            '|', ('event_source_id', '=', source_id),
            ('event_source_id', '=', False),
        ], limit=1).id

    def get_event_type(self, code, source):
        """ Return recordset with event type for specified code
        """
        event_type_id = self._get_event_type_id(code, source.id)
        return self.browse(event_type_id) if event_type_id else self.browse()
