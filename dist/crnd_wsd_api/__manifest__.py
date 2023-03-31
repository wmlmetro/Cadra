{
    'name': 'Website Service Desk API',
    'category': 'Service Desk',
    'summary': """
        Allows API to redirect to Request Page on Service Desk.
    """,
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.1.0',
    'depends': [
        'crnd_wsd',
        'generic_request_api',
    ],
    'data': [
    ],
    'demo': [
    ],
    'qweb': ['static/src/xml/*.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
}
