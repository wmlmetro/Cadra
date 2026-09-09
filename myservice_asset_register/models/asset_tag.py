from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.modules.registry import Registry
import base64
import logging
import re

_logger = logging.getLogger(__name__)


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
    # NOT the date the tag was printed or affixed: it defaults to the day the
    # record was created, which for an auto-generated tag is the day the asset
    # was. Kept for compatibility; read `printed_date` / `affixed_date` below
    # for what actually happened.
    tag_date = fields.Date('Tag Date', default=fields.Date.today)
    scrapped_date = fields.Date('Scrapped Date')

    # ── Physical lifecycle (INT-04/05) ────────────────────────
    #
    # Deliberately separate from `state`, which is the *replacement* lifecycle
    # (active / replacement pending / scrapped) and reads `active` from the
    # moment a tag record exists. That is why `state` could never answer "is
    # this asset physically tagged?" — every asset would have said yes from
    # creation, writing a false completeness claim into the audit trail.
    #
    # The Integration Flow separates the three steps on purpose: Cadra
    # generates the identity, an INDEPENDENT Tag-Issuing Unit prints and
    # affixes, and the serial-to-tag match is recorded at the point of
    # tagging. So this field is readonly and moves only through the methods
    # below — `_mark_printed` from the print action, `_mark_affixed` from a
    # confirmation carrying the tag number that was actually scanned. A value
    # someone can type at a desk would be evidence of nothing.
    label_state = fields.Selection([
        ('issued',   'Issued — identity generated, nothing printed'),
        ('printed',  'Printed — print instruction issued'),
        ('affixed',  'Affixed — confirmed on the physical asset'),
        ('scrapped', 'Scrapped'),
    ], string='Label Status', default='issued', required=True,
       readonly=True, copy=False, tracking=True, index=True)

    printed_date = fields.Datetime('Printed On', readonly=True, copy=False)
    printed_by = fields.Many2one(
        'res.users', string='Printed By', readonly=True, copy=False)
    affixed_date = fields.Datetime('Affixed On', readonly=True, copy=False)
    affixed_by = fields.Many2one(
        'res.users', string='Affixed — Recorded By', readonly=True, copy=False,
        help='The API client or user that submitted the affix confirmation')
    affixed_by_name = fields.Char(
        'Affixed — Fitted By', readonly=True, copy=False,
        help='Name of the Tag-Issuing Unit operative who physically affixed '
             'the label. Free text: they are not Cadra users.')

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
            r.with_context(cadra_tag_capture=True).write({
                'state': 'scrapped',
                'label_state': 'scrapped',
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

    # Fields that describe an event Cadra observed. They are written by the
    # two methods below and nowhere else — `readonly=True` only stops the web
    # client offering an input, it is not an ORM guard, and the model is
    # writable by group_asset_manager over XML-RPC.
    _CAPTURE_FIELDS = frozenset({
        'label_state', 'printed_date', 'printed_by',
        'affixed_date', 'affixed_by', 'affixed_by_name',
    })

    def write(self, vals):
        if (self._CAPTURE_FIELDS & set(vals)
                and not self.env.context.get('cadra_tag_capture')):
            raise ValidationError(_(
                'Tag capture fields (%s) record events and cannot be set '
                'directly. A label becomes "affixed" only through a '
                'confirmation carrying the tag number scanned off the asset '
                '(POST /api/v1/assets/<id>/tag-affixed).'
            ) % ', '.join(sorted(self._CAPTURE_FIELDS & set(vals))))
        return super().write(vals)

    def _mark_printed(self):
        """Record that a print instruction was issued for these labels.

        `printed` means Cadra emitted the instruction — Integration Flow step
        3.3 — not that paper physically emerged from a printer, which Cadra
        cannot observe. A label already `affixed` is not walked backwards: a
        reprint of a label someone has already stuck on an asset does not make
        the asset less tagged.
        """
        to_mark = self.filtered(lambda t: t.label_state in ('issued', 'printed'))
        if to_mark:
            to_mark.with_context(cadra_tag_capture=True).write({
                'label_state': 'printed',
                'printed_date': fields.Datetime.now(),
                'printed_by': self.env.uid,
            })
        return to_mark

    def _mark_affixed(self, scanned_tag_number, affixed_by_name=None,
                      affixed_date=None):
        """Record the serial-to-tag match at the point of physical tagging.

        The scanned number is checked against this label's own number rather
        than trusted, because that check IS the control: it is what makes the
        record evidence that the label on the asset is the label Cadra issued
        for it, rather than an assertion that someone tagged something.
        """
        self.ensure_one()
        if self.state == 'scrapped' or self.label_state == 'scrapped':
            raise ValidationError(_(
                'Tag %s has been scrapped and cannot be confirmed as affixed.'
            ) % self.name)
        if (scanned_tag_number or '').strip() != self.name:
            raise ValidationError(_(
                'Scanned tag %(scanned)s does not match the tag issued for '
                'this asset (%(expected)s). The label on the asset is not the '
                'one Cadra issued for it.'
            ) % {'scanned': scanned_tag_number or '(none)', 'expected': self.name})

        if self.label_state == 'affixed':
            # A second confirmation must not rewrite the first. The original
            # record is the evidence — who fitted the label and when — and
            # overwriting it would blank `affixed_by_name` and move
            # `affixed_at` for any caller that retried without the optional
            # fields. Neither field is tracked, so the old values would be
            # gone rather than superseded. Log the repeat and keep the record.
            self.message_post(body=_(
                'Repeat affix confirmation for tag %(tag)s ignored; the '
                'original record of %(when)s stands.'
            ) % {'tag': self.name, 'when': self.affixed_date})
            return self

        self.with_context(cadra_tag_capture=True).write({
            'label_state': 'affixed',
            'affixed_date': affixed_date or fields.Datetime.now(),
            'affixed_by': self.env.uid,
            'affixed_by_name': (affixed_by_name or '').strip() or False,
        })
        self.message_post(body=_(
            'Tag %(tag)s confirmed affixed to %(asset)s%(who)s.'
        ) % {
            'tag': self.name,
            'asset': self.asset_id.display_name,
            'who': _(' by %s') % affixed_by_name if affixed_by_name else '',
        })
        return self

    def action_print_tag(self):
        """Print the label that is on this tag's asset.

        The four tag reports are declared on `nrs.asset`, so the ids handed to
        one must be ASSET ids — this used to pass the tag ids and render
        whichever unrelated asset happened to share the number. The stamp is
        not made here: `ir.actions.report._render_qweb_pdf` records the print
        when a PDF is actually produced, which is the only moment Cadra can
        honestly claim a print instruction was issued.
        """
        assets = self.mapped('asset_id')
        if not assets:
            raise ValidationError(_('This tag is not linked to an asset.'))
        return self.env.ref(
            'myservice_asset_register.action_report_asset_tag'
        ).report_action(assets)

    def action_print_labels(self):
        """Print a selection of labels as an A4 sheet, from the tag list.

        This is what the sheet report's `binding_model_id` on
        `nrs.asset.tag.label` was reaching for, and could never deliver: the
        binding handed the report label ids while the template reads
        `o.asset_tag` / `o.asset_code` / `o.get_barcode_base64` off an
        `nrs.asset`. Translating here is the only place that knows both sides.
        """
        assets = self.env['nrs.asset'].browse(
            [t.asset_id.id for t in self if t.asset_id])
        if not assets:
            raise ValidationError(_(
                'None of the selected tags is linked to an asset.'))
        return self.env.ref(
            'myservice_asset_register.action_report_asset_tag_sheet'
        ).report_action(assets)


class NRSAsset(models.Model):
    _inherit = 'nrs.asset'

    tag_ids = fields.One2many('nrs.asset.tag.label', 'asset_id', string='Tag History')
    active_tag_id = fields.Many2one(
        'nrs.asset.tag.label', string='Active Tag',
        compute='_compute_active_tag', store=True)
    active_tag_number = fields.Char(
        'Active Tag Number', related='active_tag_id.name', store=True)
    # Stored so `GET /api/v1/assets?tag_label_state=affixed` is a real query
    # rather than a post-filter. False for an asset with no active tag, which
    # is the honest answer: never tagged.
    physical_tag_id = fields.Many2one(
        'nrs.asset.tag.label', string='Physical Label',
        compute='_compute_physical_tag', store=True,
        help='The label physically on the asset. Unlike active_tag_id this '
             'includes a tag awaiting replacement, which is still stuck to '
             'the asset until someone removes it.')
    tag_label_state = fields.Selection(
        related='physical_tag_id.label_state', string='Tag Status',
        store=True, readonly=True, index=True)
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

    @api.depends('tag_ids.state', 'tag_ids.label_state')
    def _compute_physical_tag(self):
        """The label actually on the asset, for the physical question.

        `active_tag_id` drops a tag the moment a replacement is REQUESTED
        (state becomes `pending`), which would make an asset whose label is
        still stuck to it read as never tagged — the mirror image of the
        false-completeness bug this module exists to remove. Requesting a
        replacement is a decision about the future; it does not peel the
        label off.
        """
        for r in self:
            candidates = r.tag_ids.filtered(lambda t: t.state != 'scrapped')
            affixed = candidates.filtered(lambda t: t.label_state == 'affixed')
            r.physical_tag_id = (affixed[:1] or candidates[:1]) or False

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
            # capped-count-ok: a sequence number, not a count of
            # anything. `existing` is a limit=1 lookup of the highest
            # tag already issued, which is what it should be.
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
        # No stamp here. `report_action` only hands the client an action; the
        # PDF may never be fetched. `_render_qweb_pdf` is the moment a print
        # instruction actually exists, and it is the one funnel every caller
        # passes through, so it is the only place that records one.
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


class IrActionsReport(models.Model):
    """Catch the tag prints that never touch a Python action method.

    The obvious hooks — `action_print_tag`, `action_print_asset_tag`,
    `action_batch_print_tags` — look like the single funnel for printing a tag
    and are not. Three paths bypass all three:

      * the label wizard (`wizard/asset_label_wizard.py`) calls
        `report.report_action(...)` directly;
      * the barcode station hands the browser a raw
        `/report/pdf/<report>/<asset_id>` URL (`myservice_barcode_station/
        controllers/main.py`), so no Python of ours runs at all;
      * the four tag reports carry `binding_model_id` on `nrs.asset`, so they
        appear in Odoo's own Print menu and fire from there.

    Stamping only the action methods would under-record printing badly, and a
    print record that is silently incomplete is the same class of defect as the
    tag state this work exists to fix. `_render_qweb_pdf` is the one place every
    PDF path converges.

    ── Which id space `res_ids` is in ──────────────────────────────────────

    Asset ids and `nrs.asset.tag.label` ids collide by construction — every
    asset mints a label on creation, so the two sequences advance together. On
    `nrs19`, measured 2026-09-08: 11,928 of 11,932 asset ids are also valid
    label ids, 99.97%. The first version of this hook met that by DECLINING
    whenever the ids could be label ids — which, at 99.97%, is every normal
    print. Both real callers were declined and the register held 11,879 labels
    at `issued` and exactly one at `printed`.

    The ids cannot be told apart by value, so the caller has to say which it
    means — and there is exactly one channel that survives to this method. A
    report action's context is NOT it: `web/.../reports/utils.js` turns the
    action into `/report/pdf/<report_name>/<active_ids>` and posts it to
    `/report/download` with the *user* context, so everything the action put in
    its context is dropped at the browser. The id list is the only thing left.

    So the rule is the framework's own: **`res_ids` are ids of the report's
    declared model**, which for all four tag labels is `nrs.asset`. That is
    enforced at the boundary by `report_action` below, which refuses a
    recordset of any other model rather than translating it — the two callers
    that used to pass tag ids were not merely ambiguous, they rendered the
    wrong asset. With the boundary closed, this hook has nothing left to guess.
    """
    _inherit = 'ir.actions.report'

    # The four tag labels, matched on report_name (the QWeb template) rather
    # than xmlid: report_name is the handle that appears in the
    # `/report/pdf/<report_name>/<ids>` URL and the only one `_get_report`
    # resolves there, so it is the one an HTTP caller can actually be holding.
    # `action_report_asset_tag_sheet` also used to be DECLARED twice, on two
    # different models, which is a second reason not to key on the xmlid; the
    # duplicate is gone (see data/asset_tag_report.xml) but the first reason
    # stands on its own.
    _TAG_LABEL_REPORTS = (
        'myservice_asset_register.report_asset_tag_label',
        'myservice_asset_register.report_asset_tag_label_small',
        'myservice_asset_register.report_asset_tag_label_large',
        'myservice_asset_register.report_asset_tag_label_sheet',
    )

    def report_action(self, docids, data=None, config=True):
        """Refuse a foreign recordset on a tag label report, loudly.

        `docids` becomes `active_ids`, which becomes the id list in the
        `/report/pdf/` URL, which becomes `res_ids` at render. Nothing between
        here and there carries the model, and asset ids and label ids collide,
        so a recordset of the wrong model is a silent wrong-record render —
        which is exactly what `action_print_tag` and the label wizard did.
        Raise instead of translating: a caller that does not know which id
        space it is in should be corrected, not guessed at.

        `docids` given as a bare int or list carries no model to check. That is
        the raw form the HTTP route already uses, where the ids are the
        report's own model by the framework's contract.
        """
        if (len(self) == 1
                and self.report_name in self._TAG_LABEL_REPORTS
                and isinstance(docids, models.BaseModel)
                and docids._name != self.model):
            raise UserError(_(
                'The report "%(report)s" renders %(model)s records, and was '
                'handed %(given)s records. Asset ids and tag label ids collide '
                'numerically — on the NRS register 99.97%% of asset ids are '
                'also valid label ids — and only the ids reach the renderer, '
                'so this cannot be resolved further down. Pass the assets '
                '(for a label recordset: `labels.asset_id`).'
            ) % {
                'report': self.name or self.report_name,
                'model': self.model,
                'given': docids._name,
            })
        return super().report_action(docids, data=data, config=config)

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        result = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        try:
            # Inside a savepoint, not just a try. Swallowing a DATABASE error
            # without one leaves the transaction aborted, so the next query
            # anywhere in the request fails with "current transaction is
            # aborted" — the print would still break, just further away and
            # with a message about something else. "Never fail a print over
            # bookkeeping" is only true if the bookkeeping can be rolled back.
            with self.env.cr.savepoint():
                self._stamp_printed_tags(report_ref, res_ids)
        except Exception:          # noqa: BLE001 — never fail a print over bookkeeping
            _logger.exception("could not stamp tag print for %s / %s",
                              report_ref, res_ids)
        return result

    @api.model
    def _stamp_printed_tags(self, report_ref, res_ids):
        """Mark the active tags of the printed assets as printed.

        ── The cursor serving a print CANNOT write ─────────────────────────

        Odoo 19 declares the report route

            @http.route(['/report/<converter>/<reportname>',
                         '/report/<converter>/<reportname>/<docids>'],
                        type='http', auth='user', website=True, readonly=True)

        so every render reached through that URL runs on a **read-only
        Postgres cursor**, and any write raises *"cannot execute UPDATE in a
        read-only transaction"*. Fixing the id space is necessary and is not
        sufficient: with the ids finally unambiguous, the stamp still could
        not be recorded through the one path the barcode station and
        `GET /api/v1/barcode/print-url` actually use.

        Odoo's own Print menu is unaffected, because it goes through
        `/report/download`, which is read/write and calls `report_routes` as a
        plain Python method — the route's `readonly` flag does not apply to a
        direct call. So this is not "printing never records"; it is "printing
        records from the web client and silently does not from the published
        URL", which is worse, because it looks like it works.

        The record therefore goes on its own read/write cursor and commits
        independently. That is also the honest transaction boundary: the PDF
        has already been produced by the time this runs, so the print
        instruction has been issued whatever happens to the request afterwards.
        Under a test the registry is in test mode and hands back a `TestCursor`
        wrapping the running transaction, so this stays inside the test's
        rollback rather than committing to the tenant.
        """
        if not res_ids:
            return
        report = self._get_report(report_ref)
        if not report or report.report_name not in self._TAG_LABEL_REPORTS:
            return
        if getattr(self.env.cr, 'readonly', False):
            with Registry(self.env.cr.dbname).cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                env['ir.actions.report']._mark_printed_for(res_ids, report)
                cr.commit()
            return
        self._mark_printed_for(res_ids, report)

    @api.model
    def _mark_printed_for(self, res_ids, report):
        """The stamp itself, on whatever cursor the caller decided on."""
        # `res_ids` are ids of `report.model` — see the class docstring. The
        # boundary that used to leak label ids in here is closed above, so
        # there is no ambiguity left to decline over.
        assets = self.env['nrs.asset'].sudo().browse(res_ids).exists()
        if not assets:
            _logger.warning(
                "tag label %s rendered for res_ids %s, none of which is an "
                "nrs.asset — nothing stamped", report.report_name, res_ids)
            return
        # The ACTIVE tag, not the physical one: printing is what produces the
        # label about to be affixed, and a tag awaiting replacement is not the
        # one coming off the printer. It is also the tag the template renders
        # (`o.asset_tag`), so the stamp and the paper agree.
        tags = assets.mapped('active_tag_id')
        if tags:
            tags._mark_printed()
