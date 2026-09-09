from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .asset_custody import CUSTODY_REASON_KEY, CUSTODY_SOURCE_KEY


class NRSAssetTransfer(models.Model):
    _name = 'nrs.asset.transfer'
    _description = 'Asset Transfer / Movement'
    _inherit = ['mail.thread']
    _order = 'transfer_date desc'

    name = fields.Char('Reference', required=True, copy=False,
                        default=lambda self: _('New'))
    asset_id = fields.Many2one('nrs.asset', string='Asset', required=True, ondelete='cascade')
    asset_code = fields.Char(related='asset_id.asset_code', store=True)

    from_location_id = fields.Many2one('generic.location', string='From Location', required=True)
    to_location_id = fields.Many2one('generic.location', string='To Location', required=True)

    from_custodian_id = fields.Many2one('hr.employee', string='From Custodian')
    to_custodian_id = fields.Many2one('hr.employee', string='To Custodian')

    transfer_date = fields.Date('Transfer Date', required=True, default=fields.Date.today)
    reason = fields.Text('Reason for Transfer')

    state = fields.Selection([
        ('draft',    'Draft'),
        ('approved', 'Approved'),
        ('done',     'Completed'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    approved_by = fields.Many2one('res.users', string='Approved By')
    approved_date = fields.Datetime('Approved Date')
    notes = fields.Text('Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('nrs.asset.transfer') or '/'
        return super().create(vals_list)

    @api.constrains('from_location_id', 'to_location_id')
    def _check_locations(self):
        for r in self:
            if r.from_location_id == r.to_location_id:
                raise ValidationError(_('From and To locations must be different.'))

    def action_approve(self):
        for r in self:
            r.write({
                'state': 'approved',
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
            })

    def action_complete(self):
        for r in self:
            # Update asset location and custodian
            vals = {'location_id': r.to_location_id.id, 'state': 'active'}
            if r.to_custodian_id:
                vals['custodian_id'] = r.to_custodian_id.id
            # `nrs.asset.write` records the chain of custody for whoever
            # writes `custodian_id`. Declaring the source here is what stops
            # a completed transfer reading as an anonymous direct edit.
            r.asset_id.with_context(
                **{CUSTODY_SOURCE_KEY: 'transfer',
                   CUSTODY_REASON_KEY: r.reason or False},
            ).write(vals)
            r.write({'state': 'done'})
            r.message_post(body=_(
                'Asset transferred from %s to %s') % (
                r.from_location_id.name, r.to_location_id.name))

    def action_reject(self):
        self.write({'state': 'rejected'})
