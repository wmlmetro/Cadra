from odoo import http
from odoo.http import request
from datetime import date, timedelta


class SecurityDashboardController(http.Controller):

    @http.route('/myservice/security/kpis', type='json', auth='user', methods=['POST'])
    def get_kpis(self):
        Incident = request.env['security.incident']
        Guard    = request.env['security.guard']
        Access   = request.env['security.access.log']
        Watch    = request.env['security.watchlist']

        today = date.today()
        week_ago = today - timedelta(days=7)

        return {
            'incidents': {
                'open':        Incident.search_count([('state', 'not in', ['resolved','closed'])]),
                'critical':    Incident.search_count([('severity','=','critical'),('state','not in',['resolved','closed'])]),
                'high':        Incident.search_count([('severity','=','high'),('state','not in',['resolved','closed'])]),
                'today':       Incident.search_count([('date_incident','>=', str(today))]),
                'this_week':   Incident.search_count([('date_incident','>=', str(week_ago))]),
            },
            'guards': {
                'total':       Guard.search_count([('is_active','=',True)]),
                'on_duty':     Guard.search_count([('on_duty','=',True)]),
            },
            'access': {
                'today_in':    Access.search_count([('datetime','>=',str(today)),('direction','=','in')]),
                'today_out':   Access.search_count([('datetime','>=',str(today)),('direction','=','out')]),
                'flagged':     Access.search_count([('flagged','=',True),('datetime','>=',str(today))]),
            },
            'watchlist': {
                'total':       Watch.search_count([('approval_state','=','approved')]),
                'critical':    Watch.search_count([('threat_level','=','critical'),('approval_state','=','approved')]),
                'high':        Watch.search_count([('threat_level','=','high'),('approval_state','=','approved')]),
            },
        }

    @http.route('/myservice/security/map_data', type='json', auth='user', methods=['POST'])
    def get_map_data(self):
        Incident = request.env['security.incident']
        Guard    = request.env['security.guard']

        # Recent open incidents with location
        incidents = Incident.search([
            ('state', 'not in', ['closed']),
            ('location_id.latitude', '!=', 0.0),
        ], order='date_incident desc', limit=200)

        incident_data = []
        for i in incidents:
            incident_data.append({
                'id':       i.id,
                'name':     i.name,
                'type':     i.incident_type,
                'severity': i.severity,
                'state':    i.state,
                'location': i.location_id.name,
                'lat':      i.location_id.latitude,
                'lng':      i.location_id.longitude,
                'date':     i.date_incident.strftime('%d %b %Y %H:%M') if i.date_incident else '',
            })

        # Active guards with location
        from datetime import date as _date
        today = _date.today()
        rosters = request.env['security.duty.roster'].search([
            ('date', '=', today),
            ('status', '=', 'active'),
        ])
        guard_data = []
        for r in rosters:
            loc = r.location_id
            if loc.latitude and loc.longitude:
                guard_data.append({
                    'id':       r.guard_id.id,
                    'name':     r.guard_id.name,
                    'badge':    r.guard_id.badge_number,
                    'location': loc.name,
                    'shift':    r.shift,
                    'lat':      loc.latitude,
                    'lng':      loc.longitude,
                })

        return {
            'incidents': incident_data,
            'guards':    guard_data,
        }

    @http.route('/myservice/security/trend', type='json', auth='user', methods=['POST'])
    def get_trend(self):
        from datetime import date, timedelta
        Incident = request.env['security.incident']

        # Last 8 weeks
        weeks = []
        for i in range(7, -1, -1):
            week_start = date.today() - timedelta(weeks=i+1)
            week_end   = date.today() - timedelta(weeks=i)
            count = Incident.search_count([
                ('date_incident', '>=', str(week_start)),
                ('date_incident', '<',  str(week_end)),
            ])
            weeks.append({
                'label': week_start.strftime('W%W'),
                'count': count,
            })

        # By type
        types = {}
        for t, label in Incident._fields['incident_type'].selection:
            c = Incident.search_count([
                ('incident_type', '=', t),
                ('state', 'not in', ['closed']),
            ])
            if c:
                types[label] = c

        return {'weekly': weeks, 'by_type': types}

    @http.route('/myservice/security/recent', type='json', auth='user', methods=['POST'])
    def get_recent(self):
        incidents = request.env['security.incident'].search([
            ('state', 'not in', ['closed']),
        ], order='date_incident desc', limit=15)

        return [{
            'id':       i.id,
            'name':     i.name,
            'type':     dict(request.env['security.incident']._fields['incident_type'].selection).get(i.incident_type, ''),
            'severity': i.severity,
            'state':    i.state,
            'location': i.location_id.name if i.location_id else '',
            'date':     i.date_incident.strftime('%d %b %Y') if i.date_incident else '',
        } for i in incidents]
