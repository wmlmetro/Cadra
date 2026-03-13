{
    'name': 'myservice Request Fields',
    'version': '15.0.1.0.0',
    'summary': 'Adds vehicle and location fields to ITSM requests',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Technical',
    'depends': ['generic_request', 'generic_location', 'fleet', 'website'],
    'data': [
        'views/request_request_views.xml',
        'views/request_portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'myservice_request_fields/static/src/css/portal_fields.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
