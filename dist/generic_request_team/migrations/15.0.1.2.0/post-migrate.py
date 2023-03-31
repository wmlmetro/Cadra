from odoo import api, SUPERUSER_ID
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('1.2.0')
def migrate(cr, installed_version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    rtypes = env['request.type'].search([])
    for rtype in rtypes:
        rtype.send_default_assigned_team_notification = \
            rtype.send_default_assigned_notification
        rtype.assigned_team_notification_show_request_text = \
            rtype.assigned_notification_show_request_text
        rtype.assigned_team_notification_show_response_text = \
            rtype.assigned_notification_show_response_text
