from odoo import api, SUPERUSER_ID


def _post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})

    for resource_type in env['generic.resource.type'].search([]):
        cr.execute("""
            INSERT INTO ir_act_window
                   (name, res_model, binding_type,
                    view_mode, target, context,
                    domain, type, binding_model_id)
            SELECT name, res_model, binding_type,
                   view_mode, target, context,
                   domain, type, %(binding_model_id)s
            FROM ir_act_window
            WHERE id = %(base_action_id)s
            RETURNING id;
        """, {
            'binding_model_id': resource_type.model_id.id,
            'base_action_id': env.ref(
                'generic_resource_role.'
                'action_resource_open_wizard_manage_roles').id,
        })
        action_id = cr.fetchone()[0]
        resource_type.resource_act_manage_roles_id = action_id
