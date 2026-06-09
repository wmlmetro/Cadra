{
    'name': 'NRS Facilities Management Dashboard',
    'version': '15.0.2.0.1',
    'summary': 'FM operations dashboard — KPIs, SLA table, map, request list, team workload',
    'category': 'Facilities',
    'author': 'WestMetro Limited',
    'depends': ['base', 'web', 'mail', 'generic_request', 'generic_service', 'generic_location', 'myservice_nrs_base'],
    'data': [
        'views/fm_dashboard_menu.xml',
        'data/default_home_action.xml',
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
