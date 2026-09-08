{
    'name': 'NRS Design System Base',
    'version': '19.0.1.1.0',
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
            # Odoo 19 dropped jQuery auto-loading; the legacy NRS dashboards need
            # it. Load it first, then the legacy-module compatibility shim (which
            # re-provides web.core / web.rpc / web.ajax / web.session /
            # web.AbstractAction backed by real Odoo 19 services).
            ('prepend', 'web/static/lib/jquery/jquery.js'),
            ('prepend', 'myservice_nrs_base/static/src/css/nrs_base.css'),
            'myservice_nrs_base/static/src/js/legacy_compat.js',
            # NOTE (Odoo 19 rebuild): the 15.0 bus_service_compat.js shim and the
            # legacy odoo.define-based nrs_placeholder.js client action were both
            # removed — bus_service is native in 19 and the placeholder was unused.
        ],
    },
    # Fresh install: turn off Odoo's outbound third-party crons (the
    # services.odoo.com telemetry POST and the digest mailer). Existing tenants
    # get the same call from migrations/19.0.1.1.0/post-migrate.py — an install
    # runs no migration script and an upgrade runs no post_init_hook, so both
    # entry points are needed. Odoo 19 calls the hook with `env`.
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
