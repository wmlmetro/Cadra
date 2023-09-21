from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


def remove_old_views(cr):
    cr.execute("""
        -- Delete views
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE model = 'ir.ui.view' AND
                module = 'crnd_wsd' AND
                name IN (
                    'generic_service_view_form',
                    'view_request_category_form')
                );
    """)


@ensure_version('1.113.0')
def migrate(cr, installed_version):
    remove_old_views(cr)
