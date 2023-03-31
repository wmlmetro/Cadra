{
    'name': "Generic Request Action Project",

    'summary': """
        Project tasks can be created using automated actions
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',

    'version': '15.0.1.9.0',

    # any module necessary for this one to work correctly
    'depends': [
        'project',
        'generic_request_project',
        'generic_request_action',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/demo_request_event_action.xml'
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
