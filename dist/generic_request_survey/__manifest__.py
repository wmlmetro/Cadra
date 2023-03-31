{
    'name': "Generic Request Survey",

    'summary': """
        Helpdesk Survey.
        Send surveys from requests.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.1.1',

    # any module necessary for this one to work correctly
    'depends': [
        'survey',
        'generic_request'
    ],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/request_send_survey_view.xml',
        'views/request_request.xml',
        'data/survey_email_template.xml',
        'data/system_event_type.xml',
        'views/request_event.xml',
        'views/request_type.xml',
    ],
    'demo': [
        'demo/request_survey_bug.xml',
        'demo/user_input.xml',
        'demo/user_input_line.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'EUR',
}
