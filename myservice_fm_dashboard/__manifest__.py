{
    'name': 'NRS Facilities Management Dashboard',
    'version': '15.0.1.0.0',
    'summary': 'FM operations dashboard — requests by domain, SLA status, team workload, overdue alerts',
    'category': 'Facilities',
    'author': 'WestMetro Limited',
    'depends': ['base', 'web', 'mail', 'generic_request', 'generic_service', 'generic_team'],
    'data': [
        'views/fm_dashboard_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_fm_dashboard/static/src/css/fm_dashboard.css',
            'myservice_fm_dashboard/static/src/js/fm_dashboard.js',
        ],
        'web.assets_qweb': [
            'myservice_fm_dashboard/static/src/xml/fm_dashboard.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
