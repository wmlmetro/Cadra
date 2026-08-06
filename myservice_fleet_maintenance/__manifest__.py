{
    'name': 'myservice Fleet Maintenance',
    'version': '19.0.2.0.0',
    'summary': 'Fleet Command Center dashboard, preventive maintenance alerts, vendor registry and auto ITSM ticket creation',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Fleet',
    'depends': [
        'fleet',
        'myservice_request_core',
        'generic_location',
        'myservice_request_fields',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/mail_templates.xml',
        'views/fleet_service_vendor_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_fleet_maintenance/static/src/xml/fleet_dashboard.xml',

            'myservice_fleet_maintenance/static/src/css/fleet_dashboard.css',
            'myservice_fleet_maintenance/static/src/js/fleet_dashboard.js',
        ],
        
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
