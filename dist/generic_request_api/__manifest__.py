{
    'name': "Generic Request API",

    'summary': """
        Allows you to use API endpoints to create requests.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.2.12.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        'http_routing',
        'website',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'templates/templates.xml',
        'views/generic_request_api.xml',
        'views/generic_request_api_key.xml',
        'views/request_request.xml',

        'wizard/wizard_add_access_key_views.xml',
    ],
    'demo': [
        'demo/request_category.xml',
        'demo/request_type.xml',
        'demo/request_creation_template.xml',
        'demo/request_api_endpoint.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}
