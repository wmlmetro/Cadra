{
    'name': 'Security Command Center',
    'version': '15.0.1.0.0',
    'summary': 'Tabbed command center with case management, OSINT, AI patterns & daily briefs',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Security',
    'depends': ['myservice_security'],
    'data': [
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_security_scc/static/src/css/security_tabs.css',
            'myservice_security_scc/static/src/js/security_tabs.js',
        ],
        'web.assets_qweb': [
            'myservice_security_scc/static/src/xml/security_tabs.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
