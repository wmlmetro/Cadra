{
    'name': "Generic Request Project",

    'summary': """
        Link requests with project tasks
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.3.7.0',

    # any module necessary for this one to work correctly
    'depends': [
        'project',
        'hr_timesheet',
        'generic_request',
        'base_field_m2m_view',
        'generic_system_event_project',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/request_request.xml',
        'views/project_task.xml',
        'views/request_event.xml',
        'data/system_event_category.xml',
        'data/system_event_type.xml',
        'views/request_type.xml',
        'views/project_project.xml',
        'views/account_analytic_line.xml',
        'wizard/work_log_wizard.xml'
    ],
    'demo': [
        'demo/request_type_with_task.xml',
        'demo/project_project.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
