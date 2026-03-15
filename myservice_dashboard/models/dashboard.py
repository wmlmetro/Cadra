from odoo import models, api
from datetime import date, timedelta


class MyServiceDashboard(models.AbstractModel):
    _name = 'myservice.dashboard'
    _description = 'myservice Operations Dashboard'

    @api.model
    def get_kpis(self):
        Vehicle = self.env['fleet.vehicle']
        Location = self.env['generic.location']
        Request = self.env['request.request']

        # Fleet KPIs
        total_vehicles = Vehicle.search_count([])
        maintenance_overdue = Vehicle.search_count([
            ('maintenance_status', '=', 'overdue')])
        maintenance_due_soon = Vehicle.search_count([
            ('maintenance_status', '=', 'due_soon')])
        maintenance_ok = Vehicle.search_count([
            ('maintenance_status', '=', 'ok')])
        no_schedule = Vehicle.search_count([
            ('maintenance_status', '=', 'no_schedule')])

        # Location KPIs
        total_locations = Location.search_count([])
        locations_with_coords = Location.search_count([
            ('latitude', '!=', 0.0),
            ('longitude', '!=', 0.0),
        ])

        # Request KPIs
        total_open = Request.search_count([
            ('stage_id.closed', '=', False)])
        maintenance_tickets = Request.search_count([
            ('is_maintenance_ticket', '=', True),
            ('stage_id.closed', '=', False),
        ])
        total_requests_today = Request.search_count([
            ('date_created', '>=', date.today().strftime('%Y-%m-%d')),
        ])

        # Vendor KPIs
        try:
            total_vendors = self.env['fleet.service.vendor'].search_count([])
            approved_vendors = self.env['fleet.service.vendor'].search_count([
                ('is_approved', '=', True)])
        except Exception:
            total_vendors = 0
            approved_vendors = 0

        return {
            'fleet': {
                'total': total_vehicles,
                'overdue': maintenance_overdue,
                'due_soon': maintenance_due_soon,
                'ok': maintenance_ok,
                'no_schedule': no_schedule,
            },
            'locations': {
                'total': total_locations,
                'mapped': locations_with_coords,
            },
            'requests': {
                'open': total_open,
                'maintenance': maintenance_tickets,
                'today': total_requests_today,
            },
            'vendors': {
                'total': total_vendors,
                'approved': approved_vendors,
            },
        }

    @api.model
    def get_map_data(self):
        """Return fleet and location data for the map."""

        # ── Locations ─────────────────────────────────────────────────
        locations = self.env['generic.location'].search([
            ('latitude', '!=', 0.0),
            ('longitude', '!=', 0.0),
        ])
        location_data = []
        for loc in locations:
            # Count open requests for this location
            req_count = self.env['request.request'].search_count([
                ('generic_location_id', '=', loc.id),
                ('stage_id.closed', '=', False),
            ])
            location_data.append({
                'id': loc.id,
                'name': loc.name,
                'lat': loc.latitude,
                'lng': loc.longitude,
                'state': loc.state_name or '',
                'type': 'location',
                'open_requests': req_count,
                'model': 'generic.location',
            })

        # ── Fleet vehicles (use home_location coords) ─────────────────
        vehicles = self.env['fleet.vehicle'].search([
            ('home_location_id', '!=', False),
        ])
        fleet_data = []
        seen_locations = {}

        for v in vehicles:
            loc = v.home_location_id
            if not loc.latitude or not loc.longitude:
                continue

            # Slightly offset vehicles at same location
            key = loc.id
            offset = seen_locations.get(key, 0)
            seen_locations[key] = offset + 1

            import math
            angle = offset * (360 / max(seen_locations.get(key, 1), 1))
            radius = 0.008 * (1 + offset // 8)
            lat = loc.latitude + radius * math.cos(math.radians(angle))
            lng = loc.longitude + radius * math.sin(math.radians(angle))

            fleet_data.append({
                'id': v.id,
                'name': v.name,
                'plate': v.license_plate or '',
                'lat': lat,
                'lng': lng,
                'status': v.maintenance_status or 'no_schedule',
                'driver': v.driver_id.name if v.driver_id else '',
                'location': loc.name,
                'state': loc.state_name or '',
                'type': 'vehicle',
                'model': 'fleet.vehicle',
            })

        # ── Recent open requests ──────────────────────────────────────
        recent = self.env['request.request'].search([
            ('stage_id.closed', '=', False),
        ], order='date_created desc', limit=10)

        recent_data = []
        for r in recent:
            recent_data.append({
                'id': r.id,
                'name': r.name,
                'service': r.service_id.name if r.service_id else '',
                'category': r.category_id.name if r.category_id else '',
                'location': r.generic_location_id.name if r.generic_location_id else '',
                'stage': r.stage_id.name if r.stage_id else '',
                'date': r.date_created.strftime('%d %b %Y') if r.date_created else '',
                'is_maintenance': r.is_maintenance_ticket,
            })

        return {
            'locations': location_data,
            'fleet': fleet_data,
            'recent_requests': recent_data,
        }
