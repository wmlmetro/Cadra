{
    'name': "Bureaucrat Service Desk Ultimate",

    'summary': """
        Service Desk / Helpdesk / Requests / Tickets
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'version': '15.0.1.12.0',
    'category': 'Service Desk',

    # any module necessary for this one to work correctly
    'depends': [
        'bureaucrat_servicedesk_pro',
        'generic_request_action',
        'generic_request_action_priority',
        'generic_request_action_subrequest',
        'generic_request_action_tag',
        'generic_request_action_team',
        'generic_request_action_todo',
        'generic_request_action_invoice',
        'generic_request_action_project',
        'generic_request_action_survey',
        'generic_request_route_auto',
        'generic_assignment',
        'generic_request_assignment',
        'generic_request_action_assignment',
        'generic_request_action_subrequest_assignment',
        'generic_request_assignment_team',
        'generic_request_sale',
        'generic_assignment_hr',
        'generic_assignment_team',
        'generic_assignment_project',
        'generic_assignment_hr_holidays',
        'generic_assignment_team_hr_holidays',
        'generic_request_action_hr',
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
                     "template/bureaucrat-servicedesk-ultimate-14-0-demo-258",
}
