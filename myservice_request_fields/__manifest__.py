{
    'name': 'myservice Request Fields',
    'version': '19.0.1.0.0',
    'summary': 'Adds vehicle and location fields + triage to service requests',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Technical',
    # Odoo 19 rebuild: generic_request -> myservice_request_core; crnd_wsd
    # (website portal) dropped — request submission is served by the React SPA +
    # /api/v1; generic_request_location dropped — request_core provides
    # generic_location_id directly.
    'depends': [
        'myservice_request_core',
        'generic_location',
        'generic_team',
        'fleet',
        'myservice_nrs_base',
    ],
    'data': [
        'views/request_request_views.xml',
        'views/triage_views.xml',
        'views/triage_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
