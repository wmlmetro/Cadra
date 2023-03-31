from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('0.10.0')
def migrate(cr, installed_version):
    cr.execute("""
        UPDATE generic_contract_resource_line
        SET date_added = generic_contract.date_start
        FROM generic_contract
        WHERE generic_contract.id = generic_contract_resource_line.contract_id;
    """)
