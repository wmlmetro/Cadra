from odoo import models, exceptions, _


class RequestClassifier(models.Model):
    _inherit = 'request.classifier'

    def unlink(self):
        # In case when user tries to remove classifier that defines relations
        # with certain service or category that is used in request fields,
        # and there no more classifiers to reference such service
        # and categories for this type, then raise error.
        # TODO: May be it have sense to search for possible classifiers that
        #       allow to select certain field instead.
        types_to_check = self.mapped('type_id')
        res = super().unlink()
        for rec in types_to_check:
            type_request_categ = rec.classifier_ids.mapped('category_id')
            type_request_service = rec.classifier_ids.mapped('service_id')
            fields_categ = rec.mapped('field_ids.category_ids')
            fields_service = rec.mapped('field_ids.service_ids')
            if not fields_categ <= type_request_categ:
                excepted_category = (
                    fields_categ - type_request_categ
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "There are no classifiers defined for request type "
                    "%(request_type)s for request categories (%(categories)s) "
                    "that are used in fields of this request type."
                ) % {
                    'categories': excepted_category,
                    'request_type': rec.name,
                })

            if not fields_service <= type_request_service:
                excepted_services = (
                    fields_service - type_request_service
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "There are no classifiers defined for request type "
                    "%(request_type)s for request services (%(services)s) "
                    "that are used in fields of this request type."
                ) % {
                    'services': excepted_services,
                    'request_type': rec.name,
                })
        return res
