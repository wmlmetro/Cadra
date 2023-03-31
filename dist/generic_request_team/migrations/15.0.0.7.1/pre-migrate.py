def migrate(cr, installed_version):
    # Delete buggy views, they will be automatically recreated after update
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE module = 'generic_request_team'
              AND model = 'ir.ui.view'
              AND name IN (
                'view_request_request_searchpanel',
                'view_request_team_request_request_search'
              )
        );
        DELETE FROM ir_model_data
        WHERE module = 'generic_request_team'
          AND model = 'ir.ui.view'
          AND name IN (
            'view_request_request_searchpanel',
            'view_request_team_request_request_search'
          );
    """)
