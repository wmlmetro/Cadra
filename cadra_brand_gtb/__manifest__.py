{
    'name': 'Cadra Brand — GTB',
    'version': '19.0.1.0.0',
    'summary': 'Per-client brand package (Guaranty Trust Bank): primary colour tokens.',
    'description': """
Cadra Brand — GTB
=================

Per-client visual identity for Guaranty Trust Bank, installed only in the
GTB tenant database. Sibling of cadra_brand_nrs — see that module for the
full pattern.

To adjust GTB's branding:
  * colour  -> the three --brand-primary* values in static/src/css/brand.css
  * label   -> cadra.brand_short_name in data/brand_params.xml
  * logo    -> uploaded to res.company in the GTB database (served per-DB)
""",
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': ['myservice_nrs_base'],
    'data': [
        'data/brand_params.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('prepend', 'cadra_brand_gtb/static/src/css/brand.css'),
        ],
        'website.assets_frontend': [
            ('prepend', 'cadra_brand_gtb/static/src/css/brand.css'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
