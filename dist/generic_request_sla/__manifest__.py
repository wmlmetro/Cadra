{
    'name': "Generic Request SLA",

    'summary': """
        Allows you to use a Service Level Agreement when dealing with requests.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.13.0',

    # any module necessary for this one to work correctly
    'depends': [
        'mail',
        'generic_request',
        'generic_request_sla_log',
        'generic_request_condition',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/request_sla_rule_type.xml',
        'data/generic_system_event_type.xml',
        'views/menu.xml',
        'views/request_sla_rule_view.xml',
        'views/request_sla_rule_line_view.xml',
        'views/request_sla_rule_type_view.xml',
        'views/request_sla_rule_condition_view.xml',
        'views/request_type_view.xml',
        'views/request_request_view.xml',
        'views/request_sla_control_view.xml',
        'views/request_event.xml',
        'views/mail_templates.xml',

        'reports/request_graph_reports.xml',
    ],
    'demo': [
        'demo/resource_calendar.xml',
        'demo/request_sla_rule_type.xml',
        'demo/request_type_sla.xml',
        'demo/request_type_sla_complex.xml',
        'demo/request_type_sla_2.xml',
        'demo/request_type_sla_condition.xml',
        'demo/request_sla_rule_line.xml',
    ],
    'images': ['static/description/banner.gif'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 200.0,
    'currency': 'EUR',
}
