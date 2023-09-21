{
    'name': "Bureaucrat ITSM",

    'summary': """
        ITSM
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'version': '15.0.1.11.1',
    'category': 'ITSM',

    # any module necessary for this one to work correctly
    'depends': [
        'bureaucrat_servicedesk_ultimate',
        'generic_resource',
        'generic_resource_role',
        'generic_service_resource',
        'generic_resource_timesheet',
        'generic_resource_location',
        'generic_resource_document',
        'generic_resource_role_hr',
        'generic_request_resource',
        'crnd_wsd_resource',
        'crnd_wsd_resource_role',
        'generic_contract',
        'generic_contract_invoicing',
        'generic_contract_resource',
        'generic_contract_resource_role',
        'generic_request_api',
        'generic_request_api_field',
        'generic_request_contract',
        'crnd_wsd_contract_service',
        'generic_request_contract_resource',
        'crnd_wsd_api',
        'crnd_wsd_legal',
        'crnd_wsd_broadcast',
        # 'crnd_wsd_hr',
    ],

    # always loaded
    'data': [
    ],
    'images': ['static/description/banner.gif'],
    'demo': [],

    'installable': True,
    'application': True,
    'license': 'OPL-1',

    'price': 1.0,
    'currency': 'EUR',
    "live_test_url": "https://yodoo.systems/saas/templates",
}
