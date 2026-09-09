import logging
from datetime import date

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
NRS_HQ_FALLBACK = [
    {'name': 'NRS Headquarters', 'lat': 9.0579, 'lng': 7.4951},
]

# Rows fetched for the two LISTS on this dashboard. These are windows and
# they are allowed to be: a list is a sample and says so by being a list.
# Every NUMBER on this payload is counted over the whole register.
RECENT_ROWS = 30
OVERDUE_ROWS = 50


class FMDashboardController(http.Controller):

    @http.route('/myservice/fm_dashboard/data', type='json', auth='user')
    def dashboard_data(self, **kw):
        """Facilities dashboard payload, also published as GET /api/v1/fm/dashboard.

        Every count here used to be `len()` over the newest 500 open
        requests. Four of the five KPIs were therefore the size of that
        window, standing next to `resolved_today`, which was a real
        `search_count` — one payload, five numbers, one of them honest, and
        the honest one made the others look measured.

        Worse was `sla_pct`: a RATIO whose numerator and denominator were
        both taken from inside a window biased toward the newest requests,
        published under the name of a compliance figure. An NRS manager
        quotes that in a meeting and nobody in the room can tell it from a
        true one.

        Counts are now `search_count` / `_read_group` on the unclamped
        domains. `_read_group` is never given a limit, so a per-category
        breakdown is exact and costs one query instead of one per category.
        """
        Req = request.env['request.request'].sudo()
        today = date.today()
        today_str = fields.Date.to_string(today)

        # ---------- The domains every number on this page is counted over ----------
        open_domain = [('closed', '=', False)]
        overdue_domain = open_domain + [
            ('deadline_date', '!=', False),
            ('deadline_date', '<', today_str),
        ]
        escalated_domain = open_domain + [('priority', '=', '3')]
        # `request.stage.code` is a stored Char, so the dotted path is a real
        # SQL join and not a Python filter wearing a domain's clothes.
        #
        # The code is `in_progress`. It was `progress` here, and no tenant
        # has ever had a stage with that code — cadra19, nrs19, gtb19,
        # test19 and jaizbankplc all ship `new, triage, in_progress,
        # resolved, closed`, and the string `'progress'` appears nowhere
        # else in this repo. So this KPI was not merely counted inside a
        # window: it was structurally ZERO, on every tenant, always, and it
        # sat on the dashboard next to four numbers that moved.
        in_progress_domain = open_domain + [('stage_id.code', '=', 'in_progress')]

        # ---------- KPIs ----------
        kpis = {
            'open': Req.search_count(open_domain),
            'overdue': Req.search_count(overdue_domain),
            'escalated': Req.search_count(escalated_domain),
            'in_progress': Req.search_count(in_progress_domain),
            'resolved_today': Req.search_count([
                ('closed', '=', True),
                ('date_closed', '>=', today_str + ' 00:00:00'),
                ('date_closed', '<=', today_str + ' 23:59:59'),
            ]),
        }

        # ---------- SLA by domain ----------
        # Group by category_id to simulate domains. One grouped query per
        # term, over the whole register — not a tally over a fetched page.
        cat_open = self._tally(Req, open_domain, 'category_id')
        cat_overdue = self._tally(Req, overdue_domain, 'category_id')
        cat_escalated = self._tally(Req, escalated_domain, 'category_id')

        # If no categories, group by type — same fallback as before, same
        # substring matching, now over grouped counts rather than a window.
        if not (set(cat_open) - {'Uncategorised'}):
            cat_open = self._by_domain_name(
                self._tally(Req, open_domain, 'type_id'))
            cat_overdue = self._by_domain_name(
                self._tally(Req, overdue_domain, 'type_id'))
            cat_escalated = self._by_domain_name(
                self._tally(Req, escalated_domain, 'type_id'))

        if not (set(cat_open) - set(DOMAIN_NAMES) - {'Uncategorised'}):
            group_names = DOMAIN_NAMES
        else:
            group_names = sorted(cat_open)

        sla_data = []
        for domain_name in group_names:
            total = cat_open.get(domain_name, 0)
            ov = cat_overdue.get(domain_name, 0)
            esc = cat_escalated.get(domain_name, 0)
            sla_data.append({
                'domain': domain_name,
                'open': total,
                'overdue': ov,
                'escalated': esc,
                'sla_pct': round((1 - ov / total) * 100) if total else 100,
            })

        # ---------- Recent open requests ----------
        # A LIST of the newest 30. `kpis.open` beside it says how many there
        # are; this says which ones arrived last.
        recent = []
        for r in Req.search(open_domain, order='create_date desc',
                            limit=RECENT_ROWS):
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
        workload = self._tally(Req, open_domain, 'user_id',
                               empty_label='Unassigned')
        team_workload = sorted(
            [{'name': k, 'count': v} for k, v in workload.items()],
            key=lambda x: -x['count']
        )[:10]

        # ---------- Overdue list ----------
        overdue_list = []
        for r in Req.search(overdue_domain, order='deadline_date asc',
                            limit=OVERDUE_ROWS):
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
        map_locations = []
        Location = request.env['generic.location'].sudo()
        locs = Location.search([('latitude', '!=', False), ('longitude', '!=', False)])
        per_location = dict(Req._read_group(
            open_domain + [('generic_location_id', 'in', locs.ids)],
            ['generic_location_id'], ['__count']))
        for loc in locs:
            map_locations.append({
                'name': loc.name,
                'lat': loc.latitude,
                'lng': loc.longitude,
                'request_count': per_location.get(loc, 0),
            })

        if not map_locations:
            map_locations = [dict(o, request_count=0) for o in NRS_HQ_FALLBACK]

        return {
            'kpis': kpis,
            'sla_data': sla_data,
            'recent_requests': recent,
            'team_workload': team_workload,
            'overdue_list': overdue_list,
            'map_locations': map_locations,
        }

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _tally(Req, domain, groupby, empty_label='Uncategorised'):
        """{group label: count} over the WHOLE domain.

        `_read_group` is never handed a limit, so this is the exact answer
        and one query. The label for the empty group is spelled out rather
        than dropped: a request with no category is a fact about the
        register, and hiding it would make the columns stop summing to the
        headline beside them.
        """
        out = {}
        for group, count in Req._read_group(domain, [groupby], ['__count']):
            label = group.display_name if group else empty_label
            out[label] = out.get(label, 0) + count
        return out

    @staticmethod
    def _by_domain_name(type_counts):
        """Fold {type name: count} onto the five fixed FM domain names.

        Same substring rule the windowed version used, applied to grouped
        counts. Anything that matches nothing lands in Building Services,
        exactly as before — so the columns still sum to `kpis.open`.
        """
        out = {name: 0 for name in DOMAIN_NAMES}
        for type_name, count in type_counts.items():
            placed = False
            for name in DOMAIN_NAMES:
                if name.lower() in (type_name or '').lower():
                    out[name] += count
                    placed = True
                    break
            if not placed:
                out['Building Services'] += count
        return out
