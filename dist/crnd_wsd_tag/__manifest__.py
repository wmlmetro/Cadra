{
    'name': 'Website Service Desk (Tag)',
    'category': 'Service Desk',
    'summary': 'Tag support in Website Service Desk',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.0.15.0',
    'depends': [
        'crnd_wsd',
        'generic_request',
    ],
    'data': [
        'views/templates.xml',
    ],
    'demo': [
        'demo/request_type_generic.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'crnd_wsd_tag/static/src/css/colors.css',
        ],
        'web.assets_tests': [
            'crnd_wsd_tag/static/src/js/tours/request_new_with_tags.js',
            'crnd_wsd_tag/static/src/js/tours/request_public_user.js',
            'crnd_wsd_tag/static/src/js/tours/request_public_user_redirect.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 10.0,
    'currency': 'EUR',
}
