{
    'name': "Generic Request Action Survey",

    'summary': """
        Surveys can be sent using automated action
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',

    'version': '15.0.1.8.1',

    # any module necessary for this one to work correctly
    'depends': [
        'survey',
        'generic_request_survey',
        'generic_request_action',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/request_type_with_survey.xml',
        'demo/demo_request_event_action.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
