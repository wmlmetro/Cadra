{
    'name': "Generic Request (Action Subrequest Assignment) [Obsolete]",

    'summary': """
        This module reached the end of life and can be safely removed.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.8.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action_subrequest',
        'generic_request_action_assignment',
    ],

    # always loaded
    'data': [],
    'demo': [],

    'images': ['static/description/banner.png'],
    'tags': ['obsolete'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 40.0,
    'currency': 'EUR',
}
