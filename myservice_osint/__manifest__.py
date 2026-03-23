{
    'name': 'myservice OSINT Intelligence',
    'version': '15.0.1.0.0',
    'summary': 'Multi-source OSINT collection, threat scoring engine, and state threat assessment matrix',
    'author': 'WestMetro Limited',
    'category': 'Security',
    'depends': ['web', 'mail', 'myservice_security'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/osint_sources.xml',
        'views/osint_source_config_views.xml',
        'views/osint_feed_entry_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_osint/static/src/css/osint.css',
            'myservice_osint/static/src/js/osint_dashboard.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
