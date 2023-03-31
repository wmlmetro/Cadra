{
    'name': "Generic Service Team",

    'summary': """
        Create and manage service teams
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Service',
    'version': '15.0.0.4.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_service',
        'generic_team',
    ],

    # always loaded
    'data': [
        'views/generic_service_views.xml',
    ],
    'demo': [],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
