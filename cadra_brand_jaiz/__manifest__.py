{
    'name': 'Cadra Brand — Jaiz',
    'version': '15.0.1.0.0',
    'summary': 'Per-client brand package (Jaiz Bank Plc): primary colour tokens.',
    'description': """
Cadra Brand — Jaiz
==================

Per-client visual identity for Jaiz Bank Plc (Nigerian non-interest bank),
installed only in the Jaiz tenant database. Sibling of cadra_brand_nrs /
cadra_brand_gtb — see cadra_brand_nrs for the full pattern.

To adjust Jaiz's branding:
  * colour  -> the three --brand-primary* values in static/src/css/brand.css
               (keep cadra.brand_primary in data/brand_params.xml in sync)
  * label   -> cadra.brand_short_name in data/brand_params.xml
  * logo    -> cadra.brand_logo (base64 data URI) in data/brand_params.xml,
               read by the React frontend via GET /api/v1/brand
""",
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': ['myservice_nrs_base'],
    'data': [
        'data/brand_params.xml',
    ],
    'assets': {
        'web.assets_backend': [
            ('prepend', 'cadra_brand_jaiz/static/src/css/brand.css'),
        ],
        'website.assets_frontend': [
            ('prepend', 'cadra_brand_jaiz/static/src/css/brand.css'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
