from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.0.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group_to_remove = env.ref(
        'generic_contract.group_use_subcontracts',
        raise_if_not_found=False,
    )
    if group_to_remove:
        group_to_remove.unlink()
