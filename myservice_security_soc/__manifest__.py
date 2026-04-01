{
    'name': 'Security Operations Centre',
    'version': '15.0.1.0.0',
    'summary': 'Live SOC dashboard with geospatial map, KPIs, watchlist board & intelligence feed',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Security',
    'depends': ['myservice_security'],
    'data': [
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_security_soc/static/src/css/security_soc.css',
            'myservice_security_soc/static/src/js/security_dashboard.js',
        ],
        'web.assets_qweb': [
            'myservice_security_soc/static/src/xml/security_dashboard.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
