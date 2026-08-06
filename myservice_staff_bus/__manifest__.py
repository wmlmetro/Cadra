{
    'name': 'NRS Staff Bus Management',
    'version': '19.0.1.0.0',
    'summary': 'Staff bus routes, scheduling, passenger manifests, fuel and maintenance',
    'category': 'Fleet',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'depends': [
        'base',
        'fleet',
        'hr',
        'mail',
        'web',
        'myservice_nrs_base',
    ],
    'data': [
        'security/bus_security.xml',
        'security/ir.model.access.csv',
        'data/bus_sequence.xml',
        'views/bus_route_views.xml',
        'views/bus_schedule_views.xml',
        'views/bus_manifest_views.xml',
        'views/bus_fuel_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/bus_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_staff_bus/static/src/xml/bus_dashboard.xml',

            'myservice_staff_bus/static/src/css/bus_dashboard.css',
            'myservice_staff_bus/static/src/js/bus_dashboard.js',
        ],
        
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
