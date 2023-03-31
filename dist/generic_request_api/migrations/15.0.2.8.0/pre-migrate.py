from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.8.0')
def migrate(cr, installed_version):
    cr.execute("""
        ALTER TABLE IF EXISTS wizard_add_access_key
            RENAME TO request_api_wizard_add_access_key;
        ALTER SEQUENCE IF EXISTS wizard_add_access_key_id_seq
            RENAME TO request_api_wizard_add_access_key_id_seq;
    """)
