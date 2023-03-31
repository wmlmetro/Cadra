{
    'name': 'Website Service Desk (Resource Role)',
    'category': 'Service Desk',
    'summary': 'Integration addon to enable resource roles feature',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.2.0',
    'depends': [
        'generic_resource_role',
        'crnd_wsd_resource',
    ],
    'data': [
    ],
    'demo': [
        'demo/resource_role_link.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'price': 20.0,
    'currency': 'EUR',
}
