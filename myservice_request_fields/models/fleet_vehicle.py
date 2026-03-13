from odoo import models, api


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """
        Extended search: match on name, license_plate, vin_sn (chassis), or tag name.
        This makes the Many2one dropdown searchable by any of those fields.
        """
        args = args or []
        if name:
            domain = [
                '|', '|', '|',
                ('name', operator, name),
                ('license_plate', operator, name),
                ('vin_sn', operator, name),
                ('tag_ids.name', operator, name),
            ]
            return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
        return super()._name_search(
            name=name, args=args, operator=operator,
            limit=limit, name_get_uid=name_get_uid,
        )

    def name_get(self):
        """
        Show: [LICENSE PLATE] Model Name  (or chassis if no plate)
        e.g.  [ABC-123EF] Toyota Corolla
        """
        result = []
        for rec in self:
            identifier = rec.license_plate or rec.vin_sn or '—'
            result.append((rec.id, f'[{identifier}] {rec.name}'))
        return result
