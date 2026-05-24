{
    'name': 'myservice Request Fields',
    'version': '15.0.1.0.0',
    'summary': 'Adds vehicle and location fields to ITSM requests',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Technical',
    'depends': ['generic_request', 'crnd_wsd', 'generic_request_location', 'generic_location', 'generic_team', 'fleet', 'website', 'myservice_nrs_base'],
    'data': [
        'views/request_request_views.xml',
        'views/portal_location_template.xml',
        'views/request_portal_templates.xml',
        'views/triage_views.xml',
        'views/triage_menus.xml',
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
