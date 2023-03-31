{
    'name': "Generic Todo",

    'summary': """ Provides Todo tasks for any model""",

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Todo',
    'version': '15.0.1.3.0',

    # any module necessary for this one to work correctly
    'depends': [
        'crnd_web_actions',
        'generic_m2o',
        'generic_mixin',
        'generic_system_event',
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'views/generic_todo_views.xml',
        'views/generic_todo_simple.xml',
        'views/generic_todo_template_line_views.xml',
        'views/generic_todo_template_views.xml',
        'views/generic_todo_type_views.xml',
        'views/generic_todo_event_data.xml',

        'wizard/todo_wizard_add_template_views.xml',

        'data/generic_todo_type_data.xml',
        'data/ir_module_category.xml',

        'data/generic_todo_event_source.xml',
        'data/generic_todo_event_category.xml',
        'data/generic_todo_event_type.xml',
    ],
    'demo': [
        'demo/generic_todo_template_demo.xml',
    ],
    'images': [],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
