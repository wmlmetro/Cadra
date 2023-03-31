{
    'name': "Generic Request (Action Subrequest)",

    'summary': """
        Automatically create sub-requests using automated
        actions
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.5.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/request_creation_template.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
