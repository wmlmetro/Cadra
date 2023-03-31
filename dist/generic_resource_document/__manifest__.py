{
    'name': "Generic Resource Document",

    'summary': """
        Link documents to generic resources
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.0.7.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource',
    ],

    # always loaded
    'data': [
        'views/generic_resource.xml',
    ],
    'demo': [
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
