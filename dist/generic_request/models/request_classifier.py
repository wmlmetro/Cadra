from odoo import models, fields, api
from odoo.addons.generic_mixin import post_create, post_write


class RequestClassifier(models.Model):
    _name = 'request.classifier'
    _inherit = [
        'generic.mixin.track.changes',
    ]
    _description = 'Request Classifier'
    _order = 'service_id ASC, category_id ASC, type_id ASC'

    service_id = fields.Many2one(
        'generic.service', string='Service', index=True, ondelete='restrict',
        help="Service of request")
    service_id_group = fields.Many2one(
        comodel_name='generic.service.group',
        related='service_id.service_group_id',
        string='Service group', store=True, readonly=True)
    category_id = fields.Many2one(
        'request.category', 'Category', index=True, ondelete="restrict",
        help="Category of request")
    type_id = fields.Many2one(
        'request.type', 'Type', index=True, ondelete='restrict', required=True,
        help="Type of request")

    active = fields.Boolean(index=True, default=True)

    _sql_constraints = [
        ('classifier_service_category_type_unique',
         'UNIQUE(service_id, category_id, type_id)',
         "Binding: service_id, category_id and type_id must be unique!"),
    ]

    @api.model
    def get_classifiers(self, service=None, category=None,
                        request_type=None, limit=None):
        """ Return classifier recordset with mentioned service, category, type.
        """
        def get_id(value):
            if isinstance(value, str):
                return self.env.ref(value).id
            if isinstance(value, models.BaseModel):
                return value.id
            if isinstance(value, int):
                return value
            if value is None or value is False:
                return value
            raise AssertionError("Unknown format: %s" % value)

        service_id = get_id(service)
        category_id = get_id(category)
        type_id = get_id(request_type)

        domain = []
        if service_id is not None:
            domain.append(('service_id', '=', service_id))
        if category_id is not None:
            domain.append(('category_id', '=', category_id))
        if type_id is not None:
            domain.append(('type_id', '=', type_id))

        classifier = self.env['request.classifier'].search(domain, limit=limit)
        return classifier

    def name_get(self):
        res = []
        for record in self:
            if self.env.user.has_group(
                    'generic_request.group_request_use_services'):
                name = "%s - %s - %s" % (
                    record.service_id.name,
                    record.category_id.name,
                    record.type_id.name)
            else:
                name = "%s - %s" % (
                    record.category_id.name,
                    record.type_id.name)

            res += [(record.id, name)]
        return res

    @post_create()
    @post_write('service_id', 'category_id', 'type_id', 'active')
    def _update_cache_for_m2m_relations_on_srv_categ_type(self, changes):
        self.env['request.type'].invalidate_cache(
            fnames=['category_ids', 'service_ids'], ids=[self.type_id.id])
        if self.category_id:
            self.env['request.category'].invalidate_cache(
                fnames=['request_type_ids', 'service_ids'],
                ids=[self.category_id.id])
        if self.service_id:
            self.env['generic.service'].invalidate_cache(
                fnames=['request_type_ids', 'category_ids'],
                ids=[self.service_id.id])

    def unlink(self):
        services = self.mapped('service_id')
        categories = self.mapped('category_id')
        types = self.mapped('type_id')
        res = super().unlink()

        self.env['request.type'].invalidate_cache(
            fnames=['category_ids', 'service_ids'], ids=types.ids)

        if categories:
            self.env['request.category'].invalidate_cache(
                fnames=['request_type_ids', 'service_ids'],
                ids=categories.ids)
        if services:
            self.env['generic.service'].invalidate_cache(
                fnames=['request_type_ids', 'category_ids'],
                ids=services.ids)
        return res
