from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.176.0')
def migrate(cr, installed_version):
    cr.execute("""
        -- Delete old access rules
        DELETE FROM ir_rule WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE model = 'ir.rule'
              AND module = 'generic_request_parent'
        );

        -- DELETE references to ir_model
        DELETE FROM ir_model_data
        WHERE model = 'ir.model'
          AND module = 'generic_request_parent';
    """)
