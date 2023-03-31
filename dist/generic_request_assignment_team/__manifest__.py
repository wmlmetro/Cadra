{
    'name': "Generic Request Assignment (Team)",

    'summary': """
        Integration module for generic teams and request assignment policies
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Request',
    'version': '15.0.0.1.0',


    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_assignment',
        'generic_assignment_team',
        'generic_request_team',
    ],

    # always loaded
    'data': [
        'data/request_assign_policy_model.xml',
    ],
    'demo': [
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
