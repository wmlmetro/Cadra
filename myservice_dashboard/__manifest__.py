{
    'name': 'myservice Operations Dashboard',
    'version': '19.0.1.1.0',
    'summary': 'Interactive map dashboard — Fleet, Locations, KPIs',
    'author': 'WestMetro Limited',
    'category': 'Dashboard',
    'depends': [
        'web', 'fleet', 'myservice_request_core', 'generic_location',
        'myservice_request_fields', 'myservice_fleet_maintenance',
        'myservice_nrs_base',
    ],
    'data': [
        'views/dashboard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_dashboard/static/src/xml/dashboard.xml',

            'myservice_dashboard/static/src/css/dashboard.css',
            'myservice_dashboard/static/src/js/dashboard.js',
        ],
        
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}