{
    'name': 'myservice Operations Dashboard',
    'version': '15.0.1.0.0',
    'summary': 'Interactive map dashboard — Fleet, Locations, KPIs',
    'author': 'WestMetro Limited',
    'category': 'Dashboard',
    'depends': [
        'web', 'fleet', 'generic_request', 'generic_location',
        'myservice_request_fields', 'myservice_fleet_maintenance',
    ],
    'data': [
        'views/dashboard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_dashboard/static/src/css/dashboard.css',
            'myservice_dashboard/static/src/js/dashboard.js',
        ],
        'web.assets_qweb': [
            'myservice_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}