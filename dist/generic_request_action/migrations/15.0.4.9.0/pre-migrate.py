from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('4.9.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_action_priority',
        dst_module='generic_request_action',
        models=[
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
            'request.event.action',
        ],
        cleanup=True,
    )
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_action_tag',
        dst_module='generic_request_action',
        models=[
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
            'request.event.action',
        ],
        cleanup=True,
    )

    # Cleanup module data
    cleanup_module_data(cr, 'generic_request_action_priority')
    cleanup_module_data(cr, 'generic_request_action_tag')
