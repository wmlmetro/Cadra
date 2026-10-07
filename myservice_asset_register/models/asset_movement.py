from odoo import models, fields, api, _
from odoo.exceptions import UserError

# The context key a caller sets to say WHERE a change of location came from.
# Anything that does not set it lands on `direct` — the Odoo form, an import,
# a shell session — exactly as `asset_custody.CUSTODY_SOURCE_KEY` does.
MOVEMENT_SOURCE_KEY = 'cadra_movement_source'

# The reason the caller gave, when it gave one. In the context for the reason
# custody's is: an ORM write carrying a move has nowhere to put a sentence.
MOVEMENT_REASON_KEY = 'cadra_movement_reason'

# The `nrs.asset.transfer` this move was the execution of, WHEN THERE IS ONE.
# `POST /assets/<id>/move` and `nrs.asset.transfer.action_complete` set it;
# nothing else does, because a move is not always a transfer.
MOVEMENT_TRANSFER_KEY = 'cadra_movement_transfer_id'

# The flag `_record` sets on itself; `create` refuses without it.
MOVEMENT_APPEND_KEY = 'cadra_movement_append'

# The sources a CALLER may declare through the context. The others —
# `test`, `tracking_backfill`, `location_deleted` — say something about the
# evidence itself and are never taken from the context: see `_resolve_source`.
_CONTEXT_SOURCES = ('api_move', 'api_write', 'transfer', 'approval',
                    'direct')


# Literal inside the function, translated at the call — see
# `asset_custody._append_only_message` for why both halves of that matter.
def _append_only_message():
    return _(
        "The record of where an asset has been is append-only. A movement "
        "cannot be edited or deleted once written — not through the "
        "interface, not over the API, and not as an administrator with "
        "sudo. Move the asset again instead; the history is the evidence."
    )


def _no_hand_written_movements_message():
    return _(
        "A movement record cannot be created directly. One is written only "
        "as a side effect of an asset's location actually changing, so that "
        "the record says what happened rather than what somebody typed. "
        "Change the asset's location instead."
    )


class NRSAssetMovement(models.Model):
    """One change of an asset's location. Append-only, as custody is.

    Handoff 27 measured what the system held about a move NRS had watched
    being made: on `nrs19`, 1,146 tracked changes of `location_id` and ONE
    `nrs.asset.transfer` row. Only `POST /assets/<id>/move` and a completed
    transfer wrote a row at all; PATCH, the Odoo form and the importer left a
    chatter line and nothing else, deletable by anyone able to edit the
    asset. And the row, where there was one, was worse than nothing in one
    specific way — it LOOKS like a record, and it is editable, deletable,
    cascade-deleted with the asset, holds a date rather than a time and has
    no field for who moved the thing. A reader who finds one trusts it.

    **This is the FACT that the asset moved. `nrs.asset.transfer` is a PROCESS
    DOCUMENT** — draft, approved, done, an approver. They are different
    things and this model does not replace that one: a move is not always a
    transfer, so `transfer_id` is set where one exists and empty where it
    does not, and nothing here invents a transfer for a move that had none.

    Written by `nrs.asset.write` and `nrs.asset.create`, where every writer of
    `location_id` passes — not by any route. Handoff 14 was told
    `custodian_id` had one writer and found six; the lesson is recorded at
    `nrs.asset.write` and applied here without being re-learnt.

    `write` and `unlink` are guarded on the model and not by ACL, for the
    reason `nrs.asset.custody` gives: an ACL is configuration. They raise
    unconditionally, so they hold under `sudo()`. **`create` is weaker, and
    this docstring's first draft did not say so:** it refuses without a
    context flag, and a context is something an RPC caller supplies. What
    actually stops a hand-written row is that flag AND the ACL, which grants
    `create` to nobody (`_record` writes under `sudo()`). Two locks, one of
    them configuration. Custody is the same and says otherwise.

    **What this does not defend against**, said here because a guarantee
    whose edge is not stated gets quoted past it: it is Python. There is no
    database trigger, so somebody with direct SQL access is not stopped; and
    a change made to `nrs_asset.location_id` BY the database — a raw
    `UPDATE`, or the `SET NULL` the foreign key performs when a location is
    deleted — never passes `nrs.asset.write` and is not recorded. The second
    of those is closed separately: see `GenericLocation.unlink` below.
    """

    _name = 'nrs.asset.movement'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'Asset Movement Record'
    # Chronological; `id` breaks ties inside one transaction.
    _order = 'moved_at, id'

    asset_id = fields.Many2one(
        'nrs.asset', string='Asset', required=True, index=True,
        # NOT cascade, for custody's reason: deleting the asset would erase
        # where it had been, which is the defect this model exists to remove.
        # `nrs.asset.transfer` cascades, and that is half of why a transfer
        # row was never evidence.
        ondelete='restrict')

    from_location_id = fields.Many2one(
        'generic.location', string='From Location', ondelete='set null')
    to_location_id = fields.Many2one(
        'generic.location', string='To Location', ondelete='set null')

    # The locations AS THEY READ AT THE TIME — the full path, not the leaf.
    # A location can be renamed, re-parented or deleted; without these an
    # append-only row could still be emptied of its content from outside.
    from_location_name = fields.Char(string='From Location (as recorded)')
    to_location_name = fields.Char(string='To Location (as recorded)')

    moved_at = fields.Datetime(
        string='Moved At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO MOVED IT. `nrs.asset.transfer` has no such field at all: its
    # `create_uid` is whoever raised the paperwork.
    moved_by_id = fields.Many2one(
        'res.users', string='Moved By', ondelete='set null')
    moved_by_name = fields.Char(string='Moved By (as recorded)')

    reason = fields.Text(string='Reason')

    # The process document this move executed, where there was one. `set
    # null`, because a transfer row is deletable by an asset manager and this
    # record must survive that — which is what `transfer_reference` is for.
    transfer_id = fields.Many2one(
        'nrs.asset.transfer', string='Transfer', ondelete='set null',
        index=True)
    transfer_reference = fields.Char(string='Transfer Reference (as recorded)')

    source = fields.Selection([
        ('api_move', 'API — move'),
        ('api_write', 'API — asset create or update'),
        ('transfer', 'Asset transfer completion'),
        # Handoff 35. A move a second person agreed to. It is a separate
        # label from `api_move` rather than a flag on it, because the
        # question an auditor asks is not *which endpoint wrote this* but
        # *did anybody else agree* — and the answer has to be legible in the
        # movement row itself, not only by following `nrs.asset.change.request`.
        ('approval', 'Approved change request'),
        ('direct', 'Direct write (Odoo UI, import or script)'),
        ('location_deleted', 'The location was deleted'),
        # Nothing writes this today. Handoff 28 ruled that location is NOT
        # backfilled from chatter alongside the model, and that a backfill
        # would be ruled on separately. The value is here so that the
        # property "a reconstruction says so" exists AT THE SOURCE before any
        # reconstruction does: a backfill added later has a label waiting for
        # it, rather than a reason to borrow one.
        ('tracking_backfill', 'Reconstructed from chatter tracking'),
        ('test', 'Written by the automated test suite'),
    ], string='Source', required=True, default='direct', index=True)

    # ── Append-only ───────────────────────────────────────────────────
    #
    # The guard — `create`, `write`, `unlink` and `_resolve_source` — is
    # `nrs.asset.append.only.mixin` since handoff 31. This model's own copy
    # was the CORRECT one of the two: it refused a context-claimed `test`,
    # and custody's did not. See the note in `asset_custody.py`.
    _append_key = MOVEMENT_APPEND_KEY
    _source_key = MOVEMENT_SOURCE_KEY
    _context_sources = _CONTEXT_SOURCES

    def _append_only_message(self):
        return _append_only_message()

    def _no_hand_written_rows_message(self):
        return _no_hand_written_movements_message()

    # ── When the record began ─────────────────────────────────────────

    @api.model
    def recording_began_at(self):
        """The instant of the oldest row on THIS database, or None.

        Measured, not declared — a constant in the source would be wrong on
        every server deployed after the day it was typed. It is when the
        first movement was recorded here, which is on or after the day the
        recorder was installed; a location an asset held before that has no
        record of how it came to be there, and the asset history says so.
        """
        self.env.cr.execute("SELECT min(create_date) FROM nrs_asset_movement")
        return self.env.cr.fetchone()[0]

    # ── The one way a row is written ──────────────────────────────────

    @api.model
    def _record(self, asset, from_location, to_location, *,
                reason=None, moved_at=None, moved_by=None, source=None,
                transfer=None):
        """Append one movement. The only way a row is ever written.

        `moved_by` defaults to the acting user, which is who made the write
        and therefore who moved it as far as this system can know. It is
        never read from a `create_uid` that means something else.
        """
        user = moved_by if moved_by is not None else self.env.user
        source = self._resolve_source(source, user)
        if transfer is None:
            transfer_id = self.env.context.get(MOVEMENT_TRANSFER_KEY)
            transfer = self.env['nrs.asset.transfer'].sudo().browse(
                transfer_id).exists() if transfer_id else None
        # The link is only as good as the check on it. The id arrives in the
        # context, which a caller controls, and the history shows the linked
        # document's APPROVER inside an append-only event — so a transfer
        # belonging to another asset, or one that names a different
        # destination, would let somebody borrow an approval for a move it
        # never covered. NRS have asked for approvals on moves; this is the
        # forgery path to one, closed before there is anything to forge.
        if transfer and (transfer.asset_id != asset
                         or transfer.to_location_id != to_location):
            transfer = None
        if source == 'transfer' and not transfer:
            source = 'direct'
        vals = {
            'asset_id': asset.id,
            'from_location_id': from_location.id if from_location else False,
            'to_location_id': to_location.id if to_location else False,
            'from_location_name': (
                from_location.display_name if from_location else False),
            'to_location_name': (
                to_location.display_name if to_location else False),
            'moved_at': moved_at or fields.Datetime.now(),
            'moved_by_id': user.id if user else False,
            'moved_by_name': user.name if user else False,
            'reason': reason or False,
            'transfer_id': transfer.id if transfer else False,
            'transfer_reference': transfer.name if transfer else False,
            'source': source,
        }
        return self.sudo().with_context(
            **{MOVEMENT_APPEND_KEY: True}).create(vals)


class GenericLocation(models.Model):
    """Deleting a location moves every asset in it to nowhere. Say so.

    `nrs_asset.location_id` is `ON DELETE SET NULL`, and
    `generic_location.parent_id` is `ON DELETE CASCADE`. So deleting a
    building empties `location_id` on every asset in it AND in every floor
    and room beneath it — done by the database, in one statement, with no
    ORM write. No `nrs.asset.write` runs, so the recorder never sees it; no
    tracking value is written either, so not even the chatter says it
    happened. The asset simply stops being anywhere, and the last movement
    on its record still says it is in a room that no longer exists.

    Found by reading the foreign key rather than the model (handoff 28): the
    handoff listed the writers of `location_id` and the database was not on
    the list. It is the one writer no search of the Python could have found.
    """
    _inherit = 'generic.location'

    def unlink(self):
        # `child_of` and not `self`: the cascade takes the descendants
        # without the ORM ever calling `unlink` on them.
        doomed = self.sudo().with_context(active_test=False).search(
            [('id', 'child_of', self.ids)])
        # `cadra_candidates`: a receipt candidate is orphaned by this delete
        # too (handoff 57 hides candidates from searches by default).
        assets = self.env['nrs.asset'].sudo().with_context(
            active_test=False, cadra_candidates=True).search(
                [('location_id', 'in', doomed.ids)])
        # DISPOSED IS TERMINAL, and this is a door `nrs.asset.write` cannot
        # see. The rule that a disposed asset is not moved lives in that
        # method (handoff 30) — and this delete never calls it: the database
        # empties `location_id` itself. So deleting a room would have moved
        # every disposed asset in it to nowhere, and the page that says "its
        # record keeps the location it was disposed of from" would have been
        # wrong. Found by the verification pass, which asked whether the rule
        # held "through any door" and went looking for one. Refused outright,
        # before anything is recorded; a location can be archived instead.
        disposed = assets.filtered(lambda a: a.state == 'disposed')
        if disposed:
            raise UserError(_(
                "%(count)s disposed asset(s) keep a location being deleted as "
                "the place they were disposed of from (%(first)s%(more)s), "
                "and a disposed asset's record cannot be changed. Archive the "
                "location instead of deleting it.",
                count=len(disposed), first=disposed[0].display_name,
                more=_(' and others') if len(disposed) > 1 else ''))
        Movement = self.env['nrs.asset.movement']
        nowhere = self.env['generic.location']
        # BEFORE the delete, while the names can still be read.
        # In a SAVEPOINT. The rows are written before `super()` has checked
        # anything, and a refusal that raises in Python — an access error, an
        # `@api.ondelete` — does not abort the cursor. A caller that catches
        # it would otherwise keep PERMANENT rows saying a location was
        # deleted that is still there, in a table that refuses correction.
        with self.env.cr.savepoint():
            for asset in assets:
                Movement._record(
                    asset, asset.location_id, nowhere,
                    source='location_deleted',
                    reason=_("The location was deleted."))
            return super().unlink()
