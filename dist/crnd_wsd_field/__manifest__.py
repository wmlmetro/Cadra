# flake8: noqa: E501
{
    'name': 'Website Service Desk (Field)',
    'category': 'Service Desk',
    'summary': """
        Provides integration between the Website Service Desk
        and Generic Request Fileds modules. Adds custom fields (string)
        to fill in while submitting the request.
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.19.1',
    'depends': [
        'crnd_wsd',
        'generic_request_field'
    ],
    'data': [
        'views/templates.xml',
        'views/request_field.xml',
    ],
    'demo': [
        'demo/request_type_create_vm.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'crnd_wsd_field/static/src/scss/request_fields.scss',
        ],
        'web.assets_tests': [
            'crnd_wsd_field/static/src/js/request_fields_tour.js',
            'crnd_wsd_field/static/src/js/request_fields_service_tour.js',
            'crnd_wsd_field/static/src/js/request_public_user_tour.js',
            'crnd_wsd_field/static/src/js/request_public_user_create_request_tour.js',
            'crnd_wsd_field/static/src/js/request_public_user_redirect_tour.js',
        ],
    },

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 50.0,
    'currency': 'EUR',
    'tags': ['obsolete'],
}
