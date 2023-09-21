{
    'name': "Generic Request (Actions)",

    'summary': """
        Configurable automatic actions that trigger on request events
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.4.17.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'generic_condition',
        'mail',
        'resource',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/request_stage_route_view.xml',
        'views/request_event_action.xml',
        'views/request_type.xml',
    ],
    'demo': [
        'demo/mail_template.xml',
        'demo/request_category_demo.xml',
        'demo/request_type_action.xml',
        'demo/generic_condition.xml',
        'demo/request_event_action.xml',
        'demo/request_creation_template.xml',
        'demo/demo_request_template_text.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 230.0,
    'currency': 'EUR',
}
