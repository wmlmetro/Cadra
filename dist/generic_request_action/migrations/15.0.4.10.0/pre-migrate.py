from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('4.10.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_action_subrequest',
        dst_module='generic_request_action',
        models=[
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
            'request.event.action',
            'request.creation.template',
        ],
        cleanup=True,
    )

    # Migrate default template
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'generic_request_action'
        WHERE module = 'generic_request_action_subrequest'
          AND model = 'ir.ui.view'
          AND name = 'request_text_template_test';
    """)

    # Cleanup module data
    cleanup_module_data(cr, 'generic_request_action_subrequest')
