from odoo.tools.sql import column_exists, create_column, table_exists
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.10.0')
def migrate(cr, installed_version):
    if column_exists(cr, "request_request", "company_id"):
        # Field 'company_id' already exists (possibly added by other module)
        # thus nothing to migrate
        return

    create_column(cr, "request_request", "company_id", "int4")

    if (table_exists(cr, "website") and
            column_exists(cr, "website", "company_id") and
            column_exists(cr, "request_request", "website_id")):
        cr.execute("""
            UPDATE request_request AS rr
            SET company_id = w.company_id
            FROM website AS w
            WHERE rr.website_id = w.id
              AND rr.website_id IS NOT NULL
              AND rr.company_id IS NULL;
        """)

    cr.execute("""
        UPDATE request_request AS rr
        SET company_id = u.company_id
        FROM res_users AS u
        WHERE rr.created_by_id = u.id
          AND rr.company_id IS NULL;
    """)
