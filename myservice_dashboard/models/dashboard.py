import logging

from odoo import models, api
from datetime import date, timedelta

_logger = logging.getLogger(__name__)


class MyServiceDashboard(models.AbstractModel):
    _name = 'myservice.dashboard'
    _description = 'myservice Operations Dashboard'

    @api.model
    def get_kpis(self):
        Vehicle = self.env['fleet.vehicle']
        Location = self.env['generic.location']
        Request = self.env['request.request']
        Asset = self.env.get('nrs.asset')

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

        # Vendor KPIs.
        #
        # This was `except Exception: total = approved = 0` — the same shape,
        # over the same model, that told every tenant "No approved vendors yet"
        # for three years on `get_fleet_command`. Two endpoints, one question,
        # and this was the half that still answered zero without saying so.
        #
        # Nothing here needs a handler. `myservice_dashboard.__manifest__`
        # DEPENDS on `myservice_fleet_maintenance`, which is where
        # `fleet.service.vendor` is declared, so Odoo cannot load the model
        # holding this method without loading that one — the "vendors module
        # may not be installed" case the handler read as does not exist. And
        # `is_approved` is one of its eight columns. A handler over a body that
        # cannot fail is not protection; it is a standing instruction to report
        # zero the next time somebody renames something, which is precisely how
        # the last one survived.
        Vendor = self.env['fleet.service.vendor']
        total_vendors = Vendor.search_count([])
        approved_vendors = Vendor.search_count([('is_approved', '=', True)])

        # Asset KPIs + category breakdown.
        # `read_group` on nrs.asset groups all rows by category_id, returning
        # one dict per category with {category_id: (id, name), category_id_count}.
        # We skip when the nrs.asset model isn't installed (this dashboard ships
        # outside the NRS bundle too) so the rest of the payload still renders.
        asset_categories = []
        total_assets = 0
        if Asset is not None:
            total_assets = Asset.search_count([])
            groups = Asset.read_group(
                domain=[],
                fields=['category_id'],
                groupby=['category_id'],
                lazy=False,
            )
            asset_categories = sorted(
                (
                    {
                        'id':    (g['category_id'][0] if g.get('category_id') else None),
                        'name':  (g['category_id'][1] if g.get('category_id') else 'Uncategorised'),
                        'count': g['__count'],
                    }
                    for g in groups
                ),
                key=lambda c: c['count'],
                reverse=True,
            )

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
            'assets': {
                'total': total_assets,
                'categories': asset_categories,
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

        # ── How a failed panel answers ────────────────────────────────
        #
        # This method is a seven-panel aggregator served two ways: the Odoo web
        # client calls it directly, and `GET /api/v1/dashboard/fleet-command`
        # wraps whatever it returns as `data` in the PRD envelope. `cadra_route`
        # has no per-key failure shape — `err()` replaces the whole body — so
        # raising out of one panel answers nothing about the other six, to
        # either caller, beyond `500 internal_error`.
        #
        # So a panel that cannot be built is NAMED rather than served empty.
        # `data._warnings` is already how this API admits a partial answer
        # inside a successful payload — `rejected_fields` on assets, requests,
        # locations and settings — so this is that convention one key deeper
        # and not a new one.
        #
        # It is NOT the same key as the envelope's own `_warnings.truncated`,
        # which `ok()` attaches at the TOP LEVEL and deliberately so: a list
        # endpoint's `data` is an array and has nowhere to hang it. The two
        # can therefore both appear in one response, at different depths. A
        # caller reading warnings has to look in both places, which is worth
        # saying out loud rather than discovering.
        #
        # The point is only that `[]` and "I could not build this" stop being
        # the same answer: rule 3 is about silent degradation, and a named gap
        # is not silent.
        #
        # It is additive, so it breaks no existing consumer.
        unavailable = []

        # Idle: no maintenance log in 30 days.
        #
        # The `except Exception: idle = 0` that was here could not fire. Its
        # only conceivable failure was `fleet.vehicle.log.services` being
        # absent, and that model ships in the same core `fleet` addon as the
        # `fleet.vehicle` this method already browses unguarded fifteen lines
        # above — if fleet were missing, line 1 of this method would have raised
        # first. `date` and `vehicle_id` are its own columns.
        #
        # Nor is there anywhere to admit a gap: `idle` is a NUMBER inside
        # `kpis`, and `idle: 0` — "every vehicle has been serviced this month" —
        # is exactly the confident wrong answer this pass exists to remove. If
        # this ever does raise, a 500 naming the model is a better bug report
        # than a zero nobody can see.
        since_30 = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        active_ids = self.env['fleet.vehicle.log.services'].search(
            [('date', '>=', since_30)]).mapped('vehicle_id').ids
        idle = Vehicle.search_count([('id', 'not in', active_ids)])

        # ── Vendor performance ────────────────────────────────────────
        # `vendor_total` is the NUMBER; `vendors` is a six-row sample of it.
        # `kpis.vendors` used to be `len(vendors)`, so it maxed out at 6
        # while `get_kpis()` counted the same quantity correctly — two
        # endpoints, two answers, one question. The web client labels this
        # figure "Approved Vendors", so that is what it counts.
        vendor_total = 0
        vendors = []
        try:
            vendor_total = self.env['fleet.service.vendor'].search_count(
                [('is_approved', '=', True)])
            for v in self.env['fleet.service.vendor'].search(
                    [('is_approved','=',True)], limit=6):
                vendors.append({
                    'id':   v.id,
                    'name': v.name,
                    'approved': v.is_approved,
                    'specialisation': v.specialisation or '',
                    # The vendor's own state, via its contact. It was
                    # `v.state_id`, and `fleet.service.vendor` HAS NO SUCH
                    # FIELD — the columns are name, partner_id, email,
                    # phone, specialisation, is_approved, active, notes. So
                    # the first vendor raised AttributeError into the bare
                    # `except` below and the list came back EMPTY on every
                    # tenant, always. `kpis.vendors` was `len()` of that, so
                    # it was not "capped at 6": it was zero, and the web
                    # client's card read "No approved vendors yet" to a
                    # tenant that had them.
                    'state': (v.partner_id.state_id.name
                              if v.partner_id.state_id else ''),
                })
        except Exception:
            # catch-all: reported — a panel of the answer, so a failure is
            # announced in `_warnings.unavailable` rather than served as an
            # empty vendor list. Broad because nothing identifiable is left to
            # fail, not because the failure is acceptable.
            #
            # Handoff 13 left this reading "the model is absent outside the NRS
            # bundle, which is the case this try exists for". That is not true:
            # `myservice_dashboard` depends on `myservice_fleet_maintenance` in
            # its manifest, so `fleet.service.vendor` cannot be absent here, and
            # the sibling handler in `get_kpis()` has been deleted on exactly
            # that evidence. Every field this block reads is verified against
            # the model. So this is `unknown`, not `optional` — there is no
            # benign condition it is waiting for.
            #
            # It stays broad, and stays here, only because of the aggregator
            # rule above: six working panels should not be taken out by the
            # seventh. What has changed is that an empty list can no longer be
            # mistaken for "no approved vendors".
            _logger.warning("dashboard: vendor performance unavailable",
                            exc_info=True)
            unavailable.append('vendors')

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
        #
        # THIS PANEL WAS STRUCTURALLY EMPTY ON EVERY TENANT, ALWAYS.
        #
        # It counted `('insurance_expiration_date', '<', today)` on
        # `fleet.vehicle`. There is no such field — not in core fleet on any
        # version, and nowhere in this repo: it was copied from a throwaway
        # root-level patch script, `fleet_command_patch.py`, which is now
        # deleted (handoff 16 C1) because a reader would re-seed the defect
        # from it. Odoo's domain parser rejects an unknown field, the bare
        # `except: pass` below ate the error, and the Compliance Alerts panel
        # has shown nothing since the day it was written. Same family as the FM
        # `in_progress` KPI and the vendor list: not a wrong number, a
        # permanent zero that no one can distinguish from good news.
        #
        # Odoo models vehicle insurance as `fleet.vehicle.log.contract`
        # (`expiration_date`, `insurer_id`), surfaced on the vehicle as the
        # searchable `contract_renewal_overdue` / `contract_renewal_due_soon`.
        # Those keep the panel counting VEHICLES, which is what the old `count`
        # meant, and take the "soon" window from fleet's own
        # `hr_fleet.delay_alert_contract` parameter (30 days by default) rather
        # than a second one declared here.
        #
        # `soon_14` went with it: it was computed and never read.
        compliance = []
        try:
            contract_overdue = Vehicle.search_count([
                ('contract_renewal_overdue', '=', True)])
            contract_soon = Vehicle.search_count([
                ('contract_renewal_due_soon', '=', True)])
            if contract_overdue:
                compliance.append({'type': 'Insurance / contract expired',
                    'count': contract_overdue, 'level': 'critical'})
            if contract_soon:
                compliance.append({'type': 'Insurance / contract expiring soon',
                    'count': contract_soon, 'level': 'warning'})
        except Exception:
            # catch-all: reported — the panel this replaces was empty for
            # years because its failure had nowhere to go, so its
            # replacement's failure is announced in `_warnings.unavailable`
            # instead of repeating the trick.
            _logger.warning("dashboard: compliance alerts unavailable",
                            exc_info=True)
            unavailable.append('compliance')

        # ── Recent maintenance logs ───────────────────────────────────
        #
        # THIS PANEL WAS EMPTY ON EVERY TENANT THAT HAD ANY SERVICE LOG.
        #
        # `lg.service_id` — `fleet.vehicle.log.services` has no such field. Its
        # columns are vehicle_id, service_type_id, description, notes, amount,
        # date, vendor_id, purchaser_id, inv_ref, odometer*, state. So the
        # FIRST row of the loop raised AttributeError, the bare `except: pass`
        # below swallowed it, and `recent_maint` came back `[]` — with the
        # partially-built list discarded, so even the rows that had already
        # been appended were lost. Byte for byte the `v.state_id` defect
        # handoff 13 found in the vendor block twenty lines up, in the same
        # function, written the same day. A model with no rows would produce
        # the identical output, which is why nobody caught it.
        #
        # `service_type_id` is required on the model, so it is always set; the
        # `description` / `notes` fallbacks preserve what the old expression
        # was reaching for. Note `vendor_id` here is a `res.partner`, not the
        # `fleet.service.vendor` of the vendors panel above — two different
        # models, one word.
        recent_maint = []
        try:
            logs = self.env['fleet.vehicle.log.services'].search(
                [], order='date desc', limit=8)
            for lg in logs:
                recent_maint.append({
                    'id':      lg.id,
                    'vehicle': lg.vehicle_id.name if lg.vehicle_id else '',
                    'plate':   lg.vehicle_id.license_plate if lg.vehicle_id else '',
                    'service': (lg.service_type_id.name
                                or lg.description or lg.notes or ''),
                    'vendor':  lg.vendor_id.name if lg.vendor_id else '',
                    'date':    lg.date.strftime('%d %b %Y') if lg.date else '',
                    'cost':    lg.amount or 0,
                    'location':lg.vehicle_id.home_location_id.name
                               if lg.vehicle_id and lg.vehicle_id.home_location_id else '',
                })
        except Exception:
            # catch-all: reported — a per-row build over live tenant data,
            # where a partial list is indistinguishable from a short one, so
            # the panel is dropped and named in `_warnings.unavailable` rather
            # than served half-built.
            #
            # This is the only one of the three whose body loops over rows the
            # tenant supplies rather than issuing counts, so it is also the
            # only one where the old handler destroyed work it had already
            # done. Naming it is what makes "no services logged" and "I could
            # not read the service log" two different answers.
            recent_maint = []
            _logger.warning("dashboard: recent maintenance logs unavailable",
                            exc_info=True)
            unavailable.append('recent_maint')

        # ── Driver stats ──────────────────────────────────────────────
        driver_stats = {
            'total_drivers': self.env['res.partner'].search_count(
                [('id','in', Vehicle.search([('driver_id','!=',False)])
                  .mapped('driver_id').ids)]),
            'unassigned':    unassigned_drv,
            'assigned':      total - unassigned_drv,
        }

        out = {
            'kpis': {
                'total':        total,
                'overdue':      overdue,
                'due_soon':     due_soon,
                'ok':           ok,
                'idle':         idle,
                'no_location':  without_loc,
                'unassigned':   unassigned_drv,
                'vendors':      vendor_total,
            },
            'by_location':  by_location,
            'by_make':      by_make_list,
            'by_status':    by_status,
            'vendors':      vendors,
            'compliance':   compliance,
            'recent_maint': recent_maint,
            'driver_stats': driver_stats,
        }
        # Present only when a panel failed, so its absence carries no meaning
        # and a client that never looks is unaffected. A key listed here is a
        # panel whose value in this payload is a placeholder, not an answer.
        if unavailable:
            out['_warnings'] = {'unavailable': unavailable}
        return out

