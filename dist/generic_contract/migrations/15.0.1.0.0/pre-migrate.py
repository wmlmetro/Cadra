from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.0.0')
def migrate(cr, installed_version):
    cr.execute("""

        -- Delete views
        DELETE FROM ir_ui_view WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE model = 'ir.ui.view'
              AND module = 'generic_contract'
              AND name = 'res_config_settings_view_form'
        );

        -- Delete constraints
        DELETE FROM ir_model_constraint
        WHERE module = (
            SELECT id
            FROM ir_module_module
            WHERE name='generic_contract')
        AND name IN (
            'generic_contract_parent_contract_id_name_unique',
            'generic_contract_parent_contract_id_number_unique',
            'generic_contract_template_parent_contract_id_name_unique');

    """)
