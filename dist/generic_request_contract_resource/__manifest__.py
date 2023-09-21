{
    'name': "Generic Request Contract Resource",

    'summary': """
        Link request with resource contract
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.6.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_contract',
        'generic_request_resource',
        'generic_contract_resource',
    ],

    # always loaded
    'data': [],
    'demo': [],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
