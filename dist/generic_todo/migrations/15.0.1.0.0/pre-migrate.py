from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.0.0')
def migrate(cr, installed_version):
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'generic_todo'
        WHERE module = 'generic_system_event_todo'
          AND model IN (
              'generic.system.event.category',
              'generic.system.event.type',
              'generic.system.event.source'
          );

        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE module = 'generic_system_event_todo'
              AND model = 'ir.ui.view'
        );

        DELETE FROM ir_model_data
        WHERE module = 'generic_system_event_todo'
          AND model = 'ir.ui.view';

        DELETE FROM ir_model_access
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE module = 'generic_system_event_todo'
              AND model = 'ir.model.access'
        );
    """)
