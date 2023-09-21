from odoo import fields, models


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    resource_use_generic_locations = fields.Boolean(
        related='res_type_id.use_generic_locations', readonly=True)

    placed_on_location_id = fields.Many2one(
        'generic.location', string='Located in', index=True,
        ondelete='restrict')

    # Location's geolocation
    longitude = fields.Float(
        related='placed_on_location_id.longitude', readonly=True,
        digits=(16, 5))
    latitude = fields.Float(
        related='placed_on_location_id.latitude', readonly=True,
        digits=(16, 5))

    # Location's address fields
    country_id = fields.Many2one(
        related='placed_on_location_id.country_id', store=True, index=True)
    state_id = fields.Many2one(
        related='placed_on_location_id.state_id', store=True, index=True)
    city = fields.Char(
        related='placed_on_location_id.city', store=True, index=True)
    zip = fields.Char(
        related='placed_on_location_id.zip', store=True, index=True)
    street = fields.Char(
        related='placed_on_location_id.street', store=True, index=True)
    street2 = fields.Char(
        related='placed_on_location_id.street2', store=True, index=True)
