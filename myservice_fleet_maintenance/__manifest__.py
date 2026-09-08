{
    'name': 'myservice Fleet Maintenance',
    'version': '19.0.2.2.0',
    'summary': 'Fleet Command Center dashboard, preventive maintenance alerts, vendor registry and auto ITSM ticket creation',
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Fleet',
    'depends': [
        'fleet',
        'myservice_request_core',
        'generic_location',
        'myservice_request_fields',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/mail_templates.xml',
        'views/fleet_service_vendor_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        # RETIRED (handoff 11, R54). fleet_dashboard.js registered the client
        # action `myservice_fleet_dashboard`, and NOTHING dispatches to it:
        # there is no ir.actions.client record carrying that tag anywhere in
        # the repo, and both menuitems in views/menu.xml are active="0". So it
        # was downloaded, parsed and registered into the actions registry on
        # every backend page load in every app, for a screen that has no way
        # to be opened. Verified in a browser on jaizbankplc: the tag is in
        # the registry and no route reaches it.
        #
        # It is also the one legacy dashboard whose module does not depend on
        # myservice_nrs_base, which is what provides the web.AbstractAction /
        # web.rpc shim it requires — it only ever loaded because
        # myservice_dashboard happened to drag nrs_base in.
        #
        # The code stays. See docs/retired-screens.md for what reviving it
        # would take. Note that it loads Leaflet from
        # /myservice_security/static/lib/leaflet/ — a cross-module URL nothing
        # declares — so that directory must not be deleted either.
        'web.assets_backend': [],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
