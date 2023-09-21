{
    'name': "Generic team tag",

    'summary': """
        With this module you can create tags for teams and team members.
    """,

    'author': "Center of Research and Development",
    'website': "https://crnd.pro",

    'category': 'Generic Team',
    'version': '15.0.0.4.1',

    "depends": [
        'generic_tag',
        'generic_team',
    ],

    "data": [
        'data/tags.xml',
        'views/generic_team_menu.xml',
        'views/generic_team_view.xml',
        'views/generic_team_member_view.xml',
        'views/res_users.xml',
    ],

    "demo": [
        'demo/generic_team_tag_category.xml',
        'demo/generic_team_tag.xml',
    ],
    'images': ['static/description/banner.png'],
    "installable": True,
    "application": False,
    'license': 'OPL-1',
    'price': 10.0,
    'currency': 'EUR',
}
