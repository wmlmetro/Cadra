import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def uninstall_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    menu = env.ref('generic_team.menu_generic_team_root')
    menu.write({
        'web_icon': 'generic_team,static/description/icon.png',
    })
