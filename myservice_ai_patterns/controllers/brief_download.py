# -*- coding: utf-8 -*-
"""
controllers/brief_download.py
NRS myservice — Intelligence Brief Secure Download Controller

Handles:
  - Clearance level check (user vs brief classification)
  - Download log creation (user, timestamp, IP, ref)
  - Watermark parameter injection into PDF render context
  - PDF generation and stream to browser
"""

from odoo import http, fields
from odoo.http import request, content_disposition
import logging

_logger = logging.getLogger(__name__)

# ── Clearance hierarchy ────────────────────────────────────────────────────────
CLEARANCE_ORDER = ['restricted', 'confidential', 'secret', 'top_secret']

# Maps Odoo security groups to clearance levels
GROUP_CLEARANCE = {
    'myservice_security.group_security_officer':  'confidential',
    'myservice_security.group_security_manager':  'secret',
    'base.group_system':                           'top_secret',
}


def _get_user_clearance(user):
    """Return the highest clearance level the user holds."""
    clearance = 'restricted'   # default — all security staff
    for group_ref, level in GROUP_CLEARANCE.items():
        if user.has_group(group_ref):
            if CLEARANCE_ORDER.index(level) > CLEARANCE_ORDER.index(clearance):
                clearance = level
    return clearance


class BriefDownloadController(http.Controller):

    @http.route('/security/brief/download/<int:brief_id>', type='http',
                auth='user', methods=['GET'])
    def download_brief(self, brief_id, **kwargs):
        """
        Secure brief download endpoint.
        1. Validates brief exists and is released
        2. Checks user clearance vs brief classification
        3. Creates download log record
        4. Generates PDF with dynamic watermark
        5. Streams PDF to browser
        """
        Brief = request.env['ai.daily.brief'].sudo()
        brief = Brief.browse(brief_id)

        if not brief.exists():
            return request.not_found()

        # ── 1. Brief must be released ────────────────────────────────────────
        if brief.state != 'released':
            return request.make_response(
                '<h3>Brief not available for download.</h3>'
                '<p>This brief has not been released. Status: '
                f'<strong>{brief.state}</strong></p>',
                headers=[('Content-Type', 'text/html')]
            )

        # ── 2. Clearance check ───────────────────────────────────────────────
        user = request.env.user
        user_clearance = _get_user_clearance(user)
        brief_level    = brief.classification

        if CLEARANCE_ORDER.index(user_clearance) < CLEARANCE_ORDER.index(brief_level):
            _logger.warning(
                'SECURITY ALERT: User %s (clearance: %s) attempted to download '
                'brief %s (classification: %s)',
                user.name, user_clearance, brief.ref, brief_level
            )
            return request.make_response(
                f'<h3>ACCESS DENIED</h3>'
                f'<p>Your clearance level ({user_clearance.upper()}) is insufficient '
                f'for this document ({brief_level.upper().replace("_", " ")}).</p>',
                headers=[('Content-Type', 'text/html')]
            )

        # ── 3. Check NEED TO KNOW / EYES ONLY distribution ──────────────────
        if brief.distribution_caveat in ('need_to_know', 'eyes_only', 'limited'):
            if brief.distribution_list and user not in brief.distribution_list:
                _logger.warning(
                    'SECURITY: User %s not on distribution list for brief %s',
                    user.name, brief.ref
                )
                return request.make_response(
                    '<h3>ACCESS DENIED</h3>'
                    '<p>You are not on the distribution list for this brief.</p>',
                    headers=[('Content-Type', 'text/html')]
                )

        # ── 4. Get user IP address ───────────────────────────────────────────
        ip_address = (
            request.httprequest.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.httprequest.remote_addr
            or 'Unknown'
        )

        # ── 5. Create download log ────────────────────────────────────────────
        DownloadLog = request.env['ai.brief.download.log'].sudo()
        download_datetime_str = fields.Datetime.now().strftime('%d %b %Y %H:%M:%S')
        download_ref = request.env['ir.sequence'].sudo().next_by_code('nrs.brief.download')

        watermark_line1 = f'DOWNLOADED BY: {user.name.upper()}'
        watermark_line2 = f'DATE/TIME: {download_datetime_str}  |  REF: {download_ref}'
        watermark_line3 = f'NRS INTERNAL  |  {brief.classification_label}  |  UNAUTHORISED DISCLOSURE IS AN OFFENCE'

        log = DownloadLog.create({
            'brief_id':          brief.id,
            'user_id':           user.id,
            'download_ref':      download_ref,
            'download_datetime': fields.Datetime.now(),
            'ip_address':        ip_address,
            'brief_format':      brief.brief_format,
            'classification':    brief.classification_label,
            'watermark_text':    f'{watermark_line1}\n{watermark_line2}\n{watermark_line3}',
        })

        _logger.info(
            'INTEL BRIEF DOWNLOAD: ref=%s | user=%s | ip=%s | brief=%s | classification=%s',
            download_ref, user.name, ip_address, brief.ref, brief.classification_label
        )

        # ── 6. Generate PDF with watermark context ────────────────────────────
        # We pass watermark variables through the report's docargs context
        report_action = request.env.ref(
            'myservice_ai_patterns.action_report_intelligence_brief')

        pdf_content, content_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'myservice_ai_patterns.report_intelligence_brief_document',
            [brief.id],
            data={
                'watermark_line1':  watermark_line1,
                'watermark_line2':  watermark_line2,
                'watermark_line3':  watermark_line3,
                'download_ref':     download_ref,
                'downloaded_by':    user.name,
                'download_datetime': download_datetime_str,
                'ip_address':       ip_address,
            }
        )

        # ── 7. Stream PDF ─────────────────────────────────────────────────────
        filename = (
            f"NRS_INTEL_{brief.brief_format.upper()}_"
            f"{brief.date}_{download_ref}.pdf"
        )

        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', content_disposition(filename)),
            ('X-Download-Ref', download_ref),
            ('Cache-Control', 'no-store, no-cache, must-revalidate'),
            ('Pragma', 'no-cache'),
        ]

        return request.make_response(pdf_content, headers=headers)

    @http.route('/security/brief/generate', type='json',
                auth='user', methods=['POST'])
    def generate_brief_manual(self, brief_format, date_from, date_to=None,
                               classification='confidential', **kwargs):
        """
        Manual brief generation endpoint.
        Allows backend users to generate briefs for custom date ranges.
        """
        if not request.env.user.has_group('myservice_security.group_security_officer'):
            return {'error': 'Insufficient permissions'}

        try:
            brief = request.env['ai.daily.brief'].sudo().create({
                'name':           f"NRS Intelligence Brief — {date_from} (Manual)",
                'date':           date_from,
                'brief_format':   brief_format,
                'classification': classification,
                'state':          'draft',
            })
            brief.action_generate_ai()
            return {
                'success': True,
                'brief_id': brief.id,
                'brief_ref': brief.ref,
                'state': brief.state,
            }
        except Exception as e:
            _logger.error('Manual brief generation failed: %s', e)
            return {'error': str(e)}

    @http.route('/security/brief/log/<int:brief_id>', type='json',
                auth='user', methods=['POST'])
    def get_download_log(self, brief_id, **kwargs):
        """Return download log for a brief (manager only)."""
        if not request.env.user.has_group('myservice_security.group_security_manager'):
            return {'error': 'Access denied'}

        logs = request.env['ai.brief.download.log'].sudo().search(
            [('brief_id', '=', brief_id)], order='download_datetime desc')

        return [{
            'ref':       l.download_ref,
            'user':      l.user_id.name,
            'datetime':  l.download_datetime.strftime('%d %b %Y %H:%M:%S') if l.download_datetime else '',
            'ip':        l.ip_address,
            'format':    l.brief_format,
        } for l in logs]
