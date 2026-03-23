from odoo import http
from odoo.http import request
from datetime import date, timedelta


class SecurityDashboardController(http.Controller):

    @http.route('/myservice/security/kpis', type='json', auth='user', methods=['POST'])
    def get_kpis(self):
        Incident = request.env['security.incident'].sudo()
        Guard    = request.env['security.guard'].sudo()
        Access   = request.env['security.access.log'].sudo()
        Watch    = request.env['security.watchlist'].sudo()
        today    = date.today()
        week_ago = today - timedelta(days=7)
        return {
            'incidents': {
                'open':      Incident.search_count([('state','not in',['resolved','closed'])]),
                'critical':  Incident.search_count([('severity','=','critical'),('state','not in',['resolved','closed'])]),
                'high':      Incident.search_count([('severity','=','high'),('state','not in',['resolved','closed'])]),
                'today':     Incident.search_count([('date_incident','>=',str(today))]),
                'this_week': Incident.search_count([('date_incident','>=',str(week_ago))]),
            },
            'guards': {
                'total':   Guard.search_count([('is_active','=',True)]),
                'on_duty': Guard.search_count([('on_duty','=',True)]),
            },
            'access': {
                'today_in':  Access.search_count([('datetime','>=',str(today)),('direction','=','in')]),
                'today_out': Access.search_count([('datetime','>=',str(today)),('direction','=','out')]),
                'flagged':   Access.search_count([('flagged','=',True),('datetime','>=',str(today))]),
            },
            'watchlist': {
                'total':    Watch.search_count([('approval_state','=','approved')]),
                'critical': Watch.search_count([('threat_level','=','critical'),('approval_state','=','approved')]),
                'high':     Watch.search_count([('threat_level','=','high'),('approval_state','=','approved')]),
            },
        }

    @http.route('/myservice/security/map_data', type='json', auth='user', methods=['POST'])
    def get_map_data(self):
        incidents = request.env['security.incident'].sudo().search([
            ('state','not in',['closed']),
            ('location_id.latitude','!=',0.0),
        ], order='date_incident desc', limit=200)
        incident_data = [{
            'id':       i.id,
            'name':     i.name,
            'type':     dict(request.env['security.incident']._fields['incident_type'].selection).get(i.incident_type,''),
            'severity': i.severity,
            'state':    i.state,
            'location': i.location_id.name,
            'lat':      i.location_id.latitude,
            'lng':      i.location_id.longitude,
            'date':     i.date_incident.strftime('%d %b %Y %H:%M') if i.date_incident else '',
        } for i in incidents]

        today = date.today()
        rosters = request.env['security.duty.roster'].sudo().search([
            ('date','=',today), ('status','=','active')])
        guard_data = [{
            'id':       r.guard_id.id,
            'name':     r.guard_id.name,
            'badge':    r.guard_id.badge_number,
            'location': r.location_id.name,
            'shift':    r.shift,
            'lat':      r.location_id.latitude,
            'lng':      r.location_id.longitude,
        } for r in rosters if r.location_id.latitude and r.location_id.longitude]

        # FIRS office locations
        locations = request.env['generic.location'].sudo().search([
            ('latitude','!=',0.0),('longitude','!=',0.0),
        ], limit=500)
        location_data = [{
            'id':    l.id,
            'name':  l.name,
            'state': l.state_name or '',
            'lat':   l.latitude,
            'lng':   l.longitude,
            'open_incidents': request.env['security.incident'].sudo().search_count([
                ('location_id','=',l.id),
                ('state','not in',['resolved','closed']),
            ]),
        } for l in locations]

        return {'incidents': incident_data, 'guards': guard_data, 'locations': location_data}

    @http.route('/myservice/security/trend', type='json', auth='user', methods=['POST'])
    def get_trend(self):
        Incident = request.env['security.incident'].sudo()
        weeks = []
        for i in range(7, -1, -1):
            ws = date.today() - timedelta(weeks=i+1)
            we = date.today() - timedelta(weeks=i)
            weeks.append({
                'label': ws.strftime('W%W'),
                'count': Incident.search_count([('date_incident','>=',str(ws)),('date_incident','<',str(we))]),
            })
        return {'weekly': weeks}

    @http.route('/myservice/security/recent', type='json', auth='user', methods=['POST'])
    def get_recent(self):
        incidents = request.env['security.incident'].sudo().search([
            ('state','not in',['closed'])
        ], order='date_incident desc', limit=15)
        sel = dict(request.env['security.incident']._fields['incident_type'].selection)
        return [{
            'id':       i.id,
            'name':     i.name,
            'type':     sel.get(i.incident_type,''),
            'severity': i.severity,
            'state':    i.state,
            'location': i.location_id.name if i.location_id else '',
            'date':     i.date_incident.strftime('%d %b %Y') if i.date_incident else '',
        } for i in incidents]

    @http.route('/myservice/security/osint', type='json', auth='user', methods=['POST'])
    def get_osint(self):
        results = []

        # ── Source 1: security.osint.feed (manual, watchlist, AI pattern) ──
        feeds = request.env['security.osint.feed'].sudo().search(
            [], order='date desc', limit=30)
        for f in feeds:
            results.append({
                'id':          f.id,
                'title':       f.title,
                'summary':     f.summary or '',
                'source_type': f.source_type,
                'source_name': f.source_name or '',
                'threat':      f.threat_level,
                'location':    f.location_id.name if f.location_id else (f.state_name or ''),
                'date':        f.date.strftime('%d %b %Y %H:%M') if f.date else '',
                'verified':    f.is_verified,
                '_sort_date':  f.date,
            })

        # ── Source 2: osint.feed.entry (ACLED, GDELT, RSS, ReliefWeb) ──
        try:
            entries = request.env['osint.feed.entry'].sudo().search(
                [], order='event_date desc', limit=50)
            for e in entries:
                results.append({
                    'id':          e.id,
                    'title':       e.title or '',
                    'summary':     e.summary or '',
                    'source_type': e.source_config_id.source_type if e.source_config_id else 'external',
                    'source_name': e.source_name or '',
                    'threat':      e.threat_level or 'info',
                    'location':    e.state_name or '',
                    'date':        e.event_date.strftime('%d %b %Y %H:%M') if e.event_date else '',
                    'verified':    e.is_verified,
                    '_sort_date':  e.event_date,
                })
        except Exception as ex:
            import logging
            logging.getLogger(__name__).warning('osint.feed.entry load error: %s', ex)

        # ── Merge, sort by date desc, return top 40 ──
        from datetime import datetime
        results.sort(
            key=lambda x: x.get('_sort_date') or datetime.min,
            reverse=True)
        for r in results:
            r.pop('_sort_date', None)
        return results[:40]

    @http.route('/myservice/security/state_threats', type='json', auth='user', methods=['POST'])
    def get_state_threats(self):
        states = request.env['security.state.threat'].sudo().search([])
        return [{'name':s.name,'level':s.threat_level,'notes':s.notes or ''} for s in states]
