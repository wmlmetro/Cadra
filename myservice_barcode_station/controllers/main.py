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
    except KeyError:
        # Optional: the field exists — `record[field_name]` above would have
        # raised otherwise — but is not a Selection, so `fields_get` describes
        # it without a `selection` key and the raw stored value is the best
        # label available. Narrowed from `except Exception`, which would also
        # have hidden a real failure inside `fields_get` and returned a code
        # where a label was expected, indistinguishable from a field that had
        # simply never been a Selection.
        return value
    return dict(selection).get(value, value)


def _escape_like(value):
    """Make `value` literal under LIKE/ILIKE: `%`, `_` and `\\` are wildcards."""
    return (value.replace('\\', '\\\\')
                 .replace('%', '\\%')
                 .replace('_', '\\_'))


def _resolve_lookup(env, query, sudo=False):
    """What a scanned string names. ONE resolution for both lookup routes.

    Precedence is TAG NUMBER, then ASSET CODE, then SERIAL NUMBER, each an
    exact match, so a scanned tag can never lose to a serial that happens to
    read the same. Measured before this was written (handoff 38, all eight
    local tenants, 2026-10-01): 0 serials equal to any tag number, 0 equal to
    any asset code, 0 tag numbers equal to an asset code — the order is for
    determinism, not because a collision has been seen.

    Until handoff 38 the serial branch did not exist, while the published
    description of both `/api/v1` twins said *"Tag, asset code, or serial
    number"* — so the serial of a TAGGED asset found nothing, and that is
    exactly what an auditor with a scanner does.

    The serial rule: the query is stripped and compared case-insensitively
    and EXACTLY (`=ilike` with the wildcards escaped). Internal whitespace and
    leading zeros are significant — `nrs19` holds 574 serials with a space
    inside and ten beginning with `0` — and no stored serial on any tenant
    carries leading or trailing whitespace (0 of 11,704 with a serial), so
    stripping the query is enough for a scanner's trailing space.

    A serial can be AMBIGUOUS: `nrs19` has 1,291 serial values on more than
    one asset (`PROBOOK` on 94), model names typed where a serial should be.
    More than one match is reported as a miss that says how many, never a
    silent first-row pick.

    The tag-number branch is unchanged: only an `active` tag resolves by its
    number. An asset found by code or serial carries its active tag, or — when
    it has none — its `physical_tag_id` (a tag whose replacement is pending,
    still stuck to the asset), so the station can show *replacement pending*
    rather than *untagged* for a label that is physically there.
    """
    q = (query or '').strip()
    Tag = env['nrs.asset.tag.label']
    # Handoff 57: the scan box must find a receipt CANDIDATE — the tagger
    # scans its label before it is registered. `cadra_candidates` lifts the
    # register's default filter (`asset_gates._search`) for this lookup only.
    Asset = env['nrs.asset'].with_context(cadra_candidates=True)
    if sudo:
        Tag, Asset = Tag.sudo(), Asset.sudo()
    if not q:
        return {'found': False, 'error': 'No query provided'}

    tag = Tag.search([('name', '=', q.upper()), ('state', '=', 'active')],
                     limit=1)
    if tag and tag.asset_id:
        return {'found': True, 'matched_by': 'tag_number',
                'asset': tag.asset_id, 'tag': tag, 'tagged': True}

    asset = Asset.search([('asset_code', '=', q)], limit=1)
    matched_by = 'asset_code'
    if not asset:
        matches = Asset.search(
            [('serial_number', '=ilike', _escape_like(q))], limit=2)
        if len(matches) > 1:  # capped-count-ok: a "more than one" probe, not a count; the count is taken below
            # `limit=2` says "more than one", which is all the answer needs;
            # the count is taken over the register so the message is true.
            count = Asset.search_count(
                [('serial_number', '=ilike', _escape_like(q))])
            return {
                'found': False, 'ambiguous': True,
                'matched_by': 'serial_number', 'matches': count,
                'error': 'Serial number %s is on %d assets; scan the tag or '
                         'the asset code instead' % (q, count),
            }
        asset = matches
        matched_by = 'serial_number'
    if not asset:
        return {'found': False,
                'error': 'No active tag, asset code or serial number '
                         'matches: %s' % q}
    active = asset.active_tag_id
    return {'found': True, 'matched_by': matched_by, 'asset': asset,
            'tag': active or asset.physical_tag_id, 'tagged': bool(active)}


class BarcodeStationController(http.Controller):

    # ── Backend JSON API ─────────────────────────────────────

    @http.route('/barcode/lookup', type='json', auth='user')
    def lookup_tag(self, query=''):
        """Look up an asset by tag number, asset code or serial number.

        Precedence and matching rules are `_resolve_lookup`'s; this method is
        the authenticated station's shape of its answer and
        `/api/v1/barcode/lookup` publishes it unchanged.
        """
        if not query:
            return {'found': False, 'error': 'No query provided'}
        hit = _resolve_lookup(request.env, query)
        if not hit['found']:
            return hit
        asset, tag = hit['asset'], hit['tag']
        return {
            'found': True,
            'matched_by': hit['matched_by'],
            'tagged': hit['tagged'],
            'tag_id': tag.id if tag else None,
            'tag_number': tag.name if tag else '',
            'tag_state': tag.state if tag else '',
            'tag_date': str(tag.tag_date) if tag and tag.tag_date else '',
            'asset_id': asset.id,
            'asset_name': asset.name,
            'asset_code': asset.asset_code or '',
            'serial_number': asset.serial_number or '',
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
            # Not a unit identified by its SAP record (handoff 59): it can
            # never carry a label, so it is never "waiting for one".
            'untagged': Asset.search_count([
                ('active_tag_id', '=', False),
                ('identification_mode', '!=', 'record_only')]),
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
        # Never a `record_only` unit (handoff 59): it carries no label.
        domain = [('active_tag_id', '=', False),
                  ('identification_mode', '!=', 'record_only')]
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
            if asset.identification_mode == 'record_only':
                # Skipped, not refused: one plot of land in a batch of fifty
                # laptops must not roll the fifty back (handoff 59).
                skipped.append({'asset_id': asset_id,
                                'reason': 'record_only'})
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
    def get_print_url(self, tag_id=None, tag_ids=None, size='medium'):
        """Return the PDF print URL for one tag or a batch of them.

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

        `tag_ids` is the batch form. The station's "Print batch" button used to
        build its own URL client-side and got BOTH halves wrong — the xmlid
        with its dot turned into a slash (the 404 above, never fixed here) and
        the tag-to-asset translation left to the browser. Resolving it server
        side is the only place either can be got right once.
        """
        action_map = {
            'small':  'myservice_asset_register.action_report_asset_tag_small',
            'medium': 'myservice_asset_register.action_report_asset_tag',
            'large':  'myservice_asset_register.action_report_asset_tag_large',
            'sheet':  'myservice_asset_register.action_report_asset_tag_sheet',
        }
        action_xmlid = action_map.get(size, action_map['medium'])
        raw = tag_ids if tag_ids is not None else tag_id
        if not isinstance(raw, (list, tuple)):
            raw = [raw]
        try:
            wanted = [int(i) for i in raw]
        except (TypeError, ValueError):
            return {'error': 'Invalid tag id in: %s' % (raw,)}
        if not wanted:
            return {'error': 'No tag ids given'}
        tags = request.env['nrs.asset.tag.label'].browse(wanted).exists()
        # Order the assets the way the tags were asked for; a print run that
        # silently reorders is a print run someone has to re-check by hand.
        by_id = {t.id: t.asset_id.id for t in tags if t.asset_id}
        asset_ids = [by_id[i] for i in wanted if by_id.get(i)]
        if not asset_ids:
            return {'error': 'Tag not found: %s' % (wanted if tag_ids is not None
                                                   else wanted[0])}
        action = request.env.ref(action_xmlid, raise_if_not_found=False)
        if not action or not action.report_name:
            return {'error': 'Report action not installed: %s' % action_xmlid}
        return {
            'url': '/report/pdf/%s/%s' % (
                action.report_name, ','.join(str(i) for i in asset_ids)),
        }

    # ── Portal routes ────────────────────────────────────────

    @http.route('/tags', type='http', auth='public', website=True)
    def barcode_portal(self, **kwargs):
        """Field team portal — no login required."""
        return request.render('myservice_barcode_station.portal_barcode_station', {})

    @http.route('/tags/lookup', type='json', auth='public')
    def portal_lookup(self, query=''):
        """Public lookup endpoint for portal scanner.

        Same resolution as `/barcode/lookup` (`_resolve_lookup`), narrower
        answer: the public portal publishes no ids.
        """
        if not query:
            return {'found': False}
        env = request.env(user=request.env.ref('base.public_user').id)
        hit = _resolve_lookup(env, query, sudo=True)
        if not hit['found']:
            return hit
        asset, tag = hit['asset'].sudo(), hit['tag']
        return {
            'found': True,
            'matched_by': hit['matched_by'],
            'tagged': hit['tagged'],
            'tag_number': tag.name if tag else '',
            'tag_state': tag.state if tag else '',
            'asset_name': asset.name,
            'asset_code': asset.asset_code or '',
            'serial_number': asset.serial_number or '',
            'category': asset.category_id.name if asset.category_id else '',
            'location': asset.location_id.name if asset.location_id else '',
            'condition': asset.condition or '',
            'state': asset.state or '',
            'last_service_date': str(asset.last_service_date) if asset.last_service_date else '',
        }
