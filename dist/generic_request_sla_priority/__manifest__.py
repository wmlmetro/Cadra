{
    "name": "Generic request SLA priority",
    "summary": "Change SLA on request when priority is changed",
    "version": "15.0.0.4.0",
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    "category": "Generic Request",
    "depends": [
        'generic_request_sla',
    ],
    "data": [
        'views/request_sla_rule_line_view.xml',
        'views/request_sla_rule_view.xml',
    ],
    "demo": [
        'demo/request_sla_rule_line.xml',
    ],
    "installable": True,
    "application": False,
    'images': ['static/description/banner.png'],
    'price': 50.0,
    'currency': 'EUR',
}
