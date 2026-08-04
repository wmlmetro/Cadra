{
    'name': 'Cadra Brand — NRS',
    'version': '19.0.1.0.0',
    'summary': 'Per-client brand package (Nigeria Revenue Service): primary colour tokens.',
    'description': """
Cadra Brand — NRS
=================

The single source of truth for *this client's* visual identity. Cadra ships one
product across many client databases; a client's branding is a thin module like
this one, installed only in that client's DB.

To create a brand for a new client:
  1. Copy this module to ``cadra_brand_<client>``.
  2. Change the three ``--brand-primary*`` hex values in
     ``static/src/css/brand.css``.
  3. Set the company name / address / email / phone on res.company (seed).
  4. Drop the client logo on res.company (it is served per-DB automatically).
  5. Add the module to CADRA_BOOTSTRAP_MODULES for that client's deploy.

Everything that consumes ``var(--nrs-red)`` / ``var(--brand-primary)`` (126+
call sites across the dashboards, theme and website) re-skins from the values
here. NOTE: a few surfaces cannot consume a CSS variable and still carry the
literal hex — the wkhtmltopdf asset-tag report, decorative SVG stroke
attributes, and JS chart colour literals. Grep the client hex if you need to
re-skin those too.
""",
    'category': 'Theme',
    'author': 'WestMetro Limited',
    'depends': ['myservice_nrs_base'],
    'data': [
        'data/brand_params.xml',
    ],
    'assets': {
        # Loaded into both the backend and the public website so the brand
        # tokens are in :root scope everywhere. Order is irrelevant: consumers
        # reference var(--brand-primary, <fallback>), resolved at use-time.
        'web.assets_backend': [
            ('prepend', 'cadra_brand_nrs/static/src/css/brand.css'),
        ],
        'website.assets_frontend': [
            ('prepend', 'cadra_brand_nrs/static/src/css/brand.css'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
