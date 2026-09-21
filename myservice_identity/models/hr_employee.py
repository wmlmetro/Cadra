from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── SAP / NRS Identity fields ──
    ir_number = fields.Char(
        string='IR Number',
        index=True,
        copy=False,
        help='NRS/FIRS unique staff identifier from SAP SuccessFactors',
    )
    sap_user_id = fields.Char(string='SAP User ID', copy=False)
    sap_status = fields.Selection([
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('on_leave', 'On Leave'),
        ('transferred', 'Transferred'),
        ('exited', 'Exited'),
    ], string='SAP Status', default='active', tracking=True)
    sap_last_sync = fields.Datetime(string='Last SAP Sync', readonly=True)
    sap_sync_status = fields.Selection([
        ('synced', 'Synced'),
        ('pending', 'Pending'),
        ('error', 'Sync Error'),
        ('never', 'Never Synced'),
    ], string='Sync Status', default='never')

    # ── NRS organisational fields ──
    grade_level = fields.Char(string='Grade Level', help='e.g. GL 14, GL 15')
    cost_centre = fields.Char(string='Cost Centre')
    sap_department = fields.Char(string='SAP Department')
    sap_location_id = fields.Many2one(
        'generic.location',
        string='Office Location',
        help='NRS office location from SAP assignment',
    )
    sap_manager_ir = fields.Char(
        string='Manager IR Number',
        help='IR number of direct manager from SAP',
    )
    employment_start_date = fields.Date(string='Employment Start Date')
    employment_end_date = fields.Date(string='Employment End Date')

    # ── Asset summary (computed) ──
    nrs_asset_ids = fields.One2many(
        'nrs.asset', 'custodian_id', string='Assigned Assets',
    )
    # Odoo 19: fields sharing a compute method must agree on both compute_sudo
    # AND store. asset_count is non-stored and has_pending_retrieval is stored,
    # so they need distinct compute methods.
    asset_count = fields.Integer(
        string='Assets', compute='_compute_asset_count',
    )
    has_pending_retrieval = fields.Boolean(
        string='Assets Pending Retrieval',
        compute='_compute_has_pending_retrieval',
        store=True,
    )

    @api.depends('nrs_asset_ids')
    def _compute_asset_count(self):
        for emp in self:
            emp.asset_count = len(emp.nrs_asset_ids)

    @api.depends('nrs_asset_ids', 'nrs_asset_ids.retrieval_flag',
                 'nrs_asset_ids.state')
    def _compute_has_pending_retrieval(self):
        # A DISPOSED asset is not outstanding (handoff 31 §C4). It left the
        # estate; there is nothing to hand back. And since handoff 30 it
        # could never be cleared either: *Mark retrieved* clears the
        # custodian, which the register refuses on a disposed asset — so an
        # asset flagged and THEN disposed would have held a leaver's
        # clearance open for ever.
        for emp in self:
            emp.has_pending_retrieval = any(
                a.retrieval_flag and a.state != 'disposed'
                for a in emp.nrs_asset_ids
            )

    @api.constrains('ir_number')
    def _check_ir_number_unique(self):
        for emp in self:
            if emp.ir_number:
                duplicate = self.search([
                    ('ir_number', '=', emp.ir_number),
                    ('id', '!=', emp.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        'IR Number %s is already assigned to %s.'
                        % (emp.ir_number, duplicate.name)
                    )

    def action_view_assets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assets — %s' % self.name,
            'res_model': 'nrs.asset',
            'view_mode': 'list,form',
            'domain': [('custodian_id', '=', self.id)],
            'context': {'default_custodian_id': self.id},
        }

    def action_flag_retrieval(self):
        """Flag all assets for retrieval when employee exits."""
        # Not the disposed ones — see `_compute_has_pending_retrieval`.
        assets = self.nrs_asset_ids.filtered(
            lambda a: not a.retrieval_flag and a.state != 'disposed')
        assets.write({
            'retrieval_flag': True,
            'retrieval_reason': 'employee_exit',
        })
        self.message_post(
            body='%d asset(s) flagged for retrieval due to employment exit.'
            % len(assets)
        )

    def action_sap_sync_single(self):
        """Queue a manual SAP sync for this employee."""
        self.ensure_one()
        self.env['nrs.sap.sync.log'].create({
            'employee_id': self.id,
            'ir_number': self.ir_number or '',
            'sync_type': 'manual',
            'status': 'pending',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'SAP Sync',
                'message': 'Sync queued for %s (%s)' % (self.name, self.ir_number),
                'type': 'info',
            },
        }
