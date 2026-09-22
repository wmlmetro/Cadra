from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from .asset_custody import CUSTODY_REASON_KEY, CUSTODY_SOURCE_KEY
from .asset_event import EVENT_REASON_KEY, EVENT_SOURCE_KEY
from .asset_movement import (
    MOVEMENT_REASON_KEY,
    MOVEMENT_SOURCE_KEY,
    MOVEMENT_TRANSFER_KEY,
)


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
        """Approve the transfer document — and never your own.

        **This check is what makes the exemption in `action_complete` mean
        anything, and it was missing.** Handoff 35 gates every writer of
        `location_id` and `custodian_id` behind a second person, and exempts
        a completed transfer on the grounds that this document has its own
        two-person step. It did not have one: `approved_by` was stamped from
        `self.env.uid` with no self-approval check, no requester column and
        no state precondition, and `group_asset_manager` holds `1,1,1,1` on
        this model and sees the Approve button.

        So one asset manager, alone, in the Odoo interface: create a
        transfer, press Approve (stamping themselves), press Complete
        Transfer — and the asset moved with the gate skipped and no
        `nrs.asset.change.request` row anywhere. The verification pass found
        it and was right about the sequence: the fix that added the exemption
        is what opened it, because before that the completion was refused
        outright.

        `create_uid` is the requester here. This model has no `requested_by`
        column of its own — that is one of the four reasons handoff 35 did
        not reuse it as the request model — so the person who made the
        document is who the approver must not be.
        """
        for r in self:
            if r.approved_by:
                raise UserError(_(
                    "%(ref)s was already approved by %(who)s. An approval is "
                    "taken once.", ref=r.name, who=r.approved_by.display_name))
            if r.create_uid.id == self.env.uid and not self.env.su:
                raise UserError(_(
                    "%(who)s created this transfer and cannot approve it. "
                    "The point of an approval is that a second person "
                    "agrees — ask somebody else to approve it.",
                    who=self.env.user.display_name))
            r.write({
                'state': 'approved',
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
            })

    def action_complete(self):
        for r in self:
            # SECOND STATEMENT OF THE SAME RULE, and deliberately not
            # trusting the first. `approved_by` is a plain writable column on
            # this model — `group_asset_manager` holds write on it and the
            # form makes it readonly, which is a screen and not a guard — so
            # a row could carry an approver it never earned. The exemption
            # below is granted on the strength of that column, so the column
            # is checked here too rather than at the one place it is set.
            if r.approved_by and r.approved_by.id == r.create_uid.id:
                raise UserError(_(
                    "%(ref)s was created and approved by the same person, "
                    "%(who)s. Moving an asset needs a second person to "
                    "agree; ask somebody else to approve this transfer.",
                    ref=r.name, who=r.approved_by.display_name))
            # Update asset location and custodian
            vals = {'location_id': r.to_location_id.id, 'state': 'active'}
            if r.to_custodian_id:
                vals['custodian_id'] = r.to_custodian_id.id
            # `nrs.asset.write` records the chain of custody for whoever
            # writes `custodian_id`. Declaring the source here is what stops
            # a completed transfer reading as an anonymous direct edit.
            # The same for the movement record, plus the one thing only this
            # caller knows: WHICH transfer the move was the execution of.
            r.asset_id.with_context(
                # Handoff 35. A move needs a second person — and for THIS
                # writer the second person is the one who pressed Approve on
                # the transfer itself, which is what `approved_by` records.
                # Declared only when there is one: an unapproved transfer
                # completing is a move nobody agreed to, and it meets the
                # gate in `nrs.asset._write_recorded` like any other write.
                # See `approval_policy.EXEMPT_REASONS` for why the condition
                # is load-bearing rather than defensive.
                **({'cadra_approval_exempt': 'transfer'}
                   if r.approved_by else {}),
                **{CUSTODY_SOURCE_KEY: 'transfer',
                   CUSTODY_REASON_KEY: r.reason or False,
                   MOVEMENT_SOURCE_KEY: 'transfer',
                   MOVEMENT_REASON_KEY: r.reason or False,
                   MOVEMENT_TRANSFER_KEY: r.id,
                   # Completing a transfer sets the asset `active`, so it can
                   # change a status too — a missing asset that is transferred
                   # has been found. Said, so the event is not `direct`.
                   EVENT_SOURCE_KEY: 'transfer',
                   EVENT_REASON_KEY: r.reason or False},
            ).write(vals)
            r.write({'state': 'done'})
            r.message_post(body=_(
                'Asset transferred from %s to %s') % (
                r.from_location_id.name, r.to_location_id.name))

    def action_reject(self):
        self.write({'state': 'rejected'})
