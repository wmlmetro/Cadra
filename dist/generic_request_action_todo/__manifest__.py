{
    'name': "Generic Request Action Todo ",

    'summary': """
            Todos can be added used automated action
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'category': 'Generic Todo',
    'version': '15.0.0.8.1',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_action',
        'generic_request_todo',
    ],

    # always loaded
    'data': [
        'views/request_event_action.xml',
    ],
    'demo': [
        'demo/request_event_action.xml',
    ],
    'images': [],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR',
}
