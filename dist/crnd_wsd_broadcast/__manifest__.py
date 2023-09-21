{
    'name': 'Website Service Desk (Broadcast messages)',
    'category': 'Service Desk',
    'summary': 'Website Service Desk Broadcast',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.10.1',
    'depends': [
        'crnd_wsd',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/broadcast_message.xml',
        'templates/templates.xml',
    ],
    'demo': [
    ],
    'images': ['static/description/banner.png'],
    'price': 10.0,
    'currency': 'EUR',
    'installable': True,
    'auto_install': False,
}
