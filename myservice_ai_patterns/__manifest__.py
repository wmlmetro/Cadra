{
    'name': 'myservice AI Pattern Detection',
    'version': '15.0.1.0.0',
    'summary': 'Claude-powered security pattern detection — clusters, escalation, actor, temporal, route risk, watchlist proximity',
    'author': 'WestMetro Limited',
    'category': 'Security',
    'depends': ['web', 'mail', 'myservice_security', 'myservice_osint'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/ai_pattern_alert_views.xml',
        'views/ai_daily_brief_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_ai_patterns/static/src/css/ai_patterns.css',
            'myservice_ai_patterns/static/src/js/ai_patterns.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
