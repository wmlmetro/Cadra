from odoo import models, fields


class GenericAssignPolicy(models.Model):
    _inherit = 'generic.assign.policy'

    assign_team_field_id = fields.Many2one(
        'ir.model.fields', related='assign_model_id.assign_team_field_id',
        store=True, readonly=True, ondelete='cascade')

    def get_assignment_fields_info(self):
        res = super(GenericAssignPolicy, self).get_assignment_fields_info()
        res['team_id'] = {
            'model': 'generic.team',
            'field_name': self.sudo().assign_team_field_id.name,
            'savable': bool(self.sudo().assign_team_field_id),
        }
        return res

    def convert_assign_data(self, assign_data, debug_log=None):
        """ Overrided for rignt assignment user_id and team_id to request."""

        # TODO: Need refactoring
        res = super(
            GenericAssignPolicy, self).convert_assign_data(assign_data)

        if not self.sudo().assign_team_field_id:
            # If team assignment is not supported, thus no adjustments needed.
            return res

        team = self.env['generic.team'].browse(res.get('team_id', False))
        user = self.env['res.users'].browse(res.get('user_id', False))
        if team and not user:
            res.update({
                'user_id': False
            })
        if user and not (team and team._check_user_in_team(user)):
            res.update({
                'team_id': False
            })

        return res
