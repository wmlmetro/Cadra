{
    'name': 'myservice NRS Theme',
    'version': '19.0.1.0.0',
    'summary': 'NRS brand theme for myservice — red/dark, clean sidebar, modern cards',
    'category': 'Themes/Backend',
    'author': 'WestMetro Limited',
    'depends': ['web', 'mail'],
    'data': [
        'views/theme_assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('append', 'myservice_theme/static/src/css/theme.css'),
            ('append', 'myservice_theme/static/src/js/theme.js'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
