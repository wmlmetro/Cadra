{
    'name': "Generic Contract Invoicing",

    'summary': """
        Contracts invoicing management
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Contract',
    'version': '15.0.2.9.0',

    # any module necessary for this one to work correctly
    'depends': [
        'hr',
        'generic_contract',
        'account',
        'uom',
        'crnd_web_list_popover_widget',
    ],

    'external_dependencies': {
        'python': [
            'first',
        ],
    },

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/generic_tag.xml',
        'views/generic_contract.xml',
        'views/generic_contract_template.xml',
        'views/account_invoice.xml',
        'views/generic_contract_employee_rate.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [
        'demo/account_journal.xml',
        'demo/product_product.xml',
        'demo/generic_contract.xml',
        'demo/generic_contract_invoice_line.xml',
        'demo/generic_contract_template.xml',
        'demo/generic_contract_template_invoice_line.xml',
    ],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 200.0,
    'currency': 'EUR',
}
