{
    'name': "Generic Request Contract",

    'summary': """
        Link requests with Service Contracts
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.3.11.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'generic_contract',
    ],

    # always loaded
    'data': [
        'views/request_request.xml',
        'views/generic_contract.xml',
        'views/generic_contract_service_line.xml',
        'views/generic_contract_template.xml',
        'views/generic_contract_template_service_line.xml',
        'data/system_event_type.xml',
        'views/request_event.xml',

        'reports/request_graph_reports.xml',
    ],
    'demo': [],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
