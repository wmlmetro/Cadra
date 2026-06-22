from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Expose the per-client brand short code to the web client so every
        dashboard can label itself without hardcoding the client name.

        The value is owned by the per-client brand module
        (cadra_brand_<client>) via the ``cadra.brand_short_name`` config
        parameter. Falls back to 'NRS' so an un-branded database still renders
        a sensible label.
        """
        result = super().session_info()
        result['brand_short_name'] = self.env['ir.config_parameter'].sudo().get_param(
            'cadra.brand_short_name', 'NRS')
        return result
