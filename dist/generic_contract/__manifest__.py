{
    'name': "Generic Service Contract",

    'summary': """
        Contracts management
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Contract',
    'version': '15.0.2.10.0',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'mail',
        'base_field_m2m_view',
        'generic_mixin',
        'generic_tag',
        'generic_system_event',
        'generic_service',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/ir_cron_data.xml',
        'data/generic_tag_model.xml',
        'data/generic_tag_category.xml',
        'views/generic_contract.xml',
        'views/generic_contract_view.xml',
        'views/generic_contract_template_view.xml',
        'views/generic_contract_service_line_views.xml',
        'views/generic_contract_template_service_line_views.xml',
        'wizards/generic_contract_wizard_create_view.xml',
        'views/res_partner_views.xml',
        'views/generic_contract_event.xml',
        'data/system_event_source.xml',
        'data/system_event_category.xml',
        'data/system_event_type.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'demo': [
        'demo/generic_contract_demo.xml',
        'demo/generic_contract_template_demo.xml',
        'demo/generic_contract_template_service_line_demo.xml',
        'demo/generic_contract_service_line_demo.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'OPL-1',
    'price': 100.0,
    'currency': 'EUR',
}
