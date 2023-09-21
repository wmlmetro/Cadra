# flake8: noqa: E501
{
    'name': 'Website Service Desk',
    'category': 'Service Desk',
    'summary': 'Website UI for Service Desk',
    'author': "Center of Research and Development",
    'website': "https://crnd.pro",
    'license': 'OPL-1',
    'version': '15.0.1.121.0',

    'depends': [
        'mail',
        'website',
        'website_mail',
        'crnd_service_desk',
    ],
    'data': [
        'security/security.xml',
        'templates/templates.xml',
        'templates/templates_request_page.xml',
        'templates/templates_request_new_page.xml',
        'templates/priority_templates.xml',
        'views/request_type_view.xml',
        'views/request_stage_route.xml',
        'views/request_classifier_view.xml',
        'views/request_kind.xml',
        'views/request_request.xml',
        'views/res_config_settings.xml',
        'data/website_data.xml',
        'data/request_type_incident.xml',
    ],
    'demo': [
        'demo/demo_res_users.xml',
        'demo/demo_category.xml',
        'demo/request_kind.xml',
        'demo/demo_generic_type.xml',
        'demo/demo_upgrade_type.xml',
        'demo/generic_service.xml',
        'demo/demo_request_type_seq.xml',
        'demo/demo_bug_report_type.xml',
        'demo/request_subrequests.xml',
        'demo/demo_type_no_service.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'crnd_wsd/static/lib/trumbowyg/dist/trumbowyg.min.js',
            'crnd_wsd/static/lib/trumbowyg/dist/langs/ua.min.js',
            'crnd_wsd/static/lib/trumbowyg/dist/langs/ru.min.js',
            'crnd_wsd/static/lib/trumbowyg/dist/plugins/table/trumbowyg.table.min.js',
            'crnd_wsd/static/lib/trumbowyg/dist/plugins/colors/trumbowyg.colors.min.js',
            'crnd_wsd/static/lib/trumbowyg/dist/ui/trumbowyg.min.css',
            'crnd_wsd/static/lib/trumbowyg/dist/plugins/table/ui/trumbowyg.table.min.css',
            'crnd_wsd/static/lib/trumbowyg/dist/plugins/colors/ui/trumbowyg.colors.min.css',

            'crnd_wsd/static/src/js/*',
            'crnd_wsd/static/src/scss/*',
        ],
        'web.assets_tests': [
            'crnd_wsd/static/src/js/tours/*',
        ],
        'web.assets_qweb': [
            'crnd_wsd/static/src/xml/templates.xml',
        ],
    },

    'images': ['static/description/banner.gif'],
    'installable': True,
    'auto_install': False,
}
