{
    'name': 'NRS Watchlist — Security Command Board',
    'version': '15.0.1.0.0',
    'summary': 'Watchlist management with mugshot board, threat tiers, and API feed integration for NRS SOC',
    'author': 'WestMetro Limited',
    'website': 'https://www.westmetrong.com',
    'category': 'Security',
    'depends': ['base', 'mail', 'web', 'myservice_security'],
    'data': [
        'security/ir.model.access.csv',
        'security/watchlist_security.xml',
        'views/watchlist_views.xml',
        'views/watchlist_menus.xml',
        'data/watchlist_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'nrs_watchlist/static/src/css/watchlist.css',
            'nrs_watchlist/static/src/js/watchlist_board.js',
            'nrs_watchlist/static/src/xml/watchlist_board.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
