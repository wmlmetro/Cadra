{
    'name': "Generic Contract Resource",

    'summary': """
        Adds resource lines to specify resources in contracts
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Contract',
    'version': '15.0.2.3.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_contract',
        'generic_resource',
        'generic_m2o',
    ],

    # always loaded
    'data': [
        'data/generic_system_event_type.xml',
        'security/ir.model.access.csv',
        'views/generic_contract_views.xml',
        'views/generic_contract_resource_line_views.xml',
        'views/generic_contract_resource_service_line_views.xml',
        'views/generic_contract_template_views.xml',
        'views/generic_contract_template_resource_line_views.xml',
        'views/generic_contract_event.xml',
        'views/generic_resource.xml',

        'wizard/contract_resource_wizard_add_lines.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [
        'demo/demo_resource.xml',
        'demo/generic_contract_resource_line_demo.xml',
        'demo/generic_contract_resource_service_line_demo.xml',
        'demo/generic_contract_template_resource_line_demo.xml',
    ],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
