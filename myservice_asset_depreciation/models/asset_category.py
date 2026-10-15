from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .depreciation_engine import (
    METHOD_DECLINING_BALANCE,
    METHOD_NONE,
    METHOD_SELECTION,
    METHOD_STRAIGHT_LINE,
)


class NRSAssetCategory(models.Model):
    """Depreciation policy defaults, inherited by every asset in the category.

    Sits alongside the existing pm_interval_days — same idea: set the rule once
    per class of asset rather than on 11k individual records.
    """
    _inherit = 'nrs.asset.category'

    # ── Depreciation policy ───────────────────────────────────
    depreciation_method = fields.Selection(
        METHOD_SELECTION, string='Depreciation Method', default=METHOD_NONE,
        help='Default method for assets in this category. Assets can override it.')
    useful_life_months = fields.Integer(
        'Useful Life (months)',
        help='Expected service life used to spread the cost. 60 = five years.')
    declining_rate = fields.Float(
        'Declining Rate (%/yr)', digits=(5, 2),
        help='Annual percentage written off the remaining book value. '
             'Only used by the declining-balance method.')
    salvage_rate = fields.Float(
        'Salvage Rate (%)', digits=(5, 2), default=0.0,
        help='Residual worth at end of life, as a percentage of cost. '
             'Depreciation stops at this floor. Zero for most asset classes.')

    asset_depreciating_count = fields.Integer(
        'Depreciating Assets', compute='_compute_asset_depreciating_count')

    @api.depends('depreciation_method')
    def _compute_asset_depreciating_count(self):
        # One grouped count for the whole recordset, not one per category
        # (handoff 61, ruling 6 on report 60 — `GET /asset-categories`
        # computes it for every row). Same domain, same `_search`.
        counts = {}
        if self.ids:
            counts = {
                category.id: n for category, n in
                self.env['nrs.asset']._read_group(
                    [('category_id', 'in', self.ids),
                     ('depreciation_method', 'in',
                      [METHOD_STRAIGHT_LINE, METHOD_DECLINING_BALANCE])],
                    ['category_id'], ['__count'])}
        for r in self:
            r.asset_depreciating_count = counts.get(r.id, 0)

    @api.constrains('useful_life_months', 'declining_rate', 'salvage_rate',
                    'depreciation_method')
    def _check_depreciation_policy(self):
        for r in self:
            if r.useful_life_months < 0:
                raise ValidationError(_('Useful life cannot be negative.'))
            if not 0 <= r.salvage_rate <= 100:
                raise ValidationError(_('Salvage rate must be between 0 and 100%.'))
            if not 0 <= r.declining_rate <= 100:
                raise ValidationError(_('Declining rate must be between 0 and 100%.'))
            if r.depreciation_method == METHOD_DECLINING_BALANCE and not r.declining_rate:
                raise ValidationError(_(
                    'Category "%s" uses declining balance, so it needs an annual rate.'
                ) % r.name)
