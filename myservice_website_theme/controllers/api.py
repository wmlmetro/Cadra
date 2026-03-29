import logging
from werkzeug.utils import redirect as wz_redirect
from odoo import http, SUPERUSER_ID
from odoo.http import request

_logger = logging.getLogger(__name__)


class NRSHomepageAPI(http.Controller):

    @http.route('/a/<string:asset_code>', type='http', auth='public', website=True)
    def asset_short_url(self, asset_code, **kwargs):
        """Short URL redirect for QR codes: /a/NRS-AST-000042 -> /asset-scan?code=..."""
        return wz_redirect('/asset-scan?code=%s' % asset_code, code=301)

    @http.route(
        '/api/myservice/form-data', type='json', auth='public',
        methods=['POST'], csrf=False,
    )
    def get_form_data(self, **kwargs):
        """Return dropdown data for the homepage quick-submit form."""
        env = request.env

        # Services
        services = env['generic.service'].sudo().search(
            [('active', '=', True)], order='sequence, name')

        # Request types via classifiers (only valid combos)
        classifiers = env['request.classifier'].sudo().search(
            [('active', '=', True)],
        )
        type_map = {}
        for clf in classifiers:
            t = clf.type_id
            if t.active and t.id not in type_map:
                type_map[t.id] = {
                    'id': t.id,
                    'name': t.name,
                    'service_id': clf.service_id.id if clf.service_id else None,
                }
        request_types = sorted(type_map.values(), key=lambda x: x['name'])

        # Locations (deduplicated, same logic as portal controller)
        all_locs = env['generic.location'].sudo().search(
            [('active', '=', True)], order='name')
        seen = set()
        locations = []
        for loc in all_locs:
            key = loc.name.strip().upper()
            if key not in seen:
                seen.add(key)
                locations.append({
                    'id': loc.id,
                    'name': loc.name,
                    'parent_id': loc.parent_id.id if loc.parent_id else None,
                    'parent_name': loc.parent_id.name if loc.parent_id else None,
                })

        return {
            'services': [{'id': s.id, 'name': s.name} for s in services],
            'request_types': request_types,
            'locations': locations,
        }

    @http.route(
        '/api/myservice/quick-submit', type='json', auth='public',
        methods=['POST'], csrf=False,
    )
    def quick_submit(self, **kwargs):
        """Handle homepage quick-submit form."""
        env = request.env

        # Resolve type_id — required
        type_id = None
        raw_type = kwargs.get('type_id')
        if raw_type:
            try:
                type_id = int(raw_type)
            except (ValueError, TypeError):
                pass

        if not type_id:
            # Fall back to first active type
            first_type = env['request.type'].sudo().search(
                [('active', '=', True)], limit=1)
            if first_type:
                type_id = first_type.id
            else:
                return {'success': False, 'error': 'No request type available'}

        req_type = env['request.type'].sudo().browse(type_id)
        if not req_type.exists():
            return {'success': False, 'error': 'Invalid request type'}

        # Build request text with reporter info
        lines = []
        if kwargs.get('reporter_name'):
            lines.append('Reported by: %s' % kwargs['reporter_name'])
        if kwargs.get('reporter_contact'):
            lines.append('Contact: %s' % kwargs['reporter_contact'])
        if lines:
            lines.append('')
        if kwargs.get('description'):
            lines.append(kwargs['description'])

        req_text = '<br/>'.join(lines) if lines else 'Quick facilities request'

        # Prepare creation data (mirrors WSD controller logic)
        vals = {
            'type_id': type_id,
            'request_text': req_text,
        }

        # Service
        raw_service = kwargs.get('service_id')
        if raw_service:
            try:
                svc = env['generic.service'].sudo().browse(int(raw_service))
                if svc.exists():
                    vals['service_id'] = svc.id
            except (ValueError, TypeError):
                pass

        # Location
        raw_loc = kwargs.get('location_id')
        if raw_loc:
            try:
                loc = env['generic.location'].sudo().browse(int(raw_loc))
                if loc.exists():
                    vals['generic_location_id'] = loc.id
            except (ValueError, TypeError):
                pass

        # Priority
        if kwargs.get('priority'):
            vals['priority'] = kwargs['priority']

        # Website channel
        channel = env.ref(
            'generic_request.request_channel_website',
            raise_if_not_found=False)
        if channel and channel.sudo().active:
            vals['channel_id'] = channel.id

        # Website
        website = env['website'].sudo().get_current_website()
        if website:
            vals['website_id'] = website.id

        # Author from contact info
        email = kwargs.get('reporter_contact', '')
        if '@' in email:
            partner_id = env['request.request'].sudo(
            )._get_or_create_partner_from_email(email, force_create=True)
            if partner_id:
                vals['author_id'] = partner_id

        try:
            req = env['request.request'].with_user(SUPERUSER_ID).create(vals)
            return {
                'success': True,
                'request_name': req.name,
                'request_id': req.id,
            }
        except Exception as e:
            _logger.exception('Quick-submit failed')
            return {'success': False, 'error': str(e)}
