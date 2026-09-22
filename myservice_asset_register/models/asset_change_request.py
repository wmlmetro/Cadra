"""Nobody moves an asset alone. Handoff 35.

WHAT THIS IS
------------
A person asking a second person to agree before an asset is put somewhere
else or placed in somebody else's hands. One model covers both, because
*"what is waiting on me"* is one question and an approver should not have to
look in two places to answer it.

WHY IT IS A NEW MODEL AND NOT `nrs.asset.transfer`
--------------------------------------------------
The handoff asked for the case both ways before the code. `nrs.asset.transfer`
has carried `draft → approved → done → rejected`, an **Approve** button that
stamps `approved_by`, and a **Complete** step that performs the move, since
the beginning. Nothing in the API or the app has ever used it: measured
2026-09-22 across all eight local tenants, all 267 transfer rows are in state
`done` — none in `draft`, none in `approved` — and the approver is set on
exactly ONE of the 267, the single `nrs19` row somebody drove through the
Odoo screen by hand. (`test19` 161, `jaizbankplc` 103, `gtb19` 2, `nrs19` 1;
`cadra19`, `nrs`, `lasg` and `gtb` nil.)

So the machinery is unused rather than load-bearing, and reusing it was the
cheaper-looking option. It was rejected on four measured grounds, none of
them aesthetic:

1. **It cannot express half the moves this register actually makes.**
   `from_location_id` and `to_location_id` are both `required=True` and
   `_check_locations` forbids them being equal. An asset that is NOWHERE
   cannot be the subject of a transfer at all — and that is not an edge
   case: 1,920 of `jaizbankplc`'s 4,164 assets (46%) and 358 of `nrs19`'s
   had no location when handoff 28 measured them. `POST /assets/<id>/move`
   already had to stop creating a transfer for those, and the endpoint
   comment there calls the transfer *paperwork* for exactly this reason.

2. **It cannot express a custody change at all.** Same two required columns,
   same constraint. `POST /assets/<id>/transfer-custody` says so in its own
   docstring: *"a pure custody change cannot be recorded in it at all."*
   Repurposing it for custody means making both location columns optional
   and dropping the constraint — that is not reuse, it is a different model
   wearing the old one's name and the old one's 267 rows.

3. **An asset manager can delete one.** `ir.model.access.csv` grants
   `group_asset_manager` 1,1,1,1 on `nrs.asset.transfer`, and `asset_id` is
   `ondelete='cascade'`, so a transfer dies with its asset. That is precisely
   why `nrs.asset.movement.transfer_id` is `ondelete='set null'` with a Char
   reference beside it. Report 27 §13.2 ruled the prerequisite for this
   handoff: *an approval recorded on a row an asset manager can delete is
   not an approval record.*

4. **Its `approved_by` is already published, meaning something else.**
   `myservice_workflow/models/sap_asset_events.py` puts `approved_by` and
   `approved_at` into the INT-09 payload SAP receives when a transfer
   completes. Changing what those columns mean is an integration-visible
   change to a live interface, made as a side effect of a UI feature.

The 267 existing `done` rows settle it. Under the alternative they would
become "requests" retroactively — 267 rows with no requester, no approver
and no premise, in the model an auditor is told to read for who authorised
what. Leaving `nrs.asset.transfer` untouched keeps them meaning exactly what
they have always meant.

**What the transfer BECOMES is the result.** When an approved request moves
an asset that had a location, this model creates the transfer document the
same way `/move` does — and fills in `approved_by`/`approved_date` with the
person who actually clicked. Those columns stop being always-null, and the
INT-09 payload starts carrying a true approver instead of a blank.

THE THREE THINGS THE HANDOFF MADE NON-NEGOTIABLE
------------------------------------------------
* **The append-only records are written on approval, never on request.** A
  request writes NOTHING to the asset. `nrs.asset.movement` and
  `nrs.asset.custody` rows appear when `action_approve` writes the asset and
  the recorders in `nrs.asset.write` see the change — the same recorders,
  underneath the same ORM, as every other writer. A row written when
  somebody merely ASKED would be a permanent record of a move that had not
  happened and might never happen, in the two tables whose whole value is
  that nobody can correct them.
* **A request carries who is being asked; an approval records who clicked.**
  `approver_id` and `approved_by_id` are two columns and are never the same
  one. Handoff 23 ruled it for disposals — the approver is the authenticated
  caller, never a field in the payload — and the reason is unchanged: a
  requester who can name the approver can forge one.
* **Self-approval is refused HERE, in the model.** Not by hiding a button.
  `_assert_may_decide` is called by `action_approve` and there is no path to
  the state change that goes round it, including `sudo()`. Report 30 found
  the same lesson when a disposed asset could be un-disposed through a route
  nobody had looked at.

WHAT SURVIVES A RESHAPING
-------------------------
NRS will reshape WHO may approve WHAT — by value, by category, by office.
That rule lives in `_eligible_approver_domain` and in the API's scope check,
and both are meant to be replaced. What must not change when it is replaced
is the RECORD: who asked, who approved, when, and what it was before. Those
are plain columns here, written once, and `write`/`unlink` refuse to touch a
request after it has been decided.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from ..approval_policy import (
    APPROVAL_KEY, EXEMPT_KEY, EXEMPT_REASONS, approval_required, set_command)
from .asset_custody import CUSTODY_REASON_KEY, CUSTODY_SOURCE_KEY
from .asset_event import EVENT_REASON_KEY, EVENT_SOURCE_KEY
from .asset_movement import (
    MOVEMENT_REASON_KEY,
    MOVEMENT_SOURCE_KEY,
    MOVEMENT_TRANSFER_KEY,
)

#: The lifecycle. `pending` is the only state from which anything can happen,
#: and the other three are terminal — there is no route back to `pending` and
#: no reversal, deliberately, for the reason handoff 30 gave when it refused
#: to build one for disposal: a decision that can be quietly retaken is not a
#: decision. Somebody who changes their mind raises a new request, which
#: leaves both records standing.
STATE_PENDING = 'pending'
STATE_APPROVED = 'approved'
STATE_REJECTED = 'rejected'
STATE_WITHDRAWN = 'withdrawn'
DECIDED_STATES = (STATE_APPROVED, STATE_REJECTED, STATE_WITHDRAWN)

#: The flag the transition methods set on themselves. `write` refuses without
#: it, exactly as the append-only models' `create` does, so the state machine
#: is enforced by the model and not by who holds which group.
TRANSITION_KEY = 'cadra_change_request_transition'

CHANGE_LOCATION = 'location'
CHANGE_CUSTODY = 'custody'


class NRSAssetChangeRequest(models.Model):
    _name = 'nrs.asset.change.request'
    _description = 'Asset Change Request (move / custody)'
    # `mail.activity.mixin` is what gives the approver an inbox without one
    # being invented. Handoff 35 §E asked for Odoo's own *somebody needs to
    # do something* mechanism by name. `nrs.asset` already carries the mixin
    # and `activity_ids` is already on its form, so the widget, the bell
    # counter and the Activities menu all work on day one; this is simply
    # the first first-party model in the repository to SCHEDULE one.
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        default=lambda self: _('New'), index=True)

    # `restrict`, NOT `cascade`. `nrs.asset.transfer.asset_id` is `cascade`
    # and that is one of the four reasons this is not that model: a record of
    # who authorised what must not be deletable by deleting its subject. It
    # matches the three append-only models, which all hold their asset with
    # `ondelete='restrict'` — so an asset with a request against it cannot be
    # deleted, and a test that needs to delete an asset must not have raised
    # one on it.
    asset_id = fields.Many2one(
        'nrs.asset', string='Asset', required=True, ondelete='restrict',
        index=True)
    asset_code = fields.Char(
        related='asset_id.asset_code', store=True, string='Asset Code')

    change_type = fields.Selection([
        (CHANGE_LOCATION, 'Move to a different location'),
        (CHANGE_CUSTODY, 'Transfer custody to a different person'),
    ], string='Change', required=True, index=True)

    # ── What is being asked for ──────────────────────────────────────

    # `set null`, NOT `restrict`, and the Char copies below are why — the
    # same pairing `nrs.asset.custody` and `nrs.asset.movement` use on their
    # from/to references, deliberately, so an append-only row never blocks a
    # deletion somebody is entitled to make.
    #
    # `restrict` here was wrong in two ways at once, both found by the
    # verification pass. It would have made `generic.location.unlink` do all
    # of handoff 28's careful work — refusing on disposed assets, appending a
    # `location_deleted` movement for every other — and then die on a foreign
    # key it knows nothing about, handing the user a raw `IntegrityError`
    # instead of Cadra's own words; the same for `hr.employee.unlink`. And it
    # made two branches of `_premise_check` unreachable: the database could
    # not produce a request whose destination had been deleted, while §D2 of
    # the report lists exactly that as a live reason a premise breaks.
    to_location_id = fields.Many2one(
        'generic.location', string='To Location', ondelete='set null')
    to_custodian_id = fields.Many2one(
        'hr.employee', string='To Custodian', ondelete='set null')
    reason = fields.Text(string='Reason')

    # ── The premise: what it was WHEN ASKED ──────────────────────────
    #
    # Recorded at request time rather than read from the asset at approval
    # time, and that is the whole of §D's second question. Without these
    # columns an approval means *"yes, move it to B"*; with them it means
    # *"yes, move it from A to B"*, and the difference is everything when
    # somebody else has moved it to C in the meantime. `_compute_premise`
    # compares them against the live asset and `action_approve` refuses on a
    # mismatch rather than applying an approval to a world that has changed.
    #
    # They are also what makes the record readable years later: *what it was
    # before* is one of the four things the handoff says must survive any
    # reshaping of the rule.

    from_location_id = fields.Many2one(
        'generic.location', string='From Location (when asked)',
        ondelete='set null')
    from_custodian_id = fields.Many2one(
        'hr.employee', string='From Custodian (when asked)',
        ondelete='set null')
    # Char copies, for the reason `nrs.asset.movement` keeps them: a location
    # can be renamed, re-parented or deleted, and an employee can be deleted
    # (`custodian_id` is ON DELETE SET NULL). Without these the premise could
    # be emptied of its content from outside the record.
    from_location_name = fields.Char(string='From Location (as recorded)')
    from_custodian_name = fields.Char(string='From Custodian (as recorded)')
    to_location_name = fields.Char(string='To Location (as recorded)')
    to_custodian_name = fields.Char(string='To Custodian (as recorded)')
    from_state = fields.Char(string='Asset Status (when asked)')

    # ── Who ──────────────────────────────────────────────────────────

    requested_by_id = fields.Many2one(
        'res.users', string='Requested By', required=True,
        ondelete='restrict', index=True)
    requested_by_name = fields.Char(string='Requested By (as recorded)')
    requested_at = fields.Datetime(
        string='Requested At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO IS BEING ASKED. Chosen by the requester in the dialog. This is a
    # nomination and nothing more: it is what puts the request in somebody's
    # queue and what the notification is addressed to. It does NOT confer the
    # right to approve and it does not withhold it — see
    # `_assert_may_decide`, where any eligible person may decide and the
    # requester may not, whoever was named.
    approver_id = fields.Many2one(
        'res.users', string='Approver Asked', required=True,
        ondelete='restrict', index=True)

    # WHO CLICKED. Written from `self.env.uid` by `action_approve` and by
    # nothing else, ever. A DIFFERENT COLUMN from `approver_id` on purpose
    # and by instruction: collapsing them would mean the record of who
    # authorised a move is a value the requester chose.
    approved_by_id = fields.Many2one(
        'res.users', string='Decided By', ondelete='restrict', readonly=True)
    approved_by_name = fields.Char(string='Decided By (as recorded)')
    decided_at = fields.Datetime(string='Decided At', readonly=True)
    decision_reason = fields.Text(string='Decision Reason')

    state = fields.Selection([
        (STATE_PENDING, 'Waiting for approval'),
        (STATE_APPROVED, 'Approved'),
        (STATE_REJECTED, 'Rejected'),
        (STATE_WITHDRAWN, 'Withdrawn'),
    ], string='Status', required=True, default=STATE_PENDING, index=True,
        tracking=True)

    # ── What it produced ─────────────────────────────────────────────
    #
    # All `set null`, and all with a Char beside them where the target is
    # deletable, for the reason `nrs.asset.movement.transfer_id` is: this
    # record must survive the deletion of anything it points at. The two
    # append-only rows are NOT deletable, so they need no Char twin — the
    # transfer is, and has one.

    movement_id = fields.Many2one(
        'nrs.asset.movement', string='Movement Recorded',
        ondelete='set null', readonly=True)
    custody_id = fields.Many2one(
        'nrs.asset.custody', string='Custody Link Recorded',
        ondelete='set null', readonly=True)
    transfer_id = fields.Many2one(
        'nrs.asset.transfer', string='Transfer Document',
        ondelete='set null', readonly=True)
    transfer_reference = fields.Char(
        string='Transfer Reference (as recorded)', readonly=True)

    # ── Is the premise still true? ───────────────────────────────────

    premise_holds = fields.Boolean(
        string='Still Applicable', compute='_compute_premise')
    premise_broken_reason = fields.Char(
        string='What Changed', compute='_compute_premise')

    @api.depends('state', 'asset_id.location_id', 'asset_id.custodian_id',
                 'asset_id.state', 'from_location_id', 'from_custodian_id',
                 'to_location_id', 'to_custodian_id')
    def _compute_premise(self):
        """Whether the world the request was raised in still holds.

        Computed and NOT stored, deliberately. A stored value would be a
        snapshot of the last time something happened to recompute it, and the
        thing that breaks a premise — somebody else moving the asset — is
        exactly the thing that happens without touching this record. An
        approver reading a stale `True` is the silent failure this whole
        field exists to prevent, so it is read fresh every time it is asked
        for, including inside `action_approve`.

        A decided request is not evaluated: its premise held or did not at
        the moment it was decided, and re-judging it against today's asset
        would make the history of a closed record change under the reader.
        """
        for r in self:
            if r.state != STATE_PENDING:
                r.premise_holds = True
                r.premise_broken_reason = False
                continue
            r.premise_holds, r.premise_broken_reason = r._premise_check()

    def _premise_check(self):
        """(holds, what_changed). The one statement of the rule.

        Called by the compute for display and by `action_approve` before it
        writes. One method, so a queue that shows a request as applicable and
        an approve that refuses it can never disagree.
        """
        self.ensure_one()
        asset = self.asset_id
        if not asset.exists():
            return False, _("The asset no longer exists.")
        # Disposed is terminal (handoff 30), and it is terminal for this too.
        # `nrs.asset._assert_disposed_is_terminal` would raise anyway when the
        # write landed — but it would raise AFTER the approver had clicked
        # Approve, with the model's words about a write they did not know they
        # were making. Refusing here says what actually changed.
        if asset.state == 'disposed':
            return False, _(
                "The asset has been disposed of since this was raised, and a "
                "disposed asset cannot be moved or change hands.")
        if asset.state != (self.from_state or asset.state):
            return False, _(
                "The asset's status was %(then)s when this was raised and is "
                "now %(now)s.",
                then=self.from_state, now=asset.state)
        if self.change_type == CHANGE_LOCATION:
            if asset.location_id.id != self.from_location_id.id:
                return False, _(
                    "The asset was at %(then)s when this was raised and is "
                    "now at %(now)s.",
                    then=self.from_location_name or _("no location"),
                    now=asset.location_id.display_name or _("no location"))
            if not self.to_location_id.exists():
                return False, _("The destination location has been deleted.")
            if asset.location_id.id == self.to_location_id.id:
                return False, _(
                    "The asset is already at %(where)s.",
                    where=self.to_location_id.display_name)
        else:
            if asset.custodian_id.id != self.from_custodian_id.id:
                return False, _(
                    "%(then)s held the asset when this was raised; "
                    "%(now)s holds it now.",
                    then=self.from_custodian_name or _("Nobody"),
                    now=asset.custodian_id.display_name or _("nobody"))
            if not self.to_custodian_id.exists():
                return False, _("The proposed custodian no longer exists.")
            if asset.custodian_id.id == self.to_custodian_id.id:
                return False, _(
                    "%(who)s already holds the asset.",
                    who=self.to_custodian_id.display_name)
        return True, False

    # ── One pending request per asset ────────────────────────────────

    def init(self):
        """A partial unique index — at most one PENDING request per asset.

        §D's first question: can two requests for the same asset exist? No,
        and the reason is that approving both is incoherent rather than
        merely untidy. Each request records the world it was raised in; if
        two are pending and the first is approved, the second's premise is
        broken by definition, so the second can only ever be refused. Letting
        it be raised at all is an interface that invites somebody to queue up
        work that cannot happen.

        A PARTIAL index, because the constraint is only on `pending`: an
        asset accumulates any number of approved, rejected and withdrawn
        requests over its life and that is the history.

        `models.Constraint` cannot express this — Odoo 19's replacement for
        `_sql_constraints` builds TABLE constraints, and a partial unique
        index is not one. So it is created here, in `init()`, which Odoo runs
        on install and on every upgrade. The route also checks and answers
        409 with the request that is in the way, because an index gives the
        user a `psycopg2.IntegrityError` and a route should give them the
        reference number of the thing blocking them.
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                nrs_asset_change_request_one_pending_per_asset
            ON nrs_asset_change_request (asset_id)
            WHERE state = 'pending'
        """)

    @api.constrains('approver_id', 'requested_by_id')
    def _check_approver_is_not_the_requester(self):
        """Nobody asks themselves.

        A Python constraint as well as the check in `action_approve`, because
        the two say different things at different moments and both are wanted:
        this refuses the NOMINATION at request time, so the dialog can tell
        somebody immediately that they cannot send it to themselves, and
        `_assert_may_decide` refuses the DECISION whoever was nominated.
        """
        for r in self:
            if r.approver_id.id == r.requested_by_id.id:
                raise ValidationError(_(
                    "A request cannot be sent to the person making it. "
                    "Choose somebody else to approve this change."))

    @api.constrains('change_type', 'to_location_id', 'to_custodian_id')
    def _check_change_is_complete(self):
        """A request must actually ask for something."""
        for r in self:
            if r.change_type == CHANGE_LOCATION and not r.to_location_id:
                raise ValidationError(_(
                    "A move request must name the location to move to."))
            if r.change_type == CHANGE_CUSTODY and not r.to_custodian_id:
                raise ValidationError(_(
                    "A custody request must name the person to transfer to."))

    # ── Who may decide ───────────────────────────────────────────────

    #: The group that grants `assets:write` — the one group on this system
    #: whose members *could have made the change themselves*, which is the
    #: whole of the owner's ruling on who may approve.
    APPROVER_GROUP = 'myservice_asset_register.group_asset_manager'

    @api.model
    def _users_group_field(self):
        """`res.users`' groups field, whose name Odoo 19 changed.

        `groups_id` became `group_ids` on 19, with `all_group_ids` computed
        beside it to include groups reached through `implied_ids`. The repo
        already pins this rename in five places (`scripts/bootstrap.py`,
        `myservice_api/migrations/19.0.3.2.0`, three test files) and this is
        the sixth; resolved from `_fields` rather than written as a literal,
        which is how the others do it.

        **Found by running the probe, not by reading.** The first draft of
        this method wrote `('groups_id', 'in', …)` from memory and would have
        raised `ValueError: Invalid field 'groups_id' in 'res.users'` on the
        first approver lookup on any tenant.
        """
        fields_ = self.env['res.users']._fields
        for name in ('all_group_ids', 'group_ids', 'groups_id'):
            if name in fields_:
                return name
        return 'groups_id'

    @api.model
    def _eligible_approver_domain(self):
        """Who could have made this change themselves — as a DOMAIN.

        **This is the rule NRS will replace**, and it is one method so that
        replacing it does not touch the record. Today it is the whole of the
        owner's ruling — *the approver is anyone who could have made the
        change themselves* — which on this system means the one group that
        grants `assets:write`. Tomorrow it may be by value, by category or by
        office, and the columns above will mean exactly the same thing.

        Used for LISTING candidates (the dialog's approver picker). The
        DECISION is `_may_decide`, which asks `has_group` instead: a domain
        and an implication can disagree, and the one that must be right is
        the one standing in front of the write.

        Archived users are excluded by the `res.users` default `active`
        domain, which is wanted: naming somebody who has left as the approver
        would produce a request nobody can see.
        """
        group = self.env.ref(self.APPROVER_GROUP, raise_if_not_found=False)
        if not group:
            # No group means nobody is eligible, not everybody. The same
            # direction as `approval_policy.REQUIRED_WHEN_UNSET`, and for the
            # same reason: the failure that has no symptom is the one where
            # an unconfigured tenant waves changes through.
            return [('id', '=', False)]
        return [(self._users_group_field(), 'in', group.ids)]

    @api.model
    def eligible_approvers(self, exclude_user=None, query=None, limit=20):
        """The people a requester may ask. Read by the API's picker.

        `exclude_user` is the requester, who is never in their own list —
        offering somebody a choice the model will refuse is the *"answer that
        looks like an answer"* this codebase rejects everywhere else.
        """
        domain = list(self._eligible_approver_domain())
        if exclude_user:
            domain.append(('id', '!=', exclude_user.id))
        if query:
            domain.append(('name', 'ilike', query))
        return self.env['res.users'].sudo().search(
            domain, limit=limit, order='name')

    def _may_decide(self, user):
        """Whether `user` may decide THIS request. Read by the API too.

        `has_group`, not the domain above, because `has_group` follows
        `implied_ids`: an Asset Manager reached through implication from some
        future group is eligible, and a domain on the stored relation would
        quietly say no. The scope map in `myservice_api/controllers/utils.py`
        makes the same choice for the same reason.
        """
        self.ensure_one()
        if user.id == self.requested_by_id.id:
            return False
        if user._is_superuser() or user._is_admin():
            # An Odoo system administrator can execute arbitrary server
            # actions and is omnipotent by construction, so withholding this
            # from them would be theatre — the same ruling, in the same
            # words, that `GROUP_SCOPES` makes about `base.group_system`.
            # The line above still applies: not their own request.
            return True
        return user.has_group(self.APPROVER_GROUP)

    def _assert_may_decide(self, user):
        """Raise unless `user` may decide this. THE model-level refusal.

        Handoff 35 §B: *self-approval is refused in the model, not hidden in
        the app.* A hidden button is a door closed on one screen — report 30
        found a disposed asset could be un-disposed through a route nobody
        had looked at, and report 29 found a control that was correct on the
        page and wrong everywhere else. So this raises, under `sudo()`, from
        the shell, from the Odoo button and from the route alike.
        """
        self.ensure_one()
        if user.id == self.requested_by_id.id:
            raise UserError(_(
                "%(who)s raised this request and cannot approve it. The "
                "point of an approval is that a second person agrees.",
                who=user.display_name))
        if not self._may_decide(user):
            raise UserError(_(
                "%(who)s is not able to approve a change of this kind. An "
                "approver must be somebody who could have made the change "
                "themselves.", who=user.display_name))

    # ── The state machine ────────────────────────────────────────────

    def action_approve(self, decision_reason=None):
        """Agree, and make the change happen. The ONLY writer of the asset.

        Everything that could refuse runs BEFORE anything is written, because
        of what handoff 28 did on `/move` and handoff 31 wrote into
        `CLAUDE.md`: a refusal returned from a route does not roll the
        transaction back, only an exception does, and a route that validates
        after it has created something leaves that something behind. Here the
        refusals raise, so they do roll back — but the order is kept anyway,
        so that the failure mode does not depend on the caller's error
        handling.
        """
        self.ensure_one()
        if self.state != STATE_PENDING:
            raise UserError(self._not_pending_message())
        self._assert_may_decide(self.env.user)
        holds, changed = self._premise_check()
        if not holds:
            # §D: *a request whose premise no longer holds must not be
            # approvable in silence.* It says what changed, in the words of
            # the thing that changed, rather than failing on a constraint
            # deeper down with a message about a column.
            raise UserError(_(
                "This request can no longer be approved. %(what)s Raise a "
                "new request if the change is still wanted.", what=changed))

        asset = self.asset_id
        approver = self.env.user
        now = fields.Datetime.now()

        # The transfer DOCUMENT, where there is one to make. Built before the
        # write, the same way and for the same reason `/move` builds it — and
        # only when the asset has a location to be transferred FROM, because
        # `nrs.asset.transfer` requires both ends and an asset that is
        # nowhere is PLACED, not transferred.
        #
        # This is where the old machinery finally earns its keep: the
        # document is created already `done` AND already approved, by the
        # person who actually clicked. `approved_by` has been null on 266 of
        # the 267 transfer rows on this machine; from here it is the real
        # approver, and the INT-09 payload SAP receives carries a true one.
        transfer = self.env['nrs.asset.transfer']
        if self.change_type == CHANGE_LOCATION and self.from_location_id:
            transfer = transfer.sudo().create({
                'asset_id': asset.id,
                'from_location_id': self.from_location_id.id,
                'to_location_id': self.to_location_id.id,
                'from_custodian_id': asset.custodian_id.id or False,
                'to_custodian_id': asset.custodian_id.id or False,
                'transfer_date': fields.Date.context_today(self),
                'reason': self.reason or '',
                'state': 'done',
                'approved_by': approver.id,
                'approved_date': now,
            })

        ctx = {
            APPROVAL_KEY: self.id,
            CUSTODY_SOURCE_KEY: 'approval',
            CUSTODY_REASON_KEY: self.reason or False,
            MOVEMENT_SOURCE_KEY: 'approval',
            MOVEMENT_REASON_KEY: self.reason or False,
            EVENT_SOURCE_KEY: 'approval',
            EVENT_REASON_KEY: self.reason or False,
        }
        if transfer:
            ctx[MOVEMENT_TRANSFER_KEY] = transfer.id

        if self.change_type == CHANGE_LOCATION:
            vals = {'location_id': self.to_location_id.id}
        else:
            vals = {'custodian_id': self.to_custodian_id.id}

        # THE DECISION IS STAMPED FIRST, BEFORE THE ASSET IS WRITTEN, and the
        # order is a security property rather than a style.
        #
        # The first cut stamped it afterwards, which forced
        # `nrs.asset._approval_clears` to accept a request that was still
        # `pending` — and that was a two-call bypass of this entire feature.
        # Anybody holding `group_asset_manager` could raise a request
        # properly, then write `location_id` directly over `call_kw` with
        # `cadra_approval_id` naming their own pending request: the gate
        # found a request for the right asset and the right destination, let
        # the write through, and the asset moved with nobody having agreed.
        # The REST API was not a way in; the Odoo web client was — which is
        # the argument this handoff makes for putting the gate on the model
        # in the first place, turned back on itself.
        #
        # Stamping first means the clearance can demand `approved` WITH a
        # decider, which only this method can produce. It is safe because
        # this is one transaction: if the write below raises — a disposed
        # asset, a broken constraint — the stamp rolls back with it and the
        # request is still pending. Found by the verification pass, by
        # writing the test for "nothing is written on request" and watching
        # it fail.
        self._transition({
            'state': STATE_APPROVED,
            'approved_by_id': approver.id,
            'approved_by_name': approver.display_name,
            'decided_at': now,
            'decision_reason': decision_reason or False,
        })

        # Everything append-only about this change is recorded by
        # `nrs.asset.write`, underneath, exactly as it is for every other
        # writer — not here. That is §B's first non-negotiable: the rows
        # appear now, at approval, and there was never a row for the request.
        asset.with_context(**ctx).write(vals)

        movement = (asset.movement_ids.sorted('id')[-1:]
                    if self.change_type == CHANGE_LOCATION
                    else self.env['nrs.asset.movement'])
        custody = (asset.custody_ids.sorted('id')[-1:]
                   if self.change_type == CHANGE_CUSTODY
                   else self.env['nrs.asset.custody'])

        # The second half of the stamp: what the write above produced. Only
        # knowable afterwards, which is why this is two transitions and not
        # one. `write` lets it through on an already-decided request because
        # `_transition` carries the context flag — see `write`.
        self._transition({
            'movement_id': movement.id or False,
            'custody_id': custody.id or False,
            'transfer_id': transfer.id or False,
            'transfer_reference': transfer.name or False,
        })
        self._close_activity()
        self._tell_the_requester(_(
            "Approved by %(who)s.", who=approver.display_name),
            decision_reason)
        return True

    def action_reject(self, decision_reason=None):
        """Refuse, with a reason, and tell the person who asked.

        The reason is REQUIRED. A rejection without one leaves the requester
        with a dead request and nothing to act on, and they will simply raise
        it again — which is the shape of control that produces noise and no
        information. `/condemn`, `/mark-missing` and `/mark-found` all require
        a reason for the same argument (handoffs 30 and 31).
        """
        self.ensure_one()
        if self.state != STATE_PENDING:
            raise UserError(self._not_pending_message())
        self._assert_may_decide(self.env.user)
        reason = (decision_reason or '').strip()
        if not reason:
            raise UserError(_(
                "Say why this is being rejected. The person who asked sees "
                "the reason, and a rejection without one tells them nothing "
                "they can act on."))
        decider = self.env.user
        self._transition({
            'state': STATE_REJECTED,
            'approved_by_id': decider.id,
            'approved_by_name': decider.display_name,
            'decided_at': fields.Datetime.now(),
            'decision_reason': reason,
        })
        self._close_activity()
        self._tell_the_requester(_(
            "Rejected by %(who)s.", who=decider.display_name), reason)
        return True

    def action_withdraw(self, decision_reason=None):
        """The requester changes their mind. §D's third question.

        Only the requester, and only while pending. It is deliberately NOT
        the same act as a rejection and does not share its column meaning:
        `approved_by_id` records the requester here because they are who
        closed it, and `state` says it was withdrawn rather than refused. An
        approver who wants it gone rejects it, which requires a reason; a
        requester withdrawing their own request owes nobody one.
        """
        self.ensure_one()
        if self.state != STATE_PENDING:
            raise UserError(self._not_pending_message())
        if self.env.user.id != self.requested_by_id.id \
                and not self.env.user._is_admin():
            raise UserError(_(
                "Only %(who)s, who raised this request, can withdraw it. "
                "Reject it instead if you are deciding on it.",
                who=self.requested_by_id.display_name))
        actor = self.env.user
        self._transition({
            'state': STATE_WITHDRAWN,
            'approved_by_id': actor.id,
            'approved_by_name': actor.display_name,
            'decided_at': fields.Datetime.now(),
            'decision_reason': (decision_reason or '').strip() or False,
        })
        self._close_activity()
        return True

    def _not_pending_message(self):
        self.ensure_one()
        return _(
            "This request was already %(state)s%(by)s. A decision is taken "
            "once; raise a new request if the change is still wanted.",
            state=dict(self._fields['state'].selection).get(
                self.state, self.state).lower(),
            by=(_(" by %s", self.approved_by_name)
                if self.approved_by_name else ""))

    def _transition(self, vals):
        """The only write to a request after it is created."""
        return self.with_context(**{TRANSITION_KEY: True}).write(vals)

    # ── Notification: Odoo's own, not a new one ──────────────────────

    def _activity_type(self):
        """`mail.activity.type` for *somebody needs to do something*.

        `mail.mail_activity_data_todo` is core Odoo's generic To-Do and ships
        with every database that has `mail` installed, which is every tenant
        here. Resolved with `raise_if_not_found=False` and falling back to no
        type, because an activity with no type still appears in the inbox and
        still counts in the bell — and a NOTIFICATION failing must never take
        the request down with it.
        """
        return self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)

    def _schedule_activity(self):
        """Put it in the named approver's Odoo inbox.

        Handoff 35 §E: *Odoo has a mechanism for somebody needs to do
        something and it gives an inbox for free; use it rather than
        inventing one.* This is `mail.activity` through `activity_schedule`,
        and this is the first first-party model in the repository to call it
        — `mail.activity.mixin` was already on seven models and on
        `nrs.asset`'s own form, and nothing had ever scheduled one.

        **The activity is the doorbell, never the record.** `asset_custody.py`
        says why in its own docstring: the chain used to live in
        `mail.thread` tracking values, which a user with the right groups can
        delete. Everything that matters is in the columns above; deleting
        every activity in the database loses a notification and no evidence.

        Wrapped, for the reason `sap_asset_events.py` and
        `workflow_dispatch_log.py` wrap their `message_post` calls: a
        notification that fails must not roll back the request it is
        announcing. A swallowed exception is a defect everywhere else in this
        codebase (handoff 15 classified 50 of them), so it is LOGGED rather
        than dropped, and the API tells the caller whether the doorbell rang.
        """
        self.ensure_one()
        try:
            activity_type = self._activity_type()
            self.sudo().activity_schedule(
                act_type_xmlid='mail.mail_activity_data_todo'
                if activity_type else None,
                user_id=self.approver_id.id,
                summary=self._activity_summary(),
                note=self._activity_note())
            return True
        except Exception:                      # noqa: BLE001 — see docstring
            import logging
            logging.getLogger(__name__).exception(
                "Could not schedule the approval activity for %s (asset %s, "
                "approver %s). The request itself is unaffected and is "
                "waiting in the queue; the approver has not been notified.",
                self.name, self.asset_id.id, self.approver_id.id)
            return False

    def _activity_summary(self):
        self.ensure_one()
        if self.change_type == CHANGE_LOCATION:
            return _("Approve move: %(asset)s", asset=self.asset_id.name)
        return _("Approve custody transfer: %(asset)s",
                 asset=self.asset_id.name)

    def _activity_note(self):
        self.ensure_one()
        if self.change_type == CHANGE_LOCATION:
            body = _(
                "%(who)s asks to move <b>%(asset)s</b> from %(frm)s to "
                "<b>%(to)s</b>.",
                who=self.requested_by_name or self.requested_by_id.display_name,
                asset=self.asset_id.display_name,
                frm=self.from_location_name or _("no location"),
                to=self.to_location_name or self.to_location_id.display_name)
        else:
            body = _(
                "%(who)s asks to transfer custody of <b>%(asset)s</b> from "
                "%(frm)s to <b>%(to)s</b>.",
                who=self.requested_by_name or self.requested_by_id.display_name,
                asset=self.asset_id.display_name,
                frm=self.from_custodian_name or _("nobody"),
                to=self.to_custodian_name or self.to_custodian_id.display_name)
        if self.reason:
            body += _("<br/>Reason given: %(why)s", why=self.reason)
        return body

    def _close_activity(self):
        """Take it out of the approver's inbox once it is decided.

        A queue that still shows a decided request is a queue people stop
        trusting, and an activity nobody can clear is worse than no activity.
        Unlinked rather than `action_done`, because `activity_schedule` may
        have failed (see above) and `action_feedback` on an empty set is a
        no-op either way.
        """
        self.ensure_one()
        try:
            self.sudo().activity_ids.unlink()
        except Exception:                      # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "Could not clear the approval activity for %s.", self.name)

    def _tell_the_requester(self, headline, reason=None):
        """§D's fourth question: *the requester finds out — the same way the
        approver found out.*

        `message_post` with the requester's partner in `partner_ids`, which
        lands in their Odoo Inbox. Not an activity: an activity means *you
        must do something* and a decided request asks nothing of them. The
        Cadra app reads their own requests from
        `GET /api/v1/approvals?mine=1`, which is the answer for a user who
        never opens Odoo.
        """
        self.ensure_one()
        partner = self.requested_by_id.partner_id
        if not partner:
            return False
        body = "<b>%s</b> %s" % (headline, self._activity_summary())
        if reason:
            body += _("<br/>Reason: %(why)s", why=reason)
        try:
            self.sudo().message_post(
                body=body, partner_ids=[partner.id],
                message_type='comment', subtype_xmlid='mail.mt_note')
            return True
        except Exception:                      # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "Could not notify %s that %s was decided.",
                partner.display_name, self.name)
            return False

    # ── Creation, and the two guards ─────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """Stamp the requester from the acting user, never from the payload.

        The same rule, for the same reason, as `approve-disposal`'s approver
        (handoff 23) and `is_test_fixture`'s label (handoff 26): a party that
        can name itself as somebody else can forge the record. `requested_by_id`
        is therefore OVERWRITTEN rather than defaulted — a caller supplying
        it does not get a validation error, it gets ignored, because there is
        no legitimate reason to send it and a 400 would only teach an
        integration to keep sending it without the value.
        """
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'nrs.asset.change.request') or '/'
            vals['requested_by_id'] = self.env.uid
            vals['requested_by_name'] = self.env.user.display_name
            vals.setdefault('requested_at', fields.Datetime.now())
            # FORCED, not defaulted. `setdefault` let a caller-supplied
            # `state` survive, so a request could be created already
            # `approved` — half of the bypass described in `action_approve`.
            # A request is born pending; there is no other way to make one.
            vals['state'] = STATE_PENDING
            # Decided-state columns are not settable at creation. A request
            # that arrives already approved is the forgery this model exists
            # to prevent.
            for protected in ('approved_by_id', 'approved_by_name',
                              'decided_at', 'movement_id', 'custody_id',
                              'transfer_id', 'transfer_reference'):
                vals.pop(protected, None)
        records = super().create(vals_list)
        for record in records:
            record._stamp_premise()
            record._schedule_activity()
        return records

    def _stamp_premise(self):
        """Record what the asset was, at the instant the request was raised.

        Read from the ASSET here rather than accepted from the caller, for
        the reason `requested_by_id` is: a premise the requester can write is
        a premise the requester can choose, and the whole use of these
        columns is to catch the case where what they believed is no longer
        true.
        """
        self.ensure_one()
        asset = self.asset_id
        self.with_context(**{TRANSITION_KEY: True}).write({
            'from_location_id': asset.location_id.id or False,
            'from_location_name': asset.location_id.display_name or False,
            'from_custodian_id': asset.custodian_id.id or False,
            'from_custodian_name': asset.custodian_id.display_name or False,
            'to_location_name': self.to_location_id.display_name or False,
            'to_custodian_name': self.to_custodian_id.display_name or False,
            'from_state': asset.state or False,
        })

    def write(self, vals):
        """A decided request is frozen; a pending one moves only by action.

        NOT the append-only mixin, and the difference is deliberate. That
        mixin refuses EVERY write unconditionally, which is right for
        `nrs.asset.custody`, `nrs.asset.movement` and `nrs.asset.event`
        because a row there is a completed fact the moment it exists. A
        request is not: it legitimately moves from `pending` to one of three
        terminal states, so it needs a state machine rather than a wall.

        What it takes from the mixin is the shape of the enforcement — the
        transition methods set a context flag on themselves and `write`
        refuses without it, so the state machine is enforced by the MODEL and
        not by who holds which group. And a request that has been decided is
        closed to everything, including `sudo()`: what it recorded is who
        authorised a change to a government asset register.

        Adopting the mixin here would also have failed
        `test_append_only_mixin.test_nothing_but_these_three_adopts_the_guard`
        — correctly, since this is not a fourth append-only record.
        """
        if self.env.context.get(TRANSITION_KEY):
            return super().write(vals)
        # `message_ids`/`activity_ids` and the follower fields are written by
        # `mail.thread` itself whenever anything is posted on the record —
        # including by the notification of its own decision. Refusing those
        # would make the record unable to carry its own chatter.
        mail_fields = {
            'message_ids', 'message_follower_ids', 'message_main_attachment_id',
            'activity_ids', 'message_is_follower', 'message_partner_ids',
            'website_message_ids', 'message_has_error', 'message_needaction',
            'access_token',
        }
        if vals and set(vals) <= mail_fields:
            return super().write(vals)
        decided = self.filtered(lambda r: r.state in DECIDED_STATES)
        if decided:
            raise UserError(_(
                "%(refs)s has already been decided and cannot be changed. "
                "The record of who asked, who decided and what the asset was "
                "at the time is what an approval IS; a decision that can be "
                "edited afterwards authorises nothing.",
                refs=", ".join(decided.mapped('name'))))
        raise UserError(_(
            "A pending request is changed by deciding it — approve it, "
            "reject it, or withdraw it. Its fields are the record of what "
            "was asked and are not edited in place."))

    def unlink(self):
        """Never. A request is a record of who authorised what.

        Exactly the rule the three append-only models carry, and here for the
        exact reason report 27 §13.2 gave when it made this handoff wait for
        handoff 28: *an approval recorded on a row an asset manager can
        delete is not an approval record.* `nrs.asset.transfer` IS deletable
        by an asset manager, which is the third of the four reasons this is
        not that model.

        A request raised by mistake is WITHDRAWN, which is a state and leaves
        the record standing.
        """
        raise UserError(_(
            "An approval request cannot be deleted. It records who asked for "
            "a change to the asset register, who decided it and what the "
            "asset was at the time. Withdraw a request raised in error — "
            "that keeps the record and takes it out of the queue."))

    # ── What the rest of the system asks this model ──────────────────

    @api.model
    def approval_is_required(self):
        """Whether this tenant needs a second person. One statement of it."""
        return approval_required(self.env)

    @api.model
    def set_switch_command(self):
        """The command an administrator runs, for printing inside refusals."""
        return set_command(self.env.cr.dbname)

    @api.model
    def pending_for(self, user=None):
        """What is waiting on this person.

        Defaults to requests NAMED to them, which is what *"what is waiting
        on me"* means to the person asking it. Anyone eligible may approve
        anything (`_may_decide`), so the queue screen also offers the whole
        pending list — but a queue that defaults to every pending request in
        the tenant is a queue nobody treats as theirs.
        """
        user = user or self.env.user
        return self.search([('state', '=', STATE_PENDING),
                            ('approver_id', '=', user.id)])

    @api.model
    def pending_for_asset(self, asset):
        """The request in the way, if there is one. Used for the 409 and for
        the banner on the asset page — §E: *somebody opening an asset should
        not have to guess why the Move button is behaving differently.*"""
        return self.search([('asset_id', '=', asset.id),
                            ('state', '=', STATE_PENDING)], limit=1)
