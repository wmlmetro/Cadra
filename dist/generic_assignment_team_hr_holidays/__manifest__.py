{
    'name': "Generic Assignment Team HR Holiday",

    'summary': """
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Assignment',
    'version': '15.0.0.2.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_assignment_team',
        'generic_team_hr',
        'hr_holidays',
    ],

    # always loaded
    'data': [
        'views/generic_assign_policy_rule_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 40.0,
    'currency': 'EUR',
}
