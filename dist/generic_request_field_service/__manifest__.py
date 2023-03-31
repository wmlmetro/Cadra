{
    'name': "Generic Request Field Service",

    'summary': """
        Different custom fields in requests are displayed
        for different services
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.12.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_field',
    ],

    # always loaded
    'data': [
        'views/request_field_view.xml',
    ],
    'demo': [
        'demo/request_types.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
