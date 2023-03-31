# flake8: noqa: E501
{
    'name': 'Website Service Desk (Service + Resource)',
    'category': 'Service Desk',
    'summary': 'Serives + Resources support in Website Service Desk',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.15.0',
    'depends': [
        'crnd_wsd_service',
        'crnd_wsd_resource',
        'generic_service_resource',
    ],
    'data': [
    ],
    'demo': [
        'demo/request_category.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'crnd_wsd_service_resource/static/src/js/request_new.js',
        ],
        'web.assets_common': [
            'crnd_wsd_service_resource/static/src/js/tours/request_new.js',
            'crnd_wsd_service_resource/static/src/js/tours/request_new_with_resource_http_parameter.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'price': 30.0,
    'currency': 'EUR',
}
