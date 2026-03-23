from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
import json
import urllib.request
import urllib.parse

_logger = logging.getLogger(__name__)


class OsintSourceConfig(models.Model):
    """
    Configuration for each OSINT data source.
    One record per source. Each source has its own adapter class below.
    """
    _name = 'osint.source.config'
    _description = 'OSINT Source Configuration'
    _rec_name = 'name'

    name = fields.Char(required=True)
    source_type = fields.Selection([
        ('acled',      'ACLED — Armed Conflict Data'),
        ('gdelt',      'GDELT — Global Events Database'),
        ('rss',        'RSS Feed — News Media'),
        ('reliefweb',  'ReliefWeb — OCHA Humanitarian'),
        ('twitter',    'Twitter/X — Social Monitoring'),
        ('telegram',   'Telegram — Channel Monitor'),
        ('manual',     'Manual Entry Only'),
    ], required=True)

    active = fields.Boolean(default=True)
    fetch_interval_hours = fields.Integer(
        string='Fetch Every (hours)', default=24)
    last_fetched = fields.Datetime(string='Last Fetched', readonly=True)
    last_fetch_count = fields.Integer(
        string='Last Fetch Count', readonly=True)
    total_entries = fields.Integer(
        string='Total Entries',
        compute='_compute_total_entries')

    # ── Auth ──────────────────────────────────────────────────────────
    acled_email = fields.Char(string='ACLED Email')
    acled_password = fields.Char(string='ACLED Password', password=True)
    acled_token = fields.Char(string='ACLED Access Token', readonly=True)
    acled_token_expiry = fields.Datetime(
        string='Token Expiry', readonly=True)

    twitter_bearer_token = fields.Char(
        string='Twitter Bearer Token', password=True)
    twitter_keywords = fields.Char(
        string='Keywords',
        default='NRS tax office,FIRS Nigeria,tax enforcement Nigeria',
        help='Comma-separated keywords to monitor')

    telegram_bot_token = fields.Char(
        string='Telegram Bot Token', password=True)
    telegram_channels = fields.Char(
        string='Channel usernames',
        help='Comma-separated public channel usernames e.g. channelname1,channelname2')

    # ── RSS ───────────────────────────────────────────────────────────
    rss_urls = fields.Text(
        string='RSS Feed URLs',
        help='One URL per line',
        default='''https://www.premiumtimesng.com/feed
https://punchng.com/feed
https://www.vanguardngr.com/feed
https://www.dailytrust.com/feed
https://guardian.ng/feed''')

    # ── Filters ───────────────────────────────────────────────────────
    nigeria_only = fields.Boolean(
        string='Nigeria Only', default=True)
    keywords_filter = fields.Char(
        string='Keyword Filter',
        default='attack,bomb,bandit,kidnap,protest,unrest,robbery,theft,fire,flood,crisis,violence,shooting,explosion,arrest,enforcement,tax',
        help='Comma-separated — only import entries matching these keywords')
    days_lookback = fields.Integer(
        string='Days Lookback', default=30,
        help='How many days back to fetch on first run')

    notes = fields.Text(string='Notes')

    @api.depends('source_type')
    def _compute_total_entries(self):
        for rec in self:
            rec.total_entries = self.env['osint.feed.entry'].search_count([
                ('source_config_id', '=', rec.id)])

    def action_fetch_now(self):
        self.ensure_one()
        count = self._run_fetch()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'OSINT Fetch Complete',
                'message': f'{count} new entries imported from {self.name}',
                'type': 'success',
                'sticky': False,
            }
        }

    def _run_fetch(self):
        self.ensure_one()
        _logger.info("OSINT fetch starting: %s (%s)", self.name, self.source_type)
        adapter = self._get_adapter()
        entries = adapter.fetch()
        count = 0
        for e in entries:
            if self._create_entry(e):
                count += 1
        self.write({
            'last_fetched': fields.Datetime.now(),
            'last_fetch_count': count,
        })
        _logger.info("OSINT fetch complete: %s — %d new entries", self.name, count)
        return count

    def _get_adapter(self):
        if self.source_type == 'acled':
            return AcledAdapter(self)
        elif self.source_type == 'gdelt':
            return GdeltAdapter(self)
        elif self.source_type == 'rss':
            return RssAdapter(self)
        elif self.source_type == 'reliefweb':
            return ReliefWebAdapter(self)
        else:
            return NullAdapter(self)

    def _create_entry(self, data):
        """Create an osint.feed.entry if not duplicate. Returns True if created."""
        import hashlib
        dedup = hashlib.md5(
            f"{data.get('source_type','')}{data.get('title','')}{data.get('event_date','')}".encode()
        ).hexdigest()
        existing = self.env['osint.feed.entry'].search(
            [('duplicate_hash', '=', dedup)], limit=1)
        if existing:
            return False
        state = data.get('state_name', '')
        threat = self._classify_threat(data.get('title','') + ' ' + data.get('summary',''), state)
        self.env['osint.feed.entry'].create({
            'source_config_id': self.id,
            'source_type':      self.source_type,
            'source_name':      self.name,
            'title':            data.get('title', '')[:500],
            'summary':          data.get('summary', '')[:2000],
            'state_name':       state,
            'event_date':       data.get('event_date') or fields.Datetime.now(),
            'latitude':         data.get('lat') or 0.0,
            'longitude':        data.get('lng') or 0.0,
            'raw_score':        data.get('raw_score') or 0,
            'threat_level':     data.get('threat_level') or threat,
            'event_type':       data.get('event_type', ''),
            'fatalities':       data.get('fatalities') or 0,
            'source_url':       data.get('url', '')[:500],
            'duplicate_hash':   dedup,
            'is_verified':      data.get('is_verified', False),
            'added_by':         self.env.user.id,
        })
        return True

    def _classify_threat(self, text, state):
        """Simple keyword-based threat classification."""
        text = text.upper()
        critical = ['BOMB','EXPLOSION','ARMED ROBBERY','KIDNAP','MASSACRE','TERRORIST','IED']
        high = ['ATTACK','BANDIT','SHOOTING','AMBUSH','ABDUCT','CASUALT','FATALI','RIOT']
        medium = ['PROTEST','UNREST','ARREST','CLASH','THEFT','ROBBERY','FIRE','FLOOD']
        elevated_states = ['BORNO','ZAMFARA','KADUNA','KATSINA','SOKOTO','NIGER','PLATEAU']
        for w in critical:
            if w in text: return 'critical'
        for w in high:
            if w in text: return 'high'
        for w in medium:
            if w in text: return 'medium'
        if state and state.upper() in elevated_states:
            return 'elevated'
        return 'info'

    @api.model
    def run_all_scheduled(self):
        """Called by cron — fetch all active sources due for refresh."""
        from datetime import timedelta
        sources = self.search([('active', '=', True),
                               ('source_type', '!=', 'manual')])
        for src in sources:
            due = True
            if src.last_fetched:
                delta = fields.Datetime.now() - src.last_fetched
                due = delta.total_seconds() / 3600 >= src.fetch_interval_hours
            if due:
                try:
                    src._run_fetch()
                except Exception as e:
                    _logger.error("OSINT fetch error for %s: %s", src.name, e)


# ══════════════════════════════════════════════════════════════════════
# ADAPTERS
# ══════════════════════════════════════════════════════════════════════

class NullAdapter:
    def __init__(self, config): self.config = config
    def fetch(self): return []


class AcledAdapter:
    """
    ACLED REST API adapter.
    Uses OAuth2 password grant. Fetches Nigeria conflict events.
    API: https://acleddata.com/api/acled/read
    """
    TOKEN_URL = 'https://acleddata.com/oauth/token'
    DATA_URL  = 'https://acleddata.com/api/acled/read'

    def __init__(self, config):
        self.config = config

    def _get_token(self):
        """Fetch or reuse OAuth token."""
        from datetime import timedelta
        cfg = self.config
        now = fields.Datetime.now()
        # Reuse if valid for >5 more minutes
        if (cfg.acled_token and cfg.acled_token_expiry
                and cfg.acled_token_expiry > now + timedelta(minutes=5)):
            return cfg.acled_token

        if not cfg.acled_email or not cfg.acled_password:
            raise Exception('ACLED email and password not configured')

        data = urllib.parse.urlencode({
            'username':   cfg.acled_email,
            'password':   cfg.acled_password,
            'grant_type': 'password',
            'client_id':  'acled',
        }).encode()
        req = urllib.request.Request(
            self.TOKEN_URL,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        token = result.get('access_token')
        if not token:
            raise Exception(f"ACLED auth failed: {result}")

        expiry = now + timedelta(seconds=result.get('expires_in', 86400))
        cfg.write({'acled_token': token, 'acled_token_expiry': expiry})
        cfg.env.cr.commit()
        return token

    def fetch(self):
        from datetime import date, timedelta
        token = self._get_token()
        days = self.config.days_lookback or 30
        since = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        today = date.today().strftime('%Y-%m-%d')

        params = urllib.parse.urlencode({
            'country':          'Nigeria',
            'event_date':       f"{since}|{today}",
            'event_date_where': 'BETWEEN',
            'fields':           'event_id_cnty|event_date|event_type|sub_event_type|actor1|admin1|admin2|location|latitude|longitude|fatalities|notes',
            'limit':            500,
            '_format':          'json',
        })
        url = f"{self.DATA_URL}?{params}"
        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {token}',
                     'User-Agent': 'NRS-myservice/1.0'},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        events = result.get('data', [])
        _logger.info("ACLED: %d events fetched for Nigeria", len(events))

        entries = []
        for e in events:
            entries.append({
                'title':       f"{e.get('event_type','')} — {e.get('location','')} ({e.get('admin1','')})",
                'summary':     e.get('notes', '')[:2000],
                'state_name':  e.get('admin1', ''),
                'event_date':  e.get('event_date', ''),
                'lat':         float(e.get('latitude') or 0),
                'lng':         float(e.get('longitude') or 0),
                'fatalities':  int(e.get('fatalities') or 0),
                'event_type':  e.get('event_type', ''),
                'raw_score':   min(100, (int(e.get('fatalities') or 0) * 5) + 20),
                'is_verified': True,
                'source_type': 'acled',
            })
        return entries


class GdeltAdapter:
    """
    GDELT 2.0 API — free, no auth required.
    Queries for Nigeria-related security events.
    """
    BASE_URL = 'https://api.gdeltproject.org/api/v2/doc/doc'

    def __init__(self, config):
        self.config = config

    def fetch(self):
        queries = [
            'Nigeria security attack violence',
            'Nigeria bandit kidnap Borno Zamfara',
            'Nigeria tax office protest unrest',
        ]
        entries = []
        for q in queries:
            try:
                params = urllib.parse.urlencode({
                    'query':      q,
                    'mode':       'artlist',
                    'maxrecords': 50,
                    'format':     'json',
                    'timespan':   '7d',
                    'sourcelang': 'english',
                })
                url = f"{self.BASE_URL}?{params}"
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'NRS-myservice/1.0'})
                import time
                time.sleep(1)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    result = json.loads(resp.read())
                articles = result.get('articles', [])
                for a in articles:
                    title = a.get('title', '')
                    state = self._extract_nigeria_state(title + ' ' + a.get('url',''))
                    entries.append({
                        'title':       title[:500],
                        'summary':     f"Source: {a.get('domain','')} | {a.get('url','')}",
                        'state_name':  state,
                        'event_date':  a.get('seendate', '')[:10],
                        'url':         a.get('url', ''),
                        'source_type': 'gdelt',
                        'is_verified': False,
                    })
            except Exception as e:
                _logger.warning("GDELT fetch error: %s", e)
        return entries

    def _extract_nigeria_state(self, text):
        states = ['Lagos','Abuja','FCT','Kano','Kaduna','Borno','Zamfara',
                  'Rivers','Delta','Enugu','Anambra','Imo','Ogun','Oyo',
                  'Katsina','Sokoto','Plateau','Niger','Kogi','Kwara']
        for s in states:
            if s.lower() in text.lower():
                return s
        return 'Nigeria'


class RssAdapter:
    """
    RSS feed adapter for Nigerian news sources.
    Parses standard RSS/Atom feeds.
    """
    def __init__(self, config):
        self.config = config

    def fetch(self):
        import xml.etree.ElementTree as ET
        urls = [u.strip() for u in (self.config.rss_urls or '').split('\n') if u.strip()]
        keywords = [k.strip().lower() for k in
                    (self.config.keywords_filter or '').split(',') if k.strip()]
        entries = []

        for url in urls:
            try:
                import time
                time.sleep(0.5)
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'NRS-myservice/1.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read()
                root = ET.fromstring(content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}

                # RSS 2.0
                items = root.findall('.//item')
                # Atom
                if not items:
                    items = root.findall('.//atom:entry', ns) or root.findall('.//entry')

                for item in items[:20]:
                    title = (item.findtext('title') or
                             item.findtext('{http://www.w3.org/2005/Atom}title') or '')
                    desc  = (item.findtext('description') or
                             item.findtext('{http://www.w3.org/2005/Atom}summary') or
                             item.findtext('{http://www.w3.org/2005/Atom}content') or '')
                    link  = (item.findtext('link') or
                             item.findtext('{http://www.w3.org/2005/Atom}id') or '')
                    pubdate = (item.findtext('pubDate') or
                               item.findtext('{http://www.w3.org/2005/Atom}published') or '')

                    combined = (title + ' ' + desc).lower()
                    if keywords and not any(k in combined for k in keywords):
                        continue

                    state = GdeltAdapter(self.config)._extract_nigeria_state(title + ' ' + desc)
                    entries.append({
                        'title':       title[:500],
                        'summary':     desc[:1000],
                        'state_name':  state,
                        'event_date':  pubdate[:10] if pubdate else '',
                        'url':         link[:500],
                        'source_type': 'rss',
                        'is_verified': False,
                    })
            except Exception as e:
                _logger.warning("RSS fetch error for %s: %s", url, e)
        return entries


class ReliefWebAdapter:
    """
    ReliefWeb API — free, no auth.
    Fetches OCHA situation reports and alerts for Nigeria.
    """
    BASE_URL = 'https://api.reliefweb.int/v1/reports'

    def __init__(self, config):
        self.config = config

    def fetch(self):
        payload = json.dumps({
            'filter': {
                'operator': 'AND',
                'conditions': [
                    {'field': 'country.name', 'value': 'Nigeria'},
                    {'field': 'theme.name', 'value': 'Security',
                     'operator': 'OR'},
                ]
            },
            'fields': {'include': ['title','body-html','date','url','source']},
            'sort': ['date:desc'],
            'limit': 20,
        }).encode()

        req = urllib.request.Request(
            f"{self.BASE_URL}?appname=nrs-myservice",
            data=payload,
            headers={'Content-Type': 'application/json',
                     'User-Agent': 'NRS-myservice/1.0'},
            method='POST',
        )
        entries = []
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read())
            for r in result.get('data', []):
                f = r.get('fields', {})
                entries.append({
                    'title':       f.get('title', '')[:500],
                    'summary':     (f.get('body-html') or '')[:1000],
                    'state_name':  'Nigeria',
                    'event_date':  (f.get('date', {}) or {}).get('created', '')[:10],
                    'url':         f.get('url', ''),
                    'source_type': 'reliefweb',
                    'is_verified': True,
                })
        except Exception as e:
            _logger.warning("ReliefWeb fetch error: %s", e)
        return entries
