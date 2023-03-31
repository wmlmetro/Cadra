{
    'name': "Generic Request Action (HR)",

    'summary': """
        HR related assignments and subscriptions
        in requests using automated actions
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.1.2.3',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action',
        'hr',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/hr_job.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
