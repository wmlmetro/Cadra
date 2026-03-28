import logging
from datetime import date, timedelta

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# FM domain mapping — category IDs → domain name
# We group requests by category to derive "domains"
DOMAIN_NAMES = [
    'Building Services',
    'Plant & Machinery',
    'Plumbing',
    'Security',
    'Fleet',
]

# NRS office locations for the map
NRS_OFFICES = [
    {'name': 'General Register House', 'lat': 55.9533, 'lng': -3.1883},
    {'name': 'New Register House', 'lat': 55.9537, 'lng': -3.1880},
    {'name': 'Thomas Thomson House', 'lat': 55.9220, 'lng': -3.1700},
    {'name': 'Ladywell House', 'lat': 55.9480, 'lng': -3.1760},
    {'name': 'West Register House', 'lat': 55.9508, 'lng': -3.2033},
]


class FMDashboardController(http.Controller):

    @http.route('/myservice/fm_dashboard/data', type='json', auth='user')
    def dashboard_data(self, **kw):
        Req = request.env['request.request'].sudo()
        today = date.today()
        today_str = fields.Date.to_string(today)

        # ---------- All non-closed requests ----------
        open_domain = [('closed', '=', False)]
        all_open = Req.search(open_domain, order='create_date desc', limit=500)

        # ---------- KPIs ----------
        overdue = all_open.filtered(
            lambda r: r.deadline_date and r.deadline_date < today)
        in_progress = all_open.filtered(
            lambda r: r.stage_id.code == 'progress')
        # "Escalated" = priority 3 (critical)
        escalated = all_open.filtered(lambda r: r.priority == '3')

        # Resolved today = closed today with done stage
        resolved_today = Req.search_count([
            ('closed', '=', True),
            ('date_closed', '>=', today_str + ' 00:00:00'),
            ('date_closed', '<=', today_str + ' 23:59:59'),
        ])

        kpis = {
            'open': len(all_open),
            'overdue': len(overdue),
            'escalated': len(escalated),
            'in_progress': len(in_progress),
            'resolved_today': resolved_today,
        }

        # ---------- SLA by domain ----------
        # Group by category_id to simulate domains
        sla_data = []
        category_groups = {}
        for r in all_open:
            cat_name = r.category_id.name if r.category_id else 'Uncategorised'
            category_groups.setdefault(cat_name, []).append(r)

        # If no categories, group by type
        if len(category_groups) <= 1 and not any(category_groups.keys() - {'Uncategorised'}):
            category_groups = {}
            for domain_name in DOMAIN_NAMES:
                category_groups[domain_name] = []
            for r in all_open:
                # Distribute into domains by type or just put in first
                type_name = r.type_id.name if r.type_id else ''
                placed = False
                for dn in DOMAIN_NAMES:
                    if dn.lower() in type_name.lower():
                        category_groups[dn].append(r)
                        placed = True
                        break
                if not placed:
                    category_groups.setdefault('Building Services', []).append(r)

        for domain_name in (DOMAIN_NAMES if not any(
                category_groups.keys() - set(DOMAIN_NAMES) - {'Uncategorised'})
                else sorted(category_groups.keys())):
            reqs = category_groups.get(domain_name, [])
            total = len(reqs)
            ov = len([r for r in reqs
                      if r.deadline_date and r.deadline_date < today])
            esc = len([r for r in reqs if r.priority == '3'])
            sla_pct = round((1 - ov / total) * 100) if total else 100
            sla_data.append({
                'domain': domain_name,
                'open': total,
                'overdue': ov,
                'escalated': esc,
                'sla_pct': sla_pct,
            })

        # ---------- Recent open requests ----------
        recent = []
        for r in all_open[:30]:
            recent.append({
                'id': r.id,
                'name': r.name or 'Untitled',
                'stage': r.stage_id.name if r.stage_id else '',
                'stage_code': r.stage_id.code if r.stage_id else '',
                'category': r.category_id.name if r.category_id else '',
                'location': r.generic_location_id.name if r.generic_location_id else '',
                'priority': r.priority or '0',
                'deadline': fields.Date.to_string(r.deadline_date) if r.deadline_date else '',
                'is_overdue': bool(r.deadline_date and r.deadline_date < today),
                'create_date': fields.Datetime.to_string(r.create_date) if r.create_date else '',
            })

        # ---------- Team workload (by assignee) ----------
        workload = {}
        for r in all_open:
            assignee = r.user_id.name if r.user_id else 'Unassigned'
            workload[assignee] = workload.get(assignee, 0) + 1
        team_workload = sorted(
            [{'name': k, 'count': v} for k, v in workload.items()],
            key=lambda x: -x['count']
        )[:10]

        # ---------- Overdue list ----------
        overdue_list = []
        for r in sorted(overdue, key=lambda x: x.deadline_date or today):
            days = (today - r.deadline_date).days if r.deadline_date else 0
            overdue_list.append({
                'id': r.id,
                'name': r.name or 'Untitled',
                'stage': r.stage_id.name if r.stage_id else '',
                'category': r.category_id.name if r.category_id else '',
                'deadline': fields.Date.to_string(r.deadline_date) if r.deadline_date else '',
                'days_overdue': days,
            })

        # ---------- Map locations ----------
        # Use generic.location records if they have coords, else NRS offices
        map_locations = []
        Location = request.env['generic.location'].sudo()
        locs = Location.search([], limit=50)
        if locs:
            for loc in locs:
                if loc.latitude and loc.longitude:
                    req_count = Req.search_count([
                        ('generic_location_id', '=', loc.id),
                        ('closed', '=', False),
                    ])
                    map_locations.append({
                        'name': loc.name,
                        'lat': loc.latitude,
                        'lng': loc.longitude,
                        'request_count': req_count,
                    })

        if not map_locations:
            map_locations = [dict(o, request_count=0) for o in NRS_OFFICES]

        return {
            'kpis': kpis,
            'sla_data': sla_data,
            'recent_requests': recent,
            'team_workload': team_workload,
            'overdue_list': overdue_list,
            'map_locations': map_locations,
        }
