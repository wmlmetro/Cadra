from odoo import http
from odoo.http import request
import json


class BarcodeStationController(http.Controller):

    # ── Backend JSON API ─────────────────────────────────────

    @http.route('/barcode/lookup', type='json', auth='user')
    def lookup_tag(self, query=''):
        """Look up asset by tag number or asset code."""
        if not query:
            return {'found': False, 'error': 'No query provided'}
        env = request.env
        # Search tag first
        tag = env['nrs.asset.tag.label'].search(
            [('name', '=', query.strip().upper()), ('state', '=', 'active')], limit=1)
        if not tag:
            # Try asset code
            asset = env['nrs.asset'].search(
                [('asset_code', '=', query.strip())], limit=1)
            if asset:
                tag = asset.active_tag_id
        if not tag or not tag.asset_id:
            return {'found': False, 'error': 'Tag or asset not found: %s' % query}
        asset = tag.asset_id
        return {
            'found': True,
            'tag_id': tag.id,
            'tag_number': tag.name,
            'tag_state': tag.state,
            'tag_date': str(tag.tag_date) if tag.tag_date else '',
            'asset_id': asset.id,
            'asset_name': asset.name,
            'asset_code': asset.asset_code or '',
            'category': asset.category_id.name if asset.category_id else '',
            'domain': dict(asset._fields['domain'].selection).get(asset.domain, '') if asset.domain else '',
            'location': asset.location_id.name if asset.location_id else '',
            'custodian': asset.custodian_id.name if asset.custodian_id else '',
            'condition': dict(asset._fields['condition'].selection).get(asset.condition, '') if asset.condition else '',
            'state': dict(asset._fields['state'].selection).get(asset.state, '') if asset.state else '',
            'last_service_date': str(asset.last_service_date) if asset.last_service_date else '',
            'next_service_date': str(asset.next_service_date) if asset.next_service_date else '',
            'sap_asset_number': asset.sap_asset_number or '',
            'import_source': asset.import_source or '',
        }

    @http.route('/barcode/kpis', type='json', auth='user')
    def get_kpis(self):
        """Return barcode station KPIs."""
        env = request.env
        Tag = env['nrs.asset.tag.label']
        Asset = env['nrs.asset']
        return {
            'total_assets': Asset.search_count([]),
            'active_tags': Tag.search_count([('state', '=', 'active')]),
            'pending_replacement': Tag.search_count([('state', '=', 'pending')]),
            'scrapped_tags': Tag.search_count([('state', '=', 'scrapped')]),
            'untagged': Asset.search_count([]) - Tag.search_count([('state', '=', 'active')]),
        }

    @http.route('/barcode/recent_tags', type='json', auth='user')
    def get_recent_tags(self, domain_filter='', limit=50):
        """Return recent active tags optionally filtered by domain."""
        env = request.env
        domain = [('state', 'in', ['active', 'pending'])]
        tags = env['nrs.asset.tag.label'].search(domain, order='create_date desc', limit=limit)
        result = []
        for tag in tags:
            asset = tag.asset_id
            if domain_filter and asset.domain != domain_filter:
                continue
            result.append({
                'tag_id': tag.id,
                'tag_number': tag.name,
                'tag_state': tag.state,
                'asset_id': asset.id,
                'asset_name': asset.name,
                'domain': asset.domain or '',
                'location': asset.location_id.name if asset.location_id else '',
                'condition': asset.condition or '',
            })
        return result

    @http.route('/barcode/print_url', type='json', auth='user')
    def get_print_url(self, tag_id, size='medium'):
        """Return the PDF print URL for a tag."""
        report_map = {
            'small':  'myservice_asset_register.action_report_asset_tag',
            'medium': 'myservice_asset_register.action_report_asset_tag',
            'large':  'myservice_asset_register.action_report_asset_tag',
            'sheet':  'myservice_asset_register.action_report_asset_tag_sheet',
        }
        report_name = report_map.get(size, report_map['medium'])
        return {
            'url': '/report/pdf/%s/%s' % (
                report_name.replace('.', '/'), tag_id)
        }

    # ── Portal routes ────────────────────────────────────────

    @http.route('/tags', type='http', auth='public', website=True)
    def barcode_portal(self, **kwargs):
        """Field team portal — no login required."""
        return request.render('myservice_barcode_station.portal_barcode_station', {})

    @http.route('/tags/lookup', type='json', auth='public')
    def portal_lookup(self, query=''):
        """Public lookup endpoint for portal scanner."""
        if not query:
            return {'found': False}
        env = request.env(user=request.env.ref('base.public_user').id)
        tag = env['nrs.asset.tag.label'].sudo().search(
            [('name', '=', query.strip().upper()), ('state', '=', 'active')], limit=1)
        if not tag:
            asset = env['nrs.asset'].sudo().search(
                [('asset_code', '=', query.strip())], limit=1)
            if asset:
                tag = asset.sudo().active_tag_id
        if not tag or not tag.asset_id:
            return {'found': False}
        asset = tag.asset_id.sudo()
        return {
            'found': True,
            'tag_number': tag.name,
            'asset_name': asset.name,
            'category': asset.category_id.name if asset.category_id else '',
            'location': asset.location_id.name if asset.location_id else '',
            'condition': asset.condition or '',
            'state': asset.state or '',
            'last_service_date': str(asset.last_service_date) if asset.last_service_date else '',
        }
