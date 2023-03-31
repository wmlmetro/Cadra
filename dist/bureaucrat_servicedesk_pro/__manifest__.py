{
    'name': "Bureaucrat Service Desk Pro",

    'summary': """
        Service Desk / Helpdesk / Requests / Tickets
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'version': '15.0.1.6.0',
    'category': 'Service Desk',

    # any module necessary for this one to work correctly
    'depends': [
        'bureaucrat_servicedesk',
        'generic_team',
        'generic_request_team',
        'generic_rule',
        'generic_request_sla',
        'generic_request_sla_service',
        'generic_request_sla_log',
        'generic_request_sla_priority',
        'generic_request_crm',
        'generic_request_invoicing',
        'generic_request_project',
        'crnd_wsd_project',
        'generic_system_event_project',
        'generic_todo',
        'generic_request_todo',
        'generic_request_sla_team',
        'generic_team_calendar',
        'generic_service_team',
        'generic_team_tag',
        'generic_request_recent',
        'generic_request_hr',
        'generic_request_survey',
        'generic_request_message_status',
        'generic_team_hr',
        'generic_location',
        'generic_request_location',
    ],

    # always loaded
    'data': [
    ],
    'images': ['static/description/banner.gif'],
    'demo': [],

    'installable': True,
    'application': True,
    'license': 'OPL-1',
    'tags': ['bundle'],

    'price': 1.0,
    'currency': 'EUR',
    "live_test_url": "https://yodoo.systems/saas/"
                     "template/bureaucrat-servicedesk-pro-14-0-demo-256",
}
