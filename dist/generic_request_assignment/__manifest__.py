{
    'name': "Generic Request Assignment",

    'summary': """
        Allows to use custom assignment policies
        in requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Request',
    'version': '15.0.1.11.1',


    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_condition',
        'generic_assignment',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'data/request_assign_policy_model.xml',
        'views/requests.xml',
    ],
    'demo': [
        'demo/assign_policies_rules.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'OPL-1',
    'price': 20.0,
    'currency': 'EUR',
}
