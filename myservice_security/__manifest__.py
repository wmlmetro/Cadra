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
    'assets': {
        'web.assets_backend': [
            # RETIRED (handoff 11, R54). security.css styles only the
            # .ms-soc-* classes in the retired security_dashboard.xml, and
            # security_tabs.css only the .nrs-* classes in security_tabs.xml.
            # Neither template is in any bundle and neither has a client
            # action, so 521 lines of CSS were shipping to every backend page
            # in every app to style markup that is never rendered.
            # See docs/retired-screens.md before reviving either.
            #
            # security_navbar.css is NOT retired and is deliberately still
            # here: despite its name and its own header comment it scopes to
            # nothing — it targets core `.o_main_navbar` / `.o_menu_sections`
            # / `.dropdown-menu` and restyles the top navbar of every backend
            # screen for every user. Removing it is a visible global change
            # (nav labels lose the condensed uppercase treatment and the
            # active-tab underline; menu dropdowns revert from dark to the
            # theme default), which is a design decision, not a retirement.
            'myservice_security/static/src/css/security_navbar.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
