{
    'name': "Generic Assignment Project",

    'summary': """
        Allows you to use additional project-related
        assignment policy models
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',

    'version': '15.0.1.2.0',

    # any module necessary for this one to work correctly
    'depends': [
        'project',
        'generic_assignment',
    ],

    # always loaded
    'data': [
        'data/generic_request_assignment_project.xml',
        'views/generic_assignment_project.xml',
        'data/assign_project_manager_policy.xml'
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
