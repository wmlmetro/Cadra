from odoo import fields, models


class GenericResourceSimpleCategory(models.Model):
    _name = 'generic.resource.simple.category'
    _inherit = [
        'mail.thread',
        'generic.mixin.parent.names',
    ]
    _description = 'Generic Resource Simple Category'

    _parent_name = 'parent_id'
    _parent_order = 'name'
    _parent_store = True

    name = fields.Char(index=True, required=True, translate=True)
    active = fields.Boolean(default=True, index=True)
    parent_id = fields.Many2one(
        'generic.resource.simple.category', 'Parent Category',
        index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)

    # Ported forward from the 15.0 copy in dist/, where `_sql_constraints`
    # was still honoured. Odoo 19 removed it (orm/model_classes.py logs
    # "no longer supported" and creates nothing), so this constraint had
    # silently ceased to exist. crnd-19/ is loaded only by the Odoo 19
    # config, so no version guard is needed here — unlike our own modules,
    # which the 15 stack still loads.
    _category_unique = models.Constraint(
        'UNIQUE(parent_id, name)',
        'Category can not have subcategories with the same name!',
    )
