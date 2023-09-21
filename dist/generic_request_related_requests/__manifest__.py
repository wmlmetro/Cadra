{
    'name': "Generic Request Related Requests",

    'summary': """
        Allows you to establish links between requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.9.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request'
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/request_request_view.xml',
        'wizard/related_requests_change_views.xml'
    ],
    'demo': [
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 20.0,
    'currency': 'EUR',
}
