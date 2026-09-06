{
    'name': 'myservice WorkSpace Integration',
    'version': '19.0.3.0.0',
    'summary': 'Bidirectional integration between myservice and NRS WorkSpace approval system',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Technical',
    'depends': [
        'web',
        'mail',
        'myservice_request_core',
        'myservice_request_fields',
        # INT-05 carries `asset.tag.affixed` out of the tag register, so
        # the transport module now knows about assets as well as requests.
        # No cycle: myservice_asset_register does not depend on this.
        'myservice_asset_register',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/workflow_stages.xml',
        'data/workflow_cron.xml',
        'views/workflow_config_views.xml',
        'views/workflow_dispatch_log_views.xml',
        'views/request_request_views.xml',
        'views/menu.xml',
        'wizard/workflow_send_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
