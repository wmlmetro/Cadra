from odoo import http
from odoo.http import request
import json


def _selection_label(record, field_name):
    """The human label of a Selection value, for any Selection field.

    `dict(record._fields[f].selection)` only works when the field declares a
    literal list. On a *related* Selection — `nrs.asset.domain` is
    `related='category_id.domain'` — Odoo fills `.selection` with a callable,
    and `dict(<function>)` raises `TypeError: 'function' object is not
    iterable`. That is what made `/barcode/lookup` answer 500 for every asset
    whose category carries an FM domain, i.e. every asset it actually found.

    `fields_get` is the public, translation-aware accessor and is indifferent
    to how the field was declared, so it holds if a field that is a literal
    list today becomes related tomorrow.
    """
    value = record[field_name]
    if not value:
        return ''
    try:
        selection = record.fields_get([field_name])[field_name]['selection']
    except Exception:
        return value
    return dict(selection).get(value, value)


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
            'domain': _selection_label(asset, 'domain'),
            'location': asset.location_id.name if asset.location_id else '',
            'custodian': asset.custodian_id.name if asset.custodian_id else '',
            'condition': _selection_label(asset, 'condition'),
            'state': _selection_label(asset, 'state'),
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
            # Count assets with no active tag directly. Subtracting the active
            # tag count from the asset count goes negative as soon as one asset
            # carries more than one active tag.
            'untagged': Asset.search_count([('active_tag_id', '=', False)]),
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

    @http.route('/barcode/untagged', type='json', auth='user')
    def get_untagged(self, q='', limit=100):
        """Assets carrying no active tag — the candidates for tagging.

        These are the assets the station generates barcodes for: an asset
        keeps its own `asset_code` (an ir.sequence value, assigned at
        creation) whether or not it has ever been physically labelled. The
        barcode is the separate, location-derived code on the tag record.
        """
        try:
            limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit = 100
        domain = [('active_tag_id', '=', False)]
        if q:
            q = q.strip()
            domain += ['|', '|',
                       ('name', 'ilike', q),
                       ('asset_code', 'ilike', q),
                       ('serial_number', 'ilike', q)]
        assets = request.env['nrs.asset'].sudo().search(
            domain, order='asset_code', limit=limit)
        return [{
            'asset_id': a.id,
            'asset_name': a.name,
            'asset_code': a.asset_code or '',
            'category': a.category_id.name if a.category_id else '',
            'domain': a.domain or '',
            'location': a.location_id.name if a.location_id else '',
            'condition': a.condition or '',
        } for a in assets]

    @http.route('/barcode/generate', type='json', auth='user')
    def generate_tags(self, asset_ids=None):
        """Mint a barcode for each of `asset_ids` that does not have one.

        Assets that already carry an active tag are skipped, not re-tagged:
        a second live barcode for one asset means two physical labels in the
        field resolving to the same thing, and no way to tell which is
        current. That also makes this endpoint safe to retry. Replacing a
        damaged tag is a different operation — action_request_replacement on
        the tag itself, which keeps the replaces/replaced_by chain intact.
        """
        ids = []
        for raw in (asset_ids or []):
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not ids:
            return {'error': '`asset_ids` must be a non-empty list of asset ids'}
        if len(ids) > 500:
            return {'error': 'Too many assets in one request (max 500)'}

        Asset = request.env['nrs.asset'].sudo()
        generated, skipped = [], []
        for asset_id in ids:
            asset = Asset.browse(asset_id).exists()
            if not asset:
                skipped.append({'asset_id': asset_id, 'reason': 'not_found'})
                continue
            if asset.active_tag_id:
                skipped.append({
                    'asset_id': asset_id,
                    'reason': 'already_tagged',
                    'tag_number': asset.active_tag_id.name,
                })
                continue
            tag = asset._generate_tag(source='manual')
            generated.append({
                'asset_id': asset.id,
                'asset_name': asset.name,
                'asset_code': asset.asset_code or '',
                'tag_id': tag.id,
                'tag_number': tag.name,
                'location': asset.location_id.name if asset.location_id else '',
            })
        return {'generated': generated, 'skipped': skipped}

    @http.route('/barcode/print_url', type='json', auth='user')
    def get_print_url(self, tag_id, size='medium'):
        """Return the PDF print URL for a tag.

        The label reports are all registered on ``nrs.asset`` (see
        myservice_asset_register/data/asset_tag_report.xml), so the id in the
        URL must be the ASSET id — passing the tag id straight through renders
        whichever unrelated asset happens to share that id.

        The path segment is the report ACTION's ``report_name``, not its
        xmlid. Odoo's ``/report/<converter>/<reportname>/<ids>`` resolves its
        second segment against ``ir.actions.report.report_name``; this used to
        emit ``action_report_asset_tag`` with the dot turned into a slash,
        which matches no report and answered the website's 404 page. Nothing
        caught it because the SPA composes labels client-side rather than
        fetching this URL (Frontend/.../src/lib/labels.ts) — so the one
        published route from an asset to a printable label had never
        rendered anything.

        Read off the action rather than hard-coded so a rename of the QWeb
        template cannot silently reintroduce the same 404.
        """
        action_map = {
            'small':  'myservice_asset_register.action_report_asset_tag_small',
            'medium': 'myservice_asset_register.action_report_asset_tag',
            'large':  'myservice_asset_register.action_report_asset_tag_large',
            'sheet':  'myservice_asset_register.action_report_asset_tag_sheet',
        }
        action_xmlid = action_map.get(size, action_map['medium'])
        try:
            tag_id = int(tag_id)
        except (TypeError, ValueError):
            return {'error': 'Invalid tag_id: %s' % tag_id}
        tag = request.env['nrs.asset.tag.label'].browse(tag_id).exists()
        if not tag or not tag.asset_id:
            return {'error': 'Tag not found: %s' % tag_id}
        action = request.env.ref(action_xmlid, raise_if_not_found=False)
        if not action or not action.report_name:
            return {'error': 'Report action not installed: %s' % action_xmlid}
        return {
            'url': '/report/pdf/%s/%s' % (action.report_name, tag.asset_id.id)
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
