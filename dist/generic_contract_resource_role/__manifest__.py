{
    'name': "Generic Contract Resource Role [Obsolete]",

    'summary': (
        "This module reached the end of life and can be safely removed. "
        "In case of uninstallation, all functionality added by this module "
        "will be kept and updatable."),

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Contract',
    'version': '15.0.0.9.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_contract_resource',
        'generic_resource_role',
    ],

    # always loaded
    'data': [],
    'images': ['static/description/banner.png'],
    'demo': [
    ],

    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
    'tags': ['obsolete'],
}
