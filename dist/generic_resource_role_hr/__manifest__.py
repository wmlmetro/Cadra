{
    'name': "Generic Resource Role HR",

    'summary': """
        Adds integration with HR (roles for employees).
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.1.6.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource_role',
        'hr',
    ],

    # always loaded
    'data': [
        'views/hr_employee.xml',
        'views/generic_resource_role_link.xml',
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
