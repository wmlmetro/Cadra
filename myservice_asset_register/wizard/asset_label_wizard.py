from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AssetLabelWizard(models.TransientModel):
    _name = 'nrs.asset.label.wizard'
    _description = 'Print Asset Barcode Labels'

    label_size = fields.Selection([
        ('small', 'Small (50 x 25 mm)'),
        ('medium', 'Medium (70 x 40 mm)'),
        ('large', 'Large (100 x 60 mm)'),
        ('a4_sheet', 'A4 Sheet (8 per page)'),
    ], string='Label Size', required=True, default='medium')

    copies = fields.Integer('Copies', default=1, required=True)
    asset_ids = fields.Many2many('nrs.asset', string='Assets')

    @api.constrains('copies')
    def _check_copies(self):
        for r in self:
            if r.copies < 1 or r.copies > 10:
                raise ValidationError(_('Copies must be between 1 and 10.'))

    def action_print(self):
        self.ensure_one()
        # Collect active tags for selected assets
        tags = self.asset_ids.mapped('active_tag_id').filtered(lambda t: t.id)
        if not tags:
            raise ValidationError(_('No active tags found for selected assets.'))

        # Duplicate tag recordset for copies
        if self.copies > 1:
            tag_ids = tags.ids * self.copies
            tags = self.env['nrs.asset.tag.label'].browse(tag_ids)

        # Map size to report + paper format
        size_map = {
            'small': (
                'myservice_asset_register.action_report_asset_tag_small',
                'myservice_asset_register.report_asset_tag_label_small',
            ),
            'medium': (
                'myservice_asset_register.action_report_asset_tag',
                'myservice_asset_register.report_asset_tag_label',
            ),
            'large': (
                'myservice_asset_register.action_report_asset_tag_large',
                'myservice_asset_register.report_asset_tag_label_large',
            ),
            'a4_sheet': (
                'myservice_asset_register.action_report_asset_tag_sheet',
                'myservice_asset_register.report_asset_tag_label_sheet',
            ),
        }

        action_ref, _template = size_map[self.label_size]
        report = self.env.ref(action_ref)
        return report.report_action(tags)
