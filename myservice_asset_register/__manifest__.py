{
    'name': 'NRS Asset Register & PM Schedules',
    'version': '19.0.1.15.0',
    'summary': 'Fixed asset register, condition tracking, tagging, transfers, PM auto-scheduling',
    'category': 'Facilities',
    'author': 'WestMetro Limited',
    'depends': [
        'base', 'mail', 'web', 'hr',
        'generic_resource',
        'myservice_request_core',
        'generic_location',
        'myservice_nrs_base',
    ],
    'data': [
        'security/asset_security.xml',
        'security/ir.model.access.csv',
        'data/asset_sequences.xml',
        'data/asset_categories.xml',
        'data/asset_tag_report.xml',
        'wizard/asset_label_wizard_view.xml',
        'views/asset_views.xml',
        'views/asset_transfer_views.xml',
        'views/asset_pm_views.xml',
        'views/asset_tag_views.xml',
        'views/asset_tag_report.xml',
        'views/asset_menu.xml',
        # AFTER asset_menu.xml, which defines `menu_asset_root` — this file
        # hangs a menu off it. Loaded before it, a cold install fails with
        # "External ID not found"; an UPGRADE resolves it from the existing
        # row and passes, which is exactly how it reached CI unnoticed.
        'views/asset_sap_views.xml',
        'data/asset_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'myservice_asset_register/static/src/xml/asset_dashboard.xml',

            'myservice_asset_register/static/src/css/asset_dashboard.css',
            'myservice_asset_register/static/src/js/asset_dashboard.js',
        ],
        
    },
    # Stamps when tracking of the handoff-28 fields began — see hooks.py.
    'post_init_hook': 'stamp_tracking_began',
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
