{
    'name': 'NRS Design System Base',
    'version': '19.0.1.3.0',
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
            # Global backend navigation styling. Arrived here from
            # myservice_security/static/src/css/security_navbar.css (handoff
            # 12, C1) — byte-identical, no selector touched. It was named and
            # filed for the Security app and had never scoped to it: every
            # selector is a core web-client class, so it styles the top
            # navigation of every backend screen for every user.
            #
            # It is here rather than in myservice_theme_v5 for two measured
            # reasons. Nothing in the repo depends on theme_v5 — it is
            # installed by hand — so a fresh tenant installing myservice_api
            # would silently stop loading this. And theme_v5's theme.css and
            # sidebar.css !important the SAME `.o_main_navbar` background;
            # they sit at bundle index 2287/2288 against this file's 2150, so
            # they win today. Moving it after them would flip the navbar from
            # white to #080c10 — a large visible change made as a side effect
            # of a tidy-up, which is the thing C1 exists to avoid. Every other
            # rule in the file wins on specificity and does not care where it
            # sits.
            'myservice_nrs_base/static/src/css/global_navbar.css',
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
