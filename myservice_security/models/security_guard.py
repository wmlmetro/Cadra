import logging

from odoo import models, fields, api
from odoo.tools import config

_logger = logging.getLogger(__name__)


class SecurityGuard(models.Model):
    _name = 'security.guard'
    _description = 'Security Guard'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(string='Full Name', required=True, tracking=True)
    badge_number = fields.Char(
        string='Badge Number', required=True, copy=False, tracking=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Contact Record', required=True)
    photo = fields.Binary(related='partner_id.image_128', string='Photo')
    phone = fields.Char(related='partner_id.phone', store=True)
    email = fields.Char(related='partner_id.email', store=True)

    home_location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Base Location',
        tracking=True,
    )
    specialisation = fields.Selection(
        selection=[
            ('access',   'Access Control'),
            ('patrol',   'Patrol'),
            ('cctv',     'CCTV Monitoring'),
            ('response', 'Emergency Response'),
            ('dog',      'K9 / Dog Handler'),
            ('all',      'General'),
        ],
        string='Specialisation',
        default='all',
        tracking=True,
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Security Company / Vendor',
        domain=[('is_company', '=', True)],
    )
    contract_start = fields.Date(string='Contract Start')
    contract_end   = fields.Date(string='Contract End')
    is_active = fields.Boolean(string='Active', default=True, tracking=True)
    notes = fields.Text(string='Notes')

    # The inverse of security.duty.roster.guard_id. It exists so the duty
    # computes below can declare a dependency on the roster: a compute that
    # searches a model it does not depend on can never be told that model
    # changed, which is how on_duty came to be computed once, at creation,
    # when no roster existed, and never again.
    duty_roster_ids = fields.One2many(
        comodel_name='security.duty.roster',
        inverse_name='guard_id',
        string='Duty Roster',
    )

    # Computed
    duty_count = fields.Integer(
        string='Duty Records',
        compute='_compute_duty_count',
    )
    active_duty_id = fields.Many2one(
        comodel_name='security.duty.roster',
        string='Current Duty',
        compute='_compute_active_duty_id',
    )
    on_duty = fields.Boolean(
        string='On Duty',
        compute='_compute_on_duty',
        store=True,
    )

    @api.depends('duty_roster_ids')
    def _compute_duty_count(self):
        for rec in self:
            rec.duty_count = len(rec.duty_roster_ids)

    def _duty_on(self, on_date):
        """Return {record id: roster} for the duty that puts each guard on
        station on ``on_date`` — the roster row for that date whose status the
        gate house has moved to 'active'.

        Saved guards are resolved with one search over that date; unsaved ones
        (an onchange in a form) can only be resolved from the in-memory
        one2many, because their roster rows are not in the database yet.
        """
        saved = self.filtered(lambda g: isinstance(g.id, int))
        result = {}
        if saved:
            rosters = self.env['security.duty.roster'].search([
                ('guard_id', 'in', saved.ids),
                ('date', '=', on_date),
                ('status', '=', 'active'),
            ])
            for roster in rosters:
                result.setdefault(roster.guard_id.id, roster)
        for rec in self - saved:
            result[rec.id] = rec.duty_roster_ids.filtered(
                lambda r: r.date == on_date and r.status == 'active')[:1]
        return result

    @api.depends('duty_roster_ids.date', 'duty_roster_ids.status')
    def _compute_active_duty_id(self):
        duty = self._duty_on(fields.Date.today())
        for rec in self:
            rec.active_duty_id = duty.get(rec.id) or False

    @api.depends('duty_roster_ids.date', 'duty_roster_ids.status')
    def _compute_on_duty(self):
        # Deliberately NOT sharing a compute method with active_duty_id.
        # Field.compute_value protects and un-marks every field a compute
        # method writes, so one method feeding a stored and a non-stored field
        # means reading the non-stored one consumes the stored one's pending
        # recompute and writes the column back as a side effect of a read —
        # under Odoo 19 that lands inside the readonly cursor that serves
        # read()/search_read().
        duty = self._duty_on(fields.Date.today())
        for rec in self:
            rec.on_duty = bool(duty.get(rec.id))

    @api.model
    def _cron_refresh_on_duty(self, batch_size=1000):
        """Daily refresh of on_duty.

        A duty roster covers one date, so on_duty stops being true at midnight
        without anything writing to the guard or to the roster. @api.depends
        covers a roster being added, rescheduled, checked in or cancelled;
        nothing covers the calendar turning over, and on_duty is stored — it
        backs the 'Guards on Duty' count on the security dashboard and
        GET /api/v1/security/kpis, both of which read the column.
        """
        guards = self.search([])
        field = self._fields['on_duty']
        # Registry.in_test_mode() was removed in Odoo 19; the config flag is
        # what's left to distinguish a test run.
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        for index in range(0, len(guards), batch_size):
            batch = guards[index:index + batch_size]
            # Read the current value first. A recomputed field is only written
            # when the new value differs from what is in cache, and "not in
            # cache" counts as different — without this the daily sweep would
            # UPDATE every guard row and bump every write_date to say nothing
            # changed.
            batch.fetch(['on_duty'])
            # Mark the field itself rather than one it depends on. This cron
            # exists precisely because no dependency covers the clock, so
            # routing the refresh through the dependency graph would make it a
            # no-op the day someone edits @api.depends.
            self.env.add_to_compute(field, batch)
            # Flush per batch so the batching is real, and so the column moves
            # under test, where nothing commits and therefore nothing flushes.
            self.env.flush_all()
            if not in_test:
                self.env.cr.commit()
        _logger.info(
            "Security: refreshed on_duty on %d guard(s)", len(guards))
        return len(guards)

    def action_view_duties(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duty Roster',
            'res_model': 'security.duty.roster',
            'view_mode': 'list,form',
            'domain': [('guard_id', '=', self.id)],
        }
