"""
Patch script: adds Fleet Command tab to myservice operations dashboard.
Modifies 3 files:
1. dashboard.py  — adds get_fleet_command() API method
2. dashboard.xml — adds tab switcher + fleet command panel to template
3. dashboard.js  — adds tab logic + fleet command rendering
4. controller    — adds /myservice/dashboard/fleet_command route
"""
import re

# ════════════════════════════════════════════════════════════════════
# 1. dashboard.py — add get_fleet_command method
# ════════════════════════════════════════════════════════════════════
MODEL = '/opt/odoo/myservicenrs/myservice_dashboard/models/dashboard.py'
with open(MODEL) as f:
    model_content = f.read()

FLEET_METHOD = '''
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
'''

if 'get_fleet_command' not in model_content:
    # Append before last line
    model_content = model_content.rstrip() + '\n' + FLEET_METHOD + '\n'
    with open(MODEL, 'w') as f:
        f.write(model_content)
    print("dashboard.py updated")
else:
    print("dashboard.py already has get_fleet_command")

# ════════════════════════════════════════════════════════════════════
# 2. controller — add fleet command route
# ════════════════════════════════════════════════════════════════════
CTRL = '/opt/odoo/myservicenrs/myservice_dashboard/controllers/main.py'
with open(CTRL) as f:
    ctrl = f.read()

ROUTE = '''
    @http.route('/myservice/dashboard/fleet_command', type='json',
                auth='user', methods=['POST'])
    def get_fleet_command(self):
        return request.env['myservice.dashboard'].get_fleet_command()
'''

if 'fleet_command' not in ctrl:
    ctrl = ctrl.rstrip() + '\n' + ROUTE + '\n'
    with open(CTRL, 'w') as f:
        f.write(ctrl)
    print("controller updated")
else:
    print("controller already has fleet_command route")

# ════════════════════════════════════════════════════════════════════
# 3. dashboard.xml — add tab switcher + fleet command panel
# ════════════════════════════════════════════════════════════════════
XML = '/opt/odoo/myservicenrs/myservice_dashboard/static/src/xml/dashboard.xml'
with open(XML) as f:
    xml = f.read()

TAB_BAR = '''        <div class="ms-tab-bar">
            <button class="ms-tab active" data-tab="overview">
                <i class="fa fa-globe"/> Overview
            </button>
            <button class="ms-tab" data-tab="fleet">
                <i class="fa fa-car"/> Fleet Command
            </button>
        </div>'''

FLEET_PANEL = '''
        <!-- ── Fleet Command Tab ──────────────────────────────────── -->
        <div class="ms-tab-panel" data-panel="fleet" style="display:none">

            <!-- Fleet KPI strip -->
            <div class="ms-fleet-kpis">
                <div class="ms-fleet-kpi red"><div class="ms-fleet-kval fk-overdue">—</div><div class="ms-fleet-klbl">Maintenance Overdue</div></div>
                <div class="ms-fleet-kpi orange"><div class="ms-fleet-kval fk-due-soon">—</div><div class="ms-fleet-klbl">Due Soon</div></div>
                <div class="ms-fleet-kpi green"><div class="ms-fleet-kval fk-ok">—</div><div class="ms-fleet-klbl">Active / OK</div></div>
                <div class="ms-fleet-kpi gray"><div class="ms-fleet-kval fk-idle">—</div><div class="ms-fleet-klbl">Idle 30+ Days</div></div>
                <div class="ms-fleet-kpi gray"><div class="ms-fleet-kval fk-unassigned">—</div><div class="ms-fleet-klbl">No Driver</div></div>
                <div class="ms-fleet-kpi gray"><div class="ms-fleet-kval fk-no-location">—</div><div class="ms-fleet-klbl">No Location</div></div>
                <div class="ms-fleet-kpi blue"><div class="ms-fleet-kval fk-vendors">—</div><div class="ms-fleet-klbl">Approved Vendors</div></div>
            </div>

            <!-- Main fleet grid -->
            <div class="ms-fleet-grid">

                <!-- Vehicles by location -->
                <div class="ms-fleet-card wide">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-map-marker"/> Vehicles by location</span>
                        <span class="ms-fleet-card-sub">Top 10 NRS offices</span>
                    </div>
                    <div class="ms-fleet-loc-bars">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

                <!-- Maintenance status donut -->
                <div class="ms-fleet-card">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-pie-chart"/> Maintenance status</span>
                    </div>
                    <div class="ms-fleet-status-list">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

                <!-- Fleet by make -->
                <div class="ms-fleet-card">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-car"/> Fleet by make</span>
                    </div>
                    <div class="ms-fleet-make-bars">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

                <!-- Approved vendors -->
                <div class="ms-fleet-card">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-wrench"/> Approved vendors</span>
                    </div>
                    <div class="ms-fleet-vendor-list">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

                <!-- Compliance alerts -->
                <div class="ms-fleet-card">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-exclamation-triangle"/> Compliance alerts</span>
                    </div>
                    <div class="ms-fleet-compliance-list">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

                <!-- Recent maintenance -->
                <div class="ms-fleet-card wide">
                    <div class="ms-fleet-card-hdr">
                        <span><i class="fa fa-history"/> Recent maintenance logs</span>
                        <span class="ms-fleet-card-sub">Latest 8 service records</span>
                    </div>
                    <div class="ms-fleet-maint-list">
                        <div class="ms-fleet-empty">Loading...</div>
                    </div>
                </div>

            </div>
        </div>'''

OVERVIEW_OPEN  = '        <div class="ms-dash-body">'
OVERVIEW_CLOSE = '    </div>\n</t>'

if 'ms-tab-bar' not in xml:
    # Wrap existing body in overview panel, add tab bar before it
    xml = xml.replace(
        OVERVIEW_OPEN,
        TAB_BAR + '\n\n        <!-- ── Overview Tab ─────────────────────────────────── -->\n        <div class="ms-tab-panel" data-panel="overview">\n        <div class="ms-dash-body">'
    )
    # Close overview panel and add fleet panel before closing tags
    xml = xml.replace(
        OVERVIEW_CLOSE,
        '        </div>\n        </div>\n' + FLEET_PANEL + '\n    </div>\n</t>'
    )
    with open(XML, 'w') as f:
        f.write(xml)
    print("dashboard.xml updated")
else:
    print("dashboard.xml already has tabs")

print("All patches done")
