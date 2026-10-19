from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.modules import module as odoo_module
from odoo.modules.registry import Registry
import base64
import hashlib
import logging
import re

import pytz

from .asset_event import EVENT_AFFIX_REFUSED

_logger = logging.getLogger(__name__)

#: Databases whose blocked unique index has been reported this process.
_INDEX_BLOCKED_REPORTED = set()

#: The register's day is a Lagos day (handoff 37) — the container's clock is
#: UTC, so a void at 23:30 UTC belongs to the next day in Lagos.
_LAGOS = pytz.timezone('Africa/Lagos')


def _lagos_date(dt):
    """`YYYY-MM-DD` of a UTC datetime, on the Lagos calendar."""
    if not dt:
        return ''
    return pytz.utc.localize(dt).astimezone(_LAGOS).strftime('%Y-%m-%d')


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
    # A LITERAL list, on purpose: `tests/test_frontend_enums.py` reads it out
    # of this source to hold the app's seed to it. `void_reason` below reads
    # its values from here, so the two cannot drift apart.
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

    # ── Prints of one number (handoff 61, ruling R3) ──────────────
    #
    # ONE ROW IS ONE PHYSICAL PRINT. Since handoff 61 an approved replacement
    # reprints the label under the SAME number — "the number on the asset
    # doesn't change because a sticker faded" — so a number can have several
    # rows: every print that was ever issued for it, at most one of them
    # `active` (`_check_unique_active`). What tells them apart is recorded
    # here, on the rows, by the approval and by nothing else
    # (`_REPLACEMENT_STAMPS`):
    #
    # * `reprint_count` on EVERY print — 0 for the first print of a number,
    #   the voided print's count + 1 for its reprint. Which print is current
    #   is the `active` row; which one it is, is its count.
    # * `voided_date` and `void_reason` on the print that was VOIDED — when
    #   it stopped being valid and why. On the voided row rather than on its
    #   successor because the void is a fact about THAT print: it is what an
    #   affix refusal of that print names, and a print can be voided with no
    #   successor ever having been made of it (none today, but the record
    #   should not need one to say why a print is dead). The successor reads
    #   it through `replaces_id`.
    #
    # `void_reason` is a stamp, not the editable `replacement_reason` it is
    # copied from: `replacement_reason` is typed on the Odoo form before
    # *Request Replacement* and is writable afterwards by anybody who can
    # write the model, so a voided print's "why" read from it could be
    # rewritten after the fact. The stamp cannot.
    reprint_count = fields.Integer(
        'Print Number', default=0, readonly=True, copy=False,
        help='0 for the first print of this number; each approved '
             'replacement reprints the label under the same number and '
             'counts one more.')
    voided_date = fields.Datetime(
        'Print Voided On', readonly=True, copy=False,
        help='When this print was voided by an approved replacement.')
    void_reason = fields.Selection(
        selection='_void_reason_selection', string='Print Voided Because',
        readonly=True, copy=False,
        help='Why this print was voided: the replacement reason, recorded '
             'at the approval and not editable afterwards.')

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

    def _void_reason_selection(self):
        """`replacement_reason`'s values: a print is voided for the reason
        its replacement was asked for."""
        return self._fields['replacement_reason'].selection

    # ── One number, one active label — measured, then enforced ────────
    #
    # `_check_unique_active` below has always promised it, and the data
    # does not keep the promise: report 61 §1 counted 84 numbers active on
    # two assets (68 `test19`, 15 `jaizbankplc`, 1 `nrs19`), cause not
    # established (the Jaiz seed's SQL re-brand of tag prefixes, concurrent
    # mints). A Python constraint sees only the ORM; the PARTIAL UNIQUE
    # INDEX below is what holds against everything else — but it cannot be
    # created on a table that already breaks it, and which of two assets is
    # the real holder of a number is a data question for a person, not
    # this code (handoff 63, ruling 2: nothing is cleaned automatically).
    #
    # So: the back office lists them (Asset Tags → *Tags active on two
    # assets*, the search below), and `init` creates the index on every
    # upgrade of this module where the count reads ZERO, and says in the
    # upgrade log, per database, how many stand in its way where it does
    # not. The owner turns it on by resolving the listed labels and
    # upgrading `myservice_asset_register` on that database.
    ACTIVE_NUMBER_INDEX = 'nrs_asset_tag_label_active_name_uniq'

    active_number_shared = fields.Boolean(
        'Active on Two Assets', compute='_compute_active_number_shared',
        search='_search_active_number_shared',
        help='This label is active and the same number is active on '
             'another label too — another asset\'s in every case measured '
             '(84 of 84 numbers, report 61). Exactly the labels that keep '
             'the unique index from being created. Which asset really '
             'holds the number is for a person to decide; nothing resolves '
             'it automatically.')

    @api.model
    def _shared_active_number_ids(self):
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT t.id FROM nrs_asset_tag_label t
             WHERE t.state = 'active' AND EXISTS (
                   SELECT 1 FROM nrs_asset_tag_label o
                    WHERE o.state = 'active' AND o.name = t.name
                      AND o.id <> t.id)""")
        return [r[0] for r in self.env.cr.fetchall()]

    def _compute_active_number_shared(self):
        shared = set(self._shared_active_number_ids()) if self else set()
        for r in self:
            r.active_number_shared = r.id in shared

    def _search_active_number_shared(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('Search "Active on Two Assets" with = or != '
                              'and true or false.'))
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in',
                 self._shared_active_number_ids())]

    @api.model
    def _active_number_duplicates(self):
        """`(numbers, labels)` active on more than one label."""
        self.env.cr.execute("""
            SELECT count(*), coalesce(sum(n), 0) FROM (
                SELECT count(*) AS n FROM nrs_asset_tag_label
                 WHERE state = 'active' GROUP BY name HAVING count(*) > 1) d""")
        numbers, labels = self.env.cr.fetchone()
        return numbers, labels

    def init(self):
        super().init()
        cr = self.env.cr
        cr.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s",
                   [self.ACTIVE_NUMBER_INDEX])
        if cr.fetchone():
            return
        numbers, labels = self._active_number_duplicates()
        if numbers:
            # `init` runs once per module the upgrade loads that extends this
            # model; say it once per database and process.
            if cr.dbname in _INDEX_BLOCKED_REPORTED:
                return
            _INDEX_BLOCKED_REPORTED.add(cr.dbname)
            _logger.warning(
                'Tag numbers on %s: %d number(s) are active on more than one '
                'label (%d labels), so the unique index %s that holds one '
                'active label per number is NOT created. Resolve them in the '
                'back office (Asset Tags → filter "Tags active on two '
                'assets"), then upgrade myservice_asset_register on this '
                'database to create it.', cr.dbname, numbers, labels,
                self.ACTIVE_NUMBER_INDEX)
            return
        cr.execute("CREATE UNIQUE INDEX %s ON nrs_asset_tag_label (name) "
                   "WHERE state = 'active'" % self.ACTIVE_NUMBER_INDEX)
        _logger.info('Tag numbers on %s: 0 numbers active on two labels; '
                     'created the unique index %s.', cr.dbname,
                     self.ACTIVE_NUMBER_INDEX)

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
    # Handoff 38. The three steps (active → pending → scrapped, and since
    # handoff 61 the scrapped print REPRINTED under the same number) and the
    # requester/approver columns were already here; what the model
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
        # Handoff 61: which print this is, and when and why a print was
        # voided. A count somebody can type would make "reprint 3" evidence
        # of nothing.
        'reprint_count', 'voided_date', 'void_reason',
    })

    #: What a CREATE may not carry without the approval's context. The
    #: write guard above never saw `create`, which is how the chain used to
    #: be set (by a write after the mint); since handoff 61 the reprint is
    #: CREATED with its count and its link, so the same refusal is needed at
    #: the other door. The decision stamps are not here — no create path has
    #: ever sent them and the write guard covers every later change.
    _CREATE_STAMPS = frozenset({
        'replaces_id', 'replaced_by_id',
        'reprint_count', 'voided_date', 'void_reason',
    })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(self.REPLACEMENT_KEY):
            for vals in vals_list:
                claimed = self._CREATE_STAMPS & {
                    k for k, v in vals.items() if v}
                if claimed:
                    raise ValidationError(_(
                        'Print fields (%s) are stamped when a replacement is '
                        'approved and cannot be set on a new label.'
                    ) % ', '.join(sorted(claimed)))
        return super().create(vals_list)

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
                'hold the Asset Manager role.'
            ) % {'user': user.display_name})

    def _reason_label(self, value):
        return dict(self._fields['replacement_reason'].selection).get(
            value, value)

    def action_request_replacement(self, reason=None, notes=None,
                                   approver=None):
        """Ask a second person to agree that this print be voided and the
        label reprinted under the same number.

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
                    'tag %s. A label is reprinted only when a second person '
                    'agrees.') % r.name)
            if who.id == self.env.uid:
                raise UserError(_(
                    'You cannot ask yourself to approve your own request. '
                    'Name somebody else.'))
            if not who.has_group(self._approver_group()) \
                    and not who._is_admin():
                raise UserError(_(
                    '%s cannot approve a tag replacement. An approver must '
                    'hold the Asset Manager role.'
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
        """Void this print and reprint the label under the SAME number.
        Returns the reprints.

        Handoff 61, ruling R3: *the number on the asset doesn't change
        because a sticker faded.* Until 61 this scrapped the label and
        called `nrs.asset._generate_tag`, which minted a new number — and on
        a unit that came through the receipt gates, whose label carries the
        ASSET CODE (ruling 4.3), the gated `_generate_tag` handed it to the
        location-prefix generator, so the replacement of a gated unit's
        label was no longer its code (findings §5.6; on `test19` 24 of the
        172 replacements made before 61 did exactly that). The approval no
        longer mints anything, so there is nothing for either generator to
        get wrong: whatever the number was — an asset code, a location
        prefix, an imported or SAP number — the reprint carries it.

        One row is one print, so the voided print keeps its row (`scrapped`
        on both lifecycles, its void stamped) and the reprint is a NEW row
        under the same `name`, `reprint_count` one higher, `replaces_id`
        naming the print it replaces. `source` is the number's provenance and
        is copied: a reprint of an auto-generated, imported or SAP number is
        still that number. `asset_tag` is not written — it already is this
        number.

        `_check_unique_active` still holds one active label per number: the
        voided print is written `scrapped` BEFORE the reprint is created, so
        when the constraint runs on the new row the only other row with its
        number is no longer active. A number ALREADY active on another asset
        — which the Python constraint did not prevent: 84 numbers on three
        local tenants on 2026-10-15 (68 on `test19`, 15 on `jaizbankplc`, 1 on
        `nrs19`), each on two assets, written by paths that went round it
        (the seed scripts' SQL re-brand of tag prefixes is one candidate,
        concurrent mints another; not established) — is refused before
        anything is written, because reprinting it would print a second
        asset's label.
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
            clash = self.sudo().search([
                ('name', '=', r.name), ('state', '=', 'active'),
                ('id', '!=', r.id)], limit=1)
            if clash:
                raise UserError(_(
                    'Tag %(tag)s cannot be reprinted: the same number is also '
                    'active on %(other)s. A number issued to two assets has '
                    'to be resolved before either label is reprinted, or the '
                    'reprint would be the other asset\'s label too.'
                ) % {'tag': r.name, 'other': clash.asset_id.display_name})
            now = fields.Datetime.now()
            r._replacement_ctx().with_context(cadra_tag_capture=True).write({
                'state': 'scrapped',
                'label_state': 'scrapped',
                # The Lagos day of the void, so the date on the row and the
                # date the affix refusal names are the same day.
                'scrapped_date': _lagos_date(now),
                'approved_by': self.env.uid,
                'approved_date': now,
                'decision_reason': (decision_reason or '').strip() or False,
                'voided_date': now,
                'void_reason': r.replacement_reason or False,
            })
            new_tag = self._replacement_ctx().create({
                'name': r.name,
                'asset_id': r.asset_id.id,
                'source': r.source or 'auto',
                'state': 'active',
                'reprint_count': r.reprint_count + 1,
                'replaces_id': r.id,
            })
            r._replacement_ctx().write({'replaced_by_id': new_tag.id})
            r.message_post(
                body=_('Replacement approved by %(who)s. %(old)s of tag '
                       '%(tag)s voided (%(why)s); %(new)s issued under the '
                       'same number.') % {
                    'who': self.env.user.display_name,
                    'old': r._print_name().capitalize(),
                    'tag': r.name,
                    'why': r._reason_label(r.void_reason) or _('no reason'),
                    'new': new_tag._print_name()},
                partner_ids=r.requested_by.partner_id.ids)
            new_tags |= new_tag
        return new_tags

    # ── Words for one print, for the refusals and the chatter ─────────

    def _print_name(self, count=None):
        """'the original print' or 'reprint N' — `reprint_count` in words."""
        n = self.reprint_count if count is None else count
        return _('the original print') if not n else _('reprint %d') % n

    def _void_words(self):
        """'voided on 2026-10-15 (Damaged / Unreadable)' for this print.

        A row scrapped before handoff 61 has no void stamp; its scrap date
        and its (editable) replacement reason are the best record there is,
        and the sentence uses them rather than inventing a void."""
        self.ensure_one()
        when = (_lagos_date(self.voided_date) if self.voided_date
                else fields.Date.to_string(self.scrapped_date)
                if self.scrapped_date else _('an unrecorded date'))
        why = self._reason_label(self.void_reason or self.replacement_reason)
        return _('voided on %(when)s (%(why)s)') % {
            'when': when, 'why': why or _('no reason recorded')}

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
                'A scrapped tag stays scrapped: %s. A voided print never '
                'comes back into service; approving a replacement reprints '
                'the label under the same number, as a new print.'
            ) % ', '.join(r.name for r in self if r.state == 'scrapped'))
        return super().write(vals)

    def _mark_printed(self):
        """Record that a print instruction was issued for these labels.

        `printed` means Cadra emitted the instruction — Integration Flow step
        3.3 — not that paper physically emerged from a printer, which Cadra
        cannot observe. A label already `affixed` is not walked backwards:
        printing again a label someone has already stuck on an asset does not
        make the asset less tagged. (Printing the same ROW again is not a
        *reprint* in handoff 61's sense — that is a new row, made by an
        approved replacement, with its own `reprint_count`; printing it is
        what lets its affix through.)
        """
        to_mark = self.filtered(lambda t: t.label_state in ('issued', 'printed'))
        if to_mark:
            to_mark.with_context(cadra_tag_capture=True).write({
                'label_state': 'printed',
                'printed_date': fields.Datetime.now(),
                'printed_by': self.env.uid,
            })
        return to_mark

    def _record_affix_refusal(self, scanned_value, reason='number_mismatch',
                              scanned_format=None):
        """Append the refused affix to `nrs.asset.event`, on its own cursor.

        `reason` is WHICH refusal — `number_mismatch` (handoff 51, and what
        a NULL on a pre-52 row means), `scrapped` or `serial_mismatch`
        (handoff 52 §4), or `voided_print` (handoff 61: the reprint of a
        number confirmed before anybody printed it, so the label in hand can
        only be the print it voided). It is the recorder's own key, never
        caller text.
        `scanned_value` is what the operative entered: a tag number for the
        first two, the scanned serial for the third. `scanned_format` is
        how THAT value was read, when the caller knew (handoff 54 §7 — the
        app's camera passes the symbology up; a typed entry passes
        nothing), already validated against `SCANNED_FORMATS` at the route;
        the event model's Selection refuses anything else here.

        ON ITS OWN CURSOR because the `ValidationError` this precedes does
        not stay here: the API decorator turns it into the 400 and calls
        `request.env.cr.rollback()` on the whole request transaction
        (`myservice_api/controllers/utils.py`), so a row written on the
        request's cursor is unwound with everything else — measured on
        `test19` before this shape was chosen (report 51 §2). The separate
        cursor commits independently, which is the honest boundary: the
        refusal is final the moment it is raised, whatever happens to the
        request afterwards. Nothing written here can outlive a SUCCESSFUL
        affix being rolled back, because a successful affix writes nothing
        here.

        UNDER A RUNNING TEST the row goes on the CURRENT cursor instead,
        and the branch is on `current_test`, not on taste: only `HttpCase`
        patches `registry.cursor` to hand back a `TestCursor` over the test
        transaction — a plain `TransactionCase` (which is what calls
        `_mark_affixed` with a wrong number in `myservice_workflow`'s
        suites) gets a REAL second connection, whose insert then waits on
        the test's own uncommitted asset row at the foreign-key check and
        never returns. Same-cursor under a test means the row is visible
        to the test that provoked it and rolled back with it, which is
        what a suite write should do.

        The payload is the scanned number AS ENTERED; the expected number
        is on this label row and is not copied. The event's `source` is
        whatever the caller declared through the context (`api_affix` from
        the affix route) and `direct` otherwise, exactly as every other
        event source is resolved. A failure to record is an ERROR line and
        never blocks the refusal itself — but unlike the print stamp this
        is a control's record, so the line is the alarm, not an apology.
        """
        self.ensure_one()
        # As entered, which is the evidence; '(none)' mirrors the refusal
        # text when nothing was sent at all.
        scanned = scanned_value or '(none)'
        try:
            if odoo_module.current_test:
                self.env['nrs.asset.event']._record(
                    self.asset_id, EVENT_AFFIX_REFUSED, to_value=scanned,
                    reason=reason, scanned_format=scanned_format)
                return
            with Registry(self.env.cr.dbname).cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                env['nrs.asset.event']._record(
                    env['nrs.asset'].browse(self.asset_id.id),
                    EVENT_AFFIX_REFUSED, to_value=scanned,
                    reason=reason, scanned_format=scanned_format)
                cr.commit()
        except Exception:   # noqa: BLE001
            # catch-all: reported — the refusal below must reach the
            # operative whatever went wrong with its own bookkeeping, and
            # an unrecorded refusal must leave an ERROR line behind rather
            # than nothing (the print funnel's lesson, handoff 10).
            _logger.exception(
                "could not record the refused affix for tag %s (asset %s)",
                self.name, self.asset_id.id)

    def _mark_affixed(self, scanned_tag_number, affixed_by_name=None,
                      affixed_date=None, scanned_format=None):
        """Record the serial-to-tag match at the point of physical tagging.

        The scanned number is checked against this label's own number rather
        than trusted, because that check IS the control: it is what makes the
        record evidence that the label on the asset is the label Cadra issued
        for it, rather than an assertion that someone tagged something.

        `scanned_format` is how the number was read, when the caller knew,
        and it reaches ONLY the refusal records below — a successful affix
        stores nothing new, by ruling (handoff 54 §7): the format earns its
        column where it tells an auditor whether a refused number came off
        Cadra's label or a manufacturer's, and nowhere else.

        ── A reprint, and the print it voided (handoff 61) ─────────────────

        A reprint carries the SAME number as the print it replaces, so the
        voided label and the reprint encode the same value and no scanner
        can tell them apart — the number is the whole of what a label says.
        What the server CAN reason about is time: while the reprint has not
        been printed (`label_state` still `issued`), the only label carrying
        this number that can physically exist is the voided one, so a scan
        that matches is refused as `voided_print` and the sentence names the
        void, its date and its reason. Once the reprint is printed — the PDF
        funnel (`_render_qweb_pdf`) or the app's station
        (`POST /api/v1/tags/printed`) records it — a matching scan is
        accepted: it is then either the reprint or a voided print the tagger
        has not peeled off, and nothing on the paper says which. The first
        print of a number (`reprint_count` 0) is not held to this, exactly as
        before 61: there is no earlier print it could be confused with.
        """
        self.ensure_one()
        if self.state == 'scrapped' or self.label_state == 'scrapped':
            # This refusal leaves a record too — handoff 52 §4. Through the
            # API route it is unreachable (the route confirms against
            # `active_tag_id`, which a scrapped label no longer is — report
            # 39), but every caller of the CHECK passes here: the Odoo form,
            # a script, a shell. A dead label presented for confirmation is
            # exactly the kind of act an auditor asks about afterwards.
            # Since handoff 61 the sentence names WHICH print is dead, when
            # and why, and what is in service in its place.
            self._record_affix_refusal(scanned_tag_number, reason='scrapped',
                                       scanned_format=scanned_format)
            successor = self.replaced_by_id
            if successor and successor.name == self.name:
                instead = _(' The label in service is %s, under the same '
                            'number.') % successor._print_name()
            elif successor:
                instead = _(' It was replaced by tag %s.') % successor.name
            else:
                instead = ''
            raise ValidationError(_(
                'Tag %(tag)s has been scrapped: %(print)s was %(void)s and '
                'cannot be confirmed as affixed.%(instead)s'
            ) % {'tag': self.name, 'print': self._print_name(),
                 'void': self._void_words(), 'instead': instead})
        if (scanned_tag_number or '').strip() != self.name:
            # The refusal leaves a record BEFORE it is raised — handoff 51.
            # The refusal text below names the expected number (ruled in
            # handoff 39: a person holding the wrong label must be told
            # which label is wanted), which means one wrong entry reveals
            # the right answer and a second attempt with it will pass. The
            # event row is what makes that sequence visible to anybody
            # reading the history: a refusal and a confirmation seconds
            # apart, same asset, same operative.
            self._record_affix_refusal(scanned_tag_number,
                                       reason='number_mismatch',
                                       scanned_format=scanned_format)
            raise ValidationError(_(
                'Scanned tag %(scanned)s does not match the tag issued for '
                'this asset (%(expected)s). The label on the asset is not the '
                'one Cadra issued for it.'
            ) % {'scanned': scanned_tag_number or '(none)', 'expected': self.name})

        if self.reprint_count and self.label_state == 'issued':
            # Handoff 61 — see the docstring. Recorded before it is raised,
            # like every affix refusal, so the scan is in the history even
            # though the number matched.
            self._record_affix_refusal(scanned_tag_number,
                                       reason='voided_print',
                                       scanned_format=scanned_format)
            voided = self.replaces_id
            raise ValidationError(_(
                'Tag %(tag)s is %(print)s and has not been printed yet, so '
                'the label being scanned can only be %(old)s, %(void)s. '
                'Print %(print)s, then confirm it.'
            ) % {'tag': self.name, 'print': self._print_name(),
                 'old': voided._print_name() if voided
                 else self._print_name(self.reprint_count - 1),
                 'void': voided._void_words() if voided
                 else _('voided by its replacement')})

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
            # Auto-generate tag unless one is provided via import — and never
            # for a unit identified by its SAP record, which carries no label
            # (handoff 59 §2). Since handoff 60 such a unit is stamped
            # `record_only` with the gates off too, and `_generate_tag`
            # refuses it, so creation leaves it out rather than fail.
            if not vals.get('asset_tag') \
                    and vals.get('tag_source', 'auto') == 'auto' \
                    and rec.identification_mode != 'record_only':
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

    def _tag_sequence(self, prefix, highest):
        """The Postgres sequence that numbers tags under `prefix`, created
        the first time the prefix is used and started at `highest`.

        Named by a digest of the prefix (a prefix is `[A-Z0-9-]`, and an
        identifier must be short and unquoted). Creation takes a
        transaction-scoped advisory lock on the name, so two first mints of
        one prefix do not both create it: the second waits, then finds it —
        the catalog is read fresh, not through the transaction's snapshot.
        """
        name = 'cadra_tag_seq_%s' % hashlib.sha1(
            prefix.encode()).hexdigest()[:20]
        cr = self.env.cr
        cr.execute("SELECT to_regclass(%s)", (name,))
        if not cr.fetchone()[0]:
            cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (name,))
            # IF NOT EXISTS as well as the lookup: it checks the catalog at
            # execution, so a lookup that ran ahead of the other creator's
            # commit cannot turn into a "relation already exists".
            cr.execute('CREATE SEQUENCE IF NOT EXISTS "%s" MINVALUE 0 START %d'
                       % (name, int(highest)))
        return name

    def _tag_sequence_next(self, sequence, at_least):
        """The next number from `sequence`, above `at_least`.

        `setval(GREATEST(nextval, at_least + 1))` in one statement: `nextval`
        alone when the sequence is ahead (every mint through here), lifted
        past a number issued around it otherwise. The lift is the one place
        two concurrent mints could still meet — both lifting to the same
        number, which only happens just after an import wrote numbers above
        the sequence — and the unique index answers that `tag_number_taken`,
        which a caller retries (`docs/api/cadra_api_endpoint_reference.md`).
        """
        self.env.cr.execute(
            'SELECT setval(%s, GREATEST(nextval(%s), %s))',
            (sequence, sequence, int(at_least) + 1))
        return self.env.cr.fetchone()[0]

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
        #
        # Since handoff 63b the number comes from a Postgres SEQUENCE per
        # prefix, not from that max plus one. Two receipts of one class
        # posted 100 ms apart (Vendra report 58: two chairs, both
        # `NRS-FURN-018`, `test19` assets 106911 and 106912) each read the
        # same max — Odoo's REPEATABLE READ snapshot hides the other's
        # uncommitted, then committed, row — and minted the same number: a
        # duplicate where no unique index stands, a 409 where report 63's
        # does. No lock fixes that inside a snapshot taken before the lock;
        # `nextval` is outside every snapshot and never hands one value to
        # two transactions. The max is still read: it starts the sequence,
        # and lifts it past numbers issued without it (an import, a seed).
        Tag.flush_model(['name'])
        self.env.cr.execute(
            "SELECT max(substr(name, %s)::bigint) FROM nrs_asset_tag_label "
            "WHERE name LIKE %s AND substr(name, %s) ~ '^[0-9]+$'",
            (len(prefix) + 1, prefix + '%', len(prefix) + 1))
        highest = self.env.cr.fetchone()[0] or 0
        sequence = self._tag_sequence(prefix, highest)
        seq = self._tag_sequence_next(sequence, highest)
        tag_number = '%s%03d' % (prefix, seq)
        # Check every tag, not just the active ones: a MINT is a new number,
        # and a number that has ever been printed belongs to the asset it
        # was printed for. (Until handoff 61 this also said that reissuing a
        # scrapped number would make the replacement history ambiguous — two
        # physical labels sharing one code. Ruling R3 answered that: a
        # replacement now REPRINTS under the same number on purpose, and the
        # history stays unambiguous because every print is its own row with
        # its `reprint_count`, and the print it replaced carries its void —
        # when, why, approved by whom. The reprint never comes through here.)
        while Tag.search_count([('name', '=', tag_number)]):
            # capped-count-ok: a sequence number, not a count of
            # anything. `existing` is a limit=1 lookup of the highest
            # tag already issued, which is what it should be.
            seq = self._tag_sequence_next(sequence, seq)
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
