from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('1.27.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(
        cr,
        src_module='crnd_wsd_service_resource',
        dst_module='crnd_wsd_resource',
        models=[
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
            'request.category',
        ],
        cleanup=True,
    )

    # Cleanup module data
    cleanup_module_data(cr, 'crnd_wsd_service_resource')
