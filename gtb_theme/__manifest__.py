{
    'name': 'GTB Theme',
    'version': '15.0.1.0.0',
    'summary': 'GTB brand layer — logo, colours and wordmark over the shared backend theme',
    'description': """
GTB brand layer
===============

A thin brand skin for the shared Cadra backend. It depends on
``myservice_theme_v5`` (the structural backend theme: white navbar, left
sidebar, grouped apps) and overrides ONLY the brand:

* primary colour tokens (re-points ``--nrs-*`` brand vars to GTB colours);
* the navbar wordmark text;
* the company name + logo + favicon (set in a post-init hook), which drives the
  sidebar logo and the login-screen logo.

All functional modules (dashboard, fleet, requests, …) are shared with the NRS
instance unchanged — only this module differs between the two deployments.

⚠️ Placeholders to replace with real GTB assets:
   * ``static/src/img/logo.png``  — the GTB logo (used as company logo/favicon)
   * the colour tokens in ``static/src/css/brand.css``
""",
    'author': 'WestMetro Limited',
    'category': 'Themes/Backend',
    # Depends on the structural theme; that pulls web, mail, web_responsive and
    # myservice_nrs_base (design tokens + the bus_service wowl bridge) in turn.
    'depends': ['myservice_theme_v5'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            # Loaded AFTER myservice_theme_v5's CSS (dependency order), so these
            # :root overrides win the cascade.
            ('append', 'gtb_theme/static/src/css/brand.css'),
        ],
    },
    'post_init_hook': '_gtb_post_init',
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
