from odoo.addons.generic_mixin.tools.migration_utils import ensure_version


def migrate_website_published_data(cr):
    cr.execute("""
        SELECT
            rclass.id,
            rclass.type_id,
            rclass.category_id,
            rclass.service_id,
            rt.website_published AS t_web_published,
            rc.website_published AS c_web_published,
            rs.website_published AS s_web_published,
            ARRAY(
                SELECT website_id
                FROM request_type_website_rel AS rtw
                WHERE rtw.request_type_id = rclass.type_id
            ) AS type_website_ids,
            ARRAY(
                SELECT website_id
                FROM request_category_website_rel AS rcw
                WHERE rcw.request_category_id = rclass.category_id
            ) AS category_website_ids,
            ARRAY(
                SELECT website_id
                FROM generic_service_website_rel AS rsw
                WHERE rsw.generic_service_id = rclass.service_id
            ) AS service_website_ids
        FROM request_classifier AS rclass
        LEFT JOIN request_type AS rt ON rt.id = rclass.type_id
        LEFT JOIN request_category AS rc ON rc.id = rclass.category_id
        LEFT JOIN generic_service AS rs ON rs.id = rclass.service_id
        WHERE NOT EXISTS (
            -- Do not update records that has xml-ids
            SELECT 1
            FROM ir_model_data
            WHERE model = 'request.classifier'
              AND res_id = rclass.id
        );
    """)

    for (
        rc_id,
        type_id, category_id, service_id,
        t_web_published, c_web_published, s_web_published,
        t_website_ids, c_website_ids, s_website_ids,
    ) in cr.fetchall():
        website_published = bool(t_web_published)
        if category_id:
            # If category defined, then use its value to update
            # website_published of classifier
            website_published = website_published and c_web_published
        if service_id:
            # If service defined, then use its value to update
            # website_published of classifier
            website_published = website_published and s_web_published

        website_ids = set()
        if t_website_ids or c_website_ids or s_website_ids:
            # If at least one component is bound to websites, then
            # classifiers must be bound to websites too
            website_ids = set(t_website_ids + c_website_ids + s_website_ids)
            if t_website_ids:
                # If we have websites in type, then we have to restrict
                # visibility of classifier to websites mentioned in type
                website_ids &= set(t_website_ids)
            if c_website_ids:
                # If we have websites in category, then we have to restrict
                # visibility of classifier to websites mentioned in category
                website_ids &= set(c_website_ids)
            if s_website_ids:
                # If we have websites in service, then we have to restrict
                # visibility of classifier to websites mentioned in service
                website_ids &= set(s_website_ids)
            if not website_ids:
                # service, category and type do not have common websites,
                # thus, this classifier must not be published on website
                website_published = False

        # Set website published to computed value
        cr.execute("""
            UPDATE request_classifier
            SET website_published = %(website_published)s
            WHERE id = %(id)s;
        """, {
            'id': rc_id,
            'website_published': website_published,
        })

        # Update relation of classifiers with websites
        for website_id in website_ids:
            cr.execute("""
                INSERT INTO request_classifier_website_rel
                       (request_classifier_id, website_id)
                VALUES (%(request_classifier_id)s, %(website_id)s)
            """, {
                'request_classifier_id': rc_id,
                'website_id': website_id,
            })


@ensure_version('1.113.0')
def migrate(cr, installed_version):
    migrate_website_published_data(cr)
