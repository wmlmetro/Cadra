{
    'name': 'Website Service Desk (Project)',
    'category': 'Service Desk',
    'summary': 'Project support in Website Service Desk',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.3.1',

    'depends': [
        'crnd_wsd',
        'generic_request_project',
    ],
    'data': [
        'templates/templates.xml',
    ],
    'demo': [
        'demo/demo_request_with_task.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'crnd_wsd_project/static/src/js/tours/request_with_task.js',
        ],
    },

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 10.0,
    'currency': 'EUR',
}
