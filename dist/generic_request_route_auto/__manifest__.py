{
    'name': "Generic Request (Auto route)",

    'summary': """
        Run routes automatically on trigger.
        This addon works greet with
        generic_condition and generic_request_condition addons
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.3.2.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_condition',
        'mail',
    ],
    'demo': [
        'demo/request_type_cron.xml',
        'demo/request_type_auto.xml',
    ],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/request_request_view.xml',
        'views/request_stage_route_trigger_view.xml',
        'views/request_stage_route_trigger_event_view.xml',
        'views/request_stage_route_view.xml',
        'views/request_type_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
    'price': 130.0,
    'currency': 'EUR',
}
