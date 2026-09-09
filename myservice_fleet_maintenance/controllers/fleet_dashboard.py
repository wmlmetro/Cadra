from odoo import http
from odoo.http import request
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class FleetDashboardController(http.Controller):

    @http.route('/myservice/fleet_dashboard/data',
                type='json', auth='user', methods=['POST'])
    def fleet_dashboard_data(self, **kwargs):
        Vehicle = request.env['fleet.vehicle'].sudo()
        today = date.today()

        # ── Total fleet counts ──
        # `active_domain` is what every breakdown below is counted over, so
        # the columns sum to `kpis.active` in this same response.
        active_domain = [('active', '=', True)]
        total = Vehicle.search_count([])
        active = Vehicle.search_count(active_domain)

        # Maintenance status breakdown
        ok_count = Vehicle.search_count([
            ('maintenance_status', '=', 'ok')])
        due_soon = Vehicle.search_count([
            ('maintenance_status', '=', 'due_soon')])
        overdue = Vehicle.search_count([
            ('maintenance_status', '=', 'overdue')])

        # Insurance / roadworthiness expiring within 30 days
        expiring_insurance = Vehicle.search_count([
            ('insurance_expiry', '!=', False),
            ('insurance_expiry', '<=', str(today + timedelta(days=30))),
            ('insurance_expiry', '>=', str(today)),
        ])
        expiring_roadworthy = Vehicle.search_count([
            ('roadworthy_expiry', '!=', False),
            ('roadworthy_expiry', '<=', str(today + timedelta(days=30))),
            ('roadworthy_expiry', '>=', str(today)),
        ])

        # Staff buses
        staff_buses = Vehicle.search_count([('is_staff_bus', '=', True)])

        # ── Vehicle list ──
        # A LIST, and allowed to be a window: it is a sample and says so by
        # being a list. `kpis.active` beside it says how many there are.
        vehicles = Vehicle.search(active_domain, order='name', limit=100)
        vehicle_list = []
        for v in vehicles:
            vehicle_list.append({
                'id':           v.id,
                'name':         v.name or '',
                'license':      v.license_plate or '',
                'model':        v.model_id.name if v.model_id else '',
                'brand':        (v.model_id.brand_id.name
                                 if v.model_id and v.model_id.brand_id
                                 else ''),
                'state':        v.state_id.name if v.state_id else 'Unknown',
                'driver':       v.driver_id.name if v.driver_id else '',
                'location':     (v.home_location_id.name
                                 if v.home_location_id else
                                 (v.location or '')),
                'maint_status': v.maintenance_status or 'no_schedule',
                'next_service': str(v.next_service_date) if v.next_service_date else '',
                'fuel_type':    v.fuel_type or '',
                'odometer':     v.odometer or 0,
                'is_staff_bus': v.is_staff_bus,
            })

        # ── Vehicles by state breakdown ──
        # Counted over the whole active fleet, not tallied over the 100-row
        # `vehicles` window above. The breakdown used to be returned NEXT TO
        # `kpis.total`, which is a real count — so on any fleet over 100 the
        # columns did not add up to the headline in the same response, and
        # the reasonable conclusion for anyone who summed them was that the
        # register was wrong.
        state_counts = self._tally(Vehicle, active_domain, 'state_id',
                                   empty_label='Unknown')

        # ── Maintenance due vehicles ──
        maint_vehicles = Vehicle.search([
            ('maintenance_status', 'in', ['due_soon', 'overdue']),
        ], order='next_service_date asc', limit=30)
        maintenance_list = []
        for v in maint_vehicles:
            maintenance_list.append({
                'id':           v.id,
                'name':         v.name or '',
                'license':      v.license_plate or '',
                'next_service': str(v.next_service_date) if v.next_service_date else '',
                'status':       v.maintenance_status,
                'vendor':       (v.preferred_vendor_id.name
                                 if v.preferred_vendor_id else ''),
                'odometer':     v.odometer or 0,
                'next_odo':     v.next_service_odometer or 0,
                'tickets':      v.open_maintenance_ticket_count,
            })

        # ── Service vendors ──
        Vendor = request.env['fleet.service.vendor'].sudo()
        vendor_count = Vendor.search_count([('active', '=', True)])
        approved_vendors = Vendor.search_count([
            ('is_approved', '=', True), ('active', '=', True)])

        # ── Fuel type breakdown ──
        fuel_counts = self._tally(Vehicle, active_domain, 'fuel_type',
                                  empty_label='unknown')

        return {
            'kpis': {
                'total':              total,
                'active':             active,
                'ok':                 ok_count,
                'due_soon':           due_soon,
                'overdue':            overdue,
                'expiring_insurance': expiring_insurance,
                'expiring_roadworthy': expiring_roadworthy,
                'staff_buses':        staff_buses,
                'vendors':            vendor_count,
                'approved_vendors':   approved_vendors,
            },
            'vehicles':        vehicle_list,
            'state_counts':    state_counts,
            'fuel_counts':     fuel_counts,
            'maintenance':     maintenance_list,
        }

    @staticmethod
    def _tally(Model, domain, groupby, empty_label='Unknown'):
        """{group label: count} over the WHOLE domain — one query, exact.

        `_read_group` is never handed a limit. A Selection groups by its
        raw value (what the JS keys off); a many2one groups by its record.
        """
        out = {}
        for group, count in Model._read_group(domain, [groupby], ['__count']):
            if hasattr(group, '_name'):
                label = group.display_name if group else empty_label
            else:
                label = group if group else empty_label
            out[label] = out.get(label, 0) + count
        return out
