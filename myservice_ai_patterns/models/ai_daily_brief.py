from odoo import models, fields, api
import json
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class AiDailyBrief(models.Model):
    """
    AI-generated daily intelligence briefing.
    Synthesises all overnight alerts, OSINT entries, and
    state threat changes into a single morning briefing.
    Generated daily at 06:00 and emailed to security leads.
    """
    _name = 'ai.daily.brief'
    _description = 'AI Daily Intelligence Brief'
    _order = 'brief_date desc'
    _rec_name = 'brief_date'

    brief_date  = fields.Date(string='Brief Date', required=True)
    subject     = fields.Char(string='Subject Line')
    headline    = fields.Text(string='Headline Summary')
    full_brief  = fields.Html(string='Full Brief')
    raw_json    = fields.Text(string='Raw AI Output', readonly=True)

    critical_alerts = fields.Integer(string='Critical Alerts', readonly=True)
    high_alerts     = fields.Integer(string='High Alerts', readonly=True)
    states_elevated = fields.Char(string='States Elevated', readonly=True)
    new_osint       = fields.Integer(string='New OSINT Entries', readonly=True)

    emailed_to      = fields.Char(string='Emailed To', readonly=True)
    email_sent_at   = fields.Datetime(string='Email Sent At', readonly=True)
    whatsapp_sent   = fields.Boolean(string='WhatsApp Sent', readonly=True)

    @api.model
    def generate_daily_brief(self):
        """Generate and distribute the daily intelligence brief."""
        from .ai_pattern_engine import _call_claude
        now   = fields.Datetime.now()
        today = fields.Date.today()
        since = now - timedelta(hours=24)

        # ── Pull live ACLED events for Nigeria (last 24h) ─────────────
        acled_events = []
        try:
            acled_events = self.env['acled.sync.log'].get_recent_events_for_brief(hours_back=24)
        except Exception as e:
            _logger.warning("ACLED data unavailable for brief: %s", e)

        acled_summary = [{
            'event_type': e.get('event_type'),
            'location':   '%s, %s' % (e.get('location', ''), e.get('admin1', '')),
            'fatalities': e.get('fatalities', 0),
            'actor':      e.get('actor1', ''),
            'notes':      (e.get('notes', '') or '')[:200],
        } for e in acled_events[:15]]

        # ── Gather data ────────────────────────────────────────────────
        new_alerts = self.env['ai.pattern.alert'].search([
            ('create_date', '>=', since)])
        new_osint = self.env['osint.feed.entry'].search([
            ('create_date', '>=', since)])
        critical_states = self.env['security.state.threat'].search([
            ('threat_level', 'in', ['red', 'orange'])])
        elevated_states = self.env['security.state.threat'].search([
            ('threat_level', '=', 'orange')])

        alert_summary = [{
            'type':       a.pattern_type,
            'title':      a.title,
            'severity':   a.severity,
            'confidence': a.confidence,
            'summary':    a.ai_summary,
        } for a in new_alerts[:10]]

        osint_summary = [{
            'source':  e.source_type,
            'title':   e.title,
            'state':   e.state_name,
            'threat':  e.threat_level,
        } for e in new_osint.filtered(
            lambda x: x.threat_level in ['critical','high','elevated'])[:10]]

        critical_state_names = [s.name for s in critical_states]
        elevated_state_names = [s.name for s in elevated_states]

        prompt = f"""Generate a daily security intelligence brief for NRS (Nigeria Revenue Service) 
facilities management. Today is {today}. This brief covers the last 24 hours.

DATA SUMMARY:
- New AI pattern alerts: {len(new_alerts)} ({len([a for a in new_alerts if a.severity == 'critical'])} critical, {len([a for a in new_alerts if a.severity == 'high'])} high)
- New OSINT entries: {len(new_osint)}
- States at critical/red level: {critical_state_names}
- States at high/orange level: {elevated_state_names}

TOP ALERTS (last 24h):
{json.dumps(alert_summary, indent=2)}

TOP THREAT OSINT (last 24h):
{json.dumps(osint_summary, indent=2)}

LIVE ACLED CONFLICT EVENTS (last 24h from ACLED database):
{json.dumps(acled_summary, indent=2)}

Generate a professional intelligence brief. Write for a security director who reads 
this over morning coffee and needs to brief the MD within 30 minutes.

Respond with ONLY this JSON:
{{
  "subject": "NRS Security Brief — {today} — [one-line situation summary]",
  "headline": "2-3 sentence executive summary of the security situation",
  "threat_level_today": "critical|high|elevated|normal",
  "sections": [
    {{
      "heading": "Key Threats",
      "content": "paragraph text"
    }},
    {{
      "heading": "Active Patterns",  
      "content": "paragraph text"
    }},
    {{
      "heading": "State Situation",
      "content": "paragraph text"
    }},
    {{
      "heading": "Recommended Actions for Today",
      "content": "paragraph text with bullet points"
    }}
  ],
  "whatsapp_summary": "Short 3-line WhatsApp message version of this brief"
}}"""

        try:
            result = _call_claude(prompt, max_tokens=2000)

            # Build HTML brief
            html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;color:#1A1A1A">
  <div style="background:#1A1A1A;padding:20px 24px;border-bottom:4px solid #E85426">
    <h2 style="color:#fff;margin:0;font-size:18px">NRS Security Intelligence Brief</h2>
    <p style="color:rgba(255,255,255,0.6);margin:4px 0 0;font-size:13px">{today}</p>
  </div>
  <div style="background:#E85426;padding:12px 24px">
    <p style="color:#fff;margin:0;font-size:14px;font-weight:600">
      {result.get('headline','')}
    </p>
  </div>
  <div style="padding:20px 24px">
"""
            for section in result.get('sections', []):
                html += f"""
    <h3 style="color:#E85426;font-size:14px;border-bottom:1px solid #eee;
               padding-bottom:6px;margin-top:20px">{section['heading']}</h3>
    <p style="font-size:13px;line-height:1.6;color:#333">
      {section['content'].replace(chr(10), '<br>')}
    </p>"""

            html += f"""
  </div>
  <div style="background:#f8f8f8;padding:12px 24px;border-top:1px solid #eee;
              font-size:11px;color:#888">
    Generated by SecureOps AI · {now.strftime('%d %b %Y %H:%M')} · WestMetro Limited
  </div>
</div>"""

            # Save brief
            brief = self.create({
                'brief_date':     today,
                'subject':        result.get('subject', f'NRS Security Brief — {today}')[:200],
                'headline':       result.get('headline', ''),
                'full_brief':     html,
                'raw_json':       json.dumps(result),
                'critical_alerts': len([a for a in new_alerts if a.severity == 'critical']),
                'high_alerts':    len([a for a in new_alerts if a.severity == 'high']),
                'states_elevated': ', '.join(critical_state_names + elevated_state_names),
                'new_osint':      len(new_osint),
            })

            # Email to security leads
            brief._send_email()

            # WhatsApp summary
            if result.get('whatsapp_summary'):
                brief._send_whatsapp(result['whatsapp_summary'])

            _logger.info("Daily brief generated and distributed: %s", brief.subject)
            return brief

        except Exception as e:
            _logger.error("Daily brief generation failed: %s", e, exc_info=True)
            return None

    def _send_email(self):
        """Email the brief to all users in the security admin group."""
        self.ensure_one()
        try:
            group = self.env.ref(
                'myservice_security.group_security_admin', raise_if_not_found=False)
            if not group:
                return
            recipients = group.users.mapped('email')
            if not recipients:
                return

            for email in recipients:
                self.env['mail.mail'].sudo().create({
                    'subject':    self.subject,
                    'email_to':   email,
                    'body_html':  self.full_brief,
                    'state':      'outgoing',
                }).send()

            self.write({
                'emailed_to': ', '.join(recipients),
                'email_sent_at': fields.Datetime.now(),
            })
            _logger.info("Daily brief emailed to: %s", ', '.join(recipients))
        except Exception as e:
            _logger.error("Brief email failed: %s", e)

    def _send_whatsapp(self, summary_text):
        """
        Send WhatsApp summary via Akraa WhatsApp integration.
        Falls back to logging if WhatsApp not configured.
        """
        self.ensure_one()
        _logger.info("WhatsApp brief: %s", summary_text)
        # TODO: Wire to Akraa WhatsApp API when available
        self.write({'whatsapp_sent': False})
