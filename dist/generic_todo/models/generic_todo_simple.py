import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericTodoSimple(models.Model):
    _name = 'generic.todo.simple'
    _description = 'Generic Todo Simple'
    _inherit = [
        'generic.todo.mixin.implementation'
    ]

    description = fields.Html(translate=False)
