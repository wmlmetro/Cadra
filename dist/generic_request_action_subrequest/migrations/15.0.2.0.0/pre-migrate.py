from odoo.tools.sql import (
    column_exists,
    create_column,
)
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


@ensure_version('2.0.0')
def migrate(cr, installed_version):
    if column_exists(cr, "request_event_action", "subrequest_template_id"):
        # Data seems to be already migrated
        return

    create_column(cr, 'request_event_action', 'subrequest_template_id', 'int4')
    cr.execute("""
        SELECT id, name, subrequest_type_id, subrequest_category_id
        FROM request_event_action
        WHERE act_type = 'subrequest';
    """)
    for aid, name, type_id, categ_id in cr.fetchall():
        cr.execute("""
            INSERT INTO request_creation_template
                   (name, request_type_id, request_category_id, active)
            VALUES (%s, %s, %s, true)
            RETURNING id;
        """, (
            "Template for action %s" % name,
            type_id,
            categ_id,
        ))
        tmpl_id = cr.fetchone()[0]
        cr.execute("""
            UPDATE request_event_action
            SET subrequest_template_id = %s
            WHERE id = %s;
        """, (tmpl_id, aid))
