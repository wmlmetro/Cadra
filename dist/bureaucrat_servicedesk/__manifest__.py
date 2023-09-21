{
    'name': "Bureaucrat Service Desk",

    'summary': """
        Service Desk / Helpdesk / Requests / Tickets
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'version': '15.0.1.12.1',
    'category': 'Service Desk',

    # any module necessary for this one to work correctly
    'depends': [
        'bureaucrat_helpdesk_lite',
        'generic_condition',
        'crnd_wsd_tag',
        'generic_request_calendar',
        'generic_request_field',
        'generic_request_mail',
        'generic_request_condition',
        'generic_request_condition_mail',
        'generic_system_event_mail_events',
        'generic_request_related_doc',
        'generic_request_related_requests',
        'crnd_wsd_related_doc',
        'crnd_wsd_related_request',
        'crnd_wsd_field',
        'bureaucrat_knowledge_rel_docs',
    ],

    # always loaded
    'data': [
        'data/res_groups.xml',
    ],
    'images': ['static/description/banner.gif'],
    'demo': [],

    'installable': True,
    'application': True,
    'license': 'OPL-1',
    'tags': ['bundle'],

    'price': 1.0,
    'currency': 'EUR',
    "live_test_url": "https://yodoo.systems/saas/templates",
}
