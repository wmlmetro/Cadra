{
    'name': "Generic Resource Location",

    'summary': """
        This addon provides integration between
        Generic Resource and Generic Location addons.
        You can add locations to resources.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.1.3.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_location',
        'generic_resource',
    ],

    # always loaded
    'data': [
        'data/generic_resource_type.xml',
        'views/generic_resource_views.xml',
        'views/generic_location_views.xml',
        'views/generic_resource_type.xml',
    ],
    'demo': ['demo/resource_location.xml'],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'OPL-1',
    'price': 20.0,
    'currency': 'EUR',
}
