# flake8: noqa: E501
{
    'name': 'Website Service Desk (Resource)',
    'category': 'Service Desk',
    'summary': """
        Provides integration between the Website Service Desk
        and Generic Request Resource addons. It allows you to
        use resources in the Website Service Desk application.
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.29.1',
    'depends': [
        'crnd_wsd',
        'generic_request_resource',
        'generic_service_resource',
    ],
    'data': [
        'views/generic_resource_type.xml',
        'views/request_type.xml',
        'views/res_config_settings.xml',
        'templates/templates.xml',
    ],
    'demo': [
        'demo/request_type_res_quest.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'crnd_wsd_resource/static/src/scss/request_new.scss',
            'crnd_wsd_resource/static/src/js/request_new.js',
        ],
        'web.assets_tests': [
            'crnd_wsd_resource/static/src/js/tours/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 80.0,
    'currency': 'EUR',
}
