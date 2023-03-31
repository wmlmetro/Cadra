{
    'name': "Generic Resource Role",

    'summary': """
        Provides the ability to easily manage access to resources via roles.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.2.33.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource',
        'generic_mixin',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/generic_resource_role.xml',
        'wizard/manage_resource_roles.xml',
        'views/generic_resource.xml',
        'views/generic_resource_permission.xml',
        'views/generic_resource_type.xml',
        'views/generic_resource_role.xml',
        'views/generic_resource_sub_role.xml',
        'views/generic_resource_role_type.xml',
        'views/generic_resource_role_link.xml',
        'views/res_partner.xml',
        'views/res_users.xml',
    ],
    'demo': [
        'demo/generic_resource_role.xml',
        'demo/generic_resource_role_link.xml',
        'demo/generic_resource_type.xml',
    ],
    'images': ['static/description/banner.png'],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 350.0,
    'currency': 'EUR',
}
