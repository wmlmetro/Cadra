{
    'name': "Generic Request (Mail Conditions)",

    'summary': """
        This module provides predefined conditions that could be used
        in automation to easily handle request's mail events.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Service',
    'version': '15.0.0.3.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_condition',
        'generic_request_mail',
    ],

    # always loaded
    'data': [
        'data/generic_condition.xml',
    ],
    'demo': [],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
