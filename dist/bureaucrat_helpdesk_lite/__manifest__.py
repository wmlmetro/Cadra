{
    'name': "Bureaucrat Helpdesk Lite",

    'summary': """
        Help desk
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'version': '15.0.1.6.0',
    'category': 'Helpdesk',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_mixin',
        'generic_m2o',
        'base_field_m2m_view',
        'generic_tag',
        'generic_service',
        'crnd_web_diagram_plus',
        'crnd_web_m2o_info_widget',
        'crnd_web_tree_colored_field',
        'crnd_web_list_popover_widget',
        'generic_request',
        'crnd_wsd',
        'crnd_service_desk',
        'generic_system_event',
        'bureaucrat_knowledge_website',
        'bureaucrat_knowledge',
    ],

    # always loaded
    'data': [
    ],
    'images': ['static/description/banner.gif'],
    'demo': [],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'tags': ['bundle'],

    'price': 0.0,
    'currency': 'EUR',
    "live_test_url": "https://yodoo.systems/saas/"
                     "template/bureaucrat-helpdesk-lite-14-0-demo-246",
}
