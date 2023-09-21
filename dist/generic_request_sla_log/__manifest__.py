{
    'name': "Generic Request SLA: Log",

    'summary': """
        The module adds the ability to log and report
        actions that occur with requests.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.15.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'resource'
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/request_sla_log_views.xml',
        'views/request_request_views.xml',
        'views/request_type_views.xml',
    ],
    'demo': [
        'demo/resource_calendar.xml',
        'demo/request_type.xml',
    ],
    'images': ['static/description/banner.gif'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
