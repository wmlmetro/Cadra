import logging

from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)


SLA_HOURS = {
    'critical': 0.5,
    'high': 2,
    'standard': 4,
    'low': 24,
}


class RequestRequestTriage(models.Model):
    _inherit = 'request.request'

    # ── Triage fields ──
    triage_note = fields.Text('Internal Triage Note')
    assigned_team_id = fields.Many2one(
        'generic.team', string='Assigned Team', tracking=True,
    )
    sla_tier = fields.Selection([
        ('critical', 'Critical — 30 min'),
        ('high', 'High — 2 hours'),
        ('standard', 'Standard — 4 hours'),
        ('low', 'Low — 1 day'),
    ], string='SLA Tier', default='standard')
    sla_deadline = fields.Datetime(
        'SLA Deadline', compute='_compute_sla_deadline', store=True,
    )
    sla_breached = fields.Boolean(
        'SLA Breached', compute='_compute_sla_breached', store=True,
    )
    intake_channel = fields.Selection([
        ('portal', 'Web Portal'),
        ('whatsapp', 'WhatsApp'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('walkin', 'Walk-in'),
    ], string='Intake Channel', default='portal')

    # ── Technician work fields ──
    work_log = fields.Text('Work Log')
    parts_used = fields.Char('Parts / Materials Used')
    time_spent_mins = fields.Integer('Time Spent (minutes)')
    resolution_note = fields.Text('Resolution Note')

    # ── Reporter fields (for phone/walk-in intake) ──
    reporter_name = fields.Char('Reporter Name')
    reporter_contact = fields.Char('Reporter Contact')

    # ── Priority shortcut (maps to existing priority field) ──
    priority_display = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], string='Display Priority', default='1')

    @api.depends('create_date', 'sla_tier')
    def _compute_sla_deadline(self):
        for rec in self:
            if rec.create_date and rec.sla_tier:
                hours = SLA_HOURS.get(rec.sla_tier, 4)
                rec.sla_deadline = rec.create_date + timedelta(hours=hours)
            else:
                rec.sla_deadline = False

    @api.depends('sla_deadline')
    def _compute_sla_breached(self):
        # The body reads the clock; the dependency list cannot. Nothing in the
        # database changes on the minute a request breaches, so this compute is
        # never re-run on its own — _cron_refresh_sla_breached is what makes it
        # true. Do not remove that cron on the strength of this @api.depends.
        now = fields.Datetime.now()
        for rec in self:
            rec.sla_breached = bool(rec.sla_deadline and rec.sla_deadline < now)

    # ── Cron ──────────────────────────────────────────────────────────

    @api.model
    def _cron_refresh_sla_breached(self, batch_size=2000):
        """Flip the requests that have run past their deadline since last time.

        Domain: rows that hold False and have a deadline at all.

        The clock only moves forward and a deadline never moves backwards by
        itself, so the only transition time can cause is False -> True. Every
        input-driven transition — the tier changed, the deadline cleared — is
        already handled by ``@api.depends('sla_deadline')`` at the moment the
        input is written. So a row already True has nothing to gain from a
        visit, and excluding it makes each run's set "requests currently inside
        their SLA window" rather than "every request ever raised": the work
        stops growing with the register's history instead of tracking it.
        """
        # active_test=False for the same reason asset_pm and fleet_vehicle do
        # it: request.request carries an `active` flag, so a bare search hides
        # archived rows, and an archived request that is later restored would
        # carry a flag last computed on the day it was archived — which is the
        # staleness this method exists to end, in a smaller box.
        requests = self.with_context(active_test=False).search([
            ('sla_deadline', '!=', False),
            ('sla_breached', '=', False),
        ])
        field = self._fields['sla_breached']
        # Registry.in_test_mode() was removed in Odoo 19; the config flag is
        # what's left to distinguish a test run.
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        flipped = 0
        for i in range(0, len(requests), batch_size):
            batch = requests[i:i + batch_size]
            # Prefetch so an unchanged row is not rewritten. `_write_multi`
            # stamps write_uid/write_date even on the compute-flush path, so a
            # sweep that touches rows needlessly would relabel requests as last
            # modified by OdooBot when nothing about them changed.
            batch.fetch(['sla_breached'])
            # Mark the FIELD rather than the dependency it is computed from.
            # This cron exists because no dependency covers the clock; routing
            # it through the graph would make it a no-op the day someone edits
            # @api.depends.
            self.env.add_to_compute(field, batch)
            # Flush per batch, or the batching is decorative: every id would
            # sit pending until the transaction's own flush at commit, which is
            # the one thing the batches exist to avoid. Under test nothing
            # commits, so without this nothing reaches the database at all and
            # a test could only ever observe the cache.
            self.env.flush_all()
            flipped += len(batch.filtered('sla_breached'))
            # Commit per batch so a long run over a large register doesn't hold
            # one transaction open — but never inside a test, where committing
            # breaks the surrounding rollback.
            if not in_test:
                self.env.cr.commit()
        if flipped:
            _logger.info(
                'SLA refresh: %d of %d unbreached requests are now past their '
                'deadline', flipped, len(requests))
        return flipped

    def action_assign_and_notify(self):
        self.ensure_one()
        if not self.user_id:
            raise UserError('Please select a technician before assigning.')
        sla_label = dict(self._fields['sla_tier'].selection).get(self.sla_tier, '')
        team_name = self.assigned_team_id.name if self.assigned_team_id else '—'
        self.message_post(
            body='Request assigned to %s (Team: %s). SLA: %s. Note: %s'
                 % (self.user_id.name, team_name, sla_label,
                    self.triage_note or 'None'),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def action_mark_resolved(self):
        self.ensure_one()
        if not self.work_log:
            raise UserError('Please enter a work log before marking as resolved.')
        self.message_post(
            body='Resolved by %s.\nWork done: %s\nParts: %s\nTime: %d min\n'
                 'Resolution: %s'
                 % (self.env.user.name, self.work_log,
                    self.parts_used or 'None', self.time_spent_mins or 0,
                    self.resolution_note or ''),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        closed_stage = self.env['request.stage'].search(
            [('closed', '=', True)], limit=1, order='sequence',
        )
        if closed_stage:
            self.stage_id = closed_stage
