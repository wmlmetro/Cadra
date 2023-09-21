from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('1.5.0')
def migrate(cr, installed_version):
    # Migrate demo data
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_action_subrequest_assignment',
        dst_module='generic_request_action_assignment',
        models=[
            'request.event.action',
            'ir.model',
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
        ]
    )
    # Cleanup module data
    cleanup_module_data(cr, 'generic_request_action_subrequest_assignment')
