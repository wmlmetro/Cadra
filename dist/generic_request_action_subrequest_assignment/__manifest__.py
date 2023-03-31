{
    'name': "Generic Request (Action Subrequest Assignment)",

    'summary': """
        Use assign policies for automatic assignments in subrequests
        created via automated actions
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.5.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action_subrequest',
        'generic_request_action_assignment',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 40.0,
    'currency': 'EUR',
}
