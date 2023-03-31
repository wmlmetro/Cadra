{
    'name': "Generic Service (Resource)",

    'summary': """
        Provides integration between the Generic Service
        and Generic Resource modules.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.1.13.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource',
        'generic_service',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/generic_resource_views.xml',
        'views/generic_resource_type_views.xml',
        'views/generic_service_views.xml',
        'wizard/generic_resource_wizard_link_service.xml',
    ],
    'demo': [
        'demo/generic_service_demo.xml'
    ],
    'images': ['static/description/banner.png'],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'auto_install': True,
    'price': 50.0,
    'currency': 'EUR',
}
