from odoo import models, fields, api
from odoo.exceptions import UserError
import json
import logging
import urllib.request
import urllib.error
import math
from datetime import timedelta

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL   = 'claude-sonnet-4-20250514'

SYSTEM_PROMPT = """You are a security intelligence analyst for NRS (Nigeria Revenue Service) 
facilities management. You analyse security incident data, OSINT feeds, and watchlist 
information to identify threat patterns that may affect NRS offices and staff across Nigeria.

You respond ONLY with valid JSON — no preamble, no markdown, no explanation outside the JSON.

Your analysis must be:
- Factual and evidence-based (cite the incident counts and dates)
- Actionable (specific recommendations security teams can execute)
- Calibrated (confidence reflects actual data quality and pattern strength)
- Nigeria-context aware (understand local security dynamics)"""


def _call_claude(prompt, max_tokens=1500, env=None):
    """Call Claude API and return parsed JSON response."""
    body = json.dumps({
        'model': CLAUDE_MODEL,
        'max_tokens': max_tokens,
        'system': SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': prompt}],
    }).encode()

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=body,
        headers={
            'Content-Type':      'application/json',
            'x-api-key':         _get_claude_key(env=env),
            'anthropic-version': '2023-06-01',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())

    text = result['content'][0]['text'].strip()
    # Strip markdown fences if present
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())


def _get_claude_key(env=None):
    """Fetch Claude API key from ir.config_parameter.
    Works in both HTTP request context and cron/shell context.
    """
    # Try passed env first
    if env is not None:
        key = env['ir.config_parameter'].sudo().get_param('ai.pattern.claude_api_key')
        if key:
            return key

    # Try HTTP request context
    try:
        from odoo.http import request as http_request
        if http_request and http_request.env:
            key = http_request.env['ir.config_parameter'].sudo().get_param(
                'ai.pattern.claude_api_key')
            if key:
                return key
    except Exception:
        pass

    # Try registry directly (works in cron/shell)
    try:
        import odoo
        from odoo import registry, SUPERUSER_ID
        import threading
        db = getattr(threading.current_thread(), 'dbname', None)
        if db:
            with registry(db).cursor() as cr:
                from odoo.api import Environment
                e = Environment(cr, SUPERUSER_ID, {})
                key = e['ir.config_parameter'].get_param('ai.pattern.claude_api_key')
                if key:
                    return key
    except Exception as ex:
        _logger.warning("Key registry fallback failed: %s", ex)

    raise UserError(
        'Claude API key not configured. '
        'Go to Settings → Technical → System Parameters → '
        'create key: ai.pattern.claude_api_key')


def _haversine_km(lat1, lng1, lat2, lng2):
    """Distance in km between two lat/lng points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


class AiPatternEngine(models.AbstractModel):
    """
    Core AI analysis engine. Six detectors, each producing
    structured JSON assessments via Claude API.
    """
    _name = 'ai.pattern.engine'
    _description = 'AI Pattern Detection Engine'

    @api.model
    def run_all_detectors(self):
        """Entry point — runs all six detectors. Called by cron."""
        _logger.info("AI Pattern Engine starting — running all detectors")
        results = []
        detectors = [
            ('cluster',    self._detect_clusters),
            ('escalation', self._detect_escalation),
            ('actor',      self._detect_actor_patterns),
            ('temporal',   self._detect_temporal_anomalies),
            ('watchlist',  self._detect_watchlist_proximity),
        ]
        for name, fn in detectors:
            try:
                alerts = fn()
                results.extend(alerts)
                _logger.info("Detector '%s' produced %d alerts", name, len(alerts))
            except Exception as e:
                _logger.error("Detector '%s' failed: %s", name, e, exc_info=True)

        _logger.info("AI Pattern Engine complete — %d total alerts", len(results))
        return results

    # ── 1. CLUSTER DETECTION ──────────────────────────────────────────
    @api.model
    def _detect_clusters(self):
        """
        Find unusual concentrations of incidents in small geographic areas
        over a rolling 72-hour window.
        Threshold: 3+ incidents within 50km in 72 hours.
        """
        since = fields.Datetime.now() - timedelta(hours=72)
        incidents = self.env['security.incident'].search([
            ('date_incident', '>=', since),
            ('location_id.latitude', '!=', 0.0),
        ])

        if len(incidents) < 3:
            return []

        # Build clusters using simple radius grouping
        clusters = []
        used = set()
        inc_list = list(incidents)

        for i, inc in enumerate(inc_list):
            if i in used:
                continue
            cluster = [inc]
            used.add(i)
            lat1 = inc.location_id.latitude
            lng1 = inc.location_id.longitude
            for j, other in enumerate(inc_list):
                if j in used or j == i:
                    continue
                lat2 = other.location_id.latitude
                lng2 = other.location_id.longitude
                if lat2 and lng2:
                    dist = _haversine_km(lat1, lng1, lat2, lng2)
                    if dist <= 50:
                        cluster.append(other)
                        used.add(j)
            if len(cluster) >= 3:
                clusters.append(cluster)

        alerts = []
        for cluster in clusters:
            # Check not already alerted in last 24h
            states = list(set(
                i.location_id.name for i in cluster if i.location_id))
            existing = self.env['ai.pattern.alert'].search([
                ('pattern_type', '=', 'cluster'),
                ('affected_locations', 'in', states),
                ('create_date', '>=', fields.Datetime.now() - timedelta(hours=24)),
            ], limit=1)
            if existing:
                continue

            inc_data = [{
                'id':       i.id,
                'type':     i.incident_type,
                'severity': i.severity,
                'location': i.location_id.name if i.location_id else '',
                'state':    (i.location_id.name if i.location_id else ''),
                'date':     str(i.date_incident),
                'description': (i.description or '')[:200],
            } for i in cluster]

            prompt = f"""Analyse this cluster of {len(cluster)} security incidents 
that occurred within 50km of each other in the last 72 hours at NRS offices in Nigeria.

INCIDENTS:
{json.dumps(inc_data, indent=2)}

Respond with ONLY this JSON structure:
{{
  "title": "Short alert title (max 80 chars)",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence intelligence assessment. What does this cluster suggest? Is it opportunistic or coordinated?",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "affected_states": ["State1", "State2"],
  "create_incident": true|false,
  "incident_title": "Title for auto-created incident if create_incident is true"
}}"""

            try:
                result = _call_claude(prompt)
                alert = self._create_alert(
                    pattern_type='cluster',
                    ai_result=result,
                    incidents=cluster,
                    extras={
                        'incident_count': len(cluster),
                        'affected_locations': ', '.join(states),
                        'date_range_start': min(i.date_incident for i in cluster),
                        'date_range_end': max(i.date_incident for i in cluster),
                    })
                if alert:
                    alerts.append(alert)
            except Exception as e:
                _logger.error("Cluster alert creation failed: %s", e)

        return alerts

    # ── 2. ESCALATION DETECTION ───────────────────────────────────────
    @api.model
    def _detect_escalation(self):
        """
        Detect states where incident severity is trending upward.
        Compare last 7 days vs previous 7 days per state.
        """
        severity_score = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
        now = fields.Datetime.now()
        week1_start = now - timedelta(days=14)
        week1_end   = now - timedelta(days=7)
        week2_start = now - timedelta(days=7)

        states = self.env['security.state.threat'].search([])
        alerts = []

        for state in states:
            sname = state.name

            week1 = self.env['security.incident'].search([
                ('location_id.name', 'ilike', sname),
                ('date_incident', '>=', week1_start),
                ('date_incident', '<',  week1_end),
            ])
            week2 = self.env['security.incident'].search([
                ('location_id.name', 'ilike', sname),
                ('date_incident', '>=', week2_start),
            ])

            if not week1 and not week2:
                continue

            score1 = sum(severity_score.get(i.severity, 1) for i in week1)
            score2 = sum(severity_score.get(i.severity, 1) for i in week2)

            # Escalation: score doubled or went from 0 to 3+
            if score2 == 0:
                continue
            escalating = (score1 == 0 and score2 >= 3) or \
                         (score1 > 0 and score2 / score1 >= 2.0)
            if not escalating:
                continue

            # Don't re-alert same state within 48h
            existing = self.env['ai.pattern.alert'].search([
                ('pattern_type', '=', 'escalation'),
                ('affected_states', 'ilike', sname),
                ('create_date', '>=', now - timedelta(hours=48)),
            ], limit=1)
            if existing:
                continue

            all_incidents = list(week1) + list(week2)
            inc_data = [{
                'type':     i.incident_type,
                'severity': i.severity,
                'location': i.location_id.name if i.location_id else '',
                'date':     str(i.date_incident),
                'week':     'week1 (8-14 days ago)' if i in week1 else 'week2 (last 7 days)',
            } for i in all_incidents]

            prompt = f"""Analyse this escalating security pattern in {sname} State, Nigeria.

WEEK 1 (8-14 days ago): {len(week1)} incidents, severity score {score1}
WEEK 2 (last 7 days):   {len(week2)} incidents, severity score {score2}
ESCALATION RATIO: {round(score2/max(score1,1), 2)}x

INCIDENT DETAILS:
{json.dumps(inc_data, indent=2)}

NRS has offices and staff in this state. Assess whether this represents:
- Organised pre-attack escalation
- Seasonal/situational spike  
- Random variance

Respond with ONLY this JSON:
{{
  "title": "Short alert title mentioning {sname} (max 80 chars)",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence intelligence assessment of this escalation pattern.",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "affected_states": ["{sname}"],
  "create_incident": true|false,
  "incident_title": "Title for auto-created incident if create_incident is true"
}}"""

            try:
                result = _call_claude(prompt)
                alert = self._create_alert(
                    pattern_type='escalation',
                    ai_result=result,
                    incidents=all_incidents,
                    extras={
                        'affected_states': sname,
                        'incident_count': len(all_incidents),
                    })
                if alert:
                    alerts.append(alert)
            except Exception as e:
                _logger.error("Escalation alert failed for %s: %s", sname, e)

        return alerts

    # ── 3. ACTOR PATTERN DETECTION ────────────────────────────────────
    @api.model
    def _detect_actor_patterns(self):
        """
        Compare suspect descriptions across incidents in last 30 days.
        Flag where descriptions are similar across multiple locations.
        Uses Claude to assess similarity — no regex needed.
        """
        since = fields.Datetime.now() - timedelta(days=30)
        incidents = self.env['security.incident'].search([
            ('date_incident', '>=', since),
            ('suspect_description', '!=', False),
            ('suspect_description', '!=', ''),
        ])

        if len(incidents) < 2:
            return []

        suspects = [{
            'id':          i.id,
            'description': i.suspect_description or '',
            'type':        i.incident_type,
            'location':    i.location_id.name if i.location_id else '',
            'date':        str(i.date_incident),
        } for i in incidents]

        # Don't run if already run in last 12h
        existing = self.env['ai.pattern.alert'].search([
            ('pattern_type', '=', 'actor'),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=12)),
        ], limit=1)
        if existing:
            return []

        prompt = f"""Review these {len(suspects)} suspect descriptions from NRS security 
incidents across Nigeria in the last 30 days. Identify if any descriptions suggest 
the SAME individual or GROUP operating across multiple locations.

SUSPECT DESCRIPTIONS:
{json.dumps(suspects, indent=2)}

If you identify a cross-location actor pattern, respond with this JSON.
If no meaningful pattern exists, respond with {{"pattern_found": false}}.

Pattern found JSON:
{{
  "pattern_found": true,
  "title": "Short alert title (max 80 chars)",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence description of the actor pattern. What links these descriptions?",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "affected_states": ["State1", "State2"],
  "matching_incident_ids": [list of incident IDs that match],
  "create_incident": true|false,
  "incident_title": "Title for auto-created incident"
}}"""

        try:
            result = _call_claude(prompt)
            if not result.get('pattern_found'):
                return []

            matching_ids = result.pop('matching_incident_ids', [])
            matching = self.env['security.incident'].browse(
                [i for i in matching_ids if i])

            alert = self._create_alert(
                pattern_type='actor',
                ai_result=result,
                incidents=list(matching) or list(incidents),
                extras={'incident_count': len(matching or incidents)})
            return [alert] if alert else []
        except Exception as e:
            _logger.error("Actor pattern detection failed: %s", e)
            return []

    # ── 4. TEMPORAL ANOMALY DETECTION ─────────────────────────────────
    @api.model
    def _detect_temporal_anomalies(self):
        """
        Compare current week's incident rate against 90-day baseline.
        Flag states where current rate is 2x+ the baseline average.
        """
        now = fields.Datetime.now()
        since_90d = now - timedelta(days=90)
        since_7d  = now - timedelta(days=7)

        states = self.env['security.state.threat'].search([])
        alerts = []

        for state in states:
            sname = state.name
            all_90d = self.env['security.incident'].search_count([
                ('location_id.name', 'ilike', sname),
                ('date_incident', '>=', since_90d),
                ('date_incident', '<', since_7d),
            ])
            last_7d = self.env['security.incident'].search_count([
                ('location_id.name', 'ilike', sname),
                ('date_incident', '>=', since_7d),
            ])

            if all_90d == 0 and last_7d == 0:
                continue

            weekly_baseline = all_90d / 12  # 12 weeks in 90 days
            if weekly_baseline == 0 and last_7d >= 3:
                ratio = 99  # Sudden activity where none existed
            elif weekly_baseline > 0:
                ratio = last_7d / weekly_baseline
            else:
                continue

            if ratio < 2.0:
                continue

            existing = self.env['ai.pattern.alert'].search([
                ('pattern_type', '=', 'temporal'),
                ('affected_states', 'ilike', sname),
                ('create_date', '>=', now - timedelta(hours=48)),
            ], limit=1)
            if existing:
                continue

            prompt = f"""Analyse this temporal anomaly in {sname} State, Nigeria.

BASELINE: {round(weekly_baseline, 1)} incidents/week (90-day average)
LAST 7 DAYS: {last_7d} incidents
RATIO: {round(ratio, 1)}x above baseline

NRS has tax offices and staff in this state.

Is this anomaly:
- A genuine security deterioration requiring action?
- Likely related to a known event (elections, enforcement drives, market days)?
- Random statistical variance?

Respond with ONLY this JSON:
{{
  "title": "Short alert title mentioning {sname} (max 80 chars)",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence assessment of this temporal anomaly.",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "affected_states": ["{sname}"],
  "create_incident": false
}}"""

            try:
                result = _call_claude(prompt)
                alert = self._create_alert(
                    pattern_type='temporal',
                    ai_result=result,
                    incidents=[],
                    extras={
                        'affected_states': sname,
                        'incident_count': last_7d,
                    })
                if alert:
                    alerts.append(alert)
            except Exception as e:
                _logger.error("Temporal anomaly detection failed for %s: %s", sname, e)

        return alerts

    # ── 5. WATCHLIST PROXIMITY ────────────────────────────────────────
    @api.model
    def _detect_watchlist_proximity(self):
        """
        Check if any active watchlist subjects were recently sighted
        near NRS office locations. Flag if within 20km.
        """
        watchlist = self.env['security.watchlist'].search([
            ('approval_state', '=', 'approved'),
            ('last_sighted', '>=', fields.Datetime.now() - timedelta(days=7)),
            ('last_sighted_location_id', '!=', False),
        ])

        if not watchlist:
            return []

        alerts = []
        for subject in watchlist:
            slat = subject.last_sighted_location_id.latitude
            slng = subject.last_sighted_location_id.longitude
            if not slat or not slng:
                continue

            # Find NRS offices within 20km
            nearby = self.env['generic.location'].search([
                ('latitude', '!=', 0.0)])
            nearby_offices = [
                loc for loc in nearby
                if _haversine_km(slat, slng, loc.latitude, loc.longitude) <= 20
            ]

            if not nearby_offices:
                continue

            existing = self.env['ai.pattern.alert'].search([
                ('pattern_type', '=', 'watchlist'),
                ('title', 'ilike', subject.name),
                ('create_date', '>=', fields.Datetime.now() - timedelta(hours=24)),
            ], limit=1)
            if existing:
                continue

            offices_data = [{
                'name': o.name,
                'distance_km': round(_haversine_km(
                    slat, slng, o.latitude, o.longitude), 1),
            } for o in nearby_offices[:5]]

            prompt = f"""A known security watchlist subject has been sighted near NRS offices in Nigeria.

SUBJECT: {subject.name}
THREAT LEVEL: {subject.threat_level}
CATEGORY: {subject.category}
LAST SIGHTED: {str(subject.last_sighted)}
LAST SIGHTED LOCATION: {subject.last_sighted_location_id.name}
REASON ON WATCHLIST: {(subject.reason or 'Not specified')[:200]}

NEARBY NRS OFFICES (within 20km):
{json.dumps(offices_data, indent=2)}

Assess the risk to NRS staff and operations. 

Respond with ONLY this JSON:
{{
  "title": "Watchlist subject near NRS offices — {subject.name[:40]}",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence risk assessment for NRS staff and offices.",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "affected_states": ["{subject.last_sighted_location_id.name}"],
  "create_incident": true,
  "incident_title": "Watchlist subject proximity alert — {subject.name[:40]}"
}}"""

            try:
                result = _call_claude(prompt)
                alert = self._create_alert(
                    pattern_type='watchlist',
                    ai_result=result,
                    incidents=[],
                    extras={
                        'affected_locations': ', '.join(
                            o.name for o in nearby_offices[:5]),
                        'incident_count': len(nearby_offices),
                    })
                if alert:
                    alerts.append(alert)
            except Exception as e:
                _logger.error("Watchlist proximity alert failed: %s", e)

        return alerts

    # ── 6. ROUTE RISK ASSESSMENT ──────────────────────────────────────
    @api.model
    def assess_route_risk(self, origin_name, destination_name):
        """
        On-demand route risk assessment between two named locations.
        Called from UI — not a scheduled detector.
        Returns structured risk assessment.
        """
        since = fields.Datetime.now() - timedelta(days=30)

        # Find origin and destination locations
        origin = self.env['generic.location'].search(
            [('name', 'ilike', origin_name)], limit=1)
        dest = self.env['generic.location'].search(
            [('name', 'ilike', destination_name)], limit=1)

        if not origin or not dest:
            return {'error': 'One or both locations not found in NRS database'}

        olat, olng = origin.latitude, origin.longitude
        dlat, dlng = dest.latitude,   dest.longitude
        total_dist = _haversine_km(olat, olng, dlat, dlng)

        # Find incidents within 15km of the straight-line route
        # Sample 10 points along the route
        route_incidents = []
        all_incidents = self.env['security.incident'].search([
            ('date_incident', '>=', since),
            ('location_id.latitude', '!=', 0.0),
        ])

        for inc in all_incidents:
            ilat = inc.location_id.latitude
            ilng = inc.location_id.longitude
            # Check distance to any of 10 points along route
            for t in [i/10 for i in range(11)]:
                rlat = olat + t * (dlat - olat)
                rlng = olng + t * (dlng - olng)
                if _haversine_km(ilat, ilng, rlat, rlng) <= 15:
                    route_incidents.append(inc)
                    break

        inc_data = [{
            'type':     i.incident_type,
            'severity': i.severity,
            'location': i.location_id.name if i.location_id else '',
            'date':     str(i.date_incident),
        } for i in route_incidents]

        prompt = f"""Assess the security risk for a convoy/vehicle route in Nigeria.

ROUTE: {origin.name} → {dest.name}
DISTANCE: {round(total_dist, 1)} km
INCIDENTS ALONG THIS ROUTE (last 30 days): {len(route_incidents)}

INCIDENT DETAILS:
{json.dumps(inc_data, indent=2) if inc_data else 'No recorded incidents along this route'}

Provide a route risk assessment for NRS staff travelling this route.

Respond with ONLY this JSON:
{{
  "risk_score": 0-100,
  "risk_level": "critical|high|medium|low",
  "title": "Route risk: {origin.name[:30]} → {dest.name[:30]}",
  "severity": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "summary": "2-3 sentence route risk assessment.",
  "recommended_actions": ["Action 1", "Action 2", "Action 3"],
  "safe_travel_times": "Best times to travel this route",
  "alternative_recommendation": "Alternative route or precaution if high risk",
  "affected_states": [],
  "create_incident": false
}}"""

        result = _call_claude(prompt)
        result.update({
            'origin':       origin.name,
            'destination':  dest.name,
            'distance_km':  round(total_dist, 1),
            'incidents':    len(route_incidents),
        })

        # Save as a pattern alert for the log
        self._create_alert(
            pattern_type='route',
            ai_result=result,
            incidents=route_incidents,
            extras={
                'route_origin':      origin.name,
                'route_destination': dest.name,
                'route_risk_score':  result.get('risk_score', 0),
            })
        return result

    # ── Alert creator ─────────────────────────────────────────────────
    @api.model
    def _create_alert(self, pattern_type, ai_result, incidents, extras=None):
        """Create ai.pattern.alert record from Claude's structured output."""
        extras = extras or {}
        if not ai_result.get('title'):
            return None

        vals = {
            'title':            ai_result.get('title', '')[:200],
            'pattern_type':     pattern_type,
            'severity':         ai_result.get('severity', 'medium'),
            'confidence':       float(ai_result.get('confidence', 0.5)),
            'ai_summary':       ai_result.get('summary', ''),
            'ai_recommended_actions': '\n'.join(
                f"• {a}" for a in ai_result.get('recommended_actions', [])),
            'ai_raw_response':  json.dumps(ai_result),
            'affected_states':  ', '.join(ai_result.get('affected_states', [])),
            'dashboard_shown':  True,
        }
        vals.update(extras)

        alert = self.env['ai.pattern.alert'].create(vals)

        # Link incidents
        if incidents:
            alert.write({'linked_incident_ids': [(6, 0, [i.id for i in incidents])]})

        # Auto-create incident if AI recommended it
        if ai_result.get('create_incident') and ai_result.get('incident_title'):
            auto_inc = self.env['security.incident'].create({
                'incident_type':  'ai_pattern',
                'severity':       ai_result.get('severity', 'medium'),
                'description':    f'<p><strong>AI Pattern Detection</strong></p>'
                                  f'<p>{ai_result.get("summary","")}</p>'
                                  f'<p><strong>Recommended Actions:</strong></p>'
                                  + ''.join(
                                      f'<p>• {a}</p>'
                                      for a in ai_result.get('recommended_actions', [])),
                'state':          'new',
            })
            alert.write({'auto_created_incident_id': auto_inc.id})

        self.env.cr.commit()
        _logger.info("AI alert created: %s [%s] confidence=%.2f",
                     alert.title, pattern_type, alert.confidence)
        return alert

    @api.model
    def cron_run_detectors(self):
        """Scheduled action entry point."""
        self.run_all_detectors()
