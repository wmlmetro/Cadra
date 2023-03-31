from odoo.tools.sql import column_exists
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.145.0')
def migrate(cr, installed_version):

    if not column_exists(cr,
                         'res_company',
                         'request_mail_create_partner_from_email'):
        # Nothing to migrate if column does not exists
        return

    cr.execute("""
        UPDATE res_company
        SET request_mail_create_author_contact_from_email = TRUE,
            request_mail_create_cc_contact_from_email = TRUE,
            request_mail_auto_subscribe_cc_contacts = TRUE
        WHERE request_mail_create_partner_from_email = TRUE;
        """)
