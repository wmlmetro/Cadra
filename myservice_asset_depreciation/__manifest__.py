{
    'name': 'NRS Asset Depreciation',
    'version': '19.0.1.0.0',
    'summary': 'Book value, accumulated depreciation and schedules for the asset register',
    'description': """
Implements PRD §8.6 "Financial properties" for the Cadra asset register.

Depreciation policy (method, useful life, salvage) is configured per asset
category and overridable per asset. Book value and accumulated depreciation are
computed and stored; the period-by-period schedule is generated on demand.

This is operational reference data, NOT accounting output — PRD §3.3 lists
financial accounting and the general ledger as explicit non-goals. There is no
dependency on `account`, and nothing here posts a journal entry.

Tenants running an authoritative ERP (NRS on SAP FICO — NRS spec §6.2) set the
method to `erp_managed`, which suppresses computation entirely and holds the
externally-supplied figures for reporting.
""",
    'category': 'Facilities',
    'author': 'WestMetro Limited',
    'depends': [
        'myservice_asset_register',
    ],
    'data': [
        'views/asset_category_views.xml',
        'views/asset_views.xml',
        'data/depreciation_policy_defaults.xml',
        'data/depreciation_cron.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
