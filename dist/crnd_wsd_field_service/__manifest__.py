{
    'name': 'Website Service Desk (Field + Service)',
    'category': 'Service Desk',
    'summary': """
        This module provides integration between the Website Service Desk,
        Generic Request Fileds and Generic Service modules.
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.9.0',
    'depends': [
        'crnd_wsd_field',
        'crnd_wsd',
        'generic_request_field_service',
    ],
    'data': [
    ],
    'demo': [
        'demo/request_type_create_vm.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'crnd_wsd_field_service/static/js/request_fields_tour.js',
        ],
    },

    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'price': 30.0,
    'currency': 'EUR',
}
