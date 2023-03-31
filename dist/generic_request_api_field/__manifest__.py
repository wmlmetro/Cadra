{
    'name': "Generic Request API Field",

    'summary': """
        Additional fields for filling when setting up the API endpoint to
        create a request.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.6.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_api',
        'generic_request_field',
    ],

    # always loaded
    'data': [
        "security/ir.model.access.csv",
        "views/request_api_endpoint.xml",
    ],
    'demo': [
        "demo/request_api_field_demo.xml",
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': True,
    'license': 'OPL-1',
}
