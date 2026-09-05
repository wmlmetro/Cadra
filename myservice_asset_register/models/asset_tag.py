from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import re


class NRSAssetTag(models.Model):
    _name = 'nrs.asset.tag.label'
    _description = 'Asset Barcode Tag'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    # ── Identity ─────────────────────────────────────────────
    name = fields.Char('Tag Number', required=True, copy=False, tracking=True)
    asset_id = fields.Many2one('nrs.asset', string='Asset', required=True,
                                ondelete='cascade')

    state = fields.Selection([
        ('active',   'Active'),
        ('pending',  'Replacement Pending'),
        ('scrapped', 'Scrapped'),
    ], default='active', tracking=True)

    # ── Source ────────────────────────────────────────────────
    source = fields.Selection([
        ('auto',   'Auto-generated'),
        ('manual', 'Manually assigned'),
        ('sap',    'SAP import'),
        ('other',  'Third-party import'),
    ], default='auto', string='Source')

    # ── Replacement ───────────────────────────────────────────
    replacement_reason = fields.Selection([
        ('damaged',  'Damaged / Unreadable'),
        ('lost',     'Lost / Missing'),
        ('stolen',   'Stolen'),
        ('reassign', 'Reassignment'),
        ('other',    'Other'),
    ], string='Replacement Reason')
    replacement_notes = fields.Text('Replacement Notes')
    replaced_by_id = fields.Many2one('nrs.asset.tag.label', string='Replaced By')
    replaces_id = fields.Many2one('nrs.asset.tag.label', string='Replaces Tag')

    # ── Approval ──────────────────────────────────────────────
    requested_by = fields.Many2one('res.users', string='Requested By')
    requested_date = fields.Datetime('Requested On')
    approved_by = fields.Many2one('res.users', string='Approved By')
    approved_date = fields.Datetime('Approved On')

    # ── Tag date ──────────────────────────────────────────────
    tag_date = fields.Date('Tag Date', default=fields.Date.today)
    scrapped_date = fields.Date('Scrapped Date')

    @api.constrains('name')
    def _check_unique_active(self):
        for r in self:
            if r.state == 'active':
                dup = self.search([
                    ('name', '=', r.name),
                    ('state', '=', 'active'),
                    ('id', '!=', r.id),
                ])
                if dup:
                    raise ValidationError(
                        _('Tag number %s is already active on asset: %s') % (
                            r.name, dup.asset_id.name))

    def action_request_replacement(self):
        self.write({
            'state': 'pending',
            'requested_by': self.env.uid,
            'requested_date': fields.Datetime.now(),
        })

    def action_approve_replacement(self):
        for r in self:
            # Scrap this tag
            r.write({
                'state': 'scrapped',
                'scrapped_date': fields.Date.today(),
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
            })
            # Generate new tag for the asset
            new_tag = r.asset_id._generate_tag(source='manual')
            new_tag.write({'replaces_id': r.id})
            r.write({'replaced_by_id': new_tag.id})
            r.message_post(body=_(
                'Tag %s scrapped. New tag %s generated.') % (r.name, new_tag.name))

    def action_reject_replacement(self):
        self.write({'state': 'active'})

    def action_print_tag(self):
        return self.env.ref(
            'myservice_asset_register.action_report_asset_tag'
        ).report_action(self)


class NRSAsset(models.Model):
    _inherit = 'nrs.asset'

    tag_ids = fields.One2many('nrs.asset.tag.label', 'asset_id', string='Tag History')
    active_tag_id = fields.Many2one(
        'nrs.asset.tag.label', string='Active Tag',
        compute='_compute_active_tag', store=True)
    active_tag_number = fields.Char(
        'Active Tag Number', related='active_tag_id.name', store=True)
    tag_source = fields.Selection([
        ('auto',   'Auto-generated'),
        ('manual', 'Manually assigned'),
        ('sap',    'SAP import'),
        ('other',  'Third-party import'),
    ], string='Tag Source', default='auto')

    # SAP / import fields
    sap_asset_number = fields.Char('SAP Asset Number', index=True)
    import_source = fields.Selection([
        ('myservice', 'myservice'),
        ('sap',       'SAP'),
        ('redhubb',   'Redhubb'),
        # The goods-receipt system (INT-03). The enum already names the
        # integration partners it receives from, and the field's whole purpose
        # is naming the source — falling back to `other` plus a reference
        # throws away the signal it exists to carry.
        ('vendra',    'Vendra'),
        ('excel',     'Excel Import'),
        ('other',     'Other'),
    ], string='Data Source', default='myservice')
    import_date = fields.Date('Import Date')
    import_ref = fields.Char('Import Reference')

    @api.depends('tag_ids.state')
    def _compute_active_tag(self):
        for r in self:
            active = r.tag_ids.filtered(lambda t: t.state == 'active')
            r.active_tag_id = active[0] if active else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            # Auto-generate tag unless one is provided via import
            if not vals.get('asset_tag') and vals.get('tag_source', 'auto') == 'auto':
                rec._generate_tag(source='auto')
            elif vals.get('asset_tag'):
                # Preserve imported tag number
                self.env['nrs.asset.tag.label'].create({
                    'name': vals['asset_tag'],
                    'asset_id': rec.id,
                    'source': vals.get('tag_source', 'other'),
                    'state': 'active',
                })
        return records

    def _tag_prefix(self):
        """Location-derived prefix for this asset's tag number.

        BUILDING-FLOOR-ROOM-CATEGORY, from the zone codes on the asset's
        building/floor/room (generic.location.zone_code — "HQ", "GF", "MR").
        Segments whose location is unset are skipped rather than emitted
        empty, so a building-only asset reads "HQ-FF-" instead of "HQ---FF-".
        With no location at all the tenant's brand short code stands in, which
        keeps tags unique and readable for assets logged before they are sited.
        """
        self.ensure_one()
        domain_codes = {
            'plant':    'PLT',
            'building': 'BLD',
            'plumbing': 'PLB',
            'fleet':    'FLT',
            'security': 'SEC',
            'it':       'ITC',
            'furniture':'FRN',
            'other':    'OTH',
        }

        def clean(value):
            # Tag codes are printed as Code 128 and read back by scanners —
            # keep them to characters that survive a hyphen-delimited split.
            return re.sub(r'[^A-Z0-9]', '', (value or '').upper())

        segments = [clean(loc.zone_code) for loc in
                    (self.building_id, self.floor_id, self.room_id) if loc]
        segments = [s for s in segments if s]
        if not segments:
            brand = self.env['ir.config_parameter'].sudo().get_param(
                'cadra.brand_short_name', 'NRS')
            segments = [clean(brand) or 'AST']

        category = clean(self.category_id.code) if self.category_id else ''
        segments.append(category or domain_codes.get(self.domain, 'AST'))
        return '-'.join(segments) + '-'

    def _generate_tag(self, source='auto'):
        """Generate a new unique tag number, e.g. HQ-GF-MR-FF-001."""
        Tag = self.env['nrs.asset.tag.label']
        prefix = self._tag_prefix()
        # `=like` anchors the match: a bare `like` is wrapped as %prefix% and
        # would match the prefix appearing anywhere in the number.
        existing = Tag.search(
            [('name', '=like', prefix + '%')], order='name desc', limit=1)
        seq = 1
        if existing:
            tail = existing.name[len(prefix):]
            if tail.isdigit():
                seq = int(tail) + 1
        tag_number = '%s%03d' % (prefix, seq)
        # Check every tag, not just the active ones. Reissuing a scrapped
        # tag's number would make the replacement history ambiguous — two
        # different physical labels sharing one code.
        while Tag.search_count([('name', '=', tag_number)]):
            seq += 1
            tag_number = '%s%03d' % (prefix, seq)
        tag = self.env['nrs.asset.tag.label'].create({
            'name':     tag_number,
            'asset_id': self.id,
            'source':   source,
            'state':    'active',
        })
        # Update asset_tag field for display
        self.write({'asset_tag': tag_number})
        return tag

    def get_barcode_base64(self, barcode_type, value, **kwargs):
        """Return a base64-encoded PNG barcode for use as a data URI in QWeb."""
        if not value:
            return ''
        png = self.env['ir.actions.report'].barcode(barcode_type, value, **kwargs)
        return base64.b64encode(png).decode()

    def get_tag_legend(self):
        """Return two legend lines decoding the tag code segments."""
        self.ensure_one()
        parts = []
        # Floor / Room from location hierarchy
        loc = self.location_id
        fr = (self.floor_room or '').split(' - ')
        if len(fr) >= 2 and loc:
            room_abbr = fr[1].strip()
            floor_abbr = fr[0].strip()
            room_name = loc.name or room_abbr
            floor_name = loc.parent_id.name if loc.parent_id else floor_abbr
            parts.append('%s = %s' % (floor_abbr, floor_name))
            parts.append('%s = %s' % (room_abbr, room_name))
        elif len(fr) == 1 and fr[0] and loc:
            parts.append('%s = %s' % (fr[0].strip(), loc.parent_id.name if loc.parent_id else loc.name))
        line1 = '  |  '.join(parts) if parts else ''
        # Category from category_id
        cat = self.category_id
        line2 = '%s = %s' % (cat.code, cat.name) if cat and cat.code else ''
        return line1, line2

    def action_request_tag_replacement(self):
        active_tag = self.active_tag_id
        if not active_tag:
            raise ValidationError(_('No active tag found for this asset.'))
        active_tag.action_request_replacement()

    def action_print_asset_tag(self):
        if not self.asset_tag:
            raise ValidationError(_('No tag code assigned to this asset.'))
        return self.env.ref(
            'myservice_asset_register.action_report_asset_tag'
        ).report_action(self)

    def action_batch_print_tags(self):
        assets = self.filtered(lambda a: a.asset_tag)
        if not assets:
            raise ValidationError(_('No assets with tag codes found in selection.'))
        return self.env.ref(
            'myservice_asset_register.action_report_asset_tag_sheet'
        ).report_action(assets)
