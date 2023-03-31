{
    'name': 'Service Desk Team',
    'category': 'Service Desk',
    'summary': """
        Provides integration between the Website Service Desk
        and Generic Team addons.
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.0.2.0',
    'depends': [
        'generic_team',
    ],
    'data': [
        'views/generic_team_menu.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}
