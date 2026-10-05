{
    'name': 'Cadra API (v1)',
    'version': '19.0.3.25.0',
    'summary': 'Cadra API-first layer (JWT, PRD envelope, idempotency, auto OpenAPI)',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Technical',
    'depends': [
        'web',
        'base',
        'website',
        # `cadra.test.fixture.mixin` (models/test_fixture.py) adds a stored
        # column to `mail.message`, `res.partner`, `hr.employee` and
        # `hr.department`. Inheriting a model whose module is only a
        # TRANSITIVE dependency lets the graph order the column apart from
        # the code that reads it, which is the failure `asset_custody.py`
        # documents. Named explicitly.
        'mail',
        'hr',
        # models/invitation.py overrides `res.users._action_reset_password`
        # and `_get_signup_invitation_scope`, which auth_signup defines.
        # Transitive through website → portal today; named so the graph
        # cannot order the override before the method it overrides.
        'auth_signup',
        # API wrappers touch these models via env lookups
        'myservice_dashboard',
        'myservice_security',
        'myservice_barcode_station',
        'myservice_fleet_maintenance',
        'myservice_fm_dashboard',
        'myservice_asset_register',
        'myservice_asset_depreciation',
        'myservice_website_theme',
        'myservice_identity',
        'myservice_workflow',
        'myservice_request_core',
        'generic_location',
    ],
    'data': [
        # BEFORE ir.model.access.csv: that file may reference a group by
        # xmlid, and a cold install resolves data files in listed order.
        'security/api_groups.xml',
        'security/ir.model.access.csv',
        'data/api_refresh_token_cron.xml',
        # Handoff 43: the invitation and the password-reset letters, in the
        # tenant's brand (models/invitation.py renders them).
        'data/mail_templates.xml',
        'views/api_client_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
