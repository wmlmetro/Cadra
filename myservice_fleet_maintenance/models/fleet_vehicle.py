from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import config
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    # ── Location & Assignment ─────────────────────────────────────────
    home_location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Home Location',
        index=True,
        tracking=True,
        help='FIRS office or facility where this vehicle is based.',
    )
    driver_id = fields.Many2one(
        comodel_name='res.partner',
        string='Assigned Driver',
        index=True,
        tracking=True,
    )
    fleet_manager_id = fields.Many2one(
        comodel_name='res.users',
        string='Fleet Manager',
        tracking=True,
        help='User responsible for this vehicle. Receives maintenance alerts.',
    )
    preferred_vendor_id = fields.Many2one(
        comodel_name='fleet.service.vendor',
        string='Preferred Service Vendor',
        tracking=True,
    )

    # ── Maintenance Schedule ──────────────────────────────────────────
    last_service_date = fields.Date(
        string='Last Service Date',
        tracking=True,
    )
    last_service_odometer = fields.Float(
        string='Odometer at Last Service (km)',
        digits=(10, 1),
        tracking=True,
    )
    service_interval_days = fields.Integer(
        string='Service Interval (Days)',
        default=90,
        help='Calendar-based service interval e.g. 90 = every 3 months.',
    )
    service_interval_km = fields.Float(
        string='Service Interval (km)',
        default=5000,
        digits=(10, 1),
        help='Mileage-based service interval e.g. 5000km.',
    )
    alert_before_days = fields.Integer(
        string='Alert Lead Time (Days)',
        default=7,
        help='Send alert this many days before service is due.',
    )
    alert_before_km = fields.Float(
        string='Alert Lead Distance (km)',
        default=500,
        digits=(10, 1),
        help='Send alert when this many km remain before service is due.',
    )

    # ── Manual override ───────────────────────────────────────────────
    manual_next_service_date = fields.Date(
        string='Manual Next Service Date',
        tracking=True,
        help='Override computed next service date if needed.',
    )

    # ── Computed fields ───────────────────────────────────────────────
    next_service_date = fields.Date(
        string='Next Service Date',
        compute='_compute_next_service',
        store=True,
    )
    next_service_odometer = fields.Float(
        string='Next Service Odometer (km)',
        compute='_compute_next_service',
        store=True,
        digits=(10, 1),
    )
    maintenance_status = fields.Selection(
        selection=[
            ('ok',        'OK'),
            ('due_soon',  'Due Soon'),
            ('overdue',   'Overdue'),
            ('no_schedule', 'No Schedule'),
        ],
        string='Maintenance Status',
        compute='_compute_maintenance_status',
        store=True,
    )
    open_maintenance_ticket_count = fields.Integer(
        string='Open Maintenance Tickets',
        compute='_compute_open_ticket_count',
    )

    @api.depends('last_service_date', 'last_service_odometer',
                 'service_interval_days', 'service_interval_km',
                 'manual_next_service_date')
    def _compute_next_service(self):
        for rec in self:
            if rec.manual_next_service_date:
                rec.next_service_date = rec.manual_next_service_date
            elif rec.last_service_date and rec.service_interval_days:
                rec.next_service_date = (
                    rec.last_service_date +
                    timedelta(days=rec.service_interval_days)
                )
            else:
                rec.next_service_date = False

            if rec.last_service_odometer and rec.service_interval_km:
                rec.next_service_odometer = (
                    rec.last_service_odometer + rec.service_interval_km
                )
            else:
                rec.next_service_odometer = 0.0

    @api.depends('next_service_date', 'next_service_odometer',
                 'alert_before_days', 'alert_before_km')
    def _compute_maintenance_status(self):
        """Nothing in the @api.depends above moves when the calendar does, so
        the stored value goes wrong on the day next_service_date passes and
        stays wrong. _cron_refresh_maintenance_status is what corrects it."""
        today = date.today()
        for rec in self:
            if not rec.next_service_date and not rec.next_service_odometer:
                rec.maintenance_status = 'no_schedule'
                continue

            overdue = False
            due_soon = False

            if rec.next_service_date:
                if today > rec.next_service_date:
                    overdue = True
                elif today >= rec.next_service_date - timedelta(days=rec.alert_before_days):
                    due_soon = True

            # Odometer check — use last logged odometer from fleet
            current_odo = rec._get_last_odometer()
            if rec.next_service_odometer and current_odo:
                if current_odo >= rec.next_service_odometer:
                    overdue = True
                elif current_odo >= rec.next_service_odometer - rec.alert_before_km:
                    due_soon = True

            if overdue:
                rec.maintenance_status = 'overdue'
            elif due_soon:
                rec.maintenance_status = 'due_soon'
            else:
                rec.maintenance_status = 'ok'

    def _get_last_odometer(self):
        """Get the last odometer reading for this vehicle."""
        self.ensure_one()
        odometer = self.env['fleet.vehicle.odometer'].search(
            [('vehicle_id', '=', self.id)],
            order='date desc, id desc',
            limit=1,
        )
        return odometer.value if odometer else 0.0

    def _compute_open_ticket_count(self):
        for rec in self:
            tickets = self.env['request.request'].search_count([
                ('vehicle_id', '=', rec.id),
                ('stage_id.closed', '=', False),
            ])
            rec.open_maintenance_ticket_count = tickets

    def action_view_maintenance_tickets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Maintenance Tickets',
            'res_model': 'request.request',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
        }

    # ── Cron: refresh the stored maintenance status ───────────────────
    @api.model
    def _cron_refresh_maintenance_status(self, batch_size=2000):
        """Daily refresh of maintenance_status.

        The status is a stored compute that reads today's date, while its
        @api.depends names only the schedule fields — so a vehicle whose
        service date passes keeps whatever value it was last given, and no
        write to any vehicle will ever correct it. It is not merely a missing
        flag: it is a wrong enum value on a published field, serialised as
        data.maintenance_status by GET /api/v1/fleet/vehicles and counted by
        the fleet dashboard's OK / Due Soon / Overdue tiles.

        Archived vehicles are refreshed too. The column is wrong the moment
        one is unarchived, and there is no saving in skipping them.
        """
        vehicles = self.with_context(active_test=False).search([])
        field = self._fields['maintenance_status']
        # Registry.in_test_mode() was removed in Odoo 19; the config flag is
        # what's left to distinguish a test run.
        in_test = bool(config.get('test_enable') or config.get('test_file'))
        for index in range(0, len(vehicles), batch_size):
            batch = vehicles[index:index + batch_size]
            # Read the current value first. A recomputed field is only written
            # when the new value differs from what is in cache, and "not in
            # cache" counts as different — without this the daily sweep would
            # UPDATE every vehicle row and bump every write_date to say
            # nothing changed.
            batch.fetch(['maintenance_status'])
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
            "Fleet Maintenance Cron: refreshed maintenance_status on %d "
            "vehicle(s)", len(vehicles))
        return len(vehicles)

    # ── Cron: check and create maintenance tickets ────────────────────
    @api.model
    def _cron_check_preventive_maintenance(self):
        """
        Daily cron job:
        1. Find vehicles with maintenance due or due soon
        2. Skip if open maintenance ticket already exists
        3. Create ITSM ticket
        4. Send email to driver, fleet manager, vendor
        """
        _logger.info("Fleet Maintenance Cron: checking vehicles...")

        vehicles = self.search([('active', '=', True)])
        tickets_created = 0

        for vehicle in vehicles:
            if vehicle.maintenance_status not in ('due_soon', 'overdue'):
                continue

            # Check if open ticket already exists
            existing = self.env['request.request'].search([
                ('vehicle_id', '=', vehicle.id),
                ('stage_id.closed', '=', False),
                ('category_id.name', 'ilike', 'Preventive Maintenance'),
            ], limit=1)

            if existing:
                _logger.info(
                    "Vehicle %s already has open maintenance ticket #%s — skipping",
                    vehicle.name, existing.name
                )
                continue

            # Create the ticket
            ticket = vehicle._create_maintenance_ticket()
            if ticket:
                vehicle._send_maintenance_alerts(ticket)
                tickets_created += 1

        _logger.info(
            "Fleet Maintenance Cron: %d ticket(s) created", tickets_created)

    def _create_maintenance_ticket(self):
        """Create a preventive maintenance ITSM ticket for this vehicle."""
        self.ensure_one()

        # Find Preventive Maintenance category
        category = self.env['request.category'].search(
            [('name', 'ilike', 'Preventive Maintenance')], limit=1)

        # Find Vehicle Maintenance service
        service = self.env['generic.service'].search(
            [('name', 'ilike', 'Vehicle Maintenance')], limit=1)

        # Find a valid type under that category/service
        req_type = self.env['request.type'].search(
            [('name', 'ilike', 'Scheduled vehicle service')], limit=1)
        if not req_type:
            req_type = self.env['request.type'].search([], limit=1)

        # Assign to fleet manager
        assignee = self.fleet_manager_id or self.env.ref('base.user_admin')

        status_label = dict(self._fields['maintenance_status'].selection).get(
            self.maintenance_status, 'Due')

        ticket_vals = {
            'name': f'Preventive Maintenance — {self.name} [{self.license_plate or self.vin_sn or "—"}]',
            'request_text': (
                f'<p>Scheduled preventive maintenance is <strong>{status_label}</strong> '
                f'for vehicle <strong>{self.name}</strong> '
                f'(Plate: {self.license_plate or "N/A"}, '
                f'Chassis: {self.vin_sn or "N/A"}).</p>'
                f'<ul>'
                f'<li>Next Service Date: {self.next_service_date or "Not set"}</li>'
                f'<li>Next Service Odometer: {self.next_service_odometer or 0:,.0f} km</li>'
                f'<li>Last Service Date: {self.last_service_date or "Not recorded"}</li>'
                f'<li>Preferred Vendor: {self.preferred_vendor_id.name if self.preferred_vendor_id else "Not assigned"}</li>'
                f'</ul>'
                f'<p>Please schedule and complete this service, then close this ticket '
                f'with the service date and odometer reading.</p>'
            ),
            'vehicle_id': self.id,
            'user_id': assignee.id,
            'type_id': req_type.id if req_type else False,
        }

        if category:
            ticket_vals['category_id'] = category.id
        if service:
            ticket_vals['service_id'] = service.id
        if self.home_location_id:
            ticket_vals['generic_location_id'] = self.home_location_id.id

        try:
            ticket = self.env['request.request'].sudo().create(ticket_vals)
            _logger.info(
                "Created maintenance ticket %s for vehicle %s",
                ticket.name, self.name
            )
            return ticket
        except Exception as e:
            _logger.error(
                "Failed to create maintenance ticket for vehicle %s: %s",
                self.name, str(e)
            )
            return False

    def _send_maintenance_alerts(self, ticket):
        """Send email alerts to driver, fleet manager and vendor."""
        self.ensure_one()
        template = self.env.ref(
            'myservice_fleet_maintenance.email_template_maintenance_alert',
            raise_if_not_found=False,
        )
        if not template:
            return

        recipients = []

        # Driver
        if self.driver_id and self.driver_id.email:
            recipients.append(self.driver_id.email)

        # Fleet manager
        if self.fleet_manager_id and self.fleet_manager_id.email:
            recipients.append(self.fleet_manager_id.email)

        # Preferred vendor
        if self.preferred_vendor_id and self.preferred_vendor_id.email:
            recipients.append(self.preferred_vendor_id.email)

        if recipients:
            template.with_context(
                email_to=','.join(set(recipients)),
                vehicle=self,
                ticket=ticket,
            ).send_mail(ticket.id, force_send=True)

    def action_log_service_complete(self):
        """Wizard-style button to log service completion directly from vehicle form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Log Service Completion',
            'res_model': 'fleet.vehicle.log.services',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vehicle_id': self.id,
                'default_date': fields.Date.today(),
            },
        }
