{
    'name': "Generic Request Service Condition",

    'summary': """
        Use Service Condition in Requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Service',
    'version': '15.0.0.6.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_condition',
    ],

    # always loaded
    'data': [
        'views/request_type.xml',
    ],
    'demo': [
        'demo/request_type_conditional.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
