from odoo import tools
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.7.0')
def migrate(cr, installed_version):
    tools.sql.rename_column(
        cr, 'generic_contract', 'date_start', 'date_begin')
