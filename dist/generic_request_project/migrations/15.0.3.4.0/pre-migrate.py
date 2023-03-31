from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('3.4.0')
def migrate(cr, installed_version):
    # Migrate demo data
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_project_timesheet',
        dst_module='generic_request_project',
        models=[
            'project.project',
            'request.request',
            'project.task',
            'account.analytic.line',
            'request.timesheet.line',
            'request.type',
            'ir.model',
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
            'ir.ui.view',
            'mail.alias',
        ],
        cleanup=True,
    )
    # Cleanup module data
    cleanup_module_data(cr, 'generic_request_project_timesheet')
