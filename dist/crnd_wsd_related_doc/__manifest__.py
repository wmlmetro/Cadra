# flake8: noqa: E501
{
    'name': 'Website Service Desk (Related doc)',
    'category': 'Service Desk',
    'summary': 'Integration addon (Related doc feature)',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.0.6.0',

    'depends': [
        'crnd_wsd',
        'generic_request_related_doc',
    ],
    'data': [
        'templates/related_doc.xml',
    ],
    'demo': [
        'demo/demo_request.xml',
    ],
    'assets': {
        'web.assets_common': [
            'crnd_wsd_related_doc/static/src/js/tours/related_document_tour.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'price': 50.0,
    'currency': 'EUR',
}
