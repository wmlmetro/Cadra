from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class NRSAssetPM(models.Model):
    _name = 'nrs.asset.pm'
    _description = 'Asset Preventive Maintenance Schedule'
    _inherit = ['mail.thread']
    _order = 'next_due_date'

    name = fields.Char('PM Schedule Name', required=True)
    asset_id = fields.Many2one('nrs.asset', string='Asset', required=True, ondelete='cascade')
    active = fields.Boolean(default=True)

    interval_days = fields.Integer(
        'Interval (days)', required=True, default=90,
        help='How often this PM should be performed in days')
    last_done_date = fields.Date('Last Done')
    next_due_date = fields.Date(
        'Next Due', compute='_compute_next_due', store=True)
    is_overdue = fields.Boolean(
        'Overdue', compute='_compute_next_due', store=True)

    # Request type to create when PM is due
    request_type_id = fields.Many2one(
        'request.type', string='Request Type',
        help='Type of service request to auto-create when PM is due')
    team_id = fields.Many2one('generic.team', string='Assigned Team')
    service_id = fields.Many2one('generic.service', string='Service')

    auto_create = fields.Boolean(
        'Auto-Create Request', default=True,
        help='Automatically create a service request when this PM becomes due')
    advance_days = fields.Integer(
        'Advance Notice (days)', default=7,
        help='Create the request this many days before the due date')

    last_request_id = fields.Many2one(
        'request.request', string='Last Request Created')
    notes = fields.Text('Notes')

    @api.depends('last_done_date', 'interval_days')
    def _compute_next_due(self):
        today = date.today()
        for r in self:
            if r.last_done_date and r.interval_days:
                r.next_due_date = r.last_done_date + timedelta(days=r.interval_days)
            elif r.interval_days:
                r.next_due_date = today
            else:
                r.next_due_date = False
            r.is_overdue = bool(r.next_due_date and r.next_due_date < today)

    def action_mark_done(self):
        self.write({'last_done_date': date.today()})
        self.message_post(body=_('PM marked as completed on %s') % date.today())

    @api.model
    def _cron_create_pm_requests(self):
        """Daily cron — create service requests for PMs due within advance_days."""
        today = date.today()
        schedules = self.search([
            ('active', '=', True),
            ('auto_create', '=', True),
            ('next_due_date', '!=', False),
        ])
        created = 0
        for sched in schedules:
            trigger_date = sched.next_due_date - timedelta(days=sched.advance_days or 0)
            if today < trigger_date:
                continue
            # Check if a request was already created for this cycle
            if sched.last_request_id:
                req = sched.last_request_id
                if req.stage_id.name not in ['Resolved', 'Closed']:
                    continue  # existing open request — skip
            if not sched.request_type_id:
                continue
            # Create the PM request
            asset = sched.asset_id
            name = 'PM — %s — %s' % (asset.name, sched.name)
            try:
                req = self.env['request.request'].create({
                    'type_id':             sched.request_type_id.id,
                    'stage_id':            sched.request_type_id.start_stage_id.id,
                    'name':                name,
                    'request_text':        name,
                    'team_id':             sched.team_id.id if sched.team_id else False,
                    'service_id':          sched.service_id.id if sched.service_id else False,
                    'generic_location_id': asset.location_id.id if asset.location_id else False,
                    'deadline_date':       sched.next_due_date,
                    'nrs_asset_id':        asset.id,
                })
                sched.write({'last_request_id': req.id})
                created += 1
            except Exception as e:
                self.env.cr.rollback()
        _logger = __import__('logging').getLogger(__name__)
        _logger.info('NRS Asset PM cron: created %d PM requests', created)
        return True


class RequestRequestAsset(models.Model):
    """Extend request.request to link to NRS asset."""
    _inherit = 'request.request'

    nrs_asset_id = fields.Many2one(
        'nrs.asset', string='Related Asset', tracking=True,
        help='The NRS asset this request relates to')
    asset_code = fields.Char(
        related='nrs_asset_id.asset_code', string='Asset Code', store=True)
