from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    migrate_xmlids_to_module,
    cleanup_module_data,
)


@ensure_version('2.0.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(
        cr,
        src_module='generic_request_contract_resource_service',
        dst_module='generic_request_contract_resource',
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
        src_module='generic_request_contract_resource_service',
        dst_module='generic_request_contract_resource',
        models=[
            'generic.contract.service.line',
            'generic.contract.template.service.line',
        ],
        cleanup=False,
    )

    # Cleanup module data
    cleanup_module_data(cr, 'generic_request_contract_resource_service')
