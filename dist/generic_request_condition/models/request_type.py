from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    change_request_text_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_request_text_cond_rel',
        'type_id', 'condition_id', string='Can change request text')
    change_assignee_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_assignee_cond_rel',
        'type_id', 'condition_id', string='Can change assignee')
    change_category_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_category_cond_rel',
        'type_id', 'condition_id', string='Can change category')
    change_deadline_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_deadline_cond_rel',
        'type_id', 'condition_id', string='Can change deadline')
    change_author_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_author_cond_rel',
        'type_id', 'condition_id', string='Can change author')
    change_service_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_service_cond_rel',
        'type_id', 'condition_id', string='Can change service')
