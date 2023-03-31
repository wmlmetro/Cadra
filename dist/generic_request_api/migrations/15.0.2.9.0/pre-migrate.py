from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.9.0')
def migrate(cr, installed_version):
    cr.execute("""
        ALTER TABLE IF EXISTS generic_request_apikeys_show
            RENAME TO request_api_wizard_add_access_key_show;
        ALTER SEQUENCE IF EXISTS generic_request_apikeys_id_seq
            RENAME TO request_api_wizard_add_access_key_show_id_seq;
    """)
