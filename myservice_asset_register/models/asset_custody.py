from odoo import models, fields, api, _
from odoo.exceptions import UserError

# The context key a caller sets to say WHERE a custody change came from.
# Anything that does not set it lands on `direct`, which is the honest label
# for "somebody wrote the field and did not say why" — the Odoo form, a data
# import, a shell session, a cron.
CUSTODY_SOURCE_KEY = 'cadra_custody_source'

# The reason the caller gave, when it gave one. It travels in the context for
# the same reason the source does: an ORM write carrying a custody change has
# nowhere to put a sentence.
CUSTODY_REASON_KEY = 'cadra_custody_reason'

# The flag `_record` sets on itself. `create` refuses without it, so the
# single entry point is enforced by the model and not by the access rules —
# see the class docstring for why that distinction is the whole point here.
CUSTODY_APPEND_KEY = 'cadra_custody_append'

# The sources a CALLER may declare through the context. `test` and
# `tracking_backfill` are never taken from it: see `_resolve_source`.
_CONTEXT_SOURCES = ('api_transfer', 'api_write', 'transfer', 'approval',
                    'direct')


# Translated at the call, not at import: `_()` evaluated at class-build time
# resolves against no context and freezes one language into the module. The
# string is a LITERAL inside the function rather than a module constant
# passed to `_()`, because Odoo's PO extractor scans literal arguments and
# would never see a variable — a message that cannot be extracted cannot be
# translated, however correct the runtime call looks.
def _append_only_message():
    return _(
        "The chain of custody is append-only. A custody record cannot be "
        "edited or deleted once written — not through the interface, not "
        "over the API, and not as an administrator with sudo. Record a new "
        "custody change instead; the history is the evidence."
    )


def _no_hand_written_links_message():
    return _(
        "A chain-of-custody record cannot be created directly. Links are "
        "written only as a side effect of an asset's custodian changing, so "
        "that the chain says what happened rather than what somebody typed. "
        "Change the asset's custodian instead."
    )


class NRSAssetCustody(models.Model):
    """One link in an asset's chain of custody. Append-only, and it means it.

    The PRD requires a record that "cannot be edited retrospectively, only
    appended… an audit-grade record suitable for legal and compliance
    purposes". Until this model existed the chain lived in `mail.thread`
    tracking values, which no API route exposed and which a user with the
    right groups can delete. A chain of custody that can be deleted is not a
    chain of custody.

    `create`, `write` and `unlink` are all guarded on the model itself
    rather than by ACL, because an ACL is configuration and configuration is
    what the last three deployment failures were made of. `write` and
    `unlink` raise unconditionally, so the guard holds under `sudo()` too —
    which is the point: a record whose whole value is that nobody can alter
    it must refuse the administrator as well. `create` raises unless the
    caller carries the flag `_record` sets, so a link can only ever be a
    side effect of a custodian actually moving.
    """

    _name = 'nrs.asset.custody'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'Asset Chain of Custody'
    # Chronological, because a chain reads forwards. `id` breaks ties inside
    # a single transaction, where several rows share one timestamp.
    _order = 'changed_at, id'

    asset_id = fields.Many2one(
        'nrs.asset', string='Asset', required=True, index=True,
        # NOT cascade. Deleting an asset would otherwise erase its custody
        # history along with it, which is the same defect this model exists
        # to remove wearing a different hat.
        #
        # This is not free: `scripts/nrs_hq_seed.py` wipes the register as
        # its opening act (`remaining.unlink()` over every `nrs.asset`), and
        # from now on that script stops on any tenant that has custody
        # history — five of the eight do. That is the intended behaviour
        # rather than a casualty of it: a script that would destroy an
        # append-only audit record should refuse and say so.
        #
        # A refusal people route around is worse than a refusal with a
        # documented exit, though, and the route around this one was
        # dropping the database — which destroys the chain AND everything
        # else, with nothing left to say it happened. So the script now
        # refuses BY NAME and offers a flag, `CADRA_SEED_DESTROY_CUSTODY=1`,
        # which prints the link count and the tenant before it proceeds.
        #
        # A cascade would have made the wipe silent, which is the one
        # outcome nobody could audit afterwards.
        ondelete='restrict')

    from_custodian_id = fields.Many2one(
        'hr.employee', string='From Custodian', ondelete='set null')
    to_custodian_id = fields.Many2one(
        'hr.employee', string='To Custodian', ondelete='set null')

    # The names as they read AT THE TIME. An `hr.employee` can be deleted or
    # renamed, and a m2o to a deleted employee goes null — so without these
    # two columns an append-only row could still be emptied of its content
    # from the outside. They are also what lets the backfill record a
    # custodian who has since left.
    from_custodian_name = fields.Char(string='From Custodian (as recorded)')
    to_custodian_name = fields.Char(string='To Custodian (as recorded)')

    changed_at = fields.Datetime(
        string='Changed At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO MOVED IT, not who held it. An auditor asks that question as often
    # as the other one, and the two custodian fields above cannot answer it.
    changed_by_id = fields.Many2one(
        'res.users', string='Changed By', ondelete='set null')
    changed_by_name = fields.Char(string='Changed By (as recorded)')

    reason = fields.Text(string='Reason')

    source = fields.Selection([
        ('api_transfer', 'API — transfer-custody'),
        ('api_write', 'API — asset create or update'),
        ('transfer', 'Asset transfer completion'),
        # Handoff 35 — a change of custodian a second person agreed to. See
        # the note beside the same value in `asset_movement.py`.
        ('approval', 'Approved change request'),
        ('direct', 'Direct write (Odoo UI, import or script)'),
        ('tracking_backfill', 'Reconstructed from chatter tracking'),
        # Written by the automated test suite. The suite exercises the
        # RECORDER — an asset's custodian actually moving — because a test
        # that does not cannot prove the chain is written at all; and the
        # recorder is append-only, so the links it produces are permanent in
        # whatever tenant the suite ran against. That is accepted. What is
        # not accepted is a reader being unable to tell.
        #
        # The reason string used to carry the test's own name, which is a
        # string somebody has to know to look for. A first-class `source`
        # returned by the API says it to anyone reading the chain, without
        # being told the artefacts exist — the same argument as
        # `tracking_backfill`, one step further on.
        ('test', 'Written by the automated test suite'),
    ], string='Source', required=True, default='direct', index=True)

    # ── Append-only ───────────────────────────────────────────────────
    #
    # The guard is `nrs.asset.append.only.mixin` (handoff 31). This model
    # carried its own copy of `create`, `write`, `unlink` and
    # `_resolve_source` from 9 September until then, and the copy is how the
    # hole got in: `_resolve_source` here honoured ANY `source` a caller put
    # in the context — `test` and `tracking_backfill` included — so anybody
    # able to change a custodian could file a real change of custody as an
    # artefact. `nrs.asset.movement` was copied from this model twelve days
    # later WITHOUT that hole; the copy was fixed and the original was not.
    # Nobody decided that. It is what two copies of a safety rule do, and it
    # is why there is now one.
    #
    # WHY the guard is on the model and not in the ACL is unchanged and worth
    # keeping here: `write` and `unlink` raising is worth nothing if `create`
    # is guarded only by `ir.model.access.csv`. One `1,1,1,1` line there — a
    # convenience edit, a bad merge, a deploy — and any internal user could
    # `call_kw` a backdated link naming an arbitrary actor into a record that
    # then cannot be corrected, because this model refuses correction by
    # design. An ACL is configuration.
    #
    # WHY `_resolve_source` is an override point is unchanged too: the module
    # ABOVE this one relabels a write made under a test credential, and the
    # column it reads (`myservice.api.client.is_test_credential`) is one that
    # module owns. When the lookup lived down here, this module read a column
    # of a module it does not depend on, Odoo could not order the two, and a
    # tenant carrying the new Python with the older `myservice_api` schema
    # would have raised `UndefinedColumn` on EVERY custodian write — on one
    # registry, a cross-tenant outage from a single-module upgrade.
    _append_key = CUSTODY_APPEND_KEY
    _source_key = CUSTODY_SOURCE_KEY
    _context_sources = _CONTEXT_SOURCES

    def _append_only_message(self):
        return _append_only_message()

    def _no_hand_written_rows_message(self):
        return _no_hand_written_links_message()

    @api.model
    def _record(self, asset, from_custodian, to_custodian, *,
                reason=None, changed_at=None, changed_by=None, source=None):
        """Append one link. The only way a row is ever written.

        `source` falls back to the caller's context key rather than to a
        parameter default, so a route can declare where a write came from
        once and every `custodian_id` write underneath it is labelled.

        The label itself is decided by `_resolve_source`, which
        `myservice_api` extends — see there for why a write made under a test
        credential is relabelled.
        """
        user = changed_by if changed_by is not None else self.env.user
        source = self._resolve_source(source, user)
        # THE NAMES ARE READ AS SUPERUSER, and this is not tidiness.
        #
        # `hr.employee._check_private_fields` refuses an employee record to
        # anybody outside `hr.group_hr_user`, and reading ONE field prefetches
        # the whole record — so building `from_custodian.name` in the acting
        # user's environment raised `AccessError: The fields
        # "is_test_fixture,ir_number,sap_user_id,…" are not available for
        # employee public profiles` for an Asset Manager who is not also an
        # HR user. The `create` below was already `sudo()`; the READS above it
        # were not, so the row never got that far.
        #
        # PRE-EXISTING — the Odoo asset form has always been able to hit it,
        # and the REST API never does because `_browse_or_404` browses
        # `sudo()`. Handoff 35 put a second Odoo-side door onto it (pressing
        # Approve on a custody request), which is how the verification pass
        # found it. `nrs.asset.movement._record` has the same shape and is
        # safe only because `generic.location` has no private-field rule —
        # left alone deliberately rather than changed on a guess.
        from_custodian = from_custodian.sudo() if from_custodian else from_custodian
        to_custodian = to_custodian.sudo() if to_custodian else to_custodian
        vals = {
            'asset_id': asset.id,
            'from_custodian_id': from_custodian.id if from_custodian else False,
            'to_custodian_id': to_custodian.id if to_custodian else False,
            'from_custodian_name': from_custodian.name if from_custodian else False,
            'to_custodian_name': to_custodian.name if to_custodian else False,
            'changed_at': changed_at or fields.Datetime.now(),
            'changed_by_id': user.id if user else False,
            'changed_by_name': user.name if user else False,
            'reason': reason or False,
            'source': source,
        }
        return self.sudo().with_context(
            **{CUSTODY_APPEND_KEY: True}).create(vals)


class HrEmployee(models.Model):
    """Deleting an employee un-assigns everything they held. Say so.

    `nrs_asset.custodian_id` is `ON DELETE SET NULL`. So deleting an employee
    empties `custodian_id` on every asset they held — done by the database,
    with no ORM write. No `nrs.asset.write` runs, so the chain of custody
    never sees it and no tracking value is written either: the asset simply
    stops being held by anybody, and the last link in its chain still says
    somebody has it.

    It is `GenericLocation.unlink` in `asset_movement.py`, word for word, on
    the older model — handoff 28 closed it for location and did not look
    here, and handoff 30's verification pass found it by asking whether
    "disposed is terminal" held through every door. It did not, through
    either of these two.
    """
    _inherit = 'hr.employee'

    def unlink(self):
        assets = self.env['nrs.asset'].sudo().with_context(
            active_test=False).search([('custodian_id', 'in', self.ids)])
        disposed = assets.filtered(lambda a: a.state == 'disposed')
        if disposed:
            raise UserError(_(
                "%(count)s disposed asset(s) keep an employee being deleted "
                "as whoever held them when they were disposed of "
                "(%(first)s%(more)s), and a disposed asset's record cannot "
                "be changed. Archive the employee instead of deleting them.",
                count=len(disposed), first=disposed[0].display_name,
                more=_(' and others') if len(disposed) > 1 else ''))
        Custody = self.env['nrs.asset.custody']
        nobody = self.env['hr.employee']
        # BEFORE the delete, while the names can still be read, and in a
        # SAVEPOINT for the reason `GenericLocation.unlink` gives: a refusal
        # that raises in Python after these rows are written must not leave
        # permanent links saying an employee was deleted who is still there.
        # `direct`, not a label of its own: it IS a direct act in Odoo, the
        # reason says which, and `source` is a published enum.
        with self.env.cr.savepoint():
            for asset in assets:
                Custody._record(
                    asset, asset.custodian_id, nobody, source='direct',
                    reason=_("The employee record was deleted."))
            return super().unlink()

