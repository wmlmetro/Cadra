{
    'name': "Generic Request (Action Tag)",

    'summary': """
        Add / Remove Tags Using Automated Actions
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/request_event_action.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
