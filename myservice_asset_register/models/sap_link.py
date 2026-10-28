# -*- coding: utf-8 -*-
"""The link — a register asset given its SAP asset number from the mirror,
by two people (handoff 65).

What this is, plainly: handoff 63 loaded SAP's asset master beside the
register (`nrs.sap.asset`) and measured that 2,445 of NRS's Cadra assets
point at exactly one SAP record with confidence — a unique old FIRS tag, or
a unique serial — and that nobody had ever written the number across. A
LINK writes it: the asset's `sap_asset_number` becomes the mirror record's,
with `sap_code_source = linked_from_sap_mirror`.

It is maker-checker, like a registration, because it changes what Cadra
tells SAP from then on: every move, handover and disposal of a linked asset
goes to SAP as an INT-09 event against that number. The Register Maker
PROPOSES, the Register Checker APPROVES or RETURNS; one person may not do
both on one asset — the no-two-gates rule of the receipt chain
(`asset_gates`), with two gates of its own, `link_make` and `link_check`.
Undoing a link is the same two acts with a reason. A link row is never
deleted; a decided one is frozen.

**No asset master is queued.** The master already exists in SAP — that is
what the mirror says. `myservice_workflow` queues `asset.master.create` at
a gated registration and at a gates-off affix, and refuses it for an asset
that already carries a number (`_queue_sap_event`); writing the number here
is a plain write of four fields, which raises nothing.

A link is not a receipt: it applies to an asset ON the register, so the
gate switch changes nothing here.

THE ROWS
--------
One `nrs.sap.link` per proposal: `kind` is `link` or `unlink` (an undo),
`state` `proposed` → `approved` | `returned`. At most one proposal is open
per asset and per SAP record (partial unique indexes), so two makers cannot
race one record onto two assets. Every act also writes an `nrs.asset.event`
of type `sap_link` on the asset, which is what the history reads and what
the no-two-gates rule reads.
"""
import itertools
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.constants import PREFETCH_MAX

from .asset_event import (EVENT_SAP_DUPLICATE_FLAGGED, EVENT_SAP_LINK)
from .asset_gates import (GATE_LINK_CHECK, GATE_LINK_MAKE, GateRefused,
                          REGISTERED, S_REGISTER_CHECK, S_REGISTER_MAKE)
from . import serial_placeholders
from .sap_mirror import LINKED_EXISTS, norm_number

#: The `sap_code_source` a link writes (`asset_sap`).
SAP_SOURCE_LINKED = 'linked_from_sap_mirror'
#: The flag `nrs.sap.link` sets on its own writes; `write` and `create`
#: refuse without it, and `asset_sap` refuses `linked_from_sap_mirror`
#: without it.
LINK_WRITE_KEY = 'cadra_sap_link'

LINK_KINDS = [('link', 'Link'), ('unlink', 'Undo a link')]
LINK_STATES = [('proposed', 'Proposed'), ('approved', 'Approved'),
               ('returned', 'Returned')]

#: The reasons a link may be proposed on, as a person reads them.
REASONS = {
    'old_tag_unique': 'old tag, unique',
    'serial_unique': 'serial, unique',
}
#: A contested record (§2): the maker chose one of several Cadra assets.
CONTESTED_SUFFIX = '; chosen from %d Cadra assets'

#: `env.cr.cache` slot holding the duplicate flags of ONE batch of assets
#: being serialized (handoff 66): `(prefetch_ids, {asset_id: event_id},
#: event_ids)`. Emptied by the only writer of a flag, `_sap_flag_duplicate`.
_FLAG_SLOT = 'cadra.sap_duplicate_flags'

_STAMP_FIELDS = ('state', 'decided_by_id', 'decided_at', 'return_reason')


class NRSSapLink(models.Model):
    _name = 'nrs.sap.link'
    _description = 'Link of a register asset to its SAP record'
    _order = 'id desc'

    kind = fields.Selection(LINK_KINDS, required=True, default='link',
                            readonly=True, index=True)
    state = fields.Selection(LINK_STATES, required=True, default='proposed',
                             readonly=True, index=True)
    asset_id = fields.Many2one('nrs.asset', required=True, readonly=True,
                               index=True, ondelete='restrict')
    sap_record_id = fields.Many2one('nrs.sap.asset', required=True,
                                    readonly=True, index=True,
                                    ondelete='restrict')
    sap_asset_number = fields.Char(
        readonly=True, help='The number the link writes (or, on an undo, '
                            'takes off), as it stood when proposed.')
    reason_code = fields.Char(readonly=True)
    reason = fields.Char(
        readonly=True, help="Why: the matcher's reason for a link (`old tag, "
                            "unique`), the maker's words for an undo.")
    note = fields.Text(readonly=True)
    proposed_by_id = fields.Many2one('res.users', required=True,
                                     readonly=True, ondelete='restrict')
    proposed_at = fields.Datetime(required=True, readonly=True)
    decided_by_id = fields.Many2one('res.users', readonly=True,
                                    ondelete='restrict')
    decided_at = fields.Datetime(readonly=True)
    return_reason = fields.Text(readonly=True)

    def init(self):
        # One open proposal per asset, and one per SAP record: two makers
        # cannot put one record on two assets by racing each other.
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS nrs_sap_link_open_asset_uniq "
            "ON nrs_sap_link (asset_id) WHERE state = 'proposed'")
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS nrs_sap_link_open_record_uniq "
            "ON nrs_sap_link (sap_record_id) WHERE state = 'proposed'")

    # ── the guard: acts only ──────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(LINK_WRITE_KEY):
            raise UserError(_(
                'A SAP link is proposed through Link to SAP, by the Register '
                'Maker; it cannot be created by hand.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get(LINK_WRITE_KEY):
            raise UserError(_(
                'A SAP link moves only by being approved or returned by the '
                'Register Checker; it cannot be edited.'))
        if set(vals) - set(_STAMP_FIELDS):
            raise UserError(_('Only a decision is written to a SAP link.'))
        if any(r.state != 'proposed' for r in self):
            raise UserError(_('A decided SAP link is frozen.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_(
            'A SAP link is never deleted. A link that no longer stands is '
            'undone — proposed and approved by two people, with a reason — '
            'and both acts stay on the record.'))

    # ── what a person reads ───────────────────────────────────────────

    def _who(self):
        """`(maker, checker)` names, for the history and the answer."""
        self.ensure_one()
        return (self.proposed_by_id.name or None,
                self.decided_by_id.name or None)

    def _record_event(self, action, gate, *, reason=None, actor=None,
                      override_of=None):
        self.ensure_one()
        maker, checker = self._who()
        notes = {'link_id': self.id, 'kind': self.kind,
                 'sap_record_id': self.sap_record_id.id,
                 'reason_code': self.reason_code or None,
                 'proposed_by': maker, 'decided_by': checker}
        if self.kind == 'link':
            frm, to = None, self.sap_asset_number
        else:
            frm, to = self.sap_asset_number, None
        self.env['nrs.asset.event']._record(
            self.asset_id, EVENT_SAP_LINK,
            source='api_sap_link' if self.asset_id._in_api() else None,
            actor=actor, from_value=frm, to_value=to, gate=gate,
            gate_action=action, reason=reason,
            notes=json.dumps(notes, sort_keys=True),
            admin_override=bool(override_of), override_of=override_of)

    # ── the checker's acts ────────────────────────────────────────────

    def _decide(self, approve, reason=None, scopes=None):
        """Approve or return one proposal. Every check before any write."""
        self.ensure_one()
        asset = self.asset_id.sudo()
        if self.state != 'proposed':
            raise GateRefused(_(
                'This SAP link was already %(state)s on %(day)s by %(who)s.',
                state=dict(LINK_STATES)[self.state],
                day=fields.Date.to_string(self.decided_at),
                who=self.decided_by_id.name or _('somebody')),
                'invalid_state', {'state': self.state})
        held = asset._gate_scopes(scopes)
        if S_REGISTER_CHECK not in held:
            raise GateRefused(_(
                'Deciding a SAP link needs the `%s` scope, which you do not '
                'hold.') % S_REGISTER_CHECK, 'forbidden',
                {'required_scopes': [S_REGISTER_CHECK]})
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if not approve and not text:
            raise GateRefused(_('A reason is required to return a SAP link '
                                '— say why, in words.'),
                              'validation_failed', {'field': 'reason'})
        # The no-two-gates rule: whoever proposed it may not decide it.
        lifted = asset._assert_two_gates(GATE_LINK_CHECK)
        if approve:
            if self.kind == 'link':
                self._assert_still_linkable()
            else:
                self._assert_still_linked()
        # ── everything after this line writes ──
        me = self.env.user
        self.with_context(**{LINK_WRITE_KEY: True}).sudo().write({
            'state': 'approved' if approve else 'returned',
            'decided_by_id': me.id,
            'decided_at': fields.Datetime.now(),
            'return_reason': False if approve else text,
        })
        if approve:
            rec = self.sap_record_id.sudo()
            if self.kind == 'link':
                vals = {
                    'sap_asset_number': rec.asset_number_norm,
                    'sap_asset_subnumber': (rec.sub_number or False)
                    if rec.sub_number_norm != '0' else False,
                    'sap_company_code': rec.company_code or False,
                    'sap_code_source': SAP_SOURCE_LINKED,
                }
            else:
                vals = {'sap_asset_number': False,
                        'sap_asset_subnumber': False,
                        'sap_company_code': False,
                        'sap_code_source': False}
            asset.with_context(**{LINK_WRITE_KEY: True}).write(vals)
        action = ('approve' if approve else 'return') + (
            '' if self.kind == 'link' else '_undo')
        self._record_event(action, GATE_LINK_CHECK if approve else None,
                           reason=self.reason if approve else text,
                           override_of=lifted)
        return self

    def _assert_still_linkable(self):
        """What made the proposal true must still be true when it is
        approved: the asset on the register with no SAP number, the record
        active, in the latest export and claimed by no Cadra asset."""
        asset, rec = self.asset_id.sudo(), self.sap_record_id.sudo()
        if asset.register_state != REGISTERED:
            raise GateRefused(_('%s is not on the register; only a register '
                                'asset is linked to SAP.') % asset.asset_code,
                              'invalid_state',
                              {'register_state': asset.register_state})
        if (asset.sap_asset_number or '').strip():
            raise GateRefused(_(
                '%(code)s already carries SAP asset number %(number)s; a '
                'link never replaces a number.', code=asset.asset_code,
                number=asset.sap_asset_number), 'invalid_state',
                {'sap_asset_number': asset.sap_asset_number})
        asset._refuse_posting_in_flight()
        if self.reason_code in ('old_tag_unique', 'serial_unique') \
                and 'chosen from' not in (self.reason or ''):
            # Proposed as uncontested; another Cadra asset may have come to
            # point at the same record since (verification pass, finding 9;
            # the serial twin, handoff 66).
            rivals = (asset._rivals_by_old_tag(rec)
                      if self.reason_code == 'old_tag_unique'
                      else asset._rivals_by_serial(rec))
            if rivals:
                raise GateRefused(_(
                    'SAP asset %(number)s is now also pointed at by '
                    '%(n)d other Cadra asset(s); return this proposal and '
                    'decide it on the contested list.',
                    number=rec.asset_number, n=len(rivals)), 'invalid_state',
                    {'contested': True, 'sap_record_id': rec.id,
                     'asset_ids': rivals})
        if not (rec.sap_active and rec.in_latest_export):
            raise GateRefused(_(
                'SAP asset %s is no longer active in the latest export of '
                "SAP's register.") % rec.asset_number, 'invalid_state',
                {'sap_record_id': rec.id})
        holder = rec._linked_assets().get(rec.id)
        if holder:
            other = self.env['nrs.asset'].sudo().with_context(
                cadra_candidates=True).browse(holder['asset_id'])
            raise GateRefused(_(
                'SAP asset %(number)s is already linked to %(code)s.',
                number=rec.asset_number, code=other.asset_code),
                'invalid_state', {'sap_record_id': rec.id,
                                  'linked_asset_id': other.id})

    def _assert_still_linked(self):
        asset = self.asset_id.sudo()
        if asset.sap_code_source != SAP_SOURCE_LINKED or norm_number(
                asset.sap_asset_number) != norm_number(self.sap_asset_number):
            raise GateRefused(_(
                '%(code)s no longer carries the linked SAP asset number '
                '%(number)s; there is nothing to undo.',
                code=asset.asset_code, number=self.sap_asset_number),
                'invalid_state', {'sap_asset_number': asset.sap_asset_number})


class NRSAssetSapLink(models.Model):
    _inherit = 'nrs.asset'

    sap_link_ids = fields.One2many('nrs.sap.link', 'asset_id',
                                   string='SAP Links', readonly=True)

    def _refuse_posting_in_flight(self):
        """A gates-off affix on an asset with no number queues INT-06's
        `asset.master.create` (`myservice_workflow`). Linking SAP's own
        number on top of a posting in flight would send SAP a second master
        for an asset it already holds (verification pass, finding 2) — so a
        link waits until that posting is decided: refused, in words."""
        self.ensure_one()
        if self.sap_posting_state in ('queued', 'posted'):
            raise GateRefused(_(
                '%(code)s already has an asset master posting to SAP '
                '(%(state)s); linking it to an existing SAP record now would '
                'give SAP two masters for one asset. Wait for SAP\'s answer '
                'and reconcile that instead.', code=self.asset_code,
                state=self.sap_posting_state), 'invalid_state',
                {'sap_posting_state': self.sap_posting_state})

    def _rivals_by_old_tag(self, rec):
        """Other register assets with no SAP number whose old tag,
        normalised as `sap_mirror.norm_tag` does, is the record's."""
        self.ensure_one()
        if not rec.old_tag_norm:
            return []
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id FROM nrs_asset WHERE id <> %s "
            "AND register_state = 'registered' "
            "AND coalesce(btrim(sap_asset_number), '') = '' "
            "AND regexp_replace(upper(replace(legacy_asset_code, E'\\\\', "
            "'/')), '\\s+', '', 'g') = %s", (self.id, rec.old_tag_norm))
        return [r[0] for r in self.env.cr.fetchall()]

    def _rivals_by_serial(self, rec):
        """Other register assets with no SAP number that the matcher would
        point at `rec` by its serial: the serial normalised as
        `serial_placeholders.normalise` does (stripped, upper-case, one
        space) equal to the record's `serial_norm`, and — the matcher tries
        a serial only when no active record carries the tag — no old tag
        carried by an active record of the latest export
        (`sap_mirror._confident_targets`)."""
        self.ensure_one()
        if rec.serial_kind != 'real' or not rec.serial_norm:
            return []
        # A value the tenant lists as a placeholder points no asset anywhere
        # (`_confident_targets` drops it on the register's side).
        if serial_placeholders.matcher(serial_placeholders.load(self.env))(
                rec.serial_norm):
            return []
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT a.id FROM nrs_asset a WHERE a.id <> %s "
            "AND a.register_state = 'registered' "
            "AND coalesce(btrim(a.sap_asset_number), '') = '' "
            "AND upper(btrim(regexp_replace(a.serial_number, '\\s+', ' ', "
            "'g'))) = %s "
            "AND NOT EXISTS (SELECT 1 FROM nrs_sap_asset s "
            "WHERE s.sap_active AND s.in_latest_export "
            "AND s.old_tag_norm = regexp_replace(upper(replace("
            "a.legacy_asset_code, E'\\\\', '/')), '\\s+', '', 'g'))",
            (self.id, rec.serial_norm))
        return [r[0] for r in self.env.cr.fetchall()]

    def _open_sap_link(self):
        self.ensure_one()
        return self.env['nrs.sap.link'].sudo().search(
            [('asset_id', '=', self.id), ('state', '=', 'proposed')], limit=1)

    def _assert_may_make_link(self, scopes):
        self.ensure_one()
        held = self._gate_scopes(scopes)
        if S_REGISTER_MAKE not in held:
            raise GateRefused(_(
                'Proposing a SAP link needs the `%s` scope, which you do not '
                'hold.') % S_REGISTER_MAKE, 'forbidden',
                {'required_scopes': [S_REGISTER_MAKE]})
        if self.register_state != REGISTERED:
            raise GateRefused(_(
                '%s is not on the register; only a register asset is linked '
                'to SAP. A receipt gets its SAP number at registration.')
                % self.asset_code, 'invalid_state',
                {'register_state': self.register_state})
        pending = self._open_sap_link()
        if pending:
            raise GateRefused(_(
                '%(code)s already has a SAP link proposal waiting on the '
                'Register Checker (by %(who)s).', code=self.asset_code,
                who=pending.proposed_by_id.name), 'invalid_state',
                {'link_id': pending.id})
        # The sentence an administrator's override lifted, or None
        # (handoff 70): the proposal's event records it.
        return self._assert_two_gates(GATE_LINK_MAKE)

    def _sap_link_propose(self, targets=None, sap_record=None, note=None,
                          scopes=None):
        """Propose linking this asset to the SAP record the matcher ranks
        first with confidence. `targets` is `_confident_targets()`, computed
        once per batch. A CONTESTED record is proposed only by naming it
        (`sap_record`, from the contested list): the maker chose."""
        self.ensure_one()
        Sap = self.env['nrs.sap.asset'].sudo()
        lifted = self._assert_may_make_link(scopes)
        self._refuse_posting_in_flight()
        targets = targets if targets is not None else Sap._confident_targets()
        hit = targets['target'].get(self.id)
        if (self.sap_asset_number or '').strip():
            raise GateRefused(_(
                '%(code)s already carries SAP asset number %(number)s.',
                code=self.asset_code, number=self.sap_asset_number),
                'invalid_state', {'sap_asset_number': self.sap_asset_number})
        if not hit:
            raise GateRefused(_(
                '%s has no confident match in the SAP mirror — no unique old '
                'tag and no unique serial on an active, unlinked record.')
                % self.asset_code, 'validation_failed', {'field': 'asset_id'})
        sap_id, basis = hit
        rivals = targets['claims'].get(sap_id, [])
        if sap_record is not None and sap_record.id != sap_id:
            raise GateRefused(_(
                '%(code)s does not point at SAP asset %(number)s.',
                code=self.asset_code, number=sap_record.asset_number),
                'validation_failed', {'field': 'sap_record_id'})
        if len(rivals) > 1 and sap_record is None:
            raise GateRefused(_(
                'SAP asset %(number)s is claimed by %(n)d Cadra assets; it '
                'is decided on the contested list, not proposed here.',
                number=Sap.browse(sap_id).asset_number, n=len(rivals)),
                'invalid_state', {'contested': True, 'sap_record_id': sap_id,
                                  'asset_ids': sorted(rivals)})
        rec = Sap.browse(sap_id)
        pending = self.env['nrs.sap.link'].sudo().search(
            [('sap_record_id', '=', sap_id), ('state', '=', 'proposed')],
            limit=1)
        if pending:
            raise GateRefused(_(
                'SAP asset %(number)s is already proposed for %(code)s.',
                number=rec.asset_number, code=pending.asset_id.asset_code),
                'invalid_state', {'link_id': pending.id})
        code = 'old_tag_unique' if basis == 'old_tag' else 'serial_unique'
        reason = REASONS[code]
        if len(rivals) > 1:
            reason += CONTESTED_SUFFIX % len(rivals)
        # ── everything after this line writes ──
        link = self.env['nrs.sap.link'].sudo().with_context(
            **{LINK_WRITE_KEY: True}).create({
                'kind': 'link', 'asset_id': self.id, 'sap_record_id': sap_id,
                'sap_asset_number': rec.asset_number_norm,
                'reason_code': code, 'reason': reason,
                'note': (note or '').strip() or False,
                'proposed_by_id': self.env.user.id,
                'proposed_at': fields.Datetime.now()})
        link._record_event('propose', GATE_LINK_MAKE, reason=reason,
                           override_of=lifted)
        # Handed back WITHOUT the write flag it was created under: a caller
        # holding the returned record must not be able to write a decision
        # onto it (found by `test_a_link_row_is_never_deleted_or_edited`).
        return self.env['nrs.sap.link'].browse(link.id)

    def _sap_unlink_propose(self, reason, scopes=None):
        """Propose undoing this asset's link, with a reason."""
        self.ensure_one()
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if not text:
            raise GateRefused(_('A reason is required to undo a SAP link — '
                                'say why, in words.'),
                              'validation_failed', {'field': 'reason'})
        if self.sap_code_source != SAP_SOURCE_LINKED:
            raise GateRefused(_(
                '%s carries no SAP number linked from the mirror; only a '
                'link is undone here.') % self.asset_code, 'invalid_state',
                {'sap_code_source': self.sap_code_source or None})
        lifted = self._assert_may_make_link(scopes)
        rec = self.env['nrs.sap.asset'].sudo()._for_asset(self)
        last = self.env['nrs.sap.link'].sudo().search(
            [('asset_id', '=', self.id), ('kind', '=', 'link'),
             ('state', '=', 'approved')], limit=1)
        rec = rec or last.sap_record_id
        if not rec:
            raise GateRefused(_(
                'The SAP record %(code)s was linked to is no longer in the '
                'mirror.', code=self.asset_code), 'invalid_state', {})
        link = self.env['nrs.sap.link'].sudo().with_context(
            **{LINK_WRITE_KEY: True}).create({
                'kind': 'unlink', 'asset_id': self.id,
                'sap_record_id': rec.id,
                'sap_asset_number': norm_number(self.sap_asset_number),
                'reason_code': 'undo', 'reason': text,
                'proposed_by_id': self.env.user.id,
                'proposed_at': fields.Datetime.now()})
        link._record_event('propose_undo', GATE_LINK_MAKE, reason=text,
                           override_of=lifted)
        return self.env['nrs.sap.link'].browse(link.id)

    # ── §2: the flag ──────────────────────────────────────────────────

    def _sap_duplicate_flags(self):
        """`{asset_id: latest flag event}` for these assets."""
        if not self.ids:
            return {}
        events = self.env['nrs.asset.event'].sudo().search(
            [('asset_id', 'in', self.ids),
             ('event_type', '=', EVENT_SAP_DUPLICATE_FLAGGED)],
            order='occurred_at desc, id desc')
        out = {}
        for ev in events:
            out.setdefault(ev.asset_id.id, ev)
        return out

    def _sap_duplicate_flag(self):
        """The latest duplicate flag event on this ONE asset, or an empty
        recordset — for the asset serializer (handoff 66: it was one event
        query per asset, N+1 on every asset list).

        Read for the asset's whole prefetch batch in one query — a page
        iterated with `for a in page` shares one `_prefetch_ids` object —
        and kept in a one-slot cursor cache keyed by THAT object, so the
        next asset of the same page is a dictionary hit and any other
        recordset reads afresh. A single record (its own prefetch) is never
        cached: what it says cannot outlive the call."""
        self.ensure_one()
        Event = self.env['nrs.asset.event'].sudo()
        prefetch = self._prefetch_ids
        cache = self.env.cr.cache
        slot = cache.get(_FLAG_SLOT)
        if slot is None or slot[0] is not prefetch or self.id not in slot[1]:
            ids = list(itertools.islice(dict.fromkeys(itertools.chain(
                (self.id,), (i for i in prefetch if isinstance(i, int)))),
                PREFETCH_MAX))
            flags = self.browse(ids)._sap_duplicate_flags()
            mapping = dict.fromkeys(ids, False)
            mapping.update({aid: ev.id for aid, ev in flags.items()})
            slot = (prefetch, mapping,
                    tuple(ev.id for ev in flags.values()))
            if len(ids) > 1:
                cache[_FLAG_SLOT] = slot
        event_id = slot[1][self.id]
        if not event_id:
            return Event
        return Event.browse(event_id).with_prefetch(slot[2])

    @api.model
    def _sap_flag_duplicate(self, sap_record, note, scopes=None,
                            targets=None):
        """Flag the Cadra assets that all point at `sap_record` as a likely
        duplicate: one event on each, the note on each. A record for NRS —
        nothing is merged, retired or deleted."""
        Sap = self.env['nrs.sap.asset'].sudo()
        targets = targets if targets is not None else Sap._confident_targets()
        group = self.sudo().browse(targets['claims'].get(sap_record.id, []))
        held = self._gate_scopes(scopes)
        if S_REGISTER_MAKE not in held:
            raise GateRefused(_(
                'Flagging a likely duplicate needs the `%s` scope, which you '
                'do not hold.') % S_REGISTER_MAKE, 'forbidden',
                {'required_scopes': [S_REGISTER_MAKE]})
        text = (note or '').strip() if isinstance(note, str) else ''
        if not text:
            raise GateRefused(_('A note is required to flag a likely '
                                'duplicate — say what you saw.'),
                              'validation_failed', {'field': 'note'})
        if len(group) < 2:
            raise GateRefused(_(
                'SAP asset %s is not contested — fewer than two Cadra assets '
                'point at it.') % sap_record.asset_number, 'invalid_state',
                {'sap_record_id': sap_record.id, 'assets': len(group)})
        flags = group._sap_duplicate_flags()
        number = sap_record.asset_number_norm
        if all(flags.get(a.id) and flags[a.id].to_value == number
               for a in group):
            first = flags[group[0].id]
            raise GateRefused(_(
                'This group was already flagged on %(day)s by %(who)s.',
                day=fields.Date.to_string(first.occurred_at),
                who=first.actor_name or _('somebody')), 'invalid_state',
                {'flagged_at': fields.Datetime.to_string(first.occurred_at)})
        Event = self.env['nrs.asset.event']
        # The serializer's batch cache is stale the moment a flag lands.
        self.env.cr.cache.pop(_FLAG_SLOT, None)
        for asset in group:
            Event._record(asset, EVENT_SAP_DUPLICATE_FLAGGED,
                          source='api_sap_link' if asset._in_api() else None,
                          to_value=number, notes=text)
        return group
