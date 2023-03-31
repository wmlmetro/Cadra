from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('0.15.0')
def migrate(cr, installed_version):
    cr.execute("""
            UPDATE generic_contract SET company_id=1;
        """)
