from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('0.4.0')
def migrate(cr, installed_version):
    cr.execute("""
        UPDATE ir_model_data
        SET name = 'generic_system_event_type_mail_comment'
        WHERE module = 'generic_system_event_mail_events'
          AND name = 'generic_system_event_mail_comment';
    """)
