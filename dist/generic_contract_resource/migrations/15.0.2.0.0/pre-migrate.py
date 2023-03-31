from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
    fix_view_inheritance,
)


@ensure_version('2.0.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(
        cr,
        src_module='generic_contract_resource_service',
        dst_module='generic_contract_resource',
        models=[
            'ir.model',
            'ir.model.fields',
            'ir.model.constraint',
            'ir.model.relation',
            'ir.ui.menu',
            'ir.model.access',
            'ir.actions.act_window',
        ],
        cleanup=True,
    )

    # Migrate demo data
    migrate_xmlids_to_module(
        cr,
        src_module='generic_contract_resource_service',
        dst_module='generic_contract_resource',
        models=[
            'generic.contract.resource.service.line',
        ],
        cleanup=False,
    )

    fix_view_inheritance(
        cr,
        'generic_contract_resource_service'
        '.view_generic_contract_resource_line_form',
        'generic_contract_resource'
        '.view_generic_contract_resource_line_form'
    )

    # Cleanup module data
    cleanup_module_data(cr, 'generic_contract_resource_service')
