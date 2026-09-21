from odoo import models, api, _
from odoo.exceptions import UserError


class NRSAssetAppendOnlyMixin(models.AbstractModel):
    """The append-only guard, written once.

    `nrs.asset.custody` and `nrs.asset.movement` each carry their own copy of
    what is below, and the copies have already disagreed: custody was written
    with a `source` any caller could claim through the context, movement was
    copied from it in handoff 28 WITHOUT that hole, and the original kept it
    until handoff 30 §D3. The copy was fixed and the original was not. A
    safety rule with two copies is how the two answers start to differ, and
    this programme has been bitten by exactly that often enough to have a
    sentence for it.

    So the third append-only model did not get a third copy (handoff 30),
    and **custody and movement adopted this one in handoff 31**, by ruling:
    one answer per rule. It defines no fields, so adoption was no migration,
    changed no id and no published name. What was NOT done, also by ruling,
    is bringing their ROWS into `nrs.asset.event`: `nrs.asset.custody` and
    its ids are named in the contract an external auditor reads, merging two
    sequences changes every id on every tenant, and tidying our schema is
    not worth a breaking change to the audit contract. Do not reopen that on
    aesthetics (`docs/DECISIONS.md`, 2026-09-21).

    `_never_relabelled` — sources that say the row is a RECONSTRUCTION. The
    credential relabel in `myservice_api` leaves them alone: a backfilled
    link written while a test credential happened to be acting is still a
    reconstruction, and that is the more important thing to say about it.

    `write` and `unlink` raise unconditionally, so they hold under `sudo()`.
    `create` is weaker and says so: it refuses without a context flag, and a
    context is something an RPC caller supplies. What actually stops a
    hand-written row is that flag AND the ACL, which grants `create` to
    nobody. Two locks, one of them configuration. And all of it is Python:
    there is no database trigger, and somebody with direct SQL access is not
    stopped.
    """

    _name = 'nrs.asset.append.only.mixin'
    _description = 'Append-only record of an asset (guard)'

    # The context flag `_record` sets on itself. Each model names its own.
    _append_key = None
    # The context key a caller may declare a source through, and the values
    # it may declare. Anything else is `direct`.
    _source_key = None
    _context_sources = ()
    _never_relabelled = ('tracking_backfill',)

    def _append_only_message(self):
        # Literal inside the function, translated at the call — see
        # `asset_custody._append_only_message` for why both halves matter.
        return _(
            "This record is append-only. It cannot be edited or deleted "
            "once written — not through the interface, not over the API, "
            "and not as an administrator with sudo. Record what happened "
            "next instead; the history is the evidence."
        )

    def _no_hand_written_rows_message(self):
        return _(
            "This record cannot be created directly. A row is written only "
            "as a side effect of the thing it records actually happening, "
            "so that it says what happened rather than what somebody typed."
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self._append_key \
                or not self.env.context.get(self._append_key):
            raise UserError(self._no_hand_written_rows_message())
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(self._append_only_message())

    def unlink(self):
        raise UserError(self._append_only_message())

    @api.model
    def _resolve_source(self, declared, user):
        """The label a row carries. `myservice_api` extends it — once.

        The context is CALLER-CONTROLLED over `call_kw`. A label that says
        something about the evidence itself — that the row is a test
        artefact, or a reconstruction — may only be passed explicitly by
        first-party code or derived from the credential, never claimed
        through the context: otherwise anybody able to change an asset could
        file the change under `test`.
        """
        if declared:
            return declared
        claimed = self.env.context.get(self._source_key) \
            if self._source_key else None
        return claimed if claimed in self._context_sources else 'direct'
