{
    'name': 'myservice NRS Theme v5',
    'version': '15.0.5.0.0',
    'summary': 'NRS brand theme — NRS red applied via primary_variables.scss patch',
    'category': 'Themes/Backend',
    'author': 'WestMetro Limited',
    'depends': ['web', 'mail', 'web_responsive', 'myservice_nrs_base'],
    'data': [
        'views/assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('append', 'myservice_theme_v5/static/src/css/theme.css'),
            ('append', 'myservice_theme_v5/static/src/css/sidebar.css'),
            ('append', 'myservice_theme_v5/static/src/js/theme.js'),
            ('append', 'myservice_theme_v5/static/src/js/apps_menu_grouped.js'),
            ('append', 'myservice_theme_v5/static/src/js/nrs_sidebar.js'),
        ],
        'web.assets_qweb': [
            'myservice_theme_v5/static/src/xml/navbar_override.xml',
            'myservice_theme_v5/static/src/xml/apps_menu_override.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
