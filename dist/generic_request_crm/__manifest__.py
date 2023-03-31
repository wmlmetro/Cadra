{
    'name': "Generic Request CRM",

    'summary': """
        Add ability to create requests from CRM.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.5.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'crm',
    ],

    # always loaded
    'data': [
        'views/request_request_view.xml',
        'views/crm_lead_views.xml',
    ],

    'demo': [],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 10.0,
    'currency': 'EUR',
}
