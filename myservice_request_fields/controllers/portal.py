from odoo import http
from odoo.http import request
from odoo.addons.generic_request.controllers.website_request import WebsiteRequestController


class MyServiceRequestController(WebsiteRequestController):
    """
    Extend the Bureaucrat portal controller to inject:
    - locations: all generic.location records (for dropdown)
    - fleet_vehicles: all fleet.vehicle records (for dropdown)
    into the request wizard template context.
    """

    def _get_request_wizard_context(self, req, **kw):
        ctx = super()._get_request_wizard_context(req, **kw)

        # All locations — ordered by complete_name for grouped display
        ctx['locations'] = request.env['generic.location'].sudo().search(
            [], order='complete_name asc'
        )

        # All fleet vehicles — ordered by license plate
        ctx['fleet_vehicles'] = request.env['fleet.vehicle'].sudo().search(
            [], order='license_plate asc'
        )

        return ctx
