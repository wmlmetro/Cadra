{
    'name': "Generic Assignment",

    'summary': """
        Allows you to create custom user assignment policies
        and rules for which these assignments will take place.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Assignment',
    'version': '15.0.1.24.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_condition',
        'generic_mixin',
        'mail',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'data/ir.module.category.xml',

        'views/generic_assign_policy_model_view.xml',
        'views/generic_assign_policy_rule_view.xml',
        'views/generic_assign_policy_view.xml',
        'views/ir_actions.xml',
        'views/generic_assign_view.xml',
        'wizard/test_assign_policy_view.xml',
        'wizard/generic_wizard_assignment.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 200.0,
    'currency': 'EUR',
}
