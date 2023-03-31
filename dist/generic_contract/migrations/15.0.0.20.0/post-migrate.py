from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('0.20.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group_use_subcontracts = env.ref('generic_contract.group_use_subcontracts')
    group_user = env.ref('base.group_user')

    has_subcontracts = env['generic.contract'].search_count([
        ('contract_type', '=', 'subcontract'),
    ]) > 0
    if (has_subcontracts and
            group_use_subcontracts not in group_user.implied_ids):
        group_user.implied_ids += group_use_subcontracts
