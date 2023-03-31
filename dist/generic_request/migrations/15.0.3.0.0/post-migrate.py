from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
)


@ensure_version('3.0.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    srv_module = env.ref('base.module_generic_request_service')
    if srv_module.exists() and srv_module.state in ('installed',
                                                    'to install',
                                                    'to upgrade'):
        # If there was installed module 'generic_request_service' in system
        # then, enable usage of services for requests by default
        (
            env.ref('base.group_user') +
            env.ref('base.group_portal') +
            env.ref('base.group_public')
        ).write({
            'implied_ids': [
                (4, env.ref('generic_request.group_request_use_services').id),
            ]
        })
