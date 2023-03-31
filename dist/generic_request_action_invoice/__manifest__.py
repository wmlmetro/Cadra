{
    'name': "Generic Request Action Invoice",

    'summary': """
         Automatically create invoices for requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Request',
    'version': '15.0.0.2.2',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action',
        'generic_request_invoicing',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
