{
    'name': "Generic Assignment Team",

    'summary': """
        Provides integration between the Generic
        Assignment Policy and Generic Team modules.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Assignment',
    'version': '15.0.1.13.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_team',
        'generic_assignment'
    ],

    # always loaded
    'data': [
        'views/generic_assign_policy_rule_view.xml',
        'views/generic_assign_policy_model.xml',
        'views/generic_assign_policy.xml',
        'wizard/generic_wizard_assignment.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
