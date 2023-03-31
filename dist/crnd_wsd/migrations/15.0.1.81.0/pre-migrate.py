from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.81.0')
def migrate(cr, installed_version):
    cr.execute("""
        UPDATE request_stage_route
        SET button_style = website_button_style;
    """)
