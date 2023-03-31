import logging
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version

_logger = logging.getLogger(__name__)


@ensure_version('3.0.0')
def migrate(cr, installed_version):
    cr.execute("""
        INSERT INTO request_stage_route_trigger__event_type__rel
               (trigger_id, event_type_id)
        SELECT r.request_stage_route_trigger_id, et.new_system_event_type_id
        FROM request_event_type_request_stage_route_trigger_rel AS r
        LEFT JOIN request_event_type AS et ON et.id = r.request_event_type_id
    """)
