from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.8.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    records = env['request.type'].search(
        [('request_ids.project_task_ids', '!=', False)])
    records.write({'use_subtasks': True})
