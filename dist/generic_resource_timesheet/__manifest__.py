{
    'name': "Generic Resource Timesheet",

    'summary': """
        Provide the ability to add resource scheduling.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Resource',
    'version': '15.0.1.9.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_resource'
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/generic_resource.xml',
        'views/generic_resource_timesheet.xml',
        'views/generic_resource_timesheet_activity.xml',
        'views/generic_resource_timesheet_line.xml',
    ],
    'demo': [],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
