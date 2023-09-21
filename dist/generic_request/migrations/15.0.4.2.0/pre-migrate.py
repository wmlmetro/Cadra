from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('4.2.0')
def migrate(cr, installed_version):
    cr.execute("""
        ALTER TABLE request_request
        ADD COLUMN deadline_date_dt TIMESTAMP;
        UPDATE request_request
        SET deadline_date_dt = deadline_date + '23:59:59.999999'::time
        WHERE deadline_date IS NOT NULL;
    """)
