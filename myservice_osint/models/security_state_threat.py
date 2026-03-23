from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SecurityStateThreat(models.Model):
    _inherit = 'security.state.threat'

    # ── Extended scoring fields ───────────────────────────────────────
    composite_score = fields.Float(
        string='Composite Score (0–100)',
        default=0.0, readonly=True)
    score_delta = fields.Float(
        string='Score Change', readonly=True,
        help='Change from previous computation')
    previous_level = fields.Selection([
        ('green',  'Low'),
        ('yellow', 'Elevated'),
        ('orange', 'High'),
        ('red',    'Critical'),
    ], string='Previous Level', readonly=True)

    # ── 6 dimension scores ────────────────────────────────────────────
    dim_armed_conflict  = fields.Float(string='Armed Conflict (30%)', readonly=True)
    dim_civil_unrest    = fields.Float(string='Civil Unrest (20%)', readonly=True)
    dim_internal_incidents = fields.Float(string='Internal Incidents (20%)', readonly=True)
    dim_watchlist       = fields.Float(string='Watchlist Activity (15%)', readonly=True)
    dim_media_sentiment = fields.Float(string='Media Sentiment (10%)', readonly=True)
    dim_humanitarian    = fields.Float(string='Humanitarian Alerts (5%)', readonly=True)

    score_computed_at = fields.Datetime(
        string='Last Computed', readonly=True)
    osint_entry_count = fields.Integer(
        string='OSINT Entries (30d)', readonly=True)
    incident_count    = fields.Integer(
        string='Internal Incidents (30d)', readonly=True)

    @api.model
    def recompute_all(self):
        """
        Recompute threat scores for all 37 states.
        Called by scheduled action daily at 03:00.
        Weights: Armed Conflict 30%, Civil Unrest 20%,
                 Internal Incidents 20%, Watchlist 15%,
                 Media Sentiment 10%, Humanitarian 5%
        """
        from datetime import timedelta
        now = fields.Datetime.now()
        since_30d = now - timedelta(days=30)
        since_7d  = now - timedelta(days=7)

        states = self.search([])
        for state in states:
            sname = state.name
            try:
                # ── Dim 1: Armed conflict (ACLED) ─────────────────────
                acled = self.env['osint.feed.entry'].search([
                    ('state_name', 'ilike', sname),
                    ('source_type', '=', 'acled'),
                    ('event_date',  '>=', since_30d),
                ])
                fatal_total = sum(e.fatalities for e in acled)
                d1 = min(100, len(acled) * 8 + fatal_total * 3)

                # ── Dim 2: Civil unrest (GDELT + RSS) ─────────────────
                unrest = self.env['osint.feed.entry'].search([
                    ('state_name', 'ilike', sname),
                    ('source_type', 'in', ['gdelt', 'rss']),
                    ('event_date',  '>=', since_7d),
                ])
                d2 = min(100, len(unrest) * 6)

                # ── Dim 3: Internal incidents ──────────────────────────
                incidents = self.env['security.incident'].search([
                    ('location_id.name', 'ilike', sname),
                    ('date_incident', '>=', since_30d),
                ])
                severity_w = {'critical':20,'high':12,'medium':6,'low':2}
                d3 = min(100, sum(severity_w.get(i.severity, 4) for i in incidents))

                # ── Dim 4: Watchlist activity ──────────────────────────
                wl = self.env['security.watchlist'].search([
                    ('last_sighted_location_id.name', 'ilike', sname),
                ])
                threat_w = {'critical':25,'high':15,'medium':8,'low':4}
                d4 = min(100, sum(threat_w.get(w.threat_level, 5) for w in wl))

                # ── Dim 5: Media sentiment ─────────────────────────────
                media = self.env['osint.feed.entry'].search([
                    ('state_name', 'ilike', sname),
                    ('source_type', 'in', ['rss', 'twitter', 'gdelt']),
                    ('threat_level', 'in', ['critical','high','elevated','medium']),
                    ('event_date', '>=', since_7d),
                ])
                d5 = min(100, len(media) * 10)

                # ── Dim 6: Humanitarian alerts ─────────────────────────
                relief = self.env['osint.feed.entry'].search([
                    ('state_name', 'ilike', sname),
                    ('source_type', '=', 'reliefweb'),
                    ('event_date', '>=', since_30d),
                ])
                d6 = min(100, len(relief) * 15)

                # ── Composite (weighted) ───────────────────────────────
                composite = (
                    d1 * 0.30 + d2 * 0.20 + d3 * 0.20 +
                    d4 * 0.15 + d5 * 0.10 + d6 * 0.05
                )

                # ── Map to threat level ────────────────────────────────
                if composite >= 70:   new_level = 'red'
                elif composite >= 45: new_level = 'orange'
                elif composite >= 20: new_level = 'yellow'
                else:                 new_level = 'green'

                delta = composite - (state.composite_score or 0)
                old_level = state.threat_level

                state.write({
                    'composite_score':        round(composite, 1),
                    'score_delta':            round(delta, 1),
                    'previous_level':         old_level,
                    'dim_armed_conflict':     round(d1, 1),
                    'dim_civil_unrest':       round(d2, 1),
                    'dim_internal_incidents': round(d3, 1),
                    'dim_watchlist':          round(d4, 1),
                    'dim_media_sentiment':    round(d5, 1),
                    'dim_humanitarian':       round(d6, 1),
                    'threat_level':           new_level,
                    'score_computed_at':      now,
                    'osint_entry_count':      len(acled) + len(unrest),
                    'incident_count':         len(incidents),
                    'last_updated':           now,
                })

                # Alert on tier change
                if old_level != new_level:
                    _logger.info(
                        "State threat change: %s %s → %s (score: %.1f)",
                        sname, old_level, new_level, composite)

            except Exception as e:
                _logger.error("Score compute error for %s: %s", sname, e)

        self.env.cr.commit()
        _logger.info("Threat recompute complete for %d states", len(states))
