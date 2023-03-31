{
    'name': "Generic Contract Resource Role",

    'summary': """
        Specify partner roles for resources used in the contract
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Contract',
    'version': '15.0.0.6.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_contract_resource',
        'generic_resource_role',
    ],

    # always loaded
    'data': [
        'views/generic_contract_resource_line_views.xml',
        'views/generic_contract_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [
        'demo/generic_resource_role.xml',
    ],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
