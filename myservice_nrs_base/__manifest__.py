{
    'name': 'NRS Design System Base',
    'version': '15.0.1.1.3',
    'summary': 'Shared CSS design tokens and component styles for all NRS modules',
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': [
        'web',
        'generic_request',
        'generic_service',
        'generic_resource',
        'generic_team',
        'generic_tag',
        'generic_rule',
        'generic_location',
    ],
    'data': [
        'views/assets.xml',
        'views/placeholder_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('prepend', 'myservice_nrs_base/static/src/css/nrs_base.css'),
            # Bridge the legacy bus_service into the wowl registry. Must load
            # before any native component that does useService("bus_service")
            # (e.g. generic_mixin's WebClient patch), otherwise /web is blank.
            ('prepend', 'myservice_nrs_base/static/src/js/bus_service_compat.js'),
            'myservice_nrs_base/static/src/js/nrs_placeholder.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
