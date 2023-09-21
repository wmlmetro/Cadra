{
    'name': "Generic Request Sale",

    'summary': """
        Allows you create requests from sale order.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.3.2',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'sale',
    ],

    # always loaded
    'data': [
        'views/product_template.xml',
        'views/sale_order.xml',
    ],
    'demo': [
        'demo/request_creation_template.xml',
        'demo/product_product.xml',
        'demo/sale_order.xml'
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 20.0,
    'currency': 'EUR',
}
