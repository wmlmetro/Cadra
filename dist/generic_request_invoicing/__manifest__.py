{
    'name': "Generic Request Invoicing",

    'summary': """
        Generic Request Invoicing
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.21.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'account',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/request_timesheet_line.xml',
        'views/request_invoice_line.xml',
        'views/account_invoice.xml',
        'views/request_request.xml',
        'views/request_type.xml',
        'wizard/request_wizard_stop_work.xml',
        'views/res_config_settings.xml',
    ],
    'demo': [
        'demo/product_product.xml',
        'demo/request_type_simple.xml',
    ],

    'images': [
        'static/description/banner.png',
    ],
    'qweb': [
    ],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
