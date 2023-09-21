{
    'name': "Generic Request Service Condition [Obsolete]",

    'summary': (
        "The functionality of this module was merged "
        "into the 'generic_request_condition' module, "
        "thus this module could be safely removed."),

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Service',
    'version': '15.0.0.8.0',

    # any module necessary for this one to work correctly
    'depends': [
        'generic_request_condition',
    ],

    # always loaded
    'data': [],
    'demo': [],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'tags': ['obsolete'],
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'EUR',
}
