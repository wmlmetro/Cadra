from odoo import models, fields, api

from odoo.addons.generic_mixin import post_write, post_create


# This have to be abstract model, but because of this
# [PR](https://github.com/odoo/odoo/pull/69372),
# Odoo does not allow to use abstract models for views
# (fields inherited via delegation will not be visible),
# we use this technical model. This model MUST NOT contain any records
# and MUST NOT be viewable via UI.
class GenericEquipment(models.Model):
    _name = 'generic.equipment'
    _inherit = [
        'mail.thread',
        'image.mixin',
        'generic.resource.mixin',
        'generic.tag.mixin',
    ]
    _description = 'Generic Equipment (Base)'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    vendor_id = fields.Many2one(
        comodel_name='generic.equipment.vendor', index=True)
    brand_id = fields.Many2one(
        comodel_name='generic.equipment.brand', index=True)
    series_id = fields.Many2one(
        comodel_name='generic.equipment.series', index=True)
    model_id = fields.Many2one(
        comodel_name='generic.equipment.model', index=True)
    serial_number = fields.Char(index=True)
    inventory_number = fields.Char(index=True)

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in-use', 'In Use'),
            ('in-storage', 'In Storage'),
            ('in-maintenance', 'In Maintenance'),
            ('broken', 'Broken'),
            ('retired', 'Retired'),
        ], required=True, index=True, default='draft', string="Status")

    currency_id = fields.Many2one(
        'res.currency', default=lambda s: s.env.user.company_id.currency_id.id)
    cost = fields.Monetary(currency_field='currency_id')

    # Dates
    date_purchase = fields.Date()
    date_in_use = fields.Date()
    date_retired = fields.Date()
    date_warranty_expire = fields.Date(string="Warranty expiration date")

    category_id = fields.Many2one(
        comodel_name='generic.equipment.category', index=True)

    # Technical field used to provide actual model name for tags
    self_model_name = fields.Char(
        compute='_compute_self_model_name', readonly=True)

    @api.depends()
    def _compute_self_model_name(self):
        for record in self:
            record.self_model_name = self._name

    @post_create('state')
    @post_write('state')
    def _after_state_changed(self, changes):
        if changes['state'].new_val == 'in-use' and not self.date_in_use:
            self.date_in_use = fields.Date.today()
        if changes['state'].new_val == 'retired' and not self.date_retired:
            self.date_retired = fields.Date.today()
