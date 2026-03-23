from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class AiPatternController(http.Controller):

    @http.route('/myservice/ai/alerts', type='json', auth='user')
    def ai_alerts(self, limit=20, severity=None, pattern_type=None, **kw):
        domain = [('dashboard_shown', '=', True), ('state', '!=', 'dismissed')]
        if severity:
            domain.append(('severity', '=', severity))
        if pattern_type:
            domain.append(('pattern_type', '=', pattern_type))
        alerts = request.env['ai.pattern.alert'].search(
            domain, order='create_date desc', limit=limit)
        return [{
            'id':           a.id,
            'title':        a.title,
            'pattern_type': a.pattern_type,
            'severity':     a.severity,
            'confidence':   round(a.confidence * 100),
            'summary':      a.ai_summary or '',
            'actions':      a.ai_recommended_actions or '',
            'states':       a.affected_states or '',
            'locations':    a.affected_locations or '',
            'state':        a.state,
            'created':      a.create_date.strftime('%d %b %Y %H:%M') if a.create_date else '',
            'incident_count': a.incident_count or 0,
            'auto_incident': a.auto_created_incident_id.id if a.auto_created_incident_id else None,
        } for a in alerts]

    @http.route('/myservice/ai/route_risk', type='json', auth='user')
    def route_risk(self, origin, destination, **kw):
        if not origin or not destination:
            return {'error': 'Origin and destination required'}
        try:
            result = request.env['ai.pattern.engine'].assess_route_risk(
                origin, destination)
            return result
        except Exception as e:
            _logger.error("Route risk assessment error: %s", e)
            return {'error': str(e)}

    @http.route('/myservice/ai/run_now', type='json', auth='user')
    def run_now(self, **kw):
        """Trigger all detectors on demand — for testing."""
        try:
            request.env['ai.pattern.engine'].run_all_detectors()
            count = request.env['ai.pattern.alert'].search_count([
                ('create_date', '>=',
                 __import__('odoo').fields.Datetime.now() -
                 __import__('datetime').timedelta(minutes=5))
            ])
            return {'ok': True, 'new_alerts': count}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    @http.route('/myservice/ai/summary', type='json', auth='user')
    def ai_summary(self, **kw):
        Alert = request.env['ai.pattern.alert']
        from datetime import timedelta
        from odoo import fields
        since_24h = fields.Datetime.now() - timedelta(hours=24)
        return {
            'total':     Alert.search_count([]),
            'new_24h':   Alert.search_count([('create_date', '>=', since_24h)]),
            'critical':  Alert.search_count([('severity', '=', 'critical'), ('state', '=', 'new')]),
            'high':      Alert.search_count([('severity', '=', 'high'), ('state', '=', 'new')]),
            'unreviewed':Alert.search_count([('state', '=', 'new')]),
            'by_type': {
                'cluster':    Alert.search_count([('pattern_type', '=', 'cluster')]),
                'escalation': Alert.search_count([('pattern_type', '=', 'escalation')]),
                'actor':      Alert.search_count([('pattern_type', '=', 'actor')]),
                'temporal':   Alert.search_count([('pattern_type', '=', 'temporal')]),
                'route':      Alert.search_count([('pattern_type', '=', 'route')]),
                'watchlist':  Alert.search_count([('pattern_type', '=', 'watchlist')]),
            }
        }
