{
    'name': "Generic request SLA team",

    'summary': """
        This addon implements SLA ability to handle team assignments.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Team',
    'version': '15.0.0.8.1',

    "depends": [
        'generic_request_sla_log',
        'generic_request_team',
        'generic_request_sla',
    ],

    "data": [
        'views/generic_request_sla_log.xml',
        'views/generic_request_sla_rule.xml',
        'views/generic_request_sla_control.xml',
    ],

    "demo": [
        'demo/request_type_sla_team.xml',
    ],
    'images': ['static/description/banner.png'],
    "installable": True,
    "application": False,
    'license': 'OPL-1',
    'price': 15.0,
    'currency': 'EUR',
}
