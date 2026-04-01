from odoo import models, fields, api
import urllib.request
import urllib.parse
import urllib.error
import json
import logging
import http.cookiejar
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

ACLED_LOGIN_URL  = 'https://acleddata.com/user/login?_format=json'
ACLED_LOGOUT_URL = 'https://acleddata.com/user/logout?_format=json'
ACLED_DATA_URL   = 'https://acleddata.com/api/acled/read'

EVENT_WEIGHTS = {
    'Battles': 3,
    'Violence against civilians': 3,
    'Explosions/Remote violence': 3,
    'Riots': 2,
    'Protests': 1,
    'Strategic developments': 1,
}

THREAT_THRESHOLDS = {'red': 15, 'orange': 8, 'yellow': 3}


def _acled_session(email, password):
    """
    Log in to ACLED using OAuth cookie flow.
    Returns (opener, csrf_token) or raises on failure.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    body = json.dumps({'name': email, 'pass': password}).encode()
    req = urllib.request.Request(
        ACLED_LOGIN_URL,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'NRS-myservice/1.0',
        },
        method='POST',
    )
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read())

    csrf_token = data.get('csrf_token')
    if not csrf_token:
        raise ValueError("ACLED login failed — no csrf_token in response: %s" % data)

    return opener, csrf_token


def _acled_fetch(opener, csrf_token, params):
    """Fetch data from ACLED API using authenticated session."""
    url = ACLED_DATA_URL + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            'X-CSRF-Token': csrf_token,
            'User-Agent': 'NRS-myservice/1.0',
        },
    )
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read())


class AcledSyncLog(models.Model):
    _name = 'acled.sync.log'
    _description = 'ACLED Sync Log'
    _order = 'sync_date desc'
    _rec_name = 'sync_date'

    sync_date        = fields.Datetime('Sync Date', default=fields.Datetime.now)
    date_from        = fields.Date('Data From')
    date_to          = fields.Date('Data To')
    events_fetched   = fields.Integer('Events Fetched')
    events_created   = fields.Integer('New OSINT Entries')
    states_updated   = fields.Integer('States Updated')
    status           = fields.Selection([
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('error',   'Error'),
    ], default='success')
    error_message    = fields.Text('Error')

    @api.model
    def _get_credentials(self):
        p = self.env['ir.config_parameter'].sudo()
        email    = p.get_param('acled.email')
        password = p.get_param('acled.password')
        if not email or not password:
            raise ValueError(
                "ACLED credentials not configured. "
                "Set acled.email and acled.password in System Parameters.")
        return email, password

    @api.model
    def sync_nigeria_events(self, days_back=7):
        """
        Fetch ACLED events for Nigeria for the last N days.
        Cron runs daily at 05:00 — before Daily Brief at 06:00.
        """
        date_to   = date.today()
        date_from = date_to - timedelta(days=days_back)

        _logger.info("ACLED sync: Nigeria %s → %s", date_from, date_to)

        try:
            email, password = self._get_credentials()
            opener, csrf    = _acled_session(email, password)

            params = {
                'country':          'Nigeria',
                'event_date':       date_from.strftime('%Y-%m-%d'),
                'event_date_where': '>=',
                'limit':            500,
                '_format':          'json',
            }

            data   = _acled_fetch(opener, csrf, params)
            events = data.get('data', [])
            _logger.info("ACLED sync: fetched %d events (total available: %s)",
                         len(events), data.get('total_count', '?'))

            created = self._create_osint_entries(events)
            updated = self._update_state_threats(events)

            log = self.create({
                'events_fetched': len(events),
                'events_created': created,
                'states_updated': updated,
                'status':         'success',
                'date_from':      date_from,
                'date_to':        date_to,
            })
            self.env.cr.commit()
            _logger.info("ACLED sync complete — %d events, %d OSINT, %d states",
                         len(events), created, updated)
            return log

        except Exception as e:
            _logger.error("ACLED sync failed: %s", e, exc_info=True)
            self.create({
                'status':        'error',
                'error_message': str(e),
                'date_from':     date_from,
                'date_to':       date_to,
            })
            self.env.cr.commit()
            return False

    def _create_osint_entries(self, events):
        """Create osint.feed.entry records. Skip duplicates by dedup hash."""
        try:
            OsintEntry  = self.env['osint.feed.entry']
            osint_fields = set(OsintEntry._fields.keys())
        except Exception:
            _logger.warning("osint.feed.entry model not found — skipping OSINT creation")
            return 0

        created = 0
        for ev in events:
            ref = ev.get('event_id_cnty', '')
            if not ref:
                continue

            # Skip duplicates via duplicate_hash
            dedup = 'acled_%s' % ref
            if OsintEntry.search([('duplicate_hash', '=', dedup)], limit=1):
                continue

            event_type = ev.get('event_type', '')
            fatalities = int(ev.get('fatalities', 0) or 0)

            if event_type in ('Battles', 'Explosions/Remote violence') or fatalities >= 5:
                threat_level = 'critical'
            elif event_type == 'Violence against civilians' or fatalities >= 1:
                threat_level = 'high'
            elif event_type == 'Riots':
                threat_level = 'elevated'
            else:
                threat_level = 'low'

            title = '%s — %s, %s' % (
                event_type,
                ev.get('location', ev.get('admin2', '')),
                ev.get('admin1', ''),
            )

            vals = {
                'title':          title[:200],
                'source_type':    'acled',
                'source_name':    (ev.get('source', 'ACLED') or 'ACLED')[:200],
                'threat_level':   threat_level,
                'state_name':     ev.get('admin1', ''),
                'event_date':     ev.get('event_date'),
                'summary':        (ev.get('notes', '') or '')[:1000],
                'event_type':     event_type,
                'fatalities':     fatalities,
                'latitude':       float(ev.get('latitude',  0) or 0),
                'longitude':      float(ev.get('longitude', 0) or 0),
                'duplicate_hash': dedup,
            }

            # Only set fields that exist on the model
            safe_vals = {k: v for k, v in vals.items() if k in osint_fields}

            try:
                OsintEntry.create(safe_vals)
                created += 1
            except Exception as e:
                _logger.warning("OSINT entry failed for %s: %s", ref, e)

        return created

    def _update_state_threats(self, events):
        """Recalculate threat level per state based on weighted event score."""
        try:
            StateThreat = self.env['security.state.threat']
            if not StateThreat.search_count([]):
                _logger.info("No state threat records — skipping update")
                return 0
        except Exception:
            _logger.warning("security.state.threat not found — skipping")
            return 0

        # Build weighted score per state
        state_scores = {}
        state_events = {}
        for ev in events:
            state = ev.get('admin1', '')
            if not state:
                continue
            weight          = EVENT_WEIGHTS.get(ev.get('event_type', ''), 1)
            fatality_bonus  = min(int(ev.get('fatalities', 0) or 0), 5)
            score           = weight + fatality_bonus
            state_scores[state] = state_scores.get(state, 0) + score
            state_events[state] = state_events.get(state, 0) + 1

        updated = 0
        for state_name, score in state_scores.items():
            level = 'green'
            if score >= THREAT_THRESHOLDS['red']:
                level = 'red'
            elif score >= THREAT_THRESHOLDS['orange']:
                level = 'orange'
            elif score >= THREAT_THRESHOLDS['yellow']:
                level = 'yellow'

            threat = StateThreat.search([('name', 'ilike', state_name)], limit=1)
            if not threat:
                continue

            update_vals = {'threat_level': level}
            threat_fields = set(threat._fields.keys())
            if 'acled_score'       in threat_fields:
                update_vals['acled_score']       = score
            if 'acled_event_count' in threat_fields:
                update_vals['acled_event_count'] = state_events.get(state_name, 0)
            if 'last_updated'      in threat_fields:
                update_vals['last_updated']      = fields.Datetime.now()

            if threat.threat_level != level:
                threat.write(update_vals)
                _logger.info("Threat updated: %s → %s (score %d)", state_name, level, score)
                updated += 1

        return updated

    @api.model
    def get_acled_heatmap_data(self, days_back=30):
        """
        Return per-state aggregated event data for the SOC geospatial heatmap.
        Called from JS via RPC — returns list of state dicts.
        """
        try:
            email, password = self._get_credentials()
            opener, csrf    = _acled_session(email, password)
        except Exception as e:
            _logger.error("ACLED heatmap login failed: %s", e)
            return []

        date_from = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        params = {
            'country':          'Nigeria',
            'event_date':       date_from,
            'event_date_where': '>=',
            'fields':           'event_date|event_type|admin1|admin2|location|latitude|longitude|fatalities|disorder_type',
            'limit':            1000,
            '_format':          'json',
        }

        try:
            data   = _acled_fetch(opener, csrf, params)
            events = data.get('data', [])
        except Exception as e:
            _logger.error("ACLED heatmap fetch failed: %s", e)
            return []

        state_data = {}
        for ev in events:
            state = ev.get('admin1', 'Unknown')
            if state not in state_data:
                state_data[state] = {
                    'state':      state,
                    'total':      0,
                    'fatalities': 0,
                    'battles':    0,
                    'violence':   0,
                    'protests':   0,
                    'lat':        float(ev.get('latitude',  0) or 0),
                    'lng':        float(ev.get('longitude', 0) or 0),
                }
            d  = state_data[state]
            et = ev.get('event_type', '')
            d['total']      += 1
            d['fatalities'] += int(ev.get('fatalities', 0) or 0)
            if et in ('Battles', 'Explosions/Remote violence'):
                d['battles']  += 1
            elif et == 'Violence against civilians':
                d['violence'] += 1
            elif et in ('Protests', 'Riots'):
                d['protests'] += 1

        return list(state_data.values())

    @api.model
    def get_recent_events_for_brief(self, hours_back=24):
        """
        Return raw recent events for the Daily Brief generator.
        Called from ai_daily_brief.py before Claude prompt assembly.
        """
        try:
            email, password = self._get_credentials()
            opener, csrf    = _acled_session(email, password)
        except Exception as e:
            _logger.error("ACLED brief login failed: %s", e)
            return []

        date_from = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        params = {
            'country':          'Nigeria',
            'event_date':       date_from,
            'event_date_where': '>=',
            'limit':            100,
            '_format':          'json',
        }

        try:
            data = _acled_fetch(opener, csrf, params)
            return data.get('data', [])
        except Exception as e:
            _logger.error("ACLED brief fetch failed: %s", e)
            return []
