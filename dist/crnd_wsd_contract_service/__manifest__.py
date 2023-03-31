# flake8: noqa: E501
{
    'name': 'Website Service Desk (Contract Service)',
    'category': 'Service Desk',
    'summary': """
        Show available services under your company's contracts
        in the Website Service Desk
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.0.14.0',
    'depends': [
        'crnd_wsd',
        'generic_contract',
        'generic_request_contract',
    ],
    'data': [
        'security/security.xml',
    ],
    'demo': [
        'demo/generic_contract_demo.xml',
    ],
    'assets': {
        'web.assets_common': [
            'crnd_wsd_contract_service/static/src/js/tours/request_contract_service.js',
            'crnd_wsd_contract_service/static/src/js/tours/request_contract_service_consulting.js',
            'crnd_wsd_contract_service/static/src/js/tours/request_contract_service_development.js',
        ],
    },

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 10.0,
    'currency': 'EUR',
}
