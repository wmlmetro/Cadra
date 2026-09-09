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


def _acts_for_a_test_credential(env, user):
    """True when `user` is the Odoo user behind a test API credential.

    The external API suite exercises the RECORDER — it moves an asset's
    custodian over HTTP — because a test that does not exercise the recorder
    proves nothing about whether the chain is written. The recorder is
    append-only, so those links are PERMANENT in whichever tenant the suite
    ran against. That is accepted. What is not accepted is a reader of the
    chain being unable to tell them apart from history.

    The label is decided HERE, from the acting user, and never from anything
    the caller sends. A request header saying "this one is a test" would let
    anybody disguise a real change of custodian as an artefact, in the one
    model whose whole value is that its contents were not invented.

    `myservice_api` sits ABOVE this module, so the lookup is a membership
    test rather than an import — a tenant without the API module has no test
    credentials and every link is real. `active_test=False` because an
    archived credential's artefacts are still artefacts.
    """
    Client = env.get('myservice.api.client')
    if Client is None or not user:
        return False
    return bool(Client.sudo().with_context(active_test=False).search_count([
        ('user_id', '=', user.id),
        ('is_test_credential', '=', True),
    ]))


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

    @api.model_create_multi
    def create(self, vals_list):
        """Refuse a link that did not come from a custodian actually moving.

        `write` and `unlink` raising is worth nothing if `create` is guarded
        only by `ir.model.access.csv`. One `1,1,1,1` line there — a
        convenience edit, a bad merge, a deploy — and any internal user could
        `call_kw` a backdated link naming an arbitrary actor into a record
        that then cannot be corrected, because this model refuses correction
        by design. An ACL is configuration, and the argument in the class
        docstring applies to all three operations or to none.

        Same shape as `workflow.dispatch.log`, which guards `create` on the
        model with a context flag for exactly this reason: there the ACL
        could not carry it because the queue writes as the acting user, and
        here it cannot carry it because the whole point is that no
        configuration mistake may reach the record.
        """
        if not self.env.context.get(CUSTODY_APPEND_KEY):
            raise UserError(_no_hand_written_links_message())
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_append_only_message())

    def unlink(self):
        raise UserError(_append_only_message())

    @api.model
    def _record(self, asset, from_custodian, to_custodian, *,
                reason=None, changed_at=None, changed_by=None, source=None):
        """Append one link. The only way a row is ever written.

        `source` falls back to the caller's context key rather than to a
        parameter default, so a route can declare where a write came from
        once and every `custodian_id` write underneath it is labelled.

        A write made under a test API credential is relabelled `test`,
        whatever the caller declared — see `_acts_for_a_test_credential`. It
        overrides rather than sits alongside because the reader's first
        question about a link is whether it happened, and "it was a test"
        answers that before "it arrived via the transfer route" is worth
        knowing. The `reason` still carries the caller's own string.
        """
        user = changed_by if changed_by is not None else self.env.user
        source = source or self.env.context.get(CUSTODY_SOURCE_KEY) or 'direct'
        if _acts_for_a_test_credential(self.env, user):
            source = 'test'
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
