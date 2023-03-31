from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.3.0')
def migrate(cr, installed_version):
    cr.execute("""
            UPDATE generic_contract
            SET date = date_start
            WHERE date IS NULL
        """)
