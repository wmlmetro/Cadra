from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class OsintDashboardController(http.Controller):

    @http.route('/myservice/osint/feed', type='json', auth='user')
    def osint_feed(self, state=None, threat_level=None, source_type=None,
                   limit=50, **kw):
        domain = []
        if state:
            domain.append(('state_name', 'ilike', state))
        if threat_level:
            domain.append(('threat_level', '=', threat_level))
        if source_type:
            domain.append(('source_type', '=', source_type))

        entries = request.env['osint.feed.entry'].search(
            domain, order='event_date desc', limit=limit)

        return [{
            'id':           e.id,
            'title':        e.title,
            'summary':      (e.summary or '')[:300],
            'state':        e.state_name or '',
            'source_type':  e.source_type,
            'source_name':  e.source_name or '',
            'threat_level': e.threat_level,
            'threat_color': e.threat_color,
            'event_date':   e.event_date.strftime('%d %b %Y %H:%M') if e.event_date else '',
            'fatalities':   e.fatalities,
            'url':          e.source_url or '',
            'verified':     e.is_verified,
            'lat':          e.latitude,
            'lng':          e.longitude,
        } for e in entries]

    @http.route('/myservice/osint/state_scores', type='json', auth='user')
    def state_scores(self, **kw):
        states = request.env['security.state.threat'].search([])
        return [{
            'name':          s.name,
            'level':         s.threat_level,
            'score':         s.composite_score,
            'delta':         s.score_delta,
            'prev_level':    s.previous_level or s.threat_level,
            'd1':            s.dim_armed_conflict,
            'd2':            s.dim_civil_unrest,
            'd3':            s.dim_internal_incidents,
            'd4':            s.dim_watchlist,
            'd5':            s.dim_media_sentiment,
            'd6':            s.dim_humanitarian,
            'osint_count':   s.osint_entry_count,
            'incident_count':s.incident_count,
            'computed_at':   s.score_computed_at.strftime('%d %b %Y %H:%M') if s.score_computed_at else '',
        } for s in states]

    @http.route('/myservice/osint/summary', type='json', auth='user')
    def osint_summary(self, **kw):
        Entry = request.env['osint.feed.entry']
        from datetime import timedelta
        from odoo import fields
        since_24h = fields.Datetime.now() - timedelta(hours=24)
        since_7d  = fields.Datetime.now() - timedelta(days=7)
        return {
            'total':       Entry.search_count([]),
            'last_24h':    Entry.search_count([('create_date','>=',since_24h)]),
            'last_7d':     Entry.search_count([('create_date','>=',since_7d)]),
            'critical':    Entry.search_count([('threat_level','=','critical')]),
            'high':        Entry.search_count([('threat_level','=','high')]),
            'unverified':  Entry.search_count([('is_verified','=',False)]),
            'sources': {
                'acled':     Entry.search_count([('source_type','=','acled')]),
                'gdelt':     Entry.search_count([('source_type','=','gdelt')]),
                'rss':       Entry.search_count([('source_type','=','rss')]),
                'reliefweb': Entry.search_count([('source_type','=','reliefweb')]),
                'manual':    Entry.search_count([('source_type','=','manual')]),
            },
        }
