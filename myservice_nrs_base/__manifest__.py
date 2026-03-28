{
    'name': 'NRS Design System Base',
    'version': '15.0.1.0.0',
    'summary': 'Shared CSS design tokens and component styles for all NRS modules',
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': ['web'],
    'data': [
        'views/assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('prepend', 'myservice_nrs_base/static/src/css/nrs_base.css'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
