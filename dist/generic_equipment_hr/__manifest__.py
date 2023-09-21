{
    'name': "Generic Equipment (HR)",

    'summary': """
        Generic Equipment HR integration
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Equipment',
    'version': '15.0.0.1.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_equipment',
        'hr',
    ],

    # always loaded
    'data': [
        'views/generic_equipment.xml',
    ],
    'demo': [
    ],

    # 'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
    # 'price': 20.0,
    # 'currency': 'EUR',
}
