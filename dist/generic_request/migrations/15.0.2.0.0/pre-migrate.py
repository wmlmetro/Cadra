import logging

from odoo.tools.sql import column_exists, create_column
from odoo.addons.generic_mixin.tools.migration_utils import ensure_version
from odoo.addons.generic_mixin.tools.xmlid import (
    xmlid_to_id,
    get_xmlid,
    register_xmlid,
    update_xmlid,
)
from odoo.addons.generic_mixin.tools.sql import unlink_view

_logger = logging.getLogger(__name__)


# Mapping for event categories:
#    old_categ_xml_id -> new_categ_xmlid
event_category_mapping = {
    ('generic_request', 'event_category_request_events'): (
        'generic_request', 'system_event_category_request_events'),
    ('generic_request', 'event_category_subrequest_events'): (
        'generic_request', 'system_event_category_request_sub_request_events'),
    ('generic_request', 'event_category_parent_request_events'): (
        'generic_request',
        'system_event_category_request_parent_request_events'),
    ('crnd_wsd_appointment', 'event_category_request_appointment'): (
        'crnd_wsd_appointment', 'system_event_category_request_appointment'),
    ('generic_request_project', 'event_category_project_task_events'): (
        'generic_request_project',
        'system_event_category_request_project_task_events'),
    ('generic_request_web_conference', 'event_category_bbb_events'): (
        'generic_request_web_conference', 'system_event_category_bbb_events'),
}

# Mapping for event types that are replaced by defaults
# from generic.system.event
#    old_type_xml_id -> new_type_xml_id
event_type_replacements = {
    ('generic_request', 'request_event_type_created'): (
        'generic_system_event', 'system_event_record_created'),
    ('generic_request_mail', 'request_event_mail_comment'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_comment'),
    ('generic_request_mail', 'request_event_mail_note'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_note'),
    ('generic_request_mail', 'request_event_mail_activity_new'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_activity_new'),
    ('generic_request_mail', 'request_event_mail_activity_done'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_activity_done'),
    ('generic_request_mail', 'request_event_mail_activity_delete'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_activity_delete'),
    ('generic_request_mail', 'request_event_mail_activity_changed'): (
        'generic_system_event_mail_events',
        'generic_system_event_type_mail_activity_changed'),
}

event_type_renames = {
    ('generic_request_action_todo',
     'request_event_type_request_all_todo_completed'): (
        'generic_request_todo', 'request_event_type__all_todo_completed'),
}


def create_event_source(cr):
    cr.execute("""
        SELECT request_event_live_time,
               request_event_live_time_uom,
               request_event_auto_remove
        FROM res_company
        WHERE id = (SELECT company_id FROM res_users WHERE id = 1);
    """)
    event_live_time, event_live_time_uom, event_auto_vacuum = cr.fetchone()
    cr.execute("""
        INSERT INTO generic_system_event_source
               (model_id, event_data_model_id,
                vacuum_time, vacuum_time_uom, vacuum_enable)
        VALUES (%(model_id)s, %(event_data_model_id)s,
                %(vacuum_time)s, %(vacuum_time_uom)s, %(vacuum_enable)s)
        RETURNING id;
    """, {
        'model_id': xmlid_to_id(cr, 'generic_request.model_request_request'),
        'event_data_model_id': xmlid_to_id(
            cr, 'generic_request.model_request_event'),
        'vacuum_time': event_live_time,
        'vacuum_time_uom': event_live_time_uom,
        'vacuum_enable': event_auto_vacuum,
    })
    event_source_id = cr.fetchone()[0]

    # Register xmlid for event source
    register_xmlid(
        cr,
        module='generic_request',
        name='system_event_source__request_request',
        model='generic.system.event.source',
        res_id=event_source_id,
    )

    return event_source_id


def migrate_categories(cr, event_source_id):
    """ Migrate already existing requerst event categories
    """
    migrated_category_mapping = {}
    cr.execute("""
        SELECT id, name, code FROM request_event_category;
    """)
    for cid, name, code in cr.fetchall():
        xml_module, xml_name = get_xmlid(
            cr, 'request.event.category', cid)
        new_xml_module, new_xml_name = event_category_mapping.get(
            (xml_module, xml_name),
            (False, False))
        cr.execute("""
            INSERT INTO generic_system_event_category
                   (event_source_id, name, code)
            VALUES (%s, %s, %s)
            RETURNING id;
        """, (event_source_id, name, code))
        new_cid = cr.fetchone()[0]
        if new_xml_name and new_xml_module:
            register_xmlid(
                cr,
                module=new_xml_module,
                name=new_xml_name,
                model='generic.system.event.category',
                res_id=new_cid,
            )
        else:
            _logger.warning(
                "Request event category %s.%s [%d] is not mentioned "
                "in migration mapping. Thus it will be migrated with xmlid.")

        migrated_category_mapping[cid] = new_cid

    return migrated_category_mapping


def migrate_event_types(cr, event_source_id, category_mapping):
    """ Migrate already existing requerst event categories
    """
    migrated_event_type_mapping = {}
    create_column(
        cr, 'request_event_type', 'new_system_event_type_id', 'INTEGER',
        comment='Keep reference to migrated event type')
    cr.execute("""
        SELECT id, name, code, category_id FROM request_event_type;
    """)
    for tid, name, code, category_id in cr.fetchall():
        xml_module, xml_name = get_xmlid(
            cr, 'request.event.type', tid)
        replace_xml_module, replace_xml_name = event_type_replacements.get(
            (xml_module, xml_name),
            (False, False))
        new_tid = xmlid_to_id(
            cr, '%s.%s' % (replace_xml_module, replace_xml_name))
        if replace_xml_module and replace_xml_name and new_tid:
            migrated_event_type_mapping[tid] = new_tid
            _logger.info(
                "Replacing request event type %s.%s with default %s.%s...",
                xml_module, xml_name, replace_xml_module, replace_xml_name)
            cr.execute("""
                UPDATE request_event_type
                SET new_system_event_type_id = %(new_tid)s
                WHERE id = %(tid)s
            """, {
                'new_tid': new_tid,
                'tid': tid,
            })
            # If we have to replace this type by already existing one,
            # then no other operations needed. Lets go to next iteration.
            continue

        cr.execute("""
            INSERT INTO generic_system_event_type
                   (name, code, event_category_id, event_source_id,
                    event_source_model_id, event_source_model_name,
                    event_data_model_id, event_data_model_name)
            VALUES (%(name)s, %(code)s, %(event_category_id)s,
                    %(event_source_id)s, %(event_source_model_id)s,
                    %(event_source_model_name)s, %(event_data_model_id)s,
                    %(event_data_model_name)s)
            RETURNING id;
        """, {
            'name': name,
            'code': code,
            'event_category_id': category_mapping[category_id],
            'event_source_id': event_source_id,
            'event_source_model_id': xmlid_to_id(
                cr, 'generic_request.model_request_request'),
            'event_source_model_name': 'request.request',
            'event_data_model_id': xmlid_to_id(
                cr, 'generic_request.model_request_event'),
            'event_data_model_name': 'request.event',
        })
        new_tid = cr.fetchone()[0]
        migrated_event_type_mapping[tid] = new_tid
        cr.execute("""
            UPDATE request_event_type
            SET new_system_event_type_id = %(new_tid)s
            WHERE id = %(tid)s
        """, {
            'new_tid': new_tid,
            'tid': tid,
        })
        if replace_xml_module and replace_xml_name:
            # In this case, this event is implement by some module fron
            # generic_system_event family, but it is not installed yet.
            # Thus, we have to register new xmlid for this event type
            # at this moment, because module will be installed later as
            # dependency of other modules.
            register_xmlid(
                cr,
                module=replace_xml_module,
                name=replace_xml_name,
                model='generic.system.event.type',
                res_id=new_tid)
        elif (xml_module, xml_name) in event_type_renames:
            new_module, new_name = event_type_renames[(xml_module, xml_name)]
            _logger.warning(
                "Renaming XMLID %s.%s to %s.%s",
                xml_module, xml_name, new_module, new_name)
            cr.execute("""
                UPDATE ir_model_data
                SET module=%(new_module)s,
                    name=%(new_name)s,
                    model=%(model)s,
                    res_id=%(res_id)s
                WHERE module=%(old_module)s
                  AND name=%(old_name)s;
            """, {
                'new_module': new_module,
                'new_name': new_name,
                'old_module': xml_module,
                'old_name': xml_name,
                'model': 'generic.system.event.type',
                'res_id': new_tid,
            })
        else:
            # If there is no replacement registered for this event type,
            # then we have to update existing xml_id to point to new
            # generic system event type.
            update_xmlid(
                cr, xml_module, xml_name,
                model='generic.system.event.type',
                res_id=new_tid)

    return migrated_event_type_mapping


def migrate_events(cr, event_source_id, event_type_map):
    cr.execute("""
        SELECT id, event_type_id, request_id, date, user_id
        FROM request_event
    """)
    for re_id, event_type_id, request_id, event_date, user_id in cr.fetchall():
        cr.execute("""
            INSERT INTO generic_system_event
                   (event_date, event_type_id, event_source_id,
                    event_source_record_id, event_data_id, user_id)
            VALUES (%(event_date)s, %(event_type_id)s, %(event_source_id)s,
                    %(event_source_record_id)s, %(event_data_id)s, %(user_id)s)
            RETURNING id;
        """, {
            'event_date': event_date,
            'event_type_id': event_type_map[event_type_id],
            'event_source_id': event_source_id,
            'event_source_record_id': request_id,
            'event_data_id': re_id,
            'user_id': user_id,
        })
        event_id = cr.fetchone()[0]
        cr.execute("""
            UPDATE request_event
            SET event_id = %(event_id)s
            WHERE id = %(request_event_id)s;
        """, {
            'event_id': event_id,
            'request_event_id': re_id,
        })


@ensure_version('2.0.0')
def migrate(cr, installed_version):
    if column_exists(cr, 'request_event', 'event_id'):
        return

    # Fix migration of generic_system_event_mail_events,
    # because this migration will be running before migration of that module
    cr.execute("""
        UPDATE ir_model_data
        SET name = 'generic_system_event_type_mail_comment'
        WHERE module = 'generic_system_event_mail_events'
          AND name = 'generic_system_event_mail_comment';
    """)

    create_column(cr, 'request_event', 'event_id', 'INT')

    event_source_id = create_event_source(cr)
    event_category_map = migrate_categories(cr, event_source_id)
    event_type_map = migrate_event_types(
        cr, event_source_id, event_category_map)
    migrate_events(cr, event_source_id, event_type_map)

    # Delete view from mail, to avoid possible conflicts during update
    unlink_view(cr, 'generic_request_mail.request_event_mail_view_form')
