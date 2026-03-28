{
    'name': 'myservice NRS Theme v5',
    'version': '15.0.5.0.0',
    'summary': 'NRS brand theme — NRS red applied via primary_variables.scss patch',
    'category': 'Themes/Backend',
    'author': 'WestMetro Limited',
    'depends': ['web', 'mail'],
    'data': [
        'views/assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('append', 'myservice_theme_v5/static/src/css/theme.css'),
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
