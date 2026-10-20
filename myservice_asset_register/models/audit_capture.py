# -*- coding: utf-8 -*-
"""The audit in the room — devices, code blocks, campaigns, captures and
their review (handoff 66; `docs/AI-CAPTURE-EVALUATION.md` R1, R2, R2a, R4).

What this is, plainly: an audit team walks a room. For each item the phone
captures it — offline — and syncs later. Each capture ends as exactly ONE of
three outcomes, and every outcome needs two people, the capturer and a
reviewer who accepts it (never the same person):

* **a · on Cadra's register** (`on_register`) — found by its Cadra label,
  its old FIRS tag or a pick from the room's list. Accepted, it is a
  VERIFICATION in place: location, condition and the photo. A missing or
  unreadable label is reprinted under its existing code (R3), the
  reviewer's acceptance being the approval. No new code.
* **b · in SAP's register, not Cadra's** (`in_sap`) — 63's matcher found
  its SAP record. Accepted, it is a new `nrs.asset` with SAP's number, class
  and capitalisation date from the mirror and the code the phone printed
  (R2). It enters at `registered`: the receipt gates do not apply (R1),
  and the event says why. **No asset master is queued** — SAP has it.
* **c · in neither** (`in_neither`) — *found, not in SAP*: an exception for
  the Asset Controller, who registers it as new through the normal Register
  Maker and Checker gates, or voids it with a reason. Its code is HELD
  (`in_review`), never registered automatically.

THE CODES (R2, R2a)
-------------------
`nrs.asset.code` is the ledger — AD-18's, finally built. ONE answer to
"which codes exist": every asset's code (backfilled by migration, then
written by `nrs.asset.create`), and every code the Asset Controller issues
to a device in a BLOCK. `reserved → in_review → active | void`, never
reissued; returning a block voids what it did not use. Block codes are
drawn from the asset-code sequence itself, so no asset created any other way
can ever be given one.

A DEVICE is not a credential (R4): the person signs in as themselves and the
phone names itself in `X-Cadra-Device`, checked against the person it is
bound to — one person at a time.

Every row here is written through the methods below; `write` refuses the
fields without `AUDIT_WRITE_KEY`, and nothing is ever deleted.
"""
import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..approval_policy import EXEMPT_KEY
from .asset_event import EVENT_AUDIT_CAPTURE, EVENT_GATE_FIRED
from .asset_gates import (GateRefused, REGISTERED, _GATE_WRITE_KEY,
                          MODE_RECORD_ONLY)
from .asset_movement import MOVEMENT_REASON_KEY, MOVEMENT_SOURCE_KEY
from .asset_photo import check_photo_size, sniff_photo
from .asset_sap import SAP_SOURCE_AUDIT, _SAP_AUDIT_CONTEXT
from .sap_mirror import LINKED_EXISTS, norm_tag

#: The flag every writer below sets; `write` refuses the guarded fields
#: without it.
AUDIT_WRITE_KEY = 'cadra_audit_record_write'
#: A different flag — set only by an outcome-b acceptance — lets `asset_sap`
#: accept `sap_code_source = audit_from_sap_mirror` (verification pass, 66:
#: one key for both let every audit write claim the source).
SAP_AUDIT_KEY = _SAP_AUDIT_CONTEXT

#: The scopes, spelled as literals for `asset_gates`' reason (the scope
#: table lives in `myservice_api`, which depends on this module).
S_AUDIT_READ = 'audit:read'
S_AUDIT_CAPTURE = 'audit:capture'
S_AUDIT_REVIEW = 'audit:review'
S_AUDIT_MANAGE = 'audit:manage'

OUTCOME_ON_REGISTER = 'on_register'
OUTCOME_IN_SAP = 'in_sap'
OUTCOME_IN_NEITHER = 'in_neither'
OUTCOMES = [
    (OUTCOME_ON_REGISTER, "Already on Cadra's register"),
    (OUTCOME_IN_SAP, "In SAP's register, not in Cadra's"),
    (OUTCOME_IN_NEITHER, 'Found, not in SAP'),
]
CODE_STATES = [('reserved', 'Reserved'), ('in_review', 'In review'),
               ('active', 'Active'), ('void', 'Void')]
CODE_SOURCES = [('block', 'Issued in a device block'),
                ('asset', 'Assigned when the asset was created'),
                ('backfill', 'Recorded from an existing asset')]
CAPTURE_STATES = [('pending_review', 'Waiting for review'),
                  ('accepted', 'Accepted'), ('returned', 'Returned')]
EXCEPTION_STATES = [('open', 'Open'), ('registered', 'Registered as new'),
                    ('voided', 'Voided')]
LABEL_STATES = [('present', 'On the item'), ('missing', 'Missing'),
                ('unreadable', 'Unreadable')]
#: The most codes one block may carry (handoff 66 §2).
MAX_BLOCK_SIZE = 500
#: How far back a capture may be dated: five working days (AI-NFR-02).
MAX_WORKING_DAYS_BACK = 5
#: Clock skew allowed on `captured_at` — a phone's clock is a phone's clock.
FUTURE_SKEW = timedelta(minutes=5)
#: The confirmed fields a capture may carry, and nothing else.
CONFIRMED_FIELDS = ('name', 'category_id', 'condition', 'make', 'model_name',
                    'serial_number', 'colour', 'material', 'dimensions',
                    'legacy_asset_code', 'notes')
CONDITIONS = ('new', 'good', 'fair', 'poor')
#: What the Asset Controller may complete when registering an exception as
#: new — its identity, as Section 12 asks of its class; nothing else.
IDENTITY_FIELDS = ('make', 'model_name', 'serial_number', 'colour',
                   'material', 'dimensions')

_LAGOS = pytz.timezone('Africa/Lagos')
_CODE_LOCK = 'cadra_audit_code_block'


def _refuse(message, kind='invalid_state', **details):
    return GateRefused(message, kind, details)


def lagos_today():
    return datetime.now(pytz.utc).astimezone(_LAGOS).date()


def earliest_capture_day(today=None):
    """The first Lagos day a capture may be dated: five working days back,
    Monday to Friday, today not counted."""
    day = today or lagos_today()
    left = MAX_WORKING_DAYS_BACK
    while left:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            left -= 1
    return day


class _Guarded(models.AbstractModel):
    """Written only through this module's methods, never deleted."""
    _name = 'nrs.audit.guarded.mixin'
    _description = 'Audit record guard'

    def write(self, vals):
        if not self.env.context.get(AUDIT_WRITE_KEY):
            raise UserError(_(
                'This audit record changes only through the audit routes '
                '(capture, review, the Asset Controller\'s acts), each of '
                'which records who did it.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_(
            'An audit record is never deleted. A device is deactivated, a '
            'block returned, a code voided, a capture returned or voided — '
            'each with who and when.'))

    def _w(self, vals):
        return self.with_context(**{AUDIT_WRITE_KEY: True}).sudo().write(vals)


# ─── devices (R4) ──────────────────────────────────────────────────────

class NRSAuditDevice(models.Model):
    _name = 'nrs.audit.device'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Audit capture device'
    _order = 'id desc'

    name = fields.Char(required=True)
    device_code = fields.Char(
        'Device Code', required=True, readonly=True, copy=False, index=True,
        help='What the phone sends in X-Cadra-Device. It names the device; '
             'it is not a credential — the person signs in as themselves.')
    user_id = fields.Many2one('res.users', 'Bound To', ondelete='restrict')
    bound_at = fields.Datetime(readonly=True)
    bound_by_id = fields.Many2one('res.users', readonly=True,
                                  ondelete='set null')
    registered_by_id = fields.Many2one('res.users', readonly=True,
                                       ondelete='set null')
    registered_at = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)
    deactivated_at = fields.Datetime(readonly=True)
    block_ids = fields.One2many('nrs.audit.code.block', 'device_id')

    _device_code_unique = models.Constraint(
        'UNIQUE (device_code)', 'A device code is unique.')

    @api.model
    def _register_device(self, name, user):
        name = (name or '').strip() if isinstance(name, str) else ''
        if not name:
            raise _refuse(_('Name the device — what is written on it, so the '
                            'team can tell one phone from another.'),
                          'validation_failed', field='name')
        if user:
            self._assert_bindable(user)
        now = fields.Datetime.now()
        me = self.env.user
        return self.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create({
            'name': name,
            'device_code': 'DEV-%s' % secrets.token_hex(4).upper(),
            'user_id': user.id if user else False,
            'bound_at': now if user else False,
            'bound_by_id': me.id if user else False,
            'registered_by_id': me.id, 'registered_at': now,
        })

    @api.model
    def _assert_bindable(self, user):
        if not user.active:
            raise _refuse(_('%s is deactivated; a device is bound to a '
                            'person who can sign in.') % user.display_name,
                          'validation_failed', field='user_id')

    def _bind(self, user):
        self.ensure_one()
        if not self.active:
            raise _refuse(_('Device %s is deactivated.') % self.name)
        if user:
            self._assert_bindable(user)
        open_block = self.block_ids.filtered(lambda b: b.state == 'issued')
        if open_block and open_block.user_id != user:
            raise _refuse(_(
                'Device %(device)s still carries block %(block)s, issued to '
                '%(who)s. Return the block first — its unused codes are '
                'voided — so no code is left reserved to a person who no '
                'longer holds the device.', device=self.name,
                block=open_block[0].name,
                who=open_block[0].user_id.display_name),
                block_id=open_block[0].id)
        self._w({'user_id': user.id if user else False,
                 'bound_at': fields.Datetime.now(),
                 'bound_by_id': self.env.user.id})
        return self

    def _deactivate(self):
        self.ensure_one()
        if self.block_ids.filtered(lambda b: b.state == 'issued'):
            raise _refuse(_('Return device %s\'s open block before '
                            'deactivating it.') % self.name)
        self._w({'active': False, 'deactivated_at': fields.Datetime.now()})
        return self

    @api.model
    def _from_header(self, value, user):
        """The device the caller names, checked against its binding."""
        code = (value or '').strip()
        if not code:
            raise _refuse(_(
                'Say which device this is: send the X-Cadra-Device header '
                'with the device code the Asset Controller registered.'),
                'validation_failed', header='X-Cadra-Device')
        device = self.sudo().with_context(active_test=False).search(
            [('device_code', '=', code)], limit=1)
        if not device:
            raise _refuse(_('No registered device has the code %s.') % code,
                          'validation_failed', header='X-Cadra-Device')
        if not device.active:
            raise _refuse(_('Device %s is deactivated.') % device.name,
                          'forbidden', device_id=device.id)
        if device.user_id != user:
            raise _refuse(_(
                'Device %(device)s is bound to %(who)s, not to you. The Asset '
                'Controller rebinds a device.', device=device.name,
                who=device.user_id.display_name or _('nobody')),
                'forbidden', device_id=device.id)
        return device


# ─── the ledger (R2, R2a) ───────────────────────────────────────────────

class NRSAssetCode(models.Model):
    _name = 'nrs.asset.code'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Asset code (the ledger)'
    _rec_name = 'code'
    _order = 'code'

    code = fields.Char(required=True, readonly=True, index=True)
    state = fields.Selection(CODE_STATES, required=True, default='reserved',
                             index=True)
    source = fields.Selection(CODE_SOURCES, required=True, default='asset')
    block_id = fields.Many2one('nrs.audit.code.block', index=True,
                               ondelete='restrict')
    device_id = fields.Many2one('nrs.audit.device', ondelete='restrict')
    user_id = fields.Many2one('res.users', 'Reserved To',
                              ondelete='set null')
    reserved_at = fields.Datetime()
    used_at = fields.Datetime('Used At')
    activated_at = fields.Datetime()
    voided_at = fields.Datetime()
    voided_by_id = fields.Many2one('res.users', ondelete='set null')
    void_reason = fields.Text()
    # SET NULL, not restrict: a ledger row must not pin every asset from
    # birth (the residue scripts and the suites delete assets made nowhere).
    # The code string stays, which is what the ledger is for.
    asset_id = fields.Many2one('nrs.asset', index=True, ondelete='set null')
    capture_id = fields.Many2one('nrs.audit.capture', ondelete='set null')
    # Handoff 67: a block code printed at a station is recorded, as every
    # tag label's print is (61). A code has no label row until an asset
    # carries it, so its prints are counted here, on the ledger.
    print_count = fields.Integer('Prints', default=0, readonly=True)
    first_printed_at = fields.Datetime(readonly=True)
    last_printed_at = fields.Datetime(readonly=True)
    last_printed_by_id = fields.Many2one('res.users', readonly=True,
                                         ondelete='set null')

    _code_unique = models.Constraint(
        'UNIQUE (code)', 'An asset code exists once.')

    def _set(self, vals):
        return self._w(vals)

    def _assert_reserved_to(self, user, device=None):
        """This code is a block code, still `reserved`, reserved to `user`
        (and to `device`, when one is named). The refusal says which."""
        self.ensure_one()
        if self.source != 'block' or self.user_id != user \
                or (device is not None and self.device_id != device):
            raise _refuse(_(
                'Code %(code)s is not reserved to you%(on)s. Only a code from '
                'a block issued to you is yours to print or void.',
                code=self.code,
                on=(_(' on this device (%s)') % device.name) if device else ''),
                'forbidden', code=self.code)
        if self.state != 'reserved':
            raise _refuse(_(
                'Code %(code)s is %(state)s; only a code not yet used can be '
                'printed or voided by its holder.', code=self.code,
                state=dict(CODE_STATES)[self.state].lower()),
                code=self.code, code_state=self.state)

    def _record_print(self):
        """One print of each code, recorded with who and when (§1)."""
        if not self:
            return self
        # One UPDATE, so two prints of one code at the same instant both
        # count (verification pass, 67: a read-then-write lost one).
        self.flush_recordset()
        self.env.cr.execute(
            "UPDATE nrs_asset_code SET print_count = "
            "COALESCE(print_count, 0) + 1, "
            "first_printed_at = COALESCE(first_printed_at, now() AT TIME "
            "ZONE 'UTC'), last_printed_at = now() AT TIME ZONE 'UTC', "
            "last_printed_by_id = %s, write_uid = %s, "
            "write_date = now() AT TIME ZONE 'UTC' WHERE id = ANY(%s)",
            (self.env.user.id, self.env.user.id, self.ids))
        self.invalidate_recordset(['print_count', 'first_printed_at',
                                   'last_printed_at', 'last_printed_by_id'])
        return self

    def _void_spoiled(self, reason):
        """The holder voids one code — a label torn at print (§2.2). Never
        reissued, like every voided code."""
        self.ensure_one()
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if not text:
            raise _refuse(_('Say why the code is voided — what happened to '
                            'its label.'), 'validation_failed',
                          field='reason')
        self._void(_('Spoiled, voided by its holder: %s') % text)
        return self

    def _void(self, reason, actor=None):
        now = fields.Datetime.now()
        self._w({'state': 'void', 'voided_at': now,
                 'voided_by_id': (actor or self.env.user).id,
                 'void_reason': reason})

    @api.model
    def _for_assets(self, assets):
        """R2a: every new asset's code is a ledger row. A code that came from
        a block already has one; it is joined to its asset."""
        if not assets:
            return
        rows = {r.code: r for r in self.sudo().search(
            [('code', 'in', [a.asset_code for a in assets])])}
        now = fields.Datetime.now()
        create = []
        for asset in assets:
            state = 'active' if asset.register_state == REGISTERED \
                else 'in_review'
            row = rows.get(asset.asset_code)
            if row and (row.source != 'block' or row.asset_id
                        or row.state not in ('reserved', 'in_review')):
                # A code is issued once (R2): a voided code, a code another
                # asset carries or carried, is never taken over — by an
                # import passing an explicit `asset_code` least of all.
                raise UserError(_(
                    'Asset code %(code)s was already issued (%(state)s%(on)s) '
                    'and is never reused.', code=asset.asset_code,
                    state=dict(CODE_STATES)[row.state],
                    on=(_(' to asset %d') % row.asset_id.id)
                    if row.asset_id else ''))
            if row:
                row._w({'asset_id': asset.id, 'state': state,
                        'activated_at': now if state == 'active' else False})
            else:
                create.append({'code': asset.asset_code, 'source': 'asset',
                               'state': state, 'asset_id': asset.id,
                               'used_at': now,
                               'activated_at': now if state == 'active'
                               else False})
        if create:
            self.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create(create)

    @api.model
    def _draw(self, size):
        """`size` fresh codes from the asset-code sequence, under a lock.

        The sequence is `ir.sequence` 'nrs.asset' — the one `nrs.asset.create`
        draws from — so a code drawn here is consumed and no asset created any
        other way is ever given it. `nextval` is outside every snapshot; the
        advisory lock keeps one block's draw contiguous against another
        block's (an asset creation in between may still take a number, which
        only leaves a gap). A number already on an asset or in the ledger (an
        import that wrote codes above the sequence) is skipped."""
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (_CODE_LOCK,))
        Seq = self.env['ir.sequence'].sudo()
        codes = []
        while len(codes) < size:
            code = Seq.next_by_code('nrs.asset')
            if not code:
                raise UserError(_('The asset code sequence "nrs.asset" is '
                                  'missing from this database.'))
            self.env.cr.execute(
                "SELECT 1 FROM nrs_asset WHERE asset_code = %s UNION ALL "
                "SELECT 1 FROM nrs_asset_code WHERE code = %s LIMIT 1",
                (code, code))
            if not self.env.cr.fetchone():
                codes.append(code)
        return codes


class NRSAuditCodeBlock(models.Model):
    _name = 'nrs.audit.code.block'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Block of asset codes issued to a device'
    _order = 'id desc'

    name = fields.Char(readonly=True)
    device_id = fields.Many2one('nrs.audit.device', required=True,
                                ondelete='restrict', index=True)
    user_id = fields.Many2one('res.users', 'Issued To', required=True,
                              ondelete='restrict')
    size = fields.Integer(required=True)
    state = fields.Selection([('issued', 'Issued'), ('returned', 'Returned')],
                             required=True, default='issued')
    issued_by_id = fields.Many2one('res.users', ondelete='set null')
    issued_at = fields.Datetime()
    returned_by_id = fields.Many2one('res.users', ondelete='set null')
    returned_at = fields.Datetime()
    return_reason = fields.Text()
    code_ids = fields.One2many('nrs.asset.code', 'block_id')
    first_code = fields.Char(readonly=True)
    last_code = fields.Char(readonly=True)

    @api.model
    def _issue_block(self, device, size):
        if not isinstance(size, int) or isinstance(size, bool) \
                or not 1 <= size <= MAX_BLOCK_SIZE:
            raise _refuse(_('A block carries between 1 and %d codes.')
                          % MAX_BLOCK_SIZE, 'validation_failed',
                          field='size', max=MAX_BLOCK_SIZE)
        if not device.active:
            raise _refuse(_('Device %s is deactivated.') % device.name)
        if not device.user_id:
            raise _refuse(_('Device %s is bound to nobody. Bind it to the '
                            'person who will carry it first: a code is '
                            'reserved to a device AND a person.')
                          % device.name, device_id=device.id)
        Code = self.env['nrs.asset.code']
        codes = Code._draw(size)
        now = fields.Datetime.now()
        block = self.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create({
            'device_id': device.id, 'user_id': device.user_id.id,
            'size': size, 'issued_by_id': self.env.user.id, 'issued_at': now,
            'first_code': codes[0], 'last_code': codes[-1],
        })
        block._w({'name': 'BLK-%06d' % block.id})
        Code.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create([{
            'code': c, 'state': 'reserved', 'source': 'block',
            'block_id': block.id, 'device_id': device.id,
            'user_id': device.user_id.id, 'reserved_at': now} for c in codes])
        return block

    def _return_block(self, reason=None, holder_only=False):
        """Return the block: every code it did not use is VOIDED, never
        reissued (R2). A code in review stays in review.

        `holder_only` (handoff 67 §2.3): the caller is the capturer, not the
        Asset Controller, and returns only a block issued to them."""
        self.ensure_one()
        if holder_only and self.user_id != self.env.user:
            raise _refuse(_(
                'Block %(block)s was issued to %(who)s, not to you. You return '
                'your own block; the Asset Controller returns anybody\'s.',
                block=self.name, who=self.user_id.display_name),
                'forbidden', block_id=self.id)
        if self.state != 'issued':
            raise _refuse(_('Block %s was already returned.') % self.name)
        text = (reason or '').strip() if isinstance(reason, str) else ''
        unused = self.code_ids.filtered(lambda c: c.state == 'reserved')
        unused._void(_('Unused when block %(block)s was returned%(why)s.',
                       block=self.name,
                       why=(': ' + text) if text else ''))
        self._w({'state': 'returned', 'returned_by_id': self.env.user.id,
                 'returned_at': fields.Datetime.now(),
                 'return_reason': text or False})
        return len(unused)

    def _counts(self):
        self.ensure_one()
        out = {s: 0 for s, _l in CODE_STATES}
        for c in self.code_ids:
            out[c.state] += 1
        return out


# ─── campaigns ──────────────────────────────────────────────────────────

class NRSAuditCampaign(models.Model):
    _name = 'nrs.audit.campaign'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Audit campaign'
    _order = 'id desc'

    name = fields.Char(required=True)
    state = fields.Selection([('open', 'Open'), ('closed', 'Closed')],
                             required=True, default='open', index=True)
    date_start = fields.Date()
    date_end = fields.Date()
    scope_ids = fields.One2many('nrs.audit.campaign.scope', 'campaign_id')
    capturer_ids = fields.Many2many(
        'res.users', 'nrs_audit_campaign_capturer_rel', 'campaign_id',
        'user_id', string='Capturers')
    reviewer_ids = fields.Many2many(
        'res.users', 'nrs_audit_campaign_reviewer_rel', 'campaign_id',
        'user_id', string='Reviewers')
    created_by_id = fields.Many2one('res.users', ondelete='set null')
    closed_by_id = fields.Many2one('res.users', ondelete='set null')
    closed_at = fields.Datetime()
    closing_json = fields.Text(
        'The two lists, as they stood at closing')
    capture_ids = fields.One2many('nrs.audit.capture', 'campaign_id')

    @api.model
    def _assert_team(self, capturers, reviewers):
        both = capturers & reviewers
        if both:
            raise _refuse(_(
                '%s cannot both capture and review in one campaign: the '
                'reviewer is the second person.') % ', '.join(
                    both.mapped('display_name')), 'validation_failed',
                user_ids=both.ids)

    @api.model
    def _open_campaign(self, name, scope, capturers, reviewers, date_start=None,
              date_end=None):
        name = (name or '').strip() if isinstance(name, str) else ''
        if not name:
            raise _refuse(_('Name the campaign.'), 'validation_failed',
                          field='name')
        lines = self._scope_lines(scope)
        self._assert_team(capturers, reviewers)
        campaign = self.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create({
            'name': name, 'date_start': date_start, 'date_end': date_end,
            'capturer_ids': [(6, 0, capturers.ids)],
            'reviewer_ids': [(6, 0, reviewers.ids)],
            'created_by_id': self.env.user.id,
            'scope_ids': [(0, 0, line) for line in lines],
        })
        return campaign

    @api.model
    def _scope_lines(self, scope):
        if not isinstance(scope, list) or not scope:
            raise _refuse(_(
                'Say what the campaign covers: `scope` is a list of '
                '{location_id, office_code} — a building or room, the SAP '
                'office code its records carry, or both.'),
                'validation_failed', field='scope')
        Loc = self.env['generic.location'].sudo()
        lines = []
        for item in scope:
            if not isinstance(item, dict) or set(item) - {'location_id',
                                                          'office_code'}:
                raise _refuse(_('Each scope line is {location_id, '
                                'office_code} and nothing else.'),
                              'validation_failed', field='scope')
            loc_id = item.get('location_id')
            office = item.get('office_code')
            office = office.strip().upper() if isinstance(office, str) \
                else None
            if loc_id is not None and (not isinstance(loc_id, int)
                                       or isinstance(loc_id, bool)
                                       or not Loc.browse(loc_id).exists()):
                raise _refuse(_('Location %s does not exist.') % (loc_id,),
                              'validation_failed', field='scope')
            if not loc_id and not office:
                raise _refuse(_('A scope line names a location, an office '
                                'code, or both.'), 'validation_failed',
                              field='scope')
            lines.append({'location_id': loc_id or False,
                          'office_code': office or False})
        return lines

    def _assert_open(self):
        self.ensure_one()
        if self.state != 'open':
            raise _refuse(_(
                'Campaign %(name)s was closed on %(day)s; nothing more is '
                'captured or reviewed in it.', name=self.name,
                day=fields.Date.to_string(
                    self.closed_at and self.closed_at.date())),
                campaign_id=self.id)

    def _office_of(self, location):
        """The SAP office a room of this campaign answers to: the scope
        line nearest above it that names one."""
        self.ensure_one()
        best, depth = None, -1
        path = location.sudo().parent_path or ''
        ids = [int(x) for x in path.strip('/').split('/') if x]
        for line in self.scope_ids:
            if line.location_id and line.location_id.id in ids \
                    and line.office_code:
                d = ids.index(line.location_id.id)
                if d > depth:
                    best, depth = line.office_code, d
        if best:
            return best
        offices = self._offices()
        return offices[0] if len(offices) == 1 else None

    def _site_of(self, location):
        """The campaign location a room counts under on the acceptance
        dashboard (handoff 67 §3): the scope line nearest above it, else the
        room itself (a campaign with no located scope covers everywhere)."""
        self.ensure_one()
        path = location.sudo().parent_path or ''
        ids = [int(x) for x in path.strip('/').split('/') if x]
        best, depth = location, -1
        for line in self.scope_ids:
            if line.location_id and line.location_id.id in ids:
                d = ids.index(line.location_id.id)
                if d > depth:
                    best, depth = line.location_id, d
        return best

    def _offices(self):
        return sorted({l.office_code for l in self.scope_ids
                       if l.office_code})

    def _covers(self, location):
        self.ensure_one()
        located = [l.location_id.id for l in self.scope_ids if l.location_id]
        if not located:
            return True
        path = location.sudo().parent_path or ''
        ids = {int(x) for x in path.strip('/').split('/') if x}
        return bool(ids & set(located))

    def _progress(self):
        self.ensure_one()
        caps = self.capture_ids
        by_state = {s: 0 for s, _l in CAPTURE_STATES}
        for c in caps:
            by_state[c.state] += 1
        return {
            'captured': len(caps),
            'waiting_for_review': by_state['pending_review'],
            'accepted': by_state['accepted'],
            'returned': by_state['returned'],
            'reviewed': by_state['accepted'] + by_state['returned'],
            'duplicates_held': len(caps.filtered(
                lambda c: c.duplicate_of_id and c.state == 'pending_review')),
            'exceptions': len(caps.filtered(
                lambda c: c.outcome == OUTCOME_IN_NEITHER
                and c.state == 'accepted')),
            'exceptions_open': len(caps.filtered(
                lambda c: c.outcome == OUTCOME_IN_NEITHER
                and c.state == 'accepted' and c.exception_state == 'open')),
        }

    def _lists(self):
        """The two lists the audit exists for, per office (§3).

        * found, not in SAP — accepted captures of outcome c;
        * in SAP, not found — active SAP records in the latest export whose
          office is in the campaign, that no accepted capture matched and no
          Cadra asset links to. Records with no office are a COUNT: without
          SAP's location extract (report 63) they cannot be placed."""
        self.ensure_one()
        found = []
        for c in self.capture_ids.filtered(
                lambda c: c.outcome == OUTCOME_IN_NEITHER
                and c.state == 'accepted').sorted('id'):
            found.append({
                'office_code': self._office_of(c.location_id) or None,
                'capture_id': c.capture_uuid, 'code': c.code,
                'name': c.name, 'category': c.category_id.name or None,
                'location': c.location_id.display_name,
                'location_id': c.location_id.id,
                'captured_by': c.operator_id.display_name,
                'captured_at': fields.Datetime.to_string(c.captured_at),
                'exception_state': c.exception_state,
            })
        offices = self._offices()
        matched = [c.sap_record_id.id for c in self.capture_ids
                   if c.sap_record_id and c.state == 'accepted']
        missing = []
        if offices:
            self.env.flush_all()
            self.env.cr.execute(
                "SELECT s.id, s.office_code, s.asset_number, s.sub_number, "
                "       s.asset_class, s.description, s.old_tag, "
                "       s.capitalized_on "
                "  FROM nrs_sap_asset s "
                " WHERE s.office_code = ANY(%%s) AND s.deactivated_on IS NULL "
                "   AND s.in_latest_export AND NOT (s.id = ANY(%%s)) "
                "   AND NOT %s "
                " ORDER BY s.office_code, s.asset_number, s.id"
                % LINKED_EXISTS, [offices, matched or [0]])
            for row in self.env.cr.fetchall():
                missing.append({
                    'office_code': row[1], 'sap_record_id': row[0],
                    'asset_number': row[2], 'sub_number': row[3] or None,
                    'asset_class': row[4], 'description': row[5],
                    'old_tag': row[6],
                    'capitalized_on': row[7] and row[7].isoformat()})
        self.env.cr.execute(
            "SELECT count(*) FROM nrs_sap_asset WHERE deactivated_on IS NULL "
            "AND in_latest_export AND (office_code IS NULL OR office_code = '')")
        no_office = self.env.cr.fetchone()[0]
        per_office = {}
        for row in found:
            per_office.setdefault(row['office_code'] or '', [0, 0])[0] += 1
        for row in missing:
            per_office.setdefault(row['office_code'], [0, 0])[1] += 1
        return {
            'found_not_in_sap': found,
            'in_sap_not_found': missing,
            'by_office': [{'office_code': k or None,
                           'found_not_in_sap': v[0],
                           'in_sap_not_found': v[1]}
                          for k, v in sorted(per_office.items())],
            'sap_records_with_no_office': no_office,
            'no_office_note': _(
                '%d active SAP records carry no office and are not counted '
                'as "in SAP, not found": without SAP\'s location extract '
                'they cannot be placed in any room.') % no_office,
            'offices': offices,
        }

    def _close_campaign(self):
        self.ensure_one()
        self._assert_open()
        waiting = self.capture_ids.filtered(
            lambda c: c.state == 'pending_review')
        if waiting:
            raise _refuse(_(
                'Campaign %(name)s still has %(n)d capture(s) waiting for '
                'review. Every capture is accepted or returned before the '
                'campaign closes.', name=self.name, n=len(waiting)),
                waiting_for_review=len(waiting))
        lists = self._lists()
        now = fields.Datetime.now()
        lists['closed_at'] = fields.Datetime.to_string(now)
        self._w({'state': 'closed', 'closed_at': now,
                 'closed_by_id': self.env.user.id,
                 'closing_json': json.dumps(lists, sort_keys=True)})
        return lists


class NRSAuditCampaignScope(models.Model):
    _name = 'nrs.audit.campaign.scope'
    _description = 'What an audit campaign covers'

    campaign_id = fields.Many2one('nrs.audit.campaign', required=True,
                                  ondelete='cascade', index=True)
    location_id = fields.Many2one('generic.location', ondelete='restrict')
    office_code = fields.Char('SAP Office Code')


# ─── the photos a capture carries ──────────────────────────────────────

class NRSAuditPhoto(models.Model):
    """A photo synced for a capture, before anybody has accepted it — the
    asset it shows may not exist yet. Kept, never expired: a capture waits
    for review for days. Copied onto the asset's photos on acceptance."""
    _name = 'nrs.audit.photo'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Audit capture photo'
    _order = 'id desc'

    image = fields.Binary(attachment=True, required=True)
    filename = fields.Char()
    mimetype = fields.Char(required=True)
    size = fields.Integer(required=True)
    sha256 = fields.Char(required=True, index=True)
    width = fields.Integer()
    height = fields.Integer()
    source = fields.Selection([('web', 'Web'), ('mobile', 'Mobile')],
                              required=True, default='mobile')
    uploaded_by_id = fields.Many2one('res.users', required=True,
                                     ondelete='restrict')
    uploaded_at = fields.Datetime(required=True)

    _same_bytes_once = models.Constraint(
        'UNIQUE (uploaded_by_id, sha256)',
        'One person syncs the same photo once.')

    @api.model
    def _upload(self, data, *, source='mobile', filename=None):
        """Check the bytes (61's checks), then keep them. The same bytes from
        the same person answer the row already kept — a retried sync."""
        if source not in ('web', 'mobile'):
            raise _refuse(_('`source` is web or mobile.'),
                          'validation_failed', field='source',
                          allowed_values=['web', 'mobile'])
        size = len(data or b'')
        check_photo_size(size)
        mimetype, width, height = sniff_photo(data)
        digest = hashlib.sha256(data).hexdigest()
        me = self.env.user
        found = self.sudo().search([('uploaded_by_id', '=', me.id),
                                    ('sha256', '=', digest)], limit=1)
        if found:
            return found, False
        row = self.sudo().with_context(
            image_no_postprocess=True, **{AUDIT_WRITE_KEY: True}).create({
                'image': base64.b64encode(data), 'mimetype': mimetype,
                'size': size, 'sha256': digest, 'width': width,
                'height': height, 'source': source,
                'filename': (filename or '').strip() or False,
                'uploaded_by_id': me.id,
                'uploaded_at': fields.Datetime.now()})
        return row, True

    def _bytes(self):
        self.ensure_one()
        data = base64.b64decode(self.sudo().with_context(bin_size=False).image
                                or b'')
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise UserError(_('Audit photo %d no longer matches the bytes '
                              'that were uploaded.') % self.id)
        return data


# ─── the capture ───────────────────────────────────────────────────────

class NRSAuditCapture(models.Model):
    """One item, captured in a room. Everything the phone sent is frozen at
    receipt (AI-NFR-05's trail); only the review moves it on."""
    _name = 'nrs.audit.capture'
    _inherit = ['nrs.audit.guarded.mixin']
    _description = 'Audit capture'
    _order = 'id desc'

    capture_uuid = fields.Char('Capture ID', required=True, readonly=True,
                               index=True)
    campaign_id = fields.Many2one('nrs.audit.campaign', required=True,
                                  ondelete='restrict', index=True)
    location_id = fields.Many2one('generic.location', 'Room', required=True,
                                  ondelete='restrict', index=True)
    outcome = fields.Selection(OUTCOMES, required=True, index=True)
    asset_id = fields.Many2one('nrs.asset', 'Cadra Asset', index=True,
                               ondelete='restrict')
    sap_record_id = fields.Many2one('nrs.sap.asset', 'SAP Record',
                                    index=True, ondelete='restrict')
    code = fields.Char(index=True)
    code_id = fields.Many2one('nrs.asset.code', 'Ledger Row',
                              ondelete='restrict')
    scanned_label = fields.Char()
    label = fields.Selection(LABEL_STATES)
    name = fields.Char('Description')
    category_id = fields.Many2one('nrs.asset.category', ondelete='restrict')
    condition = fields.Selection([(c, c) for c in CONDITIONS])
    confirmed_json = fields.Text('Confirmed fields (as sent)')
    photo_ids = fields.Many2many(
        'nrs.audit.photo', 'nrs_audit_capture_photo_rel', 'capture_id',
        'photo_id', string='Photos')
    ai_suggestion_id = fields.Many2one('nrs.ai.suggestion',
                                       ondelete='restrict')
    captured_at = fields.Datetime(required=True)
    received_at = fields.Datetime(required=True)
    # AI-FR-10 (handoff 67 §2.4): where the phone says it was, if the
    # capturer chose to send it. Stored here only — never on the asset,
    # never sent to the AI provider, never on a page outside the audit.
    gps_latitude = fields.Float('GPS Latitude', digits=(10, 7))
    gps_longitude = fields.Float('GPS Longitude', digits=(10, 7))
    gps_accuracy_m = fields.Float('GPS Accuracy (m)', digits=(10, 1))
    # An Odoo float is never NULL; this says a position was sent at all
    # (0, 0 is a place, in the Gulf of Guinea).
    gps_recorded = fields.Boolean('GPS Recorded')
    operator_id = fields.Many2one('res.users', 'Captured By', required=True,
                                  ondelete='restrict')
    device_id = fields.Many2one('nrs.audit.device', required=True,
                                ondelete='restrict')
    duplicate_of_id = fields.Many2one(
        'nrs.audit.capture', 'Held Beside', ondelete='restrict',
        help='Another capture in this campaign of the same Cadra asset, SAP '
             'record or old tag. Held for review, never refused.')
    duplicate_basis = fields.Char()
    state = fields.Selection(CAPTURE_STATES, required=True,
                             default='pending_review', index=True)
    reviewed_by_id = fields.Many2one('res.users', ondelete='set null')
    reviewed_at = fields.Datetime()
    return_reason = fields.Text()
    result_asset_id = fields.Many2one('nrs.asset', 'Became / Verified',
                                      ondelete='restrict')
    reprint_label_id = fields.Many2one('nrs.asset.tag.label',
                                       ondelete='set null')
    photos_copied = fields.Integer()
    exception_state = fields.Selection(EXCEPTION_STATES, index=True)
    exception_resolved_by_id = fields.Many2one('res.users',
                                               ondelete='set null')
    exception_resolved_at = fields.Datetime()
    exception_void_reason = fields.Text()

    _capture_uuid_unique = models.Constraint(
        'UNIQUE (capture_uuid)',
        'A capture id is stored once: a capture synced twice is one capture.')

    # ── receipt ───────────────────────────────────────────────────────

    @api.model
    def _receive(self, body, device):
        """Check everything, then write one capture. Every refusal is raised
        before anything is written. Returns `(capture, created)`."""
        me = self.env.user
        uid = body.get('capture_id')
        try:
            uid = str(uuid.UUID(str(uid))) if uid else None
        except (ValueError, TypeError, AttributeError):
            uid = None
        if not uid:
            raise _refuse(_(
                '`capture_id` is the UUID the phone gave this capture when it '
                'was taken; a sync is matched on it.'), 'validation_failed',
                field='capture_id')
        existing = self.sudo().search([('capture_uuid', '=', uid)], limit=1)
        if existing:
            if existing.operator_id != me:
                raise _refuse(_('Capture %s was synced by somebody else.')
                              % uid, 'forbidden', capture_id=uid)
            return existing, False

        Campaign = self.env['nrs.audit.campaign'].sudo()
        campaign = Campaign.browse(_int(body.get('campaign_id'),
                                        'campaign_id')).exists()
        if not campaign:
            raise _refuse(_('No such campaign.'), 'validation_failed',
                          field='campaign_id')
        campaign._assert_open()
        if me not in campaign.capturer_ids:
            raise _refuse(_(
                'You are not a capturer on campaign %s. The Asset Controller '
                'names the team.') % campaign.name, 'forbidden',
                campaign_id=campaign.id)
        room = self.env['generic.location'].sudo().browse(
            _int(body.get('location_id'), 'location_id')).exists()
        if not room:
            raise _refuse(_('No such room.'), 'validation_failed',
                          field='location_id')
        if not campaign._covers(room):
            raise _refuse(_(
                '%(room)s is outside campaign %(name)s; capture it in a '
                'campaign that covers it.', room=room.display_name,
                name=campaign.name), campaign_id=campaign.id,
                location_id=room.id)

        captured_at = _parse_moment(body.get('captured_at'))
        now = fields.Datetime.now()
        if captured_at > now + FUTURE_SKEW:
            raise _refuse(_('`captured_at` is in the future.'),
                          'validation_failed', field='captured_at')
        first = earliest_capture_day()
        local = pytz.utc.localize(captured_at).astimezone(_LAGOS).date()
        if local < first:
            raise _refuse(_(
                'This capture is dated %(day)s, more than %(n)d working days '
                'ago (the earliest accepted today is %(first)s). Capture the '
                'item again.', day=local.isoformat(),
                n=MAX_WORKING_DAYS_BACK, first=first.isoformat()),
                'validation_failed', field='captured_at',
                earliest=first.isoformat())

        outcome = body.get('outcome')
        if outcome not in dict(OUTCOMES):
            raise _refuse(_('`outcome` is one of: %s.')
                          % ', '.join(dict(OUTCOMES)), 'validation_failed',
                          field='outcome', allowed_values=list(dict(OUTCOMES)))
        confirmed = body.get('fields') or {}
        if not isinstance(confirmed, dict):
            raise _refuse(_('`fields` is an object of the confirmed values.'),
                          'validation_failed', field='fields')
        stray = sorted(set(confirmed) - set(CONFIRMED_FIELDS))
        if stray:
            raise _refuse(_('`fields` cannot carry: %s.') % ', '.join(stray),
                          'validation_failed', field='fields',
                          rejected_fields=stray,
                          writable=list(CONFIRMED_FIELDS))
        condition = confirmed.get('condition')
        if condition not in CONDITIONS:
            raise _refuse(_('Say the condition the item is in: one of %s.')
                          % ', '.join(CONDITIONS), 'validation_failed',
                          field='fields.condition',
                          allowed_values=list(CONDITIONS))
        category = self.env['nrs.asset.category']
        if confirmed.get('category_id') is not None:
            category = category.sudo().browse(_int(
                confirmed.get('category_id'), 'fields.category_id')).exists()
            if not category:
                raise _refuse(_('No such class.'), 'validation_failed',
                              field='fields.category_id')

        photos = self._photos(body.get('photo_ids'))
        suggestion = self._suggestion(body.get('ai_suggestion_id'), photos)
        gps = _gps(body.get('gps'))

        vals = {
            'capture_uuid': uid, 'campaign_id': campaign.id,
            'location_id': room.id, 'outcome': outcome,
            'name': (confirmed.get('name') or '').strip() or False
            if isinstance(confirmed.get('name'), (str, type(None))) else False,
            'category_id': category.id or False, 'condition': condition,
            'confirmed_json': json.dumps(confirmed, sort_keys=True),
            'photo_ids': [(6, 0, photos.ids)],
            'ai_suggestion_id': suggestion.id or False,
            'captured_at': captured_at, 'received_at': now,
            'operator_id': me.id, 'device_id': device.id,
            **gps,
        }
        code_row = None
        if outcome == OUTCOME_ON_REGISTER:
            vals.update(self._target_on_register(body, campaign))
        else:
            if outcome == OUTCOME_IN_SAP:
                vals.update(self._target_in_sap(body, campaign))
            elif body.get('asset_id') or body.get('sap_record_id'):
                raise _refuse(_('A capture found in neither register names '
                                'no Cadra asset and no SAP record.'),
                              'validation_failed', field='outcome')
            if not category:
                raise _refuse(_('Pick the class of the item: a capture that '
                                'will become a register asset needs one.'),
                              'validation_failed', field='fields.category_id')
            if category.identification_mode == MODE_RECORD_ONLY:
                raise _refuse(_(
                    '%s is a class identified by its record, with no label; '
                    'an audit capture is of an item a label is fixed to.')
                    % category.name, 'validation_failed',
                    field='fields.category_id')
            if outcome == OUTCOME_IN_NEITHER and not vals['name']:
                raise _refuse(_('Describe the item: a capture found in '
                                'neither register is known by what it is '
                                'called.'), 'validation_failed',
                              field='fields.name')
            if body.get('label') is not None:
                raise _refuse(_('`label` says whether an asset on the register '
                                'still carries its label; a new item\'s label '
                                'is the code it was given.'),
                              'validation_failed', field='label')
            code_row = self._code_for(body, device)
            vals.update({'code': code_row.code, 'code_id': code_row.id,
                         'scanned_label': body['scanned_label'].strip()})
        vals.update(self._duplicate(campaign, vals, confirmed))
        capture = self.sudo().with_context(**{AUDIT_WRITE_KEY: True}).create(
            vals)
        if code_row:
            code_row._set({'state': 'in_review', 'used_at': now,
                           'capture_id': capture.id})
        return capture, True

    def _photos(self, ids):
        if not isinstance(ids, list) or not ids or not all(
                isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise _refuse(_(
                'Every capture carries at least one photo: `photo_ids` lists '
                'the photos synced with POST /api/v1/audit/photos.'),
                'validation_failed', field='photo_ids')
        photos = self.env['nrs.audit.photo'].sudo().browse(ids).exists()
        theirs = photos.filtered(lambda p: p.uploaded_by_id == self.env.user)
        if len(theirs) != len(set(ids)):
            raise _refuse(_('Photos %s are not photos you synced.') % sorted(
                set(ids) - set(theirs.ids)), 'validation_failed',
                field='photo_ids')
        return theirs

    def _suggestion(self, sid, photos=None):
        Sugg = self.env['nrs.ai.suggestion'].sudo()
        if sid in (None, False):
            return Sugg
        s = Sugg.browse(_int(sid, 'ai_suggestion_id')).exists()
        if not s or s.actor_id != self.env.user:
            raise _refuse(_('Suggestion %s is not one you asked for.') % sid,
                          'validation_failed', field='ai_suggestion_id')
        if s.result != 'ok':
            # Verification pass, 67: a failed call's id (in a 503's details)
            # has nothing in it to confirm — the asset save refuses it too.
            raise _refuse(_(
                'Suggestion %(id)s has nothing to confirm: the photo was not '
                'identified (%(why)s). Send the capture without it.',
                id=sid, why=s.failure or s.result), 'validation_failed',
                field='ai_suggestion_id', reason='not_identified')
        if s.audit_photo_id and photos is not None \
                and s.audit_photo_id not in photos:
            raise _refuse(_(
                'Suggestion %(id)s was made from audit photo %(photo)d, which '
                'this capture does not carry. Name the photo in `photo_ids`.',
                id=sid, photo=s.audit_photo_id.id), 'validation_failed',
                field='ai_suggestion_id')
        return s

    def _target_on_register(self, body, campaign):
        if body.get('sap_record_id') or body.get('code') \
                or body.get('scanned_label'):
            raise _refuse(_(
                'An item already on the register keeps its code: a capture '
                'of it names the Cadra asset only (no code, no SAP record). A '
                'missing label is reprinted under its code on acceptance — say '
                'so with `label`.'), 'validation_failed', field='outcome')
        asset = self.env['nrs.asset'].sudo().with_context(
            cadra_candidates=True).browse(
                _int(body.get('asset_id'), 'asset_id')).exists()
        if not asset:
            raise _refuse(_('No such Cadra asset.'), 'validation_failed',
                          field='asset_id')
        if asset.register_state != REGISTERED:
            raise _refuse(_(
                '%s is a receipt candidate, not on the register; it is found '
                'through the receipt gates, not an audit.') % asset.asset_code,
                'not_on_the_register', asset_id=asset.id)
        if asset.state == 'disposed':
            raise _refuse(_('%s is disposed.') % asset.asset_code,
                          asset_id=asset.id)
        label = body.get('label') or 'present'
        if label not in dict(LABEL_STATES):
            raise _refuse(_('`label` is one of: %s.') % ', '.join(
                dict(LABEL_STATES)), 'validation_failed', field='label',
                allowed_values=list(dict(LABEL_STATES)))
        if label != 'present' and asset.identification_mode \
                == MODE_RECORD_ONLY:
            raise _refuse(_('%s carries no label.') % asset.asset_code,
                          'validation_failed', field='label')
        return {'asset_id': asset.id, 'label': label}

    def _target_in_sap(self, body, campaign):
        if body.get('asset_id'):
            raise _refuse(_('A capture matched to SAP\'s record names no '
                            'Cadra asset.'), 'validation_failed',
                          field='asset_id')
        rec = self.env['nrs.sap.asset'].sudo().browse(
            _int(body.get('sap_record_id'), 'sap_record_id')).exists()
        if not rec:
            raise _refuse(_('No such SAP record.'), 'validation_failed',
                          field='sap_record_id')
        if not (rec.sap_active and rec.in_latest_export):
            raise _refuse(_('SAP asset %s is retired or not in the latest '
                            'export of SAP\'s register.') % rec.asset_number,
                          sap_record_id=rec.id)
        holder = rec._linked_assets().get(rec.id)
        if holder:
            asset = self.env['nrs.asset'].sudo().with_context(
                cadra_candidates=True).browse(holder['asset_id'])
            raise _refuse(_(
                'SAP asset %(number)s is already on Cadra\'s register as '
                '%(code)s: capture it as found on the register.',
                number=rec.asset_number, code=asset.asset_code),
                sap_record_id=rec.id, asset_id=asset.id)
        return {'sap_record_id': rec.id}

    def _code_for(self, body, device):
        code = body.get('code')
        scanned = body.get('scanned_label')
        if not isinstance(code, str) or not code.strip():
            raise _refuse(_('Say the code printed on the label: `code`, from '
                            'this device\'s block.'), 'validation_failed',
                          field='code')
        if not isinstance(scanned, str) or not scanned.strip():
            raise _refuse(_('Scan the label you fixed: `scanned_label` is '
                            'what the scanner read off it.'),
                          'validation_failed', field='scanned_label')
        code = code.strip()
        if scanned.strip() != code:
            raise _refuse(_(
                'The label scanned (%(scanned)s) is not the code this capture '
                'used (%(code)s). The label on the item is not the one '
                'printed for it.', scanned=scanned.strip(), code=code),
                'validation_failed', field='scanned_label')
        row = self.env['nrs.asset.code'].sudo().search(
            [('code', '=', code)], limit=1)
        if not row or row.source != 'block' or row.device_id != device \
                or row.user_id != self.env.user:
            raise _refuse(_(
                'Code %(code)s is not reserved to this device (%(device)s) '
                'and to you. Use a code from the block the Asset Controller '
                'issued to you on this device.', code=code,
                device=device.name), 'forbidden', code=code)
        if row.state != 'reserved':
            raise _refuse(_(
                'Code %(code)s was already used (%(state)s)%(when)s; a code '
                'labels one item, once.', code=code,
                state=dict(CODE_STATES)[row.state],
                when=(_(' on %s') % fields.Datetime.to_string(row.used_at))
                if row.used_at else ''), code=code, code_state=row.state)
        return row

    def _duplicate(self, campaign, vals, confirmed):
        """A second capture of the same Cadra asset, SAP record or old tag in
        this campaign is HELD for review beside the first — never refused:
        the reviewer sees both."""
        domain = [('campaign_id', '=', campaign.id),
                  ('state', '!=', 'returned')]
        checks = []
        if vals.get('asset_id'):
            checks.append(('asset_id', vals['asset_id'], 'cadra_asset'))
        if vals.get('sap_record_id'):
            checks.append(('sap_record_id', vals['sap_record_id'],
                           'sap_record'))
        for field, value, basis in checks:
            twin = self.sudo().search(domain + [(field, '=', value)],
                                      order='id', limit=1)
            if twin:
                return {'duplicate_of_id': twin.id, 'duplicate_basis': basis}
        tag = norm_tag(confirmed.get('legacy_asset_code')) \
            if isinstance(confirmed.get('legacy_asset_code'), str) else ''
        if tag:
            for twin in self.sudo().search(domain, order='id'):
                other = json.loads(twin.confirmed_json or '{}').get(
                    'legacy_asset_code')
                if isinstance(other, str) and norm_tag(other) == tag:
                    return {'duplicate_of_id': twin.id,
                            'duplicate_basis': 'old_tag'}
        return {}

    # ── review ────────────────────────────────────────────────────────

    def _assert_reviewable(self):
        self.ensure_one()
        me = self.env.user
        self.campaign_id._assert_open()
        if self.state != 'pending_review':
            raise _refuse(_('Capture %(id)s was already %(state)s.',
                            id=self.capture_uuid,
                            state=dict(CAPTURE_STATES)[self.state].lower()),
                          capture_state=self.state)
        if me == self.operator_id:
            raise _refuse(_(
                'You captured this item; a different person must review it. '
                'The reviewer is the second person.'),
                'segregation_of_duties',
                earlier={'action': 'capture',
                         'date': fields.Datetime.to_string(self.captured_at),
                         'user_name': self.operator_id.display_name})
        if me not in self.campaign_id.reviewer_ids:
            raise _refuse(_('You are not a reviewer on campaign %s.')
                          % self.campaign_id.name, 'forbidden',
                          campaign_id=self.campaign_id.id)

    def _accepted_twin(self):
        """Another capture of the same thing, already ACCEPTED in this
        campaign — the duplicate a reviewer must return, not accept."""
        self.ensure_one()
        domain = [('campaign_id', '=', self.campaign_id.id),
                  ('state', '=', 'accepted'), ('id', '!=', self.id)]
        if self.duplicate_of_id.state == 'accepted':
            # Whatever the basis — the old tag included (verification
            # pass, 66): the capture it was held beside is accepted.
            return self.duplicate_of_id
        if self.asset_id:
            twin = self.search(domain + [('asset_id', '=', self.asset_id.id)],
                               limit=1)
            if twin:
                return twin
        if self.sap_record_id:
            return self.search(
                domain + [('sap_record_id', '=', self.sap_record_id.id)],
                limit=1)
        return self.browse()

    def _accept(self, dry_run=False):
        self.ensure_one()
        self._assert_reviewable()
        twin = self.sudo()._accepted_twin()
        if twin:
            raise _refuse(_(
                'Capture %(twin)s of the same %(what)s was already accepted '
                'in this campaign; return this one as a duplicate.',
                twin=twin.capture_uuid,
                what=_('Cadra asset') if self.asset_id else _('SAP record')
                if self.sap_record_id else _('item')),
                duplicate_of=twin.capture_uuid)
        reviewer = self.env.user
        cap = self.sudo()
        if cap.outcome == OUTCOME_ON_REGISTER:
            asset = cap._accept_on_register(reviewer)
        elif cap.outcome == OUTCOME_IN_SAP:
            asset = cap._accept_in_sap(reviewer)
        else:
            asset = self.env['nrs.asset']
        vals = {'state': 'accepted', 'reviewed_by_id': reviewer.id,
                'reviewed_at': fields.Datetime.now(),
                'result_asset_id': asset.id or False}
        if cap.outcome == OUTCOME_IN_NEITHER:
            vals['exception_state'] = 'open'
        cap._w(vals)
        if asset:
            cap._record_on_asset(asset, reviewer)
        return cap

    def _notes(self, reviewer, **extra):
        out = {'capture_id': self.capture_uuid,
               'campaign': self.campaign_id.name,
               'campaign_id': self.campaign_id.id,
               'captured_by': self.operator_id.display_name,
               'captured_at': fields.Datetime.to_string(self.captured_at),
               'reviewed_by': reviewer.display_name}
        out.update(extra)
        return json.dumps(out, sort_keys=True)

    def _record_on_asset(self, asset, reviewer):
        reasons = {
            OUTCOME_ON_REGISTER: _(
                'Found in place by audit %(name)s: captured by %(by)s, '
                'accepted by %(rev)s.'),
            OUTCOME_IN_SAP: _(
                'Registered from SAP\'s record by audit %(name)s, captured by '
                '%(by)s and accepted by %(rev)s. The receipt gates do not '
                'apply: nothing was bought and SAP already holds the asset '
                '(R1), so no asset master is sent.'),
            OUTCOME_IN_NEITHER: _(
                'Found by audit %(name)s and in neither register; registered '
                'as new by the Asset Controller through the Register Maker '
                'and Checker.'),
        }
        self.env['nrs.asset.event'].sudo().with_context(
            cadra_event_source='api_audit')._record(
            asset, EVENT_AUDIT_CAPTURE, to_value=self.outcome,
            reason=reasons[self.outcome] % {
                'name': self.campaign_id.name,
                'by': self.operator_id.display_name,
                'rev': reviewer.display_name},
            notes=self._notes(reviewer, code=self.code or asset.asset_code,
                              room=self.location_id.display_name),
            actor=reviewer)

    def _copy_photos(self, asset):
        Photo = self.env['nrs.asset.photo'].sudo()
        copied = 0
        for p in self.photo_ids.sorted('id'):
            try:
                with self.env.cr.savepoint():
                    Photo._upload(asset, p._bytes(), source=p.source,
                                  caption=_('Audit capture %s')
                                  % self.capture_uuid,
                                  filename=p.filename,
                                  actor=self.operator_id)
                    copied += 1
            except UserError:
                # catch-all: reported — the asset is at its photo limit;
                # the capture keeps the photo and says how many were copied.
                continue
        return copied

    def _accept_on_register(self, reviewer):
        asset = self.asset_id.with_context(cadra_candidates=True)
        if asset.register_state != REGISTERED or asset.state == 'disposed':
            raise _refuse(_('%s is no longer an asset on the register.')
                          % asset.asset_code, asset_id=asset.id)
        vals = {'condition': self.condition}
        if asset.location_id != self.location_id:
            vals['location_id'] = self.location_id.id
        # A second person agreed to the move (the reviewer), so the movement
        # row says `approval`, with the audit as its reason.
        asset.with_user(reviewer).sudo().with_context(**{
            EXEMPT_KEY: 'audit', MOVEMENT_SOURCE_KEY: 'approval',
            MOVEMENT_REASON_KEY: _(
                'Found in this room by audit %(name)s (capture %(id)s), '
                'accepted by %(rev)s.', name=self.campaign_id.name,
                id=self.capture_uuid, rev=reviewer.display_name),
        }).write(vals)
        asset.with_user(self.operator_id).sudo().with_context(
            cadra_event_source='api_verify').action_verify(
            notes=_('Audit %(name)s, capture %(id)s; accepted by %(rev)s.',
                    name=self.campaign_id.name, id=self.capture_uuid,
                    rev=reviewer.display_name))
        self._w({'photos_copied': self._copy_photos(asset)})
        if self.label in ('missing', 'unreadable'):
            self._w({'reprint_label_id': self._reprint(asset, reviewer).id})
        return asset

    def _reprint(self, asset, reviewer):
        """R3 through the audit: the label is reprinted under the asset's
        existing code; the capturer asked (by saying the label is missing),
        the reviewer's acceptance is the approval. 61's same-code rules:
        the old print voided with its reason, a reprint row one higher."""
        tag = asset.active_tag_id
        if not tag:
            pending = asset.tag_ids.filtered(lambda t: t.state == 'pending')
            raise _refuse(_(
                '%(code)s has a label replacement already waiting on %(who)s; '
                'decide it first.', code=asset.asset_code,
                who=pending[:1].approver_id.display_name or _('an approver'))
                if pending else _('%s has no label to reprint.')
                % asset.asset_code, asset_id=asset.id)
        reason = 'lost' if self.label == 'missing' else 'damaged'
        tag.with_user(self.operator_id).sudo()._replacement_ctx().write({
            'state': 'pending', 'replacement_reason': reason,
            'replacement_notes': _('Audit %(name)s, capture %(id)s: label '
                                   '%(label)s.', name=self.campaign_id.name,
                                   id=self.capture_uuid,
                                   label=dict(LABEL_STATES)[self.label]
                                   .lower()),
            'approver_id': reviewer.id,
            'requested_by': self.operator_id.id,
            'requested_date': fields.Datetime.now(),
            'approved_by': False, 'approved_date': False,
            'rejected_by': False, 'rejected_date': False,
            'decision_reason': False,
        })
        return tag.with_user(reviewer).sudo().with_context(
            cadra_audit_reprint=tag.id).action_approve_replacement(
            decision_reason=_('Accepted on audit capture %s.')
            % self.capture_uuid)

    def _accept_in_sap(self, reviewer):
        rec = self.sap_record_id
        if not (rec.sap_active and rec.in_latest_export):
            raise _refuse(_('SAP asset %s is no longer active in the latest '
                            'export.') % rec.asset_number,
                          sap_record_id=rec.id)
        if rec._linked_assets().get(rec.id):
            raise _refuse(_('SAP asset %s is already on Cadra\'s register.')
                          % rec.asset_number, sap_record_id=rec.id)
        confirmed = json.loads(self.confirmed_json or '{}')
        vals = {
            'name': self.name or rec.description or rec.asset_number,
            'category_id': self.category_id.id,
            'asset_code': self.code,
            'asset_tag': self.code, 'tag_source': 'manual',
            'location_id': self.location_id.id,
            'condition': self.condition,
            'register_state': REGISTERED,
            'sap_asset_number': rec.asset_number_norm,
            'sap_asset_subnumber': (rec.sub_number or False)
            if rec.sub_number_norm != '0' else False,
            'sap_company_code': rec.company_code or False,
            'sap_code_source': SAP_SOURCE_AUDIT,
            'acquisition_date': rec.capitalized_on or False,
            'legacy_asset_code': rec.old_tag or confirmed.get(
                'legacy_asset_code') or False,
        }
        for key in ('make', 'model_name', 'serial_number'):
            if isinstance(confirmed.get(key), str) and confirmed[key].strip():
                vals[key] = confirmed[key].strip()
        asset = self.env['nrs.asset'].with_user(reviewer).sudo().with_context(
            **{SAP_AUDIT_KEY: True}).create(vals)
        self._affix(asset)
        self._w({'photos_copied': self._copy_photos(asset)})
        return asset

    def _affix(self, asset):
        """The label the phone printed is on the item: the capture's scan
        was the affix check. Recorded as the capturer's."""
        tag = asset.active_tag_id
        tag.with_user(self.operator_id).sudo()._mark_affixed(
            self.scanned_label, affixed_date=self.captured_at)

    def _return_capture(self, reason):
        self.ensure_one()
        self._assert_reviewable()
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if not text:
            raise _refuse(_('A reason is required to return a capture — say '
                            'what to capture again, in words.'),
                          'validation_failed', field='reason')
        cap = self.sudo()
        cap._w({'state': 'returned', 'reviewed_by_id': self.env.user.id,
                'reviewed_at': fields.Datetime.now(), 'return_reason': text})
        code = cap.code_id
        if code and code.state == 'in_review':
            if cap.duplicate_of_id or code.block_id.state != 'issued':
                # A duplicate's label is a SECOND label on an item already
                # captured, and a code of a returned block can never be used
                # again: void it, never free it for another item (R2;
                # verification pass, 66). The label is taken off.
                code._void(_(
                    'Capture %(id)s returned%(dup)s: %(why)s',
                    id=cap.capture_uuid,
                    dup=_(' as a duplicate') if cap.duplicate_of_id
                    else _(' after its block was returned'), why=text))
            else:
                # Kept for the re-capture of the same item: back to the
                # capturer's reserve.
                code._set({'state': 'reserved', 'capture_id': False,
                           'used_at': False})
        return cap

    # ── the exceptions (outcome c) ────────────────────────────────────

    def _assert_open_exception(self):
        self.ensure_one()
        if self.outcome != OUTCOME_IN_NEITHER or self.state != 'accepted':
            raise _refuse(_('Capture %s is not a found-not-in-SAP '
                            'exception.') % self.capture_uuid)
        if self.exception_state != 'open':
            raise _refuse(_('Exception %(id)s was already %(state)s.',
                            id=self.capture_uuid,
                            state=dict(EXCEPTION_STATES)[
                                self.exception_state].lower()))

    def _register_new(self, completed=None):
        """The Asset Controller registers the exception as new: an asset
        whose label (the capture's code) is already on it, waiting on the
        Register Maker — the normal maker and checker gates, and INT-06's
        master at the checker's approval, because SAP does not hold it."""
        self.ensure_one()
        self._assert_open_exception()
        cap = self.sudo()
        me = self.env.user
        confirmed = json.loads(cap.confirmed_json or '{}')
        vals = {
            'name': cap.name, 'category_id': cap.category_id.id,
            'asset_code': cap.code, 'asset_tag': cap.code,
            'tag_source': 'manual', 'location_id': cap.location_id.id,
            'condition': cap.condition, 'register_state': 'tagged',
            'register_state_since': fields.Datetime.now(),
        }
        completed = completed or {}
        stray = sorted(set(completed) - set(IDENTITY_FIELDS))
        if stray:
            raise _refuse(_('Only the item\'s identity can be completed here: '
                            '%s.') % ', '.join(IDENTITY_FIELDS),
                          'validation_failed', rejected_fields=stray,
                          writable=list(IDENTITY_FIELDS))
        for key in ('make', 'model_name', 'serial_number',
                    'legacy_asset_code', 'colour', 'material', 'dimensions'):
            value = completed.get(key, confirmed.get(key))
            if isinstance(value, str) and value.strip():
                vals[key] = value.strip()
        # Section 12, as for any unit that will reach the register through
        # the maker and checker (verification pass, 66): the class's serial
        # and mandatory attributes, placeholders and a serial already held
        # refused in words — before anything is written.
        probe = dict(vals)
        vals.update(self.env['nrs.asset'].sudo()._check_receipt_identity(
            probe))
        asset = self.env['nrs.asset'].with_user(me).sudo().with_context(
            **{_GATE_WRITE_KEY: True}).create(vals)
        # Its birth state, said: no gate fired (`gate` empty), so nobody is
        # recorded as having received, verified or tagged it.
        self.env['nrs.asset.event'].sudo().with_context(
            cadra_event_source='api_audit')._record(
            asset, EVENT_GATE_FIRED, from_value=False, to_value='tagged',
            gate=False, gate_action='audit-exception',
            reason=_('Found by audit %(name)s in neither register; its label '
                     '%(code)s is on it. Waiting on the Register Maker.',
                     name=cap.campaign_id.name, code=cap.code),
            actor=me)
        cap._affix(asset)
        cap._w({'exception_state': 'registered',
                'exception_resolved_by_id': me.id,
                'exception_resolved_at': fields.Datetime.now(),
                'result_asset_id': asset.id,
                'photos_copied': cap._copy_photos(asset)})
        cap._record_on_asset(asset, cap.reviewed_by_id)
        return asset

    def _void_exception(self, reason):
        self.ensure_one()
        self._assert_open_exception()
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if not text:
            raise _refuse(_('A reason is required to void an exception — the '
                            'label printed for it is accounted for by it.'),
                          'validation_failed', field='reason')
        cap = self.sudo()
        cap._w({'exception_state': 'voided',
                'exception_resolved_by_id': self.env.user.id,
                'exception_resolved_at': fields.Datetime.now(),
                'exception_void_reason': text})
        if cap.code_id:
            cap.code_id._void(_('Exception %(id)s voided: %(why)s',
                                id=cap.capture_uuid, why=text))
        return cap


def _int(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refuse(_('`%s` is an id (a whole number).') % field,
                      'validation_failed', field=field)
    return value


def _gps(value):
    """`{gps_latitude, gps_longitude, gps_accuracy_m}` from a capture's
    optional `gps`, or `{}`. Refused in words when it is not a position."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _refuse(_('`gps` is an object: latitude, longitude and '
                        'optionally accuracy_m.'), 'validation_failed',
                      field='gps')
    stray = sorted(set(value) - {'latitude', 'longitude', 'accuracy_m'})
    if stray:
        raise _refuse(_('`gps` cannot carry: %s.') % ', '.join(stray),
                      'validation_failed', field='gps',
                      rejected_fields=stray,
                      writable=['latitude', 'longitude', 'accuracy_m'])
    out = {}
    for key, column, lo, hi in (('latitude', 'gps_latitude', -90, 90),
                                ('longitude', 'gps_longitude', -180, 180),
                                ('accuracy_m', 'gps_accuracy_m', 0, 1e6)):
        v = value.get(key)
        if v is None and key == 'accuracy_m':
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not lo <= v <= hi:
            raise _refuse(_('`gps.%(key)s` is a number from %(lo)s to '
                            '%(hi)s.', key=key, lo=lo, hi=int(hi)),
                          'validation_failed', field='gps.%s' % key,
                          minimum=lo, maximum=hi)
        out[column] = float(v)
    out['gps_recorded'] = True
    return out


def _parse_moment(value):
    if not isinstance(value, str) or not value.strip():
        raise _refuse(_('`captured_at` is when the item was captured, as '
                        'ISO-8601.'), 'validation_failed',
                      field='captured_at')
    text = value.strip().replace('Z', '+00:00')
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise _refuse(_('`captured_at` could not be read as ISO-8601: %s')
                      % value, 'validation_failed',
                      field='captured_at') from None
    if moment.tzinfo:
        moment = moment.astimezone(pytz.utc).replace(tzinfo=None)
    return moment


class NRSAssetAuditLedger(models.Model):
    """R2a: every asset's code is in the ledger; a registration activates
    it; an IAD rejection voids it."""
    _inherit = 'nrs.asset'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['nrs.asset.code']._for_assets(records)
        return records

    def _gate_move(self, to, action, gate, reason=None, notes=None):
        result = super()._gate_move(to, action, gate, reason=reason,
                                    notes=notes)
        if to in (REGISTERED, 'vfm_rejected'):
            rows = self.env['nrs.asset.code'].sudo().search(
                [('code', '=', self.asset_code)])
            if to == REGISTERED:
                rows.filtered(lambda r: r.state != 'active')._set(
                    {'state': 'active', 'asset_id': self.id,
                     'activated_at': fields.Datetime.now()})
            else:
                rows.filtered(lambda r: r.state == 'in_review')._void(
                    _('The receipt was rejected by IAD.'))
        return result


class NRSAssetTagLabelAuditReprint(models.Model):
    """The audit's reprint: the reviewer's acceptance is the approval
    (handoff 66 §5). Honoured only for the one label the acceptance names,
    and never for the requester."""
    _inherit = 'nrs.asset.tag.label'

    def _may_decide(self, user):
        if self.env.context.get('cadra_audit_reprint') == self.id \
                and user.id != self.requested_by.id:
            return True
        return super()._may_decide(user)
