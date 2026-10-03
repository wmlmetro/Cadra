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
    # Handoff 38. WHO IS ASKED and WHO CLICKED are two columns, as they are
    # on `nrs.asset.change.request` and for the same reason: `approver_id`
    # is a nomination made by the requester and confers nothing; the two
    # `*_by` columns are stamped from the acting user by the decision
    # methods below and by nothing else (`_REPLACEMENT_STAMPS`).
    approver_id = fields.Many2one(
        'res.users', string='Approval Asked Of',
        help='The person asked to decide this replacement. Anybody eligible '
             'may decide it; this is whose queue it sits in.')
    rejected_by = fields.Many2one('res.users', string='Rejected By')
    rejected_date = fields.Datetime('Rejected On')
    decision_reason = fields.Text(
        'Decision Reason',
        help='Why the replacement was approved or rejected. Required on a '
             'rejection, because the requester is told.')

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

    # ── Replacement: a request, then a SECOND person decides ──────────
    #
    # Handoff 38. The three steps (active → pending → scrapped-and-reissued)
    # and the requester/approver columns were already here; what the model
    # lacked was everything handoff 35 settled for a move — who is ASKED,
    # self-approval refused in the model, a reason that is actually
    # recorded, a rejection that says why, and stamps nobody can edit
    # afterwards. `nrs.asset.change.request` is deliberately NOT reused: it
    # is hard-wired to location and custody, and its one-pending-per-asset
    # index would make a pending tag replacement block a move. The RULE of
    # who may decide is shared, read off that model, so "who is an approver
    # here" has one answer.

    REPLACEMENT_KEY = 'cadra_tag_replacement'

    #: Written by the three methods below and nowhere else. `readonly=True`
    #: on the form is not an ORM guard, and the model is writable by
    #: group_asset_manager over XML-RPC — the same reasoning as
    #: `_CAPTURE_FIELDS`. `approver_id`, `replacement_reason` and
    #: `replacement_notes` are NOT in it: they are what the requester types
    #: on the Odoo form before pressing the button.
    _REPLACEMENT_STAMPS = frozenset({
        'requested_by', 'requested_date',
        'approved_by', 'approved_date',
        'rejected_by', 'rejected_date', 'decision_reason',
        'replaces_id', 'replaced_by_id',
    })

    @api.model
    def _approver_group(self):
        return self.env['nrs.asset.change.request'].APPROVER_GROUP

    def _replacement_ctx(self):
        return self.with_context(**{self.REPLACEMENT_KEY: True})

    def _may_decide(self, user):
        """The same rule as `nrs.asset.change.request._may_decide`: never
        the requester; a system administrator; otherwise the approver group,
        through `has_group` so an implied membership counts."""
        self.ensure_one()
        if user.id == self.requested_by.id:
            return False
        if user._is_superuser() or user._is_admin():
            return True
        return user.has_group(self._approver_group())

    def _assert_may_decide(self, user):
        self.ensure_one()
        if user.id == self.requested_by.id:
            raise UserError(_(
                '%(user)s raised the replacement request for tag %(tag)s '
                'and cannot decide it. The point of an approval is that a '
                'second person agrees.'
            ) % {'user': user.display_name, 'tag': self.name})
        if not self._may_decide(user):
            raise UserError(_(
                '%(user)s cannot decide a tag replacement. An approver must '
                'be somebody who could have made the change themselves.'
            ) % {'user': user.display_name})

    def _reason_label(self, value):
        return dict(self._fields['replacement_reason'].selection).get(
            value, value)

    def action_request_replacement(self, reason=None, notes=None,
                                   approver=None):
        """Ask a second person to agree that this tag be scrapped and
        reissued.

        Callable with no arguments from the Odoo form, where
        `replacement_reason` and `approver_id` are typed onto the record
        before the button; the API route passes all three. Until handoff 38
        this wrote the state and the requester and never the reason, so
        "why was this tag replaced" — the whole point of the record — was
        recorded only if somebody remembered the form field.
        """
        allowed = [v for v, _label in
                   self._fields['replacement_reason'].selection]
        for r in self:
            if r.state != 'active':
                raise UserError(_(
                    'Tag %(tag)s is %(state)s; only an active tag can have '
                    'a replacement requested.'
                ) % {'tag': r.name,
                     'state': dict(r._fields['state'].selection)[r.state]})
            why = reason or r.replacement_reason
            if why not in allowed:
                raise UserError(_(
                    'A reason is required to request a replacement for tag '
                    '%(tag)s — one of %(allowed)s.'
                ) % {'tag': r.name, 'allowed': ', '.join(allowed)})
            who = approver if approver is not None else r.approver_id
            if not who:
                raise UserError(_(
                    'Name who you are asking to approve the replacement of '
                    'tag %s. A tag is reissued only when a second person '
                    'agrees.') % r.name)
            if who.id == self.env.uid:
                raise UserError(_(
                    'You cannot ask yourself to approve your own request. '
                    'Name somebody else.'))
            if not who.has_group(self._approver_group()) \
                    and not who._is_admin():
                raise UserError(_(
                    '%s cannot approve a tag replacement. An approver must '
                    'be somebody who could have made the change themselves.'
                ) % who.display_name)
            r._replacement_ctx().write({
                'state': 'pending',
                'replacement_reason': why,
                'replacement_notes': (
                    notes if notes is not None else r.replacement_notes
                ) or False,
                'approver_id': who.id,
                'requested_by': self.env.uid,
                'requested_date': fields.Datetime.now(),
                # A new request is a new slot: an earlier rejection's stamps
                # do not describe this one. The chatter keeps the old ones.
                'approved_by': False, 'approved_date': False,
                'rejected_by': False, 'rejected_date': False,
                'decision_reason': False,
            })
            r.message_post(
                body=_('Replacement of tag %(tag)s requested by %(by)s: '
                       '%(why)s. Waiting on %(who)s.') % {
                    'tag': r.name, 'by': self.env.user.display_name,
                    'why': r._reason_label(why), 'who': who.display_name},
                partner_ids=who.partner_id.ids)
        return True

    def action_approve_replacement(self, decision_reason=None):
        """Scrap this tag and mint its successor. Returns the NEW tags.

        The old number is never reissued: `_generate_tag` checks every tag
        on the asset's prefix, scrapped ones included, before it picks a
        sequence number.
        """
        new_tags = self.browse()
        for r in self:
            if r.state != 'pending':
                raise UserError(_(
                    'Tag %(tag)s is %(state)s, not awaiting a replacement '
                    'decision.'
                ) % {'tag': r.name,
                     'state': dict(r._fields['state'].selection)[r.state]})
            r._assert_may_decide(self.env.user)
            r._replacement_ctx().with_context(cadra_tag_capture=True).write({
                'state': 'scrapped',
                'label_state': 'scrapped',
                'scrapped_date': fields.Date.today(),
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
                'decision_reason': (decision_reason or '').strip() or False,
            })
            new_tag = r.asset_id._generate_tag(source='manual')
            new_tag._replacement_ctx().write({'replaces_id': r.id})
            r._replacement_ctx().write({'replaced_by_id': new_tag.id})
            r.message_post(
                body=_('Replacement approved by %(who)s. Tag %(old)s '
                       'scrapped; new tag %(new)s generated.') % {
                    'who': self.env.user.display_name,
                    'old': r.name, 'new': new_tag.name},
                partner_ids=r.requested_by.partner_id.ids)
            new_tags |= new_tag
        return new_tags

    def action_reject_replacement(self, decision_reason=None):
        """Back to `active`, with who said no and why."""
        for r in self:
            if r.state != 'pending':
                raise UserError(_(
                    'Tag %(tag)s is %(state)s, not awaiting a replacement '
                    'decision.'
                ) % {'tag': r.name,
                     'state': dict(r._fields['state'].selection)[r.state]})
            r._assert_may_decide(self.env.user)
            why = (decision_reason or r.decision_reason or '').strip()
            if not why:
                raise UserError(_(
                    'A reason is required to reject the replacement of tag '
                    '%s: the requester is told why.') % r.name)
            r._replacement_ctx().write({
                'state': 'active',
                'rejected_by': self.env.uid,
                'rejected_date': fields.Datetime.now(),
                'decision_reason': why,
            })
            r.message_post(
                body=_('Replacement rejected by %(who)s: %(why)s') % {
                    'who': self.env.user.display_name, 'why': why},
                partner_ids=r.requested_by.partner_id.ids)
        return True

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
        if (self._REPLACEMENT_STAMPS & set(vals)
                and not self.env.context.get(self.REPLACEMENT_KEY)):
            raise ValidationError(_(
                'Replacement fields (%s) are stamped by the request, approve '
                'and reject methods and cannot be set directly.'
            ) % ', '.join(sorted(self._REPLACEMENT_STAMPS & set(vals))))
        if vals.get('state', 'scrapped') != 'scrapped' \
                and any(r.state == 'scrapped' for r in self):
            raise ValidationError(_(
                'A scrapped tag stays scrapped: %s. Its number is never '
                'reissued; approving a replacement mints a new one.'
            ) % ', '.join(r.name for r in self if r.state == 'scrapped'))
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
    # `import_source`, `import_date` and `import_ref` are TRACKED since
    # handoff 28, with the GRN, PO and vendor references in `asset.py` — see
    # the note there for what that buys and where it begins.
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
    ], string='Data Source', default='myservice', tracking=True)
    import_date = fields.Date('Import Date', tracking=True)
    import_ref = fields.Char('Import Reference', tracking=True)

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
        # The highest NUMBER issued under this prefix, compared as a number.
        # This was `search(order='name desc', limit=1)` — a TEXT sort, under
        # which `NRS-GEN-999` outranks `NRS-GEN-8305` — so past 999 tags of
        # one prefix every new tag started at 1000 and the loop below walked
        # every number already taken, one COUNT each: ~7,300 queries and ~11 s
        # per asset on `test19` (8,237 such labels), and the same walk on the
        # one `nrs19` prefix and eight `jaizbankplc` prefixes past 999. Found
        # in handoff 46 by asking why the suite ran four times slower. Issued
        # now: the number after the highest. Where numbers are contiguous that
        # is what the walk reached; where a number above 999 was never used,
        # the walk would have filled it and this does not — no number is ever
        # issued twice either way, which is the rule the loop below enforces.
        # The prefix is `[A-Z0-9-]` only (`_tag_prefix`), so LIKE is safe.
        Tag.flush_model(['name'])
        self.env.cr.execute(
            "SELECT max(substr(name, %s)::bigint) FROM nrs_asset_tag_label "
            "WHERE name LIKE %s AND substr(name, %s) ~ '^[0-9]+$'",
            (len(prefix) + 1, prefix + '%', len(prefix) + 1))
        highest = self.env.cr.fetchone()[0]
        seq = (highest or 0) + 1
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
        except Exception:          # noqa: BLE001
            # catch-all: reported — deliberately broad and deliberately not
            # re-raised. The PDF in `result` already exists, so failing the
            # print over its own bookkeeping would take a working label away
            # from somebody holding a printer, and this hook sits under every
            # report render in the product, not only ours. What it can meet is
            # correspondingly open: a readonly cursor, a second connection the
            # registry cannot hand out, `nrs.asset` absent on a tenant that
            # does not carry the asset modules, anything `_mark_printed` grows.
            # The traceback is logged with both the report and the ids, because
            # this is the funnel that recorded 2 prints in 17,217 labels while
            # saying nothing at all (handoff 10) — an unstamped print must
            # leave an ERROR line behind, which is how the next regression gets
            # noticed rather than measured a year later.
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
