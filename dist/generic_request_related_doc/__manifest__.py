{
    'name': "Generic Request Related Document",

    'summary': """
        Allow you to link any Odoo documents with requests
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.9.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_m2o',
        'generic_request'
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/request_related_document_type.xml',
        'views/request_related_document.xml',
        'views/request_related_document_type.xml',
        'views/request_request_view.xml',
    ],
    'demo': [
        'demo/request_type_sale_problem.xml'
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
