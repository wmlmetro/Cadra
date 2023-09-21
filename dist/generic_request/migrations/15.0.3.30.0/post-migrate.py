from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
)


@ensure_version('3.30.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    kinds_count = env['request.kind'].search_count([])
    if not kinds_count:
        # No migration needed
        return

    # If there is at least one active request.kind record in the system
    # then, enable usage of services for requests by default
    (
        env.ref('base.group_user') +
        env.ref('base.group_portal') +
        env.ref('base.group_public')
    ).write({
        'implied_ids': [
            (4, env.ref('generic_request.group_request_use_kind').id),
        ]
    })
