{
    'name': 'myservice Backend Theme',
    'version': '15.0.1.0.0',
    'summary': 'NRS myservice.com.ng — custom backend colour scheme',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Themes/Backend',
    'depends': ['web'],
    'data': [
        'views/assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_theme/static/src/css/myservice_backend.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
