{
    'name': 'NRS Asset Barcode Station',
    'version': '15.0.1.0.0',
    'summary': 'Barcode generation, scanning, lookup and printing for NRS assets',
    'category': 'Facilities',
    'author': 'WestMetro Limited',
    'depends': [
        'base', 'web', 'mail',
        'myservice_asset_register',
        'myservice_fm_dashboard',
        'website',
    ],
    'data': [
        'views/barcode_station_menu.xml',
        'views/portal_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_barcode_station/static/src/css/barcode_station.css',
            'myservice_barcode_station/static/src/js/barcode_station.js',
        ],
        'web.assets_qweb': [
            'myservice_barcode_station/static/src/xml/barcode_station.xml',
        ],
        'web.assets_frontend': [
            'myservice_barcode_station/static/src/css/barcode_portal.css',
            'myservice_barcode_station/static/src/js/barcode_portal.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
