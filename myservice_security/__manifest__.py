{
    'name': 'myservice Security & Safety',
    'version': '19.0.2.3.0',
    'summary': 'Incident management, guard ops, access control & security dashboard',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Security',
    'depends': [
        'web', 'mail', 'generic_location', 'myservice_request_core',
        'myservice_request_fields', 'website', 'myservice_nrs_base',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/incident_categories.xml',
        'data/mail_templates.xml',
        'data/ir_cron.xml',
        'views/security_incident_views.xml',
        'views/security_guard_views.xml',
        'views/security_duty_roster_views.xml',
        'views/security_access_log_views.xml',
        'views/dashboard_views.xml',
        'views/portal_templates.xml',
        'views/menu.xml',
        'wizard/incident_escalate_views.xml',
    ],
    # No assets. security.css and security_tabs.css are retired (handoff 11,
    # R54) — see docs/retired-screens.md. security_navbar.css was NOT retired
    # and is NOT deleted: it never scoped to Security at all, it restyles the
    # top navigation of every backend screen in the product, so it moved to
    # myservice_nrs_base as global_navbar.css, byte-identical and with its
    # bundle position chosen so nothing renders differently (handoff 12, C1).
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
