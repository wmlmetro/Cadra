{
    'name': 'NRS Design System Base',
    'version': '19.0.1.0.0',
    'summary': 'Shared CSS design tokens and component styles for all NRS modules',
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': [
        'web',
        # CRND-free request engine (replaces proprietary generic_request).
        'myservice_request_core',
        'generic_service',
        # generic_resource dep deferred until it is ported (asset_register stage).
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
            # NOTE (Odoo 19 rebuild): the 15.0 bus_service_compat.js shim and the
            # legacy odoo.define-based nrs_placeholder.js client action were both
            # removed — bus_service is native in 19 and the placeholder was unused.
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
