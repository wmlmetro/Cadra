{
    'name': 'myservice NRS Theme v5',
    'version': '15.0.5.0.0',
    'summary': 'NRS brand theme — overrides Odoo SCSS variables, white surfaces, DM Sans',
    'category': 'Themes/Backend',
    'author': 'WestMetro Limited',
    'depends': ['web', 'mail'],
    'data': [],
    'assets': {
        # Prepend SCSS variables BEFORE Odoo compiles primary_variables.scss
        # This is how Odoo 15 theming works properly
        'web.assets_backend': [
            # 1. Override SCSS variables first (prepend before everything)
            ('prepend', 'myservice_theme_v5/static/src/scss/variables.scss'),
            # 2. Append our CSS after everything else
            ('append', 'myservice_theme_v5/static/src/css/theme.css'),
            # 3. Append JS for logo injection and color fixes
            ('append', 'myservice_theme_v5/static/src/js/theme.js'),
        ],
        'web.assets_qweb': [
            'myservice_theme_v5/static/src/xml/navbar_override.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
