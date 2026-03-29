{
    'name': 'NRS Website Theme',
    'version': '15.0.1.0.0',
    'summary': 'NRS branded public website theme',
    'category': 'Website/Theme',
    'author': 'WestMetro Limited',
    'depends': ['website', 'myservice_nrs_base'],
    'data': [
        'views/website_layout.xml',
        'views/website_pages.xml',
    ],
    'assets': {
        'website.assets_frontend': [
            ('prepend', 'myservice_website_theme/static/src/css/nrs_website.css'),
        ],
    },
    'auto_install': False,
    'installable': True,
}
