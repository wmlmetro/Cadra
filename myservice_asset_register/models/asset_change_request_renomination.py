"""Who was asked instead, and who said so. Handoff 45 §1, ruling G.1(b).

WHAT THIS IS
------------
A pending `nrs.asset.change.request` names ONE person as the approver it is
waiting on. Handoff 43 measured what happens when that person's account is
deactivated: the request waits on somebody who cannot sign in, for ever,
with nothing on it saying so. The ruling was that **deactivation is never
blocked** — cutting somebody off happens the moment it is decided, and a
queue must never be able to hold an account open — so the stranded request
is fixed FORWARD: it can be re-pointed at a different approver, as an act
with a name and a time on it.

This model is that name and that time. One row per re-pointing: which
request, who it was waiting on, who it waits on now, who did it, when, and
why. The request's own `approver_id` only ever says who is being asked NOW;
this is how a reader finds out that somebody else was asked first, and who
changed it.

WHY IT IS APPEND-ONLY, AND THROUGH THE MIXIN
--------------------------------------------
A re-pointing is a completed fact the moment it exists — it changes whose
queue a request about a government asset sits in — so it is the same kind of
record as custody, movement and the event record, and `CLAUDE.md` says what
a fourth one does: *it inherits the mixin; it does not copy it.* `write` and
`unlink` raise unconditionally (under `sudo()` too), `create` refuses
without this model's own context flag, and the ACL grants `create` to
nobody. The `source` label is resolved by the mixin's `_resolve_source`, so
a row written under a test credential says `test` on its face through the
SAME relabel `myservice_api/models/append_only.py` applies to the other
three — not through a fifth copy of it.

It holds its REQUEST with `ondelete='restrict'`, not its asset. A request
cannot be deleted anyway (`nrs.asset.change.request.unlink` refuses in every
state), so this pins nothing that was not already pinned.

WHY NOT A FIELD ON THE REQUEST
------------------------------
The handoff said it in one line: *the model's `write` today refuses
everything but `_transition`, so this is a real change rather than a field;
keep the refusal and add the one path.* A column `previous_approver_id`
would hold one re-pointing and overwrite the next, which is the
`last_verified_by` defect handoff 30 retired for verifications. The one path
is `nrs.asset.change.request.action_renominate`, which validates everything,
writes a row here, and only then moves `approver_id` through `_transition`.
"""
from odoo import api, fields, models, _

#: The flag `_record` sets on itself. Only this model's — one model's flag
#: opening another's lock is what `test_append_only_mixin.test_one_models_
#: flag_does_not_open_another` exists to stop.
RENOMINATION_APPEND_KEY = 'cadra_renomination_append'

#: The context key a caller may declare HOW the re-pointing was asked for
#: through. Never `test`: that is a statement about the evidence and is
#: derived from the credential, never claimed.
RENOMINATION_SOURCE_KEY = 'cadra_renomination_source'

_CONTEXT_SOURCES = ('api_renominate', 'direct')


class NRSAssetChangeRequestRenomination(models.Model):
    _name = 'nrs.asset.change.request.renomination'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'Approval Request Re-nomination (append-only)'
    # Oldest first: a history is read in the order it happened, and `id`
    # breaks ties inside one transaction.
    _order = 'renominated_at, id'

    _append_key = RENOMINATION_APPEND_KEY
    _source_key = RENOMINATION_SOURCE_KEY
    _context_sources = _CONTEXT_SOURCES

    request_id = fields.Many2one(
        'nrs.asset.change.request', string='Request', required=True,
        ondelete='restrict', index=True)

    # `restrict` on the users, as the request's own `approver_id` and
    # `requested_by_id` are; the Char copies beside them are what the row
    # keeps if a name changes, for the reason the request keeps
    # `requested_by_name`.
    from_approver_id = fields.Many2one(
        'res.users', string='Was Waiting On', required=True,
        ondelete='restrict')
    from_approver_name = fields.Char(string='Was Waiting On (as recorded)')
    to_approver_id = fields.Many2one(
        'res.users', string='Now Waiting On', required=True,
        ondelete='restrict')
    to_approver_name = fields.Char(string='Now Waiting On (as recorded)')

    # WHO DID IT. From the acting user, never from a payload — the same rule
    # as `requested_by_id` and `approved_by_id`.
    renominated_by_id = fields.Many2one(
        'res.users', string='Re-pointed By', required=True,
        ondelete='restrict')
    renominated_by_name = fields.Char(string='Re-pointed By (as recorded)')
    renominated_at = fields.Datetime(
        string='Re-pointed At', required=True, index=True,
        default=lambda self: fields.Datetime.now())
    reason = fields.Text(string='Reason', required=True)

    source = fields.Selection([
        ('api_renominate', 'API — ask someone else'),
        ('direct', 'Direct (Odoo UI or script)'),
        ('test', 'Written by the automated test suite'),
    ], string='Source', required=True, default='direct', index=True)

    def _append_only_message(self):
        return _(
            "The record of who an approval request was re-pointed to is "
            "append-only. A re-nomination cannot be edited or deleted once "
            "written — not through the interface, not over the API, and not "
            "as an administrator with sudo. Re-point the request again "
            "instead; the history is the evidence."
        )

    def _no_hand_written_rows_message(self):
        return _(
            "A re-nomination record cannot be created directly. One is "
            "written only when a pending approval request is actually "
            "re-pointed at somebody else, so that it says what happened "
            "rather than what somebody typed."
        )

    @api.model
    def _record(self, change_request, from_approver, to_approver, actor,
                reason, at=None, source=None):
        """Append one row. The only way a row is ever written.

        Called by `nrs.asset.change.request.action_renominate` and by
        nothing else, AFTER that method has validated every part of the
        act — so a row here always describes a re-pointing that happened.
        """
        vals = {
            'request_id': change_request.id,
            'from_approver_id': from_approver.id,
            'from_approver_name': from_approver.display_name,
            'to_approver_id': to_approver.id,
            'to_approver_name': to_approver.display_name,
            'renominated_by_id': actor.id,
            'renominated_by_name': actor.display_name,
            'renominated_at': at or fields.Datetime.now(),
            'reason': reason,
            'source': self._resolve_source(source, actor),
        }
        return self.env['nrs.asset.change.request.renomination'].sudo() \
            .with_context(**{RENOMINATION_APPEND_KEY: True}).create(vals)
