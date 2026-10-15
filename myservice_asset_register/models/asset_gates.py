# -*- coding: utf-8 -*-
"""The receipt gates — Addendum A's chain, on `nrs.asset` (handoffs 57, 58).

What this is, plainly: NRS ruled on 7 October 2026 that a received unit is
not an asset until Internal Audit has sighted it, a tag is on it and a
maker-checker pair has registered it (Addendum A). This file is that chain.
A unit that has not passed it is a CANDIDATE: the same `nrs.asset` record,
carrying `register_state` anything but `registered`. Handoff 57 built it in
one night as a stand-in for a separate candidate model; handoff 58 KEPT it
(`docs/ADDENDUM-A-EVALUATION.md` §8, reversing §4.6), because report 57
measured the one property a separate model was supposed to buy and found it
already held: no list, count, report, export or dashboard shows a candidate.

The register filter in `_search` is LOAD-BEARING (handoff 57 finding P8).
It is the only thing that keeps a candidate off every register route —
22 routes list or count assets and two of them share a helper, so the
filter lives where all of them meet. Code that forgets the context flag
cannot FIND a candidate; it cannot SHOW one. That is the safe failure, and
it is why the flag must never be set by default. The cost is that the
column is read by every asset search: a tenant whose module was not
upgraded fails every asset list, not only the new column — upgrade every
database before the code ships (`CLAUDE.md`, the fan-out), and the API
answers such a tenant with `server_misconfigured`, naming the upgrade.

The machine is ONE table (`TRANSITIONS`) and ONE method (`_fire_gate`).
Nothing else changes `register_state`: `write` refuses the field without
the flag `_fire_gate` sets, and a test pins that.

The no-two-gates rule (Addendum A §4, enforcement rule 1): a user who
fired one gate on a unit may not fire a DIFFERENT gate on it. The refusal
names the earlier act, its date and the person — never "permission
denied". The officer/approver and maker/checker separations are this rule;
they are not written a second time. Rule 2 — the combinations of roles
nobody may be GRANTED — is `nrs.role.exclusion` in `myservice_api`.

A unit of a `record_only` class (handoff 59 §2 — land, buildings,
software, works in progress) has nothing a label can be fixed to. Its chain
is the same table with the two tagging gates SKIPPED, not fired: IAD's
approval moves it on to `reg_ready`, waiting on the Register Maker, and the
skip is an event of its own saying why. Five people instead of seven; the
no-two-gates rule is unchanged. A row that applies to some modes only says
so in `modes`; a row without it applies to every mode.

Before a registration is submitted or approved, the class must carry SAP's
asset class (handoff 59 §1): SAP rejects an asset master with none, and the
maker should learn that from Cadra, not from SAP after two people have
signed.

A candidate is not on the register, so nothing that only a register asset
can have happen to it may happen to it (handoff 58, P5): no custodian, no
move, no transfer, no disposal — refused on the model under every writer
(`_assert_on_the_register`), the message naming whom the unit waits on.
"""
import base64
import binascii
import json
import logging
from datetime import date as _date_cls

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from .asset_event import EVENT_GATE_FIRED

_logger = logging.getLogger(__name__)

# ── The states ────────────────────────────────────────────────────────
REGISTERED = 'registered'
REGISTER_STATES = [
    ('captured', 'Captured'),
    ('vfm_pending', 'Awaiting IAD verification'),
    ('vfm_verified', 'Verified — awaiting IAD approval'),
    ('vfm_approved', 'Value for money approved'),
    ('vfm_query', 'Queried by IAD'),
    ('vfm_rejected', 'Rejected by IAD'),
    ('tag_requested', 'Tagging requested'),
    ('tag_issued', 'Tag issued'),
    ('tagged', 'Tagged'),
    # A `record_only` unit after IAD's approval: no label, and none due —
    # waiting on the Register Maker (handoff 59 §2). Not `tagged`, which
    # would say a label is on a plot of land.
    ('reg_ready', 'Ready for registration — no label'),
    ('reg_submitted', 'Registration submitted'),
    (REGISTERED, 'Registered'),
]

# Who the record is waiting on, by state. Published as `gates.waiting_on`
# and the `?waiting_on=` filter on `GET /candidates`.
WAITING_ON = {
    'captured': 'store',
    'vfm_query': 'store',
    'vfm_pending': 'iad',
    'vfm_verified': 'iad_approver',
    'vfm_approved': 'controller',
    'tag_requested': 'tagging',
    'tag_issued': 'tagging',
    'tagged': 'maker',
    'reg_ready': 'maker',
    'reg_submitted': 'checker',
    'vfm_rejected': None,
    REGISTERED: None,
}
WAITING_ON_VALUES = ('store', 'iad', 'iad_approver', 'controller',
                     'tagging', 'maker', 'checker')
# The same, as a person reads it — for the refusals that say whom a unit
# that is not on the register is still waiting on (handoff 58, P5).
WAITING_ON_WORDS = {
    'store': 'Store',
    'iad': 'IAD verification',
    'iad_approver': 'IAD approval',
    'controller': 'the Asset Controller',
    'tagging': 'tagging',
    'maker': 'the Register Maker',
    'checker': 'the Register Checker',
}

# ── The gates (Addendum A §4 rule 1) and how a refusal says them ─────
GATE_RECEIPT = 'receipt'
GATE_VERIFY = 'verify'
GATE_APPROVE = 'approve'
GATE_TAG_REQUEST = 'tag_request'
GATE_TAGGING = 'tagging'
GATE_MAKE = 'make'
GATE_CHECK = 'check'

# "You <done> on 7 Oct; a different person must <todo>."
_GATE_DONE = {
    GATE_RECEIPT: 'received this unit',
    GATE_VERIFY: 'verified this unit',
    GATE_APPROVE: "approved this unit's value for money",
    GATE_TAG_REQUEST: 'requested tagging for this unit',
    GATE_TAGGING: 'tagged this unit',
    GATE_MAKE: 'submitted this unit for registration',
    GATE_CHECK: "approved this unit's registration",
}
_GATE_TODO = {
    GATE_RECEIPT: 'submit it',
    GATE_VERIFY: 'verify it',
    GATE_APPROVE: 'approve it',
    GATE_TAG_REQUEST: 'request its tagging',
    GATE_TAGGING: 'tag it',
    GATE_MAKE: 'submit it for registration',
    GATE_CHECK: 'approve its registration',
}

# The scopes, spelled here as literals because `myservice_api` (which owns
# the scope table) depends on this module and not the reverse.
S_ASSETS_WRITE = 'assets:write'
S_VFM_VERIFY = 'vfm:verify'
S_VFM_APPROVE = 'vfm:approve'
S_TAGGING_REQUEST = 'tagging:request'
S_REGISTER_MAKE = 'register:make'
S_REGISTER_CHECK = 'register:check'
S_TAGGING_WRITE = 'tagging:write'

# The identification modes a row may be limited to (`asset_identification`
# defines them; spelled here because it imports this module's GateRefused).
MODE_RECORD_ONLY = 'record_only'
_LABELLED = ('serial', 'tag_id', 'pool')

# ── THE table. (from states, to, action, scopes [any of], gate, needs) ─
# `gate` is the gate the actor fires (None: not a gate). `acts_as` is the
# gate the no-two-gates rule checks the actor against when the action is
# not itself a gate (a query is IAD acting, a return is the checker
# acting). `needs` names the one free-text field the action requires.
# `modes`, when present, limits the row to units received under those
# identification modes (handoff 59 §2); a unit received with the gates off
# has none and counts as `serial`.
TRANSITIONS = (
    dict(action='submit', frm=('captured',), to='vfm_pending',
         scopes=(S_ASSETS_WRITE,), gate=GATE_RECEIPT),
    dict(action='verify', frm=('vfm_pending',), to='vfm_verified',
         scopes=(S_VFM_VERIFY,), gate=GATE_VERIFY),
    dict(action='approve', frm=('vfm_verified',), to='vfm_approved',
         scopes=(S_VFM_APPROVE,), gate=GATE_APPROVE),
    dict(action='query', frm=('vfm_pending', 'vfm_verified'), to='vfm_query',
         scopes=(S_VFM_VERIFY, S_VFM_APPROVE), gate=None,
         acts_as='iad', needs='reason'),
    dict(action='resubmit', frm=('vfm_query',), to='captured',
         scopes=(S_ASSETS_WRITE,), gate=None, acts_as=GATE_RECEIPT,
         needs='response'),
    dict(action='reject', frm=('vfm_pending', 'vfm_verified'),
         to='vfm_rejected', scopes=(S_VFM_APPROVE,), gate=None,
         acts_as=GATE_APPROVE, needs='reason'),
    dict(action='request-tagging', frm=('vfm_approved',), to='tag_requested',
         scopes=(S_TAGGING_REQUEST,), gate=GATE_TAG_REQUEST, modes=_LABELLED),
    dict(action='register', frm=('tagged',), to='reg_submitted',
         scopes=(S_REGISTER_MAKE,), gate=GATE_MAKE, modes=_LABELLED),
    dict(action='register', frm=('reg_ready',), to='reg_submitted',
         scopes=(S_REGISTER_MAKE,), gate=GATE_MAKE, modes=(MODE_RECORD_ONLY,)),
    dict(action='approve-registration', frm=('reg_submitted',),
         to=REGISTERED, scopes=(S_REGISTER_CHECK,), gate=GATE_CHECK),
    dict(action='return-registration', frm=('reg_submitted',), to='tagged',
         scopes=(S_REGISTER_CHECK,), gate=None, acts_as=GATE_CHECK,
         needs='reason', modes=_LABELLED),
    dict(action='return-registration', frm=('reg_submitted',),
         to='reg_ready', scopes=(S_REGISTER_CHECK,), gate=None,
         acts_as=GATE_CHECK, needs='reason', modes=(MODE_RECORD_ONLY,)),
)
# The system steps. Not in the table a caller can fire from.
SYSTEM_TRANSITIONS = (
    dict(action='issue-tag', frm=('tag_requested',), to='tag_issued',
         modes=_LABELLED),
    dict(action='affix', frm=('tag_issued',), to='tagged', gate=GATE_TAGGING,
         modes=_LABELLED),
    # Fired inside `approve` for a unit with no label to fix (handoff 59
    # §2): the two tagging gates are SKIPPED — no gate is fired, nobody's
    # act is recorded as a tagging, and the event says why.
    dict(action='skip-tagging', frm=('vfm_approved',), to='reg_ready',
         modes=(MODE_RECORD_ONLY,)),
)
SKIP_TAGGING = SYSTEM_TRANSITIONS[-1]
ACTIONS = tuple(dict.fromkeys(t['action'] for t in TRANSITIONS))
REASON_REQUIRED = {t['action'] for t in TRANSITIONS if t.get('needs')}

VERIFY_CHECKLIST = ('quantity', 'specification', 'condition', 'price')

# ── What each waiting state waits FOR (handoff 60 §2a) ─────────────────
# The forward act a unit in that state needs, the gate the no-two-gates rule
# judges it as, and the scopes that may do it. `waiting on me` and the
# sidebar badge read this: a unit counts for a person when they hold the
# act's scope AND the no-two-gates rule does not bar them from it. A query,
# a rejection or a return is not what a unit waits for, so it is not here.
# `affix` is the station's act (`POST /assets/<id>/tag-affixed`, which
# needs `tagging:write`), a system transition and not in TRANSITIONS.
# `tag_requested` is not here: `request-tagging` issues the label in the
# same act, so no unit waits there. Pinned against TRANSITIONS by
# `test_waiting_act_matches_the_table`.
WAITING_ACT = {
    'captured': ('submit', GATE_RECEIPT, (S_ASSETS_WRITE,)),
    'vfm_query': ('resubmit', GATE_RECEIPT, (S_ASSETS_WRITE,)),
    'vfm_pending': ('verify', GATE_VERIFY, (S_VFM_VERIFY,)),
    'vfm_verified': ('approve', GATE_APPROVE, (S_VFM_APPROVE,)),
    'vfm_approved': ('request-tagging', GATE_TAG_REQUEST,
                     (S_TAGGING_REQUEST,)),
    'tag_issued': ('affix', GATE_TAGGING, (S_TAGGING_WRITE,)),
    'tagged': ('register', GATE_MAKE, (S_REGISTER_MAKE,)),
    'reg_ready': ('register', GATE_MAKE, (S_REGISTER_MAKE,)),
    'reg_submitted': ('approve-registration', GATE_CHECK,
                      (S_REGISTER_CHECK,)),
}

# The states in which a candidate has no label yet, and may not be given one
# except by `request-tagging`.
_BEFORE_THE_TAG = frozenset({
    'captured', 'vfm_pending', 'vfm_verified', 'vfm_approved', 'vfm_query',
    'vfm_rejected', 'tag_requested'})

# The context key that lets a search see candidates. Set by `GET
# /candidates`, by `?register_state=any|<value>` (for a caller holding
# `candidates:read`) and by the single-record lookups that must find a
# candidate (the scan box, by-tag). Everything else sees the register.
CANDIDATES_CTX = 'cadra_candidates'

# The flag `_fire_gate` sets so `write` lets `register_state` through.
_GATE_WRITE_KEY = 'cadra_gate_fire'
# The parameter that switches the gates on (handoff 57 §2b; built by
# Stream C on the settings screen). Absent means OFF — today's behaviour.
RECEIPT_GATED_PARAM = 'cadra.receipt.gated'
_ON_VALUES = ('1', 'true', 'True', 'TRUE', 'on', 'yes')

_LAGOS = pytz.timezone('Africa/Lagos')


class GateRefused(UserError):
    """A gate refusal, carrying what the API needs to say it.

    `kind` is one of `invalid_state`, `forbidden`, `validation_failed`,
    `segregation_of_duties`, `not_on_the_register`; the API maps it onto the
    envelope in ONE place (`myservice_api` `controllers/utils.py`,
    `gate_refusal`) for every route, the affix route included (handoff 58,
    D3). A `UserError` so any non-API caller still gets the sentence.
    """

    def __init__(self, message, kind, details=None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


def _lagos_day(dt):
    if not dt:
        return ''
    local = pytz.utc.localize(dt).astimezone(_LAGOS)
    return '%d %s' % (local.day, local.strftime('%b'))


def _m2o(value):
    """The id a many2one write names — an int, a record, or a command."""
    if isinstance(value, models.BaseModel):
        return value.id
    if isinstance(value, (list, tuple)):
        return value[0] if value else False
    return value or False


def _mode_fits(row, mode):
    return 'modes' not in row or (mode or 'serial') in row['modes']


def _row(action, state, mode=None):
    for row in TRANSITIONS:
        if row['action'] == action and state in row['frm'] \
                and _mode_fits(row, mode):
            return row
    return None


#: The first digit of SAP's 11-digit asset numbers, per class, where it is
#: NOT the class code's own first digit — measured on NRS's October 2026
#: export (report 59): 146,165 of 146,224 numeric numbers start with their
#: class's first digit, and the other 59 are every numeric number of class
#: 3500, which start `5000…`. Without this, every software asset would be
#: warned about.
SAP_NUMBER_FIRST_DIGIT = {'3500': '5'}
#: Which class a first digit says, for the sentence. `9` is two classes.
_CLASS_OF_DIGIT = {'1': '1000', '2': '2000', '3': '3000', '4': '4000',
                   '5': '3500', '6': '6000', '7': '7000', '8': '8000',
                   '9': '9000 or 9300'}


def sap_number_class_warning(number, sap_class):
    """The class-digit warning (handoff 59 §4), or None.

    SAP's numeric asset numbers are 11 digits whose first digit says the
    class (`2…` is class 2000). A legacy alphanumeric code says nothing
    about its class and is never warned on. A warning, not a refusal: the
    maker may be right and the mapping wrong.
    """
    number = (number or '').strip()
    sap_class = (sap_class or '').strip()
    if not (len(number) == 11 and number.isdigit() and sap_class
            and sap_class[:1].isdigit()):
        return None
    expected = SAP_NUMBER_FIRST_DIGIT.get(sap_class, sap_class[0])
    if number[0] == expected:
        return None
    return ('%s looks like a class %s number; this category maps to %s.'
            % (number, _CLASS_OF_DIGIT.get(number[0], number[0] + '000'),
               sap_class))


class NRSAssetGates(models.Model):
    _inherit = 'nrs.asset'

    register_state = fields.Selection(
        REGISTER_STATES, string='Register State', default=REGISTERED,
        # NOT tracked: every change already writes a `gate_fired` event,
        # which nobody can alter; a chatter line too would put each gate in
        # the asset's history twice.
        required=True, index=True, copy=False,
        help='Anything but Registered is a receipt candidate: hidden from '
             'the register, its counts and its reports, and moved only by '
             'the receipt gates (handoffs 57, 58).')
    # The Register Maker's entries (handoff 57 §2a). The cost goes into
    # `acquisition_cost`, the SAP code into `sap_asset_number` as a code
    # ENTERED BY HAND — these two had nowhere to go.
    cost_centre = fields.Char('Cost Centre', copy=False)
    capitalisation_date = fields.Date('Capitalisation Date', copy=False)
    # When the unit entered its present register state (handoff 60 §2a): the
    # Candidates list is read OLDEST first by it, so the unit that has waited
    # longest is the one on screen. Stored and indexed because a sort and a
    # keyset cursor need a column; `gates.state_since` is published FROM it,
    # so what is shown and the order agree. Set at creation and by
    # `_gate_move`, nowhere else; the 19.0.1.29.0 migration filled it on
    # every candidate from its last gate event.
    register_state_since = fields.Datetime(
        'In Register State Since', index=True, copy=False, readonly=True)

    # ── the register hides candidates — ONE place (handoff 57 §2d) ────

    @api.model
    def _search(self, domain, *args, **kwargs):
        """Registered assets only, unless the search asks otherwise.

        The ONE place §2d asks for. The route census found 22 routes that
        list, count, aggregate or export assets and only two of them share
        a domain builder — the dashboard strip, the export, the map's
        counts, the category and employee counts, the reports and the
        depreciation cron each build their own. Odoo's own `_search` hides
        archived rows this way (an implicit `active = True` unless the
        domain names `active`), so a candidate is hidden the same way: an
        implicit `register_state = 'registered'` unless the domain names
        `register_state` or the context carries `cadra_candidates`.
        `browse()` is not a search, so `GET /assets/<id>` and every
        by-id action still reach a candidate.
        """
        # NOT when `active_test` is off. Odoo reads records it already holds
        # by ids through `_search([('id', 'in', ids)], active_test=False)`
        # (`BaseModel.fetch`) — the same door it uses to let an archived
        # record it holds be read — and filtering there made a candidate
        # unreadable, sudo included, the moment its cache was dropped
        # (caught by `test_receipt_gates`). So this default steps aside
        # exactly where the `active` default does.
        if kwargs.get('active_test', True) \
                and self.env.context.get('active_test', True) \
                and not self.env.context.get(CANDIDATES_CTX):
            domain = Domain(domain)
            if not any(leaf.field_expr == 'register_state'
                       for leaf in domain.iter_conditions()):
                domain &= Domain('register_state', '=', REGISTERED)
        return super()._search(domain, *args, **kwargs)

    # ── the switch ────────────────────────────────────────────────────

    @api.model
    def _receipt_gated(self):
        """Whether a new receipt enters as a candidate. Raw SQL, like
        `cadra.approval.required`, so no cache can answer for the row; but
        here ABSENT MEANS OFF — the gates are opt-in per tenant."""
        self.env.cr.execute(
            "SELECT value FROM ir_config_parameter WHERE key = %s",
            (RECEIPT_GATED_PARAM,))
        row = self.env.cr.fetchone()
        return bool(row) and (row[0] or '').strip() in _ON_VALUES

    # ── the guard on the field ────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if not vals.get('register_state_since'):
                # Never empty on a candidate: the list pages by it.
                vals['register_state_since'] = now
            state = vals.get('register_state')
            if state and state not in ('captured', REGISTERED) \
                    and not self.env.context.get(_GATE_WRITE_KEY):
                raise UserError(_(
                    'A record enters the register either as a captured '
                    'receipt or as a registered asset; "%s" is reached only '
                    'through the receipt gates.') % state)
            if state == 'captured':
                # A receipt arrives with nobody holding it (P5), and with
                # what its class says identifies it (Section 12). Both
                # BEFORE anything is written.
                if vals.get('state') == 'disposed':
                    raise GateRefused(
                        self._not_on_the_register_message(
                            'captured', 'disposal'),
                        'not_on_the_register',
                        {'register_state': 'captured',
                         'waiting_on': WAITING_ON['captured']})
                if vals.get('state') not in (None, False, 'active'):
                    # Handoff 61 (R10), at the door as well as on `write`
                    # (verification pass): a receipt that arrived `missing`
                    # or `in_repair` could never be marked found or repaired
                    # while a candidate, since no status moves until it is
                    # registered.
                    raise GateRefused(
                        self._not_on_the_register_message(
                            'captured', 'missing'
                            if vals['state'] == 'missing' else 'status'),
                        'not_on_the_register',
                        {'register_state': 'captured',
                         'waiting_on': WAITING_ON['captured']})
                if vals.get('last_verified_date'):
                    # Nor verified at birth, for the same reason.
                    raise GateRefused(
                        self._not_on_the_register_message(
                            'captured', 'verification'),
                        'not_on_the_register',
                        {'register_state': 'captured',
                         'waiting_on': WAITING_ON['captured']})
                if vals.get('custodian_id'):
                    raise GateRefused(
                        self._not_on_the_register_message(
                            'captured', 'custodian'),
                        'not_on_the_register',
                        {'register_state': 'captured',
                         'waiting_on': WAITING_ON['captured']})
                vals.update(self.browse()._check_receipt_identity(vals))
            elif vals.get('category_id') and not vals.get(
                    'identification_mode'):
                # Handoff 60 §1.2: a new asset carries its class's mode
                # whatever the switch says. Until 60 only a gated receipt was
                # stamped, so a chair of a `tag_id` class created with the
                # gates off published `identification_mode: null` (Vendra
                # report 54 §5.3). STAMPED, not checked: nothing a gates-off
                # receipt sends is refused that was not refused before.
                # Records created before 60 keep what they have.
                category = self.env['nrs.asset.category'].sudo().browse(
                    _m2o(vals['category_id'])).exists()
                if category:
                    vals['identification_mode'] = (
                        category.identification_mode or 'serial')
        return super().create(vals_list)

    # ── a candidate is not on the register (handoff 58, P5) ───────────

    @api.model
    def _not_on_the_register_message(self, state, act):
        """The sentence refusing `act` on a unit at `state`."""
        tails = {
            'custodian': _('a custodian can be assigned once it is '
                           'registered.'),
            'move': _('it can be moved once it is registered.'),
            'transfer': _('it can be transferred once it is registered.'),
            'disposal': _('it can be disposed of once it is registered.'),
            # Handoff 61 (ruling R10): a unit not on the register cannot be
            # missing from it, found on it, or verified as present in it.
            'verification': _('it can be verified once it is registered.'),
            'missing': _('it cannot be missing from a register it is not '
                         'on yet.'),
            'found': _('it cannot be found on a register it is not on '
                       'yet.'),
            'status': _('its status can change once it is registered.'),
        }
        who = WAITING_ON.get(state)
        if who:
            return _('This unit is not on the register yet (waiting on '
                     '%(who)s); %(tail)s', who=WAITING_ON_WORDS[who],
                     tail=tails[act])
        return _('This unit is not on the register — Internal Audit '
                 'rejected it; %(tail)s', tail=tails[act])

    def _refuse_off_the_register(self, act):
        """Raise for the first candidate in `self`, if any."""
        for rec in self:
            if rec.register_state and rec.register_state != REGISTERED:
                raise GateRefused(
                    self._not_on_the_register_message(rec.register_state, act),
                    'not_on_the_register',
                    {'register_state': rec.register_state,
                     'waiting_on': WAITING_ON.get(rec.register_state),
                     'asset_id': rec.id})

    def _assert_on_the_register(self, vals):
        """Called from `nrs.asset._write_recorded`, beside the disposal and
        approval guards — under every ORM writer, with no exemption: a
        custodian, a move, a disposal — and since handoff 61 (R10) a change
        of status and a verification — are things only a register asset
        can have happen to it. A write that NAMES a field without changing
        it passes (the edit form re-sends everything), and so does CLEARING
        a custodian or a location — that takes nothing onto a candidate."""
        if not any(r.register_state != REGISTERED for r in self):
            return
        for rec in self.filtered(lambda r: r.register_state != REGISTERED):
            if vals.get('custodian_id') \
                    and _m2o(vals['custodian_id']) != rec.custodian_id.id:
                rec._refuse_off_the_register('custodian')
            if vals.get('location_id') \
                    and _m2o(vals['location_id']) != rec.location_id.id:
                rec._refuse_off_the_register('move')
            if vals.get('state') == 'disposed' and rec.state != 'disposed':
                rec._refuse_off_the_register('disposal')
            # Handoff 61 (ruling R10), under every writer like the three
            # above: a candidate's status does not move (missing, found,
            # under repair) and it is not verified — the routes say which
            # act first, this is what holds for the form, a script, PATCH.
            if 'state' in vals and vals['state'] != rec.state:
                rec._refuse_off_the_register(
                    'missing' if vals['state'] == 'missing' else 'status')
            if vals.get('last_verified_date') \
                    and fields.Date.to_date(vals['last_verified_date']) \
                    != rec.last_verified_date:
                rec._refuse_off_the_register('verification')

    def write(self, vals):
        if 'register_state' in vals \
                and not self.env.context.get(_GATE_WRITE_KEY) \
                and any(r.register_state != vals['register_state']
                        for r in self):
            raise UserError(_(
                'The register state of an asset is changed only by firing '
                'one of its receipt gates (submit, verify, approve, request '
                'tagging, register, approve registration…), never by '
                'writing it.'))
        return super().write(vals)

    # ── scopes of the caller ──────────────────────────────────────────

    def _gate_scopes(self, scopes=None):
        """The scopes to judge the caller by: the token's when the API
        passes them, else derived from the user's groups by the same table
        a login uses. `admin`/`*` hold everything."""
        if scopes is None:
            try:
                from odoo.addons.myservice_api.controllers.utils import (
                    scopes_for_user)
                scopes = scopes_for_user(self.env.user)
            except ImportError:
                scopes = []
        held = set(scopes or ())
        if 'admin' in held or '*' in held:
            held |= {S_ASSETS_WRITE, S_VFM_VERIFY, S_VFM_APPROVE,
                     S_TAGGING_REQUEST, S_REGISTER_MAKE, S_REGISTER_CHECK,
                     S_TAGGING_WRITE}
        return held

    @api.model
    def _waiting_on_me_domain(self, scopes=None, user=None):
        """The units waiting on an act this person may do (handoff 60 §2a).

        For each state in `WAITING_ACT` whose act's scope the person holds:
        the units in that state, LESS those the no-two-gates rule bars them
        from — a unit on which they fired a different gate. That is the
        same test `_two_gates_refusal` makes per unit, made here as one query
        per state, so a badge never counts work its holder cannot do and
        the barred units stay findable under the plain gate filter, where
        their row says why. A person holding no gate scope gets a domain
        that matches nothing.
        """
        held = self._gate_scopes(scopes)
        user = user or self.env.user
        Event = self.env['nrs.asset.event']
        Event.flush_model(['asset_id', 'event_type', 'actor_id', 'gate'])
        self.flush_model(['register_state'])
        clauses = []
        for state, (_act, gate, act_scopes) in WAITING_ACT.items():
            if not set(act_scopes) & held:
                continue
            self.env.cr.execute(
                "SELECT DISTINCT e.asset_id FROM nrs_asset_event e "
                "JOIN nrs_asset a ON a.id = e.asset_id "
                "WHERE e.event_type = %s AND e.actor_id = %s "
                "AND e.gate IS NOT NULL AND e.gate <> %s "
                "AND a.register_state = %s",
                (EVENT_GATE_FIRED, user.id, gate, state))
            barred = [r[0] for r in self.env.cr.fetchall()]
            clause = Domain('register_state', '=', state)
            if barred:
                clause &= Domain('id', 'not in', barred)
            clauses.append(clause)
        return Domain.OR(clauses) if clauses else Domain.FALSE

    # ── the rule ──────────────────────────────────────────────────────

    def _gate_events(self):
        self.ensure_one()
        return self.env['nrs.asset.event'].sudo().search(
            [('asset_id', '=', self.id), ('event_type', '=', EVENT_GATE_FIRED)],
            order='occurred_at, id')

    def _acting_gate(self, row, held):
        gate = row.get('gate') or row.get('acts_as')
        if gate == 'iad':
            # A query is the officer's act if they hold the officer's
            # scope, else the approver's.
            gate = GATE_VERIFY if S_VFM_VERIFY in held else GATE_APPROVE
        return gate

    def _two_gates_refusal(self, gate, user=None):
        """The sentence refusing `user` gate `gate` here, or None."""
        self.ensure_one()
        user = user or self.env.user
        for event in self._gate_events():
            if event.actor_id.id == user.id and event.gate \
                    and event.gate != gate:
                return (_(
                    'You %(done)s on %(day)s; a different person must '
                    '%(todo)s.',
                    done=_GATE_DONE.get(event.gate, event.gate),
                    day=_lagos_day(event.occurred_at),
                    todo=_GATE_TODO.get(gate, gate)), event)
        return None

    def _assert_two_gates(self, gate, user=None):
        found = self._two_gates_refusal(gate, user)
        if found:
            message, event = found
            raise GateRefused(message, 'segregation_of_duties', {
                'earlier': {
                    'action': event.gate_action,
                    'gate': event.gate,
                    'date': fields.Datetime.to_string(event.occurred_at),
                    'user_name': event.actor_name,
                }})

    # ── what the caller may do (the serialiser's `gates` block) ───────

    def _gates_block(self, scopes=None):
        self.ensure_one()
        held = self._gate_scopes(scopes)
        available = []
        for row in TRANSITIONS:
            if self.register_state not in row['frm'] \
                    or not _mode_fits(row, self.identification_mode):
                continue
            if not set(row['scopes']) & held:
                continue
            found = self._two_gates_refusal(self._acting_gate(row, held))
            available.append({
                'action': row['action'],
                'can_fire': not found,
                'refusal': found[0] if found else None,
                'reason_required': row['action'] in REASON_REQUIRED,
            })
        events = self._gate_events()
        # The stored instant the list is sorted by, so what is shown and the
        # order agree (verification pass); the events for a record that
        # predates the column.
        since = self.register_state_since or (
            events[-1:].occurred_at if events else self.create_date)
        return {
            'waiting_on': WAITING_ON.get(self.register_state),
            'state_since': fields.Datetime.to_string(since) if since else None,
            'available': available,
            'registration': self._registration_block(),
        }

    def _registration_block(self):
        """What the Register Maker submitted, as entered (handoff 60 §2d):
        the checker reads it on the Candidates row instead of opening each
        asset. None until a submission — `cost_centre` is written by the
        `register` gate and nothing else. Its own key: `sap` publishes
        SAP's side (`sap.capitalisation_date` is SAP's date, another field),
        and this is the maker's."""
        self.ensure_one()
        if not self.cost_centre:
            return None
        cat = self.category_id
        return {
            'sap_asset_code': self.sap_asset_number or None,
            'cost': self.acquisition_cost or None,
            'cost_centre': self.cost_centre,
            'capitalisation_date': fields.Date.to_string(
                self.capitalisation_date) if self.capitalisation_date
            else None,
            'asset_class': ({'id': cat.id, 'name': cat.name,
                             'sap_asset_class': cat.sap_asset_class or None}
                            if cat else None),
        }

    # ── THE method ────────────────────────────────────────────────────

    def _fire_gate(self, action, reason=None, payload=None, scopes=None):
        """Fire one gate. Every check BEFORE anything is written."""
        self.ensure_one()
        payload = payload or {}
        state = self.register_state
        row = _row(action, state, self.identification_mode)
        if row is None:
            if action not in ACTIONS:
                raise GateRefused(
                    _('There is no gate action called "%s".') % action,
                    'validation_failed')
            label = dict(REGISTER_STATES).get(state, state)
            raise GateRefused(_(
                'This unit is "%(state)s"; "%(action)s" cannot be done from '
                'there.', state=label, action=action), 'invalid_state',
                {'register_state': state})
        held = self._gate_scopes(scopes)
        if not set(row['scopes']) & held:
            raise GateRefused(_(
                '"%(action)s" needs the %(scopes)s scope, which you do not '
                'hold.', action=action,
                scopes=' or '.join('`%s`' % s for s in row['scopes'])),
                'forbidden', {'required_scopes': list(row['scopes'])})
        needs = row.get('needs')
        text = (reason or '').strip() if isinstance(reason, str) else ''
        if needs and not text:
            raise GateRefused(
                _('A %s is required — say why, in words.') % needs,
                'validation_failed', {'field': needs})
        evidence = self._gate_validate(action, payload)
        gate = self._acting_gate(row, held)
        self._assert_two_gates(gate)
        # ── everything after this line writes ──
        notes = self._gate_apply(action, payload, evidence)
        self._gate_move(row['to'], action, row.get('gate'),
                        reason=text or None, notes=notes)
        if action == 'request-tagging':
            self._gate_issue_tag()
        if row['to'] == SKIP_TAGGING['frm'][0] \
                and _mode_fits(SKIP_TAGGING, self.identification_mode):
            self._gate_skip_tagging()
        if row['to'] == REGISTERED:
            self._on_registered()
        return self

    def _gate_move(self, to, action, gate, reason=None, notes=None):
        frm = self.register_state
        self.env['nrs.asset.event']._record(
            self, EVENT_GATE_FIRED, source='api_gate' if self._in_api()
            else None, from_value=frm, to_value=to, gate=gate,
            gate_action=action, reason=reason,
            notes=json.dumps(notes, sort_keys=True) if notes else None)
        self.with_context(**{_GATE_WRITE_KEY: True}).sudo().write(
            {'register_state': to,
             'register_state_since': fields.Datetime.now()})

    def _in_api(self):
        from odoo.http import request
        return bool(request and getattr(request, 'jwt_claims', None))

    # ── per-action checks and effects ─────────────────────────────────

    def _gate_validate(self, action, payload):
        """Refuse a body the action cannot accept. Returns what to apply."""
        if action == 'verify':
            checklist = payload.get('checklist')
            if not isinstance(checklist, dict) or not all(
                    checklist.get(k) is True for k in VERIFY_CHECKLIST):
                raise GateRefused(_(
                    'Verification needs all four checks confirmed — '
                    'quantity, specification, condition and price.'),
                    'validation_failed', {'field': 'checklist',
                                          'required': list(VERIFY_CHECKLIST)})
            stored = payload.get('_stored_attachment_ids')
            if stored:
                # A batch (handoff 60 §2b): the evidence was checked and
                # stored ONCE by `_store_gate_evidence`, and every unit's
                # event links the same attachments. Internal: the HTTP
                # routes build the payload from named keys, so a body
                # cannot reach this.
                return {'checklist': {k: True for k in VERIFY_CHECKLIST},
                        'attachment_ids': list(stored)}
            files = payload.get('attachments')
            if not isinstance(files, list) or not files:
                raise GateRefused(_(
                    'Verification needs at least one piece of evidence '
                    'attached — a photograph of the unit, the delivery '
                    'note, the invoice.'), 'validation_failed',
                    {'field': 'attachments'})
            decoded = []
            for f in files:
                name = (f or {}).get('name') if isinstance(f, dict) else None
                data = (f or {}).get('data') if isinstance(f, dict) else None
                if not name or not data:
                    raise GateRefused(_(
                        'Each attachment needs a `name` and its `data` '
                        '(base64).'), 'validation_failed',
                        {'field': 'attachments'})
                try:
                    base64.b64decode(data, validate=True)
                except (binascii.Error, ValueError, TypeError):
                    raise GateRefused(_(
                        'Attachment "%s" is not valid base64.') % name,
                        'validation_failed', {'field': 'attachments'})
                decoded.append((name, f.get('mimetype') or None, data))
            return {'checklist': {k: True for k in VERIFY_CHECKLIST},
                    'files': decoded}
        if action == 'register':
            code = payload.get('sap_asset_code')
            # Both of SAP's shapes are accepted — 11 digits whose first is
            # the class's, and the 2013–14 load's codes of letters and
            # digits — and stored as SAP writes them: stripped, upper-case
            # (handoff 59 §4). Uniqueness is judged on that form, so a code
            # typed in lower case is the same code as SAP's.
            code = code.strip().upper() if isinstance(code, str) else ''
            if not code:
                raise GateRefused(_(
                    'The SAP asset code is required to submit a '
                    'registration.'), 'validation_failed',
                    {'field': 'sap_asset_code'})
            # Raw SQL: every record, candidates included, compared in the
            # stored form's normalisation.
            self.flush_model(['sap_asset_number'])
            self.env.cr.execute(
                "SELECT asset_code FROM nrs_asset "
                "WHERE upper(btrim(sap_asset_number)) = %s AND id <> %s "
                "ORDER BY id LIMIT 1", (code, self.id))
            clash = self.env.cr.fetchone()
            if clash:
                raise GateRefused(_(
                    'SAP asset code %(code)s is already on another asset '
                    '(%(asset)s).', code=code, asset=clash[0]),
                    'validation_failed', {'field': 'sap_asset_code',
                                          'asset_code': clash[0]})
            cost = payload.get('cost')
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) \
                    or cost <= 0:
                raise GateRefused(_(
                    'The cost must be a number greater than zero.'),
                    'validation_failed', {'field': 'cost'})
            centre = payload.get('cost_centre')
            centre = centre.strip() if isinstance(centre, str) else ''
            if not centre:
                raise GateRefused(_('The cost centre is required.'),
                                  'validation_failed', {'field': 'cost_centre'})
            raw = payload.get('capitalisation_date')
            try:
                cap = _date_cls.fromisoformat(raw) if isinstance(raw, str) \
                    else None
            except ValueError:
                cap = None
            if not cap:
                raise GateRefused(_(
                    'The capitalisation date is required, as YYYY-MM-DD.'),
                    'validation_failed', {'field': 'capitalisation_date'})
            klass = payload.get('asset_class')
            if isinstance(klass, bool) or not isinstance(klass, int) or \
                    not self.env['nrs.asset.category'].sudo().browse(
                        klass).exists():
                raise GateRefused(_(
                    'Confirm the asset class: send `asset_class` as the id '
                    'of an asset category.'), 'validation_failed',
                    {'field': 'asset_class'})
            self._assert_sap_class(
                self.env['nrs.asset.category'].sudo().browse(klass))
            return {'sap_asset_number': code, 'acquisition_cost': float(cost),
                    'cost_centre': centre, 'capitalisation_date': cap,
                    'category_id': klass}
        if action == 'approve-registration':
            if not (self.sap_asset_number or '').strip():
                raise GateRefused(_(
                    'This registration carries no SAP asset code; return it '
                    'to the maker rather than approving it.'),
                    'validation_failed', {'field': 'sap_asset_code'})
            self._assert_sap_class(self.category_id)
        return None

    @api.model
    def _assert_sap_class(self, category):
        """Refuse a registration whose class has no SAP asset class
        (handoff 59 §1). INT-06 sends the class as SAP's; a blank one goes
        as null and SAP rejects the master — after the maker and the
        checker have both signed. Checked at the maker's submission and
        again at the checker's approval, since a class can be cleared in
        between."""
        if (category.sap_asset_class or '').strip():
            return
        raise GateRefused(_(
            '%(cls)s has no SAP asset class, so SAP would reject this asset. '
            'An Asset Controller sets it under Settings → Asset Categories.',
            cls=category.name or _('This category')), 'validation_failed',
            {'field': 'sap_asset_class', 'category_id': category.id or None})

    def _gate_apply(self, action, payload, evidence):
        """The action's own effect. Returns the evidence for the event."""
        notes = {}
        if payload.get('notes') and isinstance(payload['notes'], str):
            notes['notes'] = payload['notes'].strip()
        if action == 'verify':
            ids = evidence.get('attachment_ids')
            if ids is None:
                ids = self._store_gate_evidence(evidence['files']).ids
            notes.update(checklist=evidence['checklist'], attachment_ids=ids)
        elif action == 'register':
            vals = dict(evidence)
            vals['sap_code_source'] = 'manual'
            self.sudo().write(vals)
            notes.update(
                sap_asset_code=vals['sap_asset_number'],
                cost=vals['acquisition_cost'],
                cost_centre=vals['cost_centre'],
                capitalisation_date=fields.Date.to_string(
                    vals['capitalisation_date']),
                asset_class=vals['category_id'])
            warning = self._sap_number_warning()
            if warning:
                # On the event too, so the checker and an auditor see what
                # the maker was told.
                notes['warning'] = warning
        elif action == 'resubmit':
            pass
        return notes or None

    @api.model
    def _validate_gate_evidence(self, checklist, files):
        """The verify body's checks, for a batch that checks them ONCE
        (handoff 60 §2b) — the same refusals, in the same words, as one
        unit's verify. Returns the decoded files."""
        return self.browse()._gate_validate(
            'verify', {'checklist': checklist, 'attachments': files})['files']

    def _store_gate_evidence(self, files):
        """Store verification evidence once, on the first unit of `self`.
        A batch's units each link these from their own event; one unit's
        verify stores its own."""
        # `image_no_postprocess` (handoff 61): without it `ir.attachment`
        # resizes and re-encodes any image above 1920 px, and IAD's evidence
        # would not be the file IAD attached.
        Attachment = self.env['ir.attachment'].sudo().with_context(
            image_no_postprocess=True)
        stored = Attachment.browse()
        first = self[:1]
        for name, mimetype, data in files:
            vals = {'name': name, 'datas': data, 'res_model': 'nrs.asset',
                    'res_id': first.id}
            if len(self) > 1:
                vals['description'] = _(
                    'Verification evidence for %d units of GRN %s, verified '
                    'together') % (len(self), first.grn_reference or '-')
            if mimetype:
                vals['mimetype'] = mimetype
            stored |= Attachment.create(vals)
        return stored

    def _gate_evidence(self):
        """The verifications of this unit and their evidence — what the
        IAD approver reads before approving (handoff 60 §2b). From the
        `verify` gate events, newest first; an attachment is listed only if
        one of THIS unit's events names it."""
        self.ensure_one()
        Event = self.env['nrs.asset.event'].sudo()
        events = Event.search(
            [('asset_id', '=', self.id), ('event_type', '=', EVENT_GATE_FIRED),
             ('gate_action', '=', 'verify')], order='occurred_at desc, id desc')
        out = []
        for ev in events:
            try:
                notes = json.loads(ev.notes) if ev.notes else {}
            except ValueError:
                notes = {}
            ids = [i for i in (notes.get('attachment_ids') or [])
                   if isinstance(i, int)]
            files = self.env['ir.attachment'].sudo().browse(ids).exists()
            out.append({'event': ev, 'checklist': notes.get('checklist'),
                        'notes': notes.get('notes'), 'files': files})
        return out

    def _gate_issue_tag(self):
        """TAG_REQUESTED → TAG_ISSUED, inside request-tagging.

        The mint MOVED here from creation for a candidate. The label's
        number is the ASSET CODE (ruling §7/4.3: one identifier, the code is
        what the label carries) — so the scan box finds it either way and
        the affix dialog checks the code."""
        Tag = self.env['nrs.asset.tag.label'].sudo()
        tag = self.active_tag_id
        if not tag:
            tag = Tag.create({'name': self.asset_code, 'asset_id': self.id,
                              'source': 'auto', 'state': 'active'})
            self.sudo().write({'asset_tag': self.asset_code})
        self._gate_move('tag_issued', 'issue-tag', None,
                        notes={'tag_number': tag.name})

    def _gate_skip_tagging(self):
        """VFM_APPROVED → REG_READY, inside `approve`, for a unit with no
        label to fix (handoff 59 §2). No gate is fired: the event's `gate`
        is empty, so nobody is recorded as having tagged it and the
        no-two-gates rule counts nothing here. No label is minted."""
        klass = self.category_id.name or _('its class')
        self._gate_move(
            SKIP_TAGGING['to'], SKIP_TAGGING['action'], None,
            reason=_('no label: %s is identified by its record') % klass)

    def _sap_number_warning(self):
        """`sap_number_class_warning` for this unit as it now stands."""
        self.ensure_one()
        return sap_number_class_warning(self.sap_asset_number,
                                        self.category_id.sap_asset_class)

    def _on_registered(self):
        """REGISTERED is reached. `myservice_workflow` queues the INT-06
        asset master here (handoff 57 §2b) — not on affix — for a unit that
        came through the gates."""
        return True


class NRSAssetTagLabelGates(models.Model):
    """TAG_ISSUED → TAGGED fires from the existing affix success path."""
    _inherit = 'nrs.asset.tag.label'

    def _mark_affixed(self, scanned_tag_number, *args, **kwargs):
        asset = self.asset_id
        candidate = asset and asset.register_state != REGISTERED
        if candidate and asset.register_state in _BEFORE_THE_TAG:
            raise ValidationError(_(
                    'This unit is a receipt candidate at "%s"; it can be '
                    'tagged only once its tag is issued.') % dict(
                        REGISTER_STATES).get(asset.register_state))
        # A REPEAT confirmation on a tagged candidate goes to the base, which
        # answers it idempotently (handoff 39) — refused only at the first.
        if candidate and asset.register_state == 'tag_issued':
            # The same refusal, code and status as every other gate — a 409
            # `segregation_of_duties` (handoff 58, D3). Until 58 this one was
            # a ValidationError and the affix route answered it 400
            # `validation_failed`, the only gate whose refusal had another
            # shape. `_assert_two_gates` raises it with `details.earlier`.
            asset._assert_two_gates(GATE_TAGGING)
        was_affixed = self.label_state == 'affixed'
        result = super()._mark_affixed(scanned_tag_number, *args, **kwargs)
        if candidate and not was_affixed and self.label_state == 'affixed' \
                and asset.register_state == 'tag_issued':
            # Which check the tagger made (Section 12): the label and the
            # serial, the label and the attributes (a `tag_id` unit, no
            # serial to scan), or the label alone. Declared by the affix
            # route, which is where the body is read.
            check = self.env.context.get('cadra_affix_check') or 'label_only'
            asset._gate_move('tagged', 'affix', GATE_TAGGING,
                             notes={'tag_number': self.name, 'check': check})
        return result


class NRSAssetTagGates(models.Model):
    """No label is minted at creation for a captured receipt — the mint
    moved to `request-tagging`."""
    _inherit = 'nrs.asset'

    def _generate_tag(self, source='auto'):
        # Only BEFORE the tag is issued. From `tag_issued` on, a candidate
        # has a label. Since handoff 61 a replacement never comes through
        # here — it reprints under the same number in
        # `action_approve_replacement` — which is what closed findings §5.6
        # (a gated unit's replacement minted under a location prefix).
        if self.register_state in _BEFORE_THE_TAG:
            return self.env['nrs.asset.tag.label']
        # Never for a unit received as `record_only` (handoff 59 §2): it
        # has nothing a label can be fixed to, so nothing after its receipt
        # — the back-office station's Generate included — mints one.
        for rec in self:
            if rec.identification_mode == MODE_RECORD_ONLY:
                raise UserError(_(
                    '%(code)s is identified by its SAP record and carries no '
                    'label (%(cls)s); no tag is minted for it.',
                    code=rec.asset_code or rec.display_name,
                    cls=rec.category_id.name or _('its class')))
        return super()._generate_tag(source=source)
