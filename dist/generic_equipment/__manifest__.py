{
    'name': "Generic Equipment",

    'summary': """
        Base module that allows you to manage your equipment.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Equipment',
    'version': '15.0.0.4.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource_location',
        'generic_tag',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/root_menu.xml',
        'views/generic_equipment.xml',
        'views/generic_equipment_vendor.xml',
        'views/generic_equipment_brand.xml',
        'views/generic_equipment_series.xml',
        'views/generic_equipment_model.xml',
        'views/generic_equipment_category.xml',
        'views/generic_equipment_simple.xml',

        'data/generic_resource_type.xml',
        'data/generic_tag_model.xml',
        'data/generic_equipment_category.xml',
    ],
    'demo': [
        'demo/generic_equipment_vendor.xml',
        'demo/generic_equipment_brand.xml',
        'demo/generic_equipment_series.xml',
        'demo/generic_equipment_model.xml',
    ],

    # 'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
