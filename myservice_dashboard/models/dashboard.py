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

    @api.model
    def get_fleet_command(self):
        """Fleet Command tab data."""
        from datetime import date, timedelta
        Vehicle = self.env['fleet.vehicle']
        today = date.today()

        # ── KPIs ──────────────────────────────────────────────────────
        total          = Vehicle.search_count([])
        overdue        = Vehicle.search_count([('maintenance_status','=','overdue')])
        due_soon       = Vehicle.search_count([('maintenance_status','=','due_soon')])
        ok             = Vehicle.search_count([('maintenance_status','=','ok')])
        no_schedule    = Vehicle.search_count([('maintenance_status','=','no_schedule')])
        with_location  = Vehicle.search_count([('home_location_id','!=',False)])
        without_loc    = total - with_location
        unassigned_drv = Vehicle.search_count([('driver_id','=',False)])

        # Idle: no maintenance log in 30 days
        since_30 = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        try:
            active_ids = self.env['fleet.vehicle.log.services'].search(
                [('date','>=',since_30)]).mapped('vehicle_id').ids
            idle = Vehicle.search_count([('id','not in',active_ids)])
        except Exception:
            idle = 0

        # ── Vendor performance ────────────────────────────────────────
        vendors = []
        try:
            for v in self.env['fleet.service.vendor'].search(
                    [('is_approved','=',True)], limit=6):
                vendors.append({
                    'id':   v.id,
                    'name': v.name,
                    'approved': v.is_approved,
                    'specialisation': v.specialisation or '',
                    'state': v.state_id.name if v.state_id else '',
                })
        except Exception:
            pass

        # ── Vehicles by location (top 10) ─────────────────────────────
        by_location = []
        loc_counts = {}
        for v in Vehicle.search([('home_location_id','!=',False)]):
            lid = v.home_location_id.id
            lname = v.home_location_id.name
            loc_counts[lid] = loc_counts.get(lid, {'name': lname, 'count': 0})
            loc_counts[lid]['count'] += 1
        top_locs = sorted(loc_counts.values(), key=lambda x: -x['count'])[:10]
        by_location = top_locs

        # ── Vehicles by make ──────────────────────────────────────────
        by_make = {}
        for v in Vehicle.search([]):
            make = v.brand_id.name if v.brand_id else 'Unknown'
            by_make[make] = by_make.get(make, 0) + 1
        by_make_list = sorted(
            [{'make': k, 'count': v} for k,v in by_make.items()],
            key=lambda x: -x['count'])[:8]

        # ── Maintenance status distribution ───────────────────────────
        by_status = [
            {'status': 'OK / Active',    'count': ok,          'color': '#28a745'},
            {'status': 'Due Soon',       'count': due_soon,    'color': '#ffc107'},
            {'status': 'Overdue',        'count': overdue,     'color': '#dc3545'},
            {'status': 'No Schedule',    'count': no_schedule, 'color': '#6c757d'},
        ]

        # ── Compliance alerts ─────────────────────────────────────────
        compliance = []
        soon_30 = (today + timedelta(days=30)).strftime('%Y-%m-%d')
        soon_14 = (today + timedelta(days=14)).strftime('%Y-%m-%d')
        today_s = today.strftime('%Y-%m-%d')
        try:
            # Insurance expiry
            ins_overdue = Vehicle.search_count([
                ('insurance_expiration_date','<', today_s)])
            ins_soon    = Vehicle.search_count([
                ('insurance_expiration_date','>=', today_s),
                ('insurance_expiration_date','<=', soon_30)])
            if ins_overdue:
                compliance.append({'type':'Insurance expired',
                    'count':ins_overdue, 'level':'critical'})
            if ins_soon:
                compliance.append({'type':'Insurance expiring soon',
                    'count':ins_soon, 'level':'warning'})
        except Exception:
            pass

        # ── Recent maintenance logs ───────────────────────────────────
        recent_maint = []
        try:
            logs = self.env['fleet.vehicle.log.services'].search(
                [], order='date desc', limit=8)
            for lg in logs:
                recent_maint.append({
                    'id':      lg.id,
                    'vehicle': lg.vehicle_id.name if lg.vehicle_id else '',
                    'plate':   lg.vehicle_id.license_plate if lg.vehicle_id else '',
                    'service': lg.service_id.name if lg.service_id else lg.notes or '',
                    'vendor':  lg.vendor_id.name if lg.vendor_id else '',
                    'date':    lg.date.strftime('%d %b %Y') if lg.date else '',
                    'cost':    lg.amount or 0,
                    'location':lg.vehicle_id.home_location_id.name
                               if lg.vehicle_id and lg.vehicle_id.home_location_id else '',
                })
        except Exception:
            pass

        # ── Driver stats ──────────────────────────────────────────────
        driver_stats = {
            'total_drivers': self.env['res.partner'].search_count(
                [('id','in', Vehicle.search([('driver_id','!=',False)])
                  .mapped('driver_id').ids)]),
            'unassigned':    unassigned_drv,
            'assigned':      total - unassigned_drv,
        }

        return {
            'kpis': {
                'total':        total,
                'overdue':      overdue,
                'due_soon':     due_soon,
                'ok':           ok,
                'idle':         idle,
                'no_location':  without_loc,
                'unassigned':   unassigned_drv,
                'vendors':      len(vendors),
            },
            'by_location':  by_location,
            'by_make':      by_make_list,
            'by_status':    by_status,
            'vendors':      vendors,
            'compliance':   compliance,
            'recent_maint': recent_maint,
            'driver_stats': driver_stats,
        }

