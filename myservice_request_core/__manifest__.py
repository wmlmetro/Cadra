{
    'name': 'NRS Request Core',
    'version': '19.0.1.0.0',
    'summary': 'In-house service request engine — CRND-free replacement for generic_request',
    'description': """
NRS Request Core
================
Provides the ``request.request`` model (plus stages, routes, types, categories,
tags and events) as fully in-house, CRND-independent code. Drop-in replacement
for the proprietary (OPL-1) ``generic_request`` addon: keeps the same model
names so the existing myservice_* extensions and the /api/v1 request serializer
work unchanged, with no commercial dependency.
""",
    'category': 'Services/Request',
    'author': 'WestMetro Limited',
    'website': 'https://myservice.com.ng',
    'depends': [
        'mail',
        'generic_service',
        'generic_team',
        'generic_location',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/request_sequence.xml',
        'data/request_stage_data.xml',
        'views/request_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
