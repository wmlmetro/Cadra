{
    'name': "Generic Request SLA (Service)",

    'summary': """
        Allows you to use different SLA limits and warning times per service.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.9.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_sla',
    ],

    # always loaded
    'data': [
        'views/request_sla_rule_view.xml',
        'views/request_sla_control_view.xml',
    ],
    'demo': [
        'demo/request_sla_rule_line.xml'
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
