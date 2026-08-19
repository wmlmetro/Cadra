from odoo import models, api, _
from odoo.exceptions import ValidationError

from .depreciation_engine import (
    METHOD_ERP_MANAGED,
    PRORATION_DAILY,
    PRORATION_WHOLE_MONTH,
    PRORATION_SELECTION,
)

#: Tenant-wide depreciation configuration, held in ir.config_parameter.
#
# Deliberately NOT a res.config.settings screen: these are edited from the Cadra
# SPA over the API, not from the Odoo backend, and a config-parameter key is the
# lightest thing that survives module upgrades. Tenancy is database-per-tenant,
# so a parameter IS per-tenant.
PARAM_MODE = 'cadra.depreciation.mode'
PARAM_PRORATION = 'cadra.depreciation.proration'
PARAM_DB_SWITCH = 'cadra.depreciation.declining_switches_to_straight_line'
PARAM_LAST_RUN = 'cadra.depreciation.last_recompute'

#: Who owns book values for this tenant — PRD §8.6's two operating modes.
MODE_COMPUTED = 'computed'
MODE_ERP_MANAGED = 'erp_managed'

MODE_SELECTION = [
    (MODE_COMPUTED, 'Cadra-computed'),
    (MODE_ERP_MANAGED, 'ERP-managed'),
]

DEFAULTS = {
    PARAM_MODE: MODE_COMPUTED,
    PARAM_PRORATION: PRORATION_WHOLE_MONTH,
    # On by default: pure declining balance leaves a final write-down that can
    # be 79x the preceding charge, which no accountant would book.
    PARAM_DB_SWITCH: '1',
}


class DepreciationSettings(models.AbstractModel):
    """Read/write helper for the tenant's depreciation configuration.

    An AbstractModel rather than a stored one — there is exactly one
    configuration per database and ir.config_parameter already stores it.
    """
    _name = 'cadra.depreciation.settings'
    _description = 'Cadra Depreciation Settings'

    # ── Read ──────────────────────────────────────────────────

    @api.model
    def _param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(
            key, DEFAULTS.get(key))

    @api.model
    def get_settings(self):
        """Everything the settings screen needs, in one call."""
        Asset = self.env['nrs.asset']
        mode = self._param(PARAM_MODE)
        return {
            'mode': mode,
            'proration': self._param(PARAM_PRORATION),
            'declining_switches_to_straight_line':
                self._param(PARAM_DB_SWITCH) in ('1', 'True', 'true', True),
            'last_recompute': self._param(PARAM_LAST_RUN) or None,
            # The counts that tell you whether the figures mean anything.
            'data_quality': {
                'needs_start_date': Asset.search_count(
                    [('depreciation_method', 'in',
                      ['straight_line', 'declining_balance']),
                     ('depreciation_start_is_estimated', '=', True)]),
                'missing_cost': Asset.search_count(
                    [('depreciation_method', 'in',
                      ['straight_line', 'declining_balance']),
                     ('depreciable_cost', '<=', 0)]),
                'not_configured': Asset.search_count(
                    [('depreciation_method', '=', 'none')]),
            },
        }

    @api.model
    def engine_options(self):
        """Convention kwargs for depreciation_engine.build_schedule/value_at."""
        return {
            'switch_to_straight_line':
                self._param(PARAM_DB_SWITCH) in ('1', 'True', 'true', True),
            'proration': self._param(PARAM_PRORATION),
        }

    # ── Write ─────────────────────────────────────────────────

    @api.model
    def set_settings(self, vals):
        """Apply a partial update and recompute, since every one of these
        changes restates book values across the whole register."""
        ICP = self.env['ir.config_parameter'].sudo()
        touched = False

        if 'mode' in vals:
            mode = vals['mode']
            if mode not in dict(MODE_SELECTION):
                raise ValidationError(_('Unknown mode "%s".') % mode)
            ICP.set_param(PARAM_MODE, mode)
            touched = True

        if 'proration' in vals:
            proration = vals['proration']
            if proration not in dict(PRORATION_SELECTION):
                raise ValidationError(_('Unknown proration "%s".') % proration)
            ICP.set_param(PARAM_PRORATION, proration)
            touched = True

        if 'declining_switches_to_straight_line' in vals:
            ICP.set_param(
                PARAM_DB_SWITCH,
                '1' if vals['declining_switches_to_straight_line'] else '0')
            touched = True

        if touched:
            self.env['nrs.asset']._cron_recompute_depreciation()
        return self.get_settings()

    @api.model
    def action_recompute(self):
        """Recompute every asset's book value on demand."""
        count = self.env['nrs.asset']._cron_recompute_depreciation()
        return {'recomputed': count, **self.get_settings()}
