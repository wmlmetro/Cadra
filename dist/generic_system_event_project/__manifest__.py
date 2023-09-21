{
    'name': "Generic Project Event",

    'summary': """ Provides event manipulation for Project instances. """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic System Event',
    'version': '15.0.0.1.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_system_event',
        'project',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/project_views.xml',
        'views/project_task_event_data.xml',
        'data/project_task_event_category.xml',
        'data/project_task_event_type.xml',
        'data/ir_cron.xml',
    ],
    'demo': [],
    'images': [],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
