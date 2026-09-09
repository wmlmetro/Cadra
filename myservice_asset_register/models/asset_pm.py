import logging
from datetime import date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import config

_logger = logging.getLogger(__name__)


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

    @api.depends('last_done_date', 'interval_days', 'create_date')
    def _compute_next_due(self):
        """One interval after the last service — or after the schedule was set up.

        A schedule with an interval and no `last_done_date` used to get
        `next_due_date = today`. That is not a due date, it is the absence of
        one: it moves forward every day, so `is_overdue` — computed in the same
        pass — can never be true, and the daily refresh cron rewrites the row
        on every tick to say nothing changed. It is the same defect handoff 09
        was written to fix (a stored value that reads the clock and therefore
        never means anything), wearing the costume of a fix.

        The anchor is `create_date`: a PM set up today with a 90-day interval
        falls due in 90 days and is overdue on day 91. The alternative — anchor
        at creation so it is due immediately — would make every newly entered
        schedule instantly overdue on the day it was typed in, which asserts
        something about the asset's service history that nobody told us.

        Latent when changed: zero `nrs.asset.pm` rows exist on any of the eight
        tenants, which is exactly what makes it safe to correct now (R29's
        reasoning, applied again).
        """
        today = date.today()
        for r in self:
            if r.interval_days:
                # `create_date` is written by the INSERT, so it is readable by
                # the time this stored compute is flushed. The fallback covers
                # an in-memory record only, and anchors it to the same instant
                # the row would have been given anyway.
                anchor = r.last_done_date or (
                    r.create_date.date() if r.create_date else today)
                r.next_due_date = anchor + timedelta(days=r.interval_days)
            else:
                r.next_due_date = False
            r.is_overdue = bool(r.next_due_date and r.next_due_date < today)

    def action_mark_done(self):
        self.write({'last_done_date': date.today()})
        self.message_post(body=_('PM marked as completed on %s') % date.today())

    @api.model
    def _cron_refresh_overdue(self, batch_size=2000):
        """Re-evaluate is_overdue against today's date.

        is_overdue is stored and depends only on last_done_date and
        interval_days, so a schedule that lapses overnight is not flagged until
        something writes to it. Nothing does — which is why the "Overdue PM
        Schedules" menu, whose whole domain is is_overdue = True, was empty on
        every tenant. Push the recompute on a schedule instead.

        The fields are marked directly and flushed per batch. Marking them
        rather than a dependency matters: this cron exists precisely because no
        dependency covers the clock, so a refresh routed through the dependency
        graph would become a no-op the day someone edits `@api.depends`.
        Batches are committed the way the depreciation cron does. The PM
        request cron below used to roll the WHOLE transaction back on one
        failure; it now takes a savepoint per schedule, so neither of them
        throws away finished work to report a single failure.
        """
        # active_test=False deliberately: an archived schedule that is
        # un-archived would otherwise carry a flag last computed on the day it
        # was archived, which is the same staleness this method exists to end.
        schedules = self.with_context(active_test=False).search(
            [('next_due_date', '!=', False)])
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        # Mark is_overdue only. next_due_date comes off the SAME compute, and
        # `Field.compute_value` un-marks every field in `pool.field_computed`,
        # so it is recomputed and written in the same pass regardless — naming
        # it here would add nothing.
        #
        # The `next_due_date = today` fallback that made a never-done schedule
        # permanently not-overdue — and made this cron dirty its row on every
        # tick — is gone (handoff 10, R45). `_compute_next_due` now anchors on
        # `create_date`, so a value written here stays put until the calendar
        # or the record actually moves.
        field = self._fields['is_overdue']
        for i in range(0, len(schedules), batch_size):
            batch = schedules[i:i + batch_size]
            # Prefetch so an unchanged row is not rewritten: a recompute writes
            # only when the value differs from cache, and absent-from-cache
            # counts as different.
            batch.fetch(['is_overdue', 'next_due_date'])
            # Mark the FIELDS themselves rather than a dependency. No
            # dependency covers the clock, which is the whole reason this cron
            # exists; going through the graph would make it a no-op the day
            # someone edits @api.depends.
            self.env.add_to_compute(field, batch)
            self.env.flush_all()
            if not in_test:
                self.env.cr.commit()
        return len(schedules)

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
        failed = 0
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
                # One savepoint per schedule, where `self.env.cr.rollback()`
                # used to be. A rollback is not schedule-scoped: it threw away
                # every PM request the run had already created — and `created`
                # is a plain integer, so the summary line below went on
                # counting them and the cron reported work that no longer
                # existed. The failed schedule now undoes itself and the ones
                # before it stand, which is what the count has always claimed.
                with self.env.cr.savepoint():
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
            except Exception:
                # catch-all: reported — creating a `request.request` runs the
                # request engine's own create hooks, its stage resolution and
                # whatever a tenant has added to the model, so the set is open.
                # It is caught rather than raised because one unbuildable
                # schedule must not stop the other tenants' PM run, and it is
                # LOGGED because the alternative is the state this cron was in:
                # a schedule whose request failed to create is indistinguishable
                # from one that was not due, on a maintenance job nobody watches
                # until an asset is missed. The failure is counted, named and
                # traced.
                failed += 1
                _logger.warning(
                    'Asset PM cron: schedule %s (%s) on asset %s — could not '
                    'create the PM request',
                    sched.id, sched.name, asset.name or asset.id,
                    exc_info=True,
                )
        if failed:
            _logger.warning(
                'Asset PM cron: created %d PM request(s), %d schedule(s) '
                'FAILED — see the tracebacks above', created, failed)
        else:
            _logger.info('Asset PM cron: created %d PM requests', created)
        return True


class RequestRequestAsset(models.Model):
    """Extend request.request to link to an asset."""
    _inherit = 'request.request'

    nrs_asset_id = fields.Many2one(
        'nrs.asset', string='Related Asset', tracking=True,
        help='The asset this request relates to')
    asset_code = fields.Char(
        related='nrs_asset_id.asset_code', string='Asset Code', store=True)
