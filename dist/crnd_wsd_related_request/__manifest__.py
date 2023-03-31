# flake8: noqa: E501
{
    'name': 'Website Service Desk (Related requests)',
    'category': 'Service Desk',
    'summary': 'Integration addon (Related requests feature)',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.0.7.1',

    'depends': [
        'crnd_wsd',
        'generic_request_related_requests',
    ],
    'data': [
        'templates/requests.xml',
    ],
    'demo': [
        'demo/request_request.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'crnd_wsd_related_request/static/src/js/tours/related_request_tour.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'price': 50.0,
    'currency': 'EUR',
}
