from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    cleanup_module_data,
)


@ensure_version('0.9.0')
def migrate(cr, installed_version):
    cleanup_module_data(cr, 'generic_contract_resource_role')
