{
    'name': "Generic Request (Conditions)",

    'summary': """
        Allows to use conditions
        while working with requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.14.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'generic_condition',
    ],

    # always loaded
    'data': [
        'data/generic_condition.xml',
        'views/request_stage_route_view.xml',
        'views/request_type.xml',
    ],
    'demo': [
        'demo/request_category.xml',
        'demo/generic_condition.xml',
        'demo/request_type_conditional.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'OPL-1',
    'price': 10.0,
    'currency': 'EUR',
}
