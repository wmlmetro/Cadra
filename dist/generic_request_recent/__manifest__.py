{
    'name': "Generic Request Recent",

    'summary': """
        Creates separate page on request form to show all related by author or
        partner requests for latest 7 days (period can be configured).
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Request',
    'version': '15.0.0.6.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request',
        ],

    # always loaded
    'data': [
        'views/res_config_settings_view.xml',
        'views/request_request_view_form.xml',
        'data/ir_config_parameter.xml',
        ],
    'demo': [
        ],
    'images': ['static/description/banner.png'],
    'qweb': [
    ],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
