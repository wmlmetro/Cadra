"""A record created under a test credential says so on its own face.

WHY THIS EXISTS
---------------
Report 24 measured a client-derived register at 88% test fixtures and could
identify almost none of them from the records themselves. What it could
identify, it identified because of a DERIVATION: 352 chain-of-custody rows
(on `jaizbankplc`, 2026-09-15 — it was 330 when handoff 24 first measured
it, and it grows with every test run, which is rather the point)
carry `source = 'test'` because `nrs.asset.custody._resolve_source` reads
`myservice.api.client.is_test_credential` off the acting user and stamps the
answer into the row. Nobody curates that. Nobody remembers to type it.

Everything else relied on a NAME PREFIX — `pytest-asset-*`, `pytest-loc-*` —
which is a convention, and a convention is a thing somebody remembers. The
one model that never adopted one, `request.request`, is the proof: its name
is a sequence (`REQ-000692`), so the 460 requests on `jaizbankplc` are
indistinguishable from real ones by any rule a cleanup script can apply.
They can never be found again. That is the cost of a convention, paid once.

This mixin makes the custody derivation a general property: **anything
created through a credential flagged `is_test_credential` carries that fact
on the record.**

WHAT IT GUARANTEES, AND HOW
---------------------------
1. **Derived, never declared.** The value comes from the ACTING USER and from
   nothing the caller sends. `create()` overwrites whatever arrived in
   `vals`, so a client cannot mint a real-looking record by omitting the flag
   and cannot slander a real one by sending it. This is the same reasoning
   `_resolve_source` records: a body field saying "this one is a test" lets
   anybody disguise a real record as an artefact.

2. **Not clearable.** `write()` refuses to move it, for the same reason the
   custody chain refuses `unlink()`. A label that the thing it labels can
   remove is a convention with extra steps. The refusal is unconditional —
   there is no superuser branch, because a superuser branch is what an
   `odoo shell` one-liner uses.

3. **Not settable over the API** by construction: the field is in no
   `_WRITABLE_FIELDS` allow-list, and `tests/test_source_guards.py` fails if
   it is ever added to one.

WHAT IT DOES NOT DO — AND THIS IS THE IMPORTANT PART
----------------------------------------------------
**It is not retroactive, and it cannot be made retroactive.** A record
created before this field existed carries no acting-user provenance that
survives credential deletion, and `create_uid` is not an answer: it is a
foreign key that says which user, not a stamped fact that says what the
record IS, and it goes stale the moment a credential is re-homed or removed.

So everything already in every register at the moment this lands is
unidentifiable forever, exactly as the access record of handoff 24 is not
retroactive. The measured cost, on `jaizbankplc` on 2026-09-15:

  * 460 service requests — unidentifiable, permanently. No prefix, no flag.
  * 4,164 assets, of which 3,894 carry a fixture NAME and are therefore
    identifiable by convention only, and 270 are not identifiable at all.
  * 440 locations, 4,164 tag labels, 14,451 chatter messages — same.

`scripts/mark_test_fixtures.py` marks the subset that can still be found by
name. Nothing can find the rest. **The register starts telling the truth
about itself on the day this ships and says nothing about the day before.**
"""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class CadraTestFixtureMixin(models.AbstractModel):
    """Stamp `is_test_fixture` from the acting user's credential."""

    _name = 'cadra.test.fixture.mixin'
    _description = 'Test-fixture provenance'

    is_test_fixture = fields.Boolean(
        string='Test Fixture',
        default=False,
        readonly=True,
        copy=False,
        index=True,
        help="TRUE when this record was created through an API credential "
             "flagged as a test credential, or by an account that is itself "
             "a test or demo fixture. Derived from the acting user at "
             "creation and never from anything the caller sends; it cannot "
             "be set, cleared or corrected afterwards. FALSE on every record "
             "created before this field existed, which is not the same as "
             "'this is a real record' — see the module docstring.")

    @api.model
    def _acting_user_is_test_credential(self):
        """The one question this mixin asks, asked in one place.

        The API routes create under `.sudo()`, which elevates privileges
        while KEEPING the uid, so the acting user is still the credential's
        own user — that is what handoff 08 bought when it stopped API clients
        acting as Administrator.

        **The one exception, and it is real.**
        `NRSHomepageAPI.quick_submit` (`myservice_website_theme/controllers/
        api.py`) creates a
        `request.request` with `.with_user(SUPERUSER_ID)`, which REPLACES the
        acting user rather than elevating it. Records created through
        `POST /api/v1/home/quick-submit` therefore carry `create_uid =
        __system__` and derive `False` here — correctly, since there is no
        credential left in the environment to read.

        Measured on `test19` on 2026-09-15, as an INVARIANT rather than a
        count — the counts climb with every test run, and quoting one is how
        a figure goes stale between two readings of the same page:

          * every record created after this field landed through a
            CREDENTIAL is labelled — assets, locations, tag labels and
            transfers all at 100%, no exceptions;
          * every UNLABELLED record has `create_uid = 1`, and they are
            requests, request events and the chatter hanging off them.

        Both halves re-checked after several further suite runs and both
        still held. It is the only `with_user(SUPERUSER_ID)` in any
        first-party module.

        Left alone on purpose: the same handler serves an `auth='public'`
        twin, so changing it changes what `env.user` is during a create on an
        unauthenticated route. The options are written out in
        `docs/GO-LIVE.md` §11.1.
        """
        Client = self.env.get('myservice.api.client')
        if Client is None:
            return False
        return Client._is_test_credential_user(self.env.uid)

    @api.model_create_multi
    def create(self, vals_list):
        derived = self._acting_user_is_test_credential()
        for vals in vals_list:
            # Overwrite rather than default: a value that arrived in the
            # payload is precisely the thing this must not honour.
            vals['is_test_fixture'] = derived
        return super().create(vals_list)

    def write(self, vals):
        if 'is_test_fixture' in vals:
            wanted = bool(vals['is_test_fixture'])
            if any(record.is_test_fixture != wanted for record in self):
                raise UserError(_(
                    "`is_test_fixture` is derived from the credential that "
                    "created the record and cannot be changed. It is a "
                    "statement about how the record came to exist, which "
                    "writing to it would not alter."))
            # Writing the value it already holds changes nothing; let a form
            # save that round-trips every field through `write` succeed.
            vals = {k: v for k, v in vals.items() if k != 'is_test_fixture'}
            if not vals:
                return True
        return super().write(vals)


# ─────────────────────────────────────────────────────────────────────────
# The models an external HTTP call can create.
#
# This list is not curated by hand and kept honest by hope:
# `tests/test_source_guards.py::
# test_every_model_a_first_party_path_creates_is_classified`
# walks EVERY first-party Python file (`myservice_*`, `cadra_brand_*`,
# excluding `tests/`), resolves every create-shaped call it finds to a model,
# and fails if one turns up that is neither declared here, nor labelled by
# its own older mechanism (`nrs.asset.custody.source`), nor listed as
# unreachable-from-a-credential with a reason.
#
# **It does NOT do route reachability**, and an earlier version of this
# comment claimed it did — that it "walks every `@cadra_route` and resolves
# every `.create(` reachable from a route handler". It has no route
# awareness at all. The error was in the safe direction (it enumerates more
# than routes reach, not less), but a confident sentence about a protection,
# in the file that protection guards, is the thing this handoff exists to
# stop. Caught by the verification pass, not by me.
#
# A model added next year turns the suite red on the day it is added.
#
# They live in `myservice_api` and not in the modules that own the models,
# and the direction matters for the same reason `asset_custody.py` records:
# `is_test_credential` is a column on `myservice.api.client`, which THIS
# module owns. Declared in a lower module, the column and the code reading it
# could be ordered apart by the dependency graph, and a tenant carrying new
# Python against an older `myservice_api` schema would raise `UndefinedColumn`
# on every create. Here they ship together and move together.
# ─────────────────────────────────────────────────────────────────────────

class NRSAsset(models.Model):
    _name = 'nrs.asset'
    _inherit = ['nrs.asset', 'cadra.test.fixture.mixin']


class GenericLocation(models.Model):
    _name = 'generic.location'
    _inherit = ['generic.location', 'cadra.test.fixture.mixin']


class RequestRequest(models.Model):
    """The measured hole: 460 rows on `jaizbankplc`, none identifiable."""
    _name = 'request.request'
    _inherit = ['request.request', 'cadra.test.fixture.mixin']


class RequestEvent(models.Model):
    _name = 'request.event'
    _inherit = ['request.event', 'cadra.test.fixture.mixin']


class NRSAssetTagLabel(models.Model):
    _name = 'nrs.asset.tag.label'
    _inherit = ['nrs.asset.tag.label', 'cadra.test.fixture.mixin']


class NRSAssetTransfer(models.Model):
    _name = 'nrs.asset.transfer'
    _inherit = ['nrs.asset.transfer', 'cadra.test.fixture.mixin']


class NRSAssetChangeRequest(models.Model):
    """Approval requests raised by the suite say so on their face.

    Handoff 35. The model refuses `unlink` outright, so anything a test run
    raises against a real tenant is permanent — exactly the property that
    made handoff 26 put this label on the other thirteen models. The guard in
    `tests/test_source_guards.py` fails on any creatable model with no
    self-label, so this is not optional.
    """
    _name = 'nrs.asset.change.request'
    _inherit = ['nrs.asset.change.request', 'cadra.test.fixture.mixin']


class NRSAssetCategory(models.Model):
    _name = 'nrs.asset.category'
    _inherit = ['nrs.asset.category', 'cadra.test.fixture.mixin']


class HREmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee', 'cadra.test.fixture.mixin']


class HRDepartment(models.Model):
    _name = 'hr.department'
    _inherit = ['hr.department', 'cadra.test.fixture.mixin']


class ResPartner(models.Model):
    """Created by `/home/quick-submit` when the reporter gives an email."""
    _name = 'res.partner'
    _inherit = ['res.partner', 'cadra.test.fixture.mixin']


class NRSEmployeeImportJob(models.Model):
    _name = 'nrs.employee.import.job'
    _inherit = ['nrs.employee.import.job', 'cadra.test.fixture.mixin']


class NRSSapSyncLog(models.Model):
    _name = 'nrs.sap.sync.log'
    _inherit = ['nrs.sap.sync.log', 'cadra.test.fixture.mixin']


class WorkflowDispatchLog(models.Model):
    _name = 'workflow.dispatch.log'
    _inherit = ['workflow.dispatch.log', 'cadra.test.fixture.mixin']


class MailMessage(models.Model):
    """Chatter, and the reason it is here rather than exempted.

    A message is the one creatable thing that lands on a record it did not
    create. `POST /assets/<id>/transfer-custody` posts to the chatter of a
    REAL asset, so exempting chatter as "not register data" would leave
    test-written history on records that are not fixtures at all — the exact
    shape of hole this mixin exists to close, on the records where it matters
    most.

    `author_id` is not the answer. It resolves to the credential's user only
    while that credential still exists and still points at that user, and
    `myservice.api.client.write` re-homes users. A stamped fact survives;
    a join does not.
    """
    _name = 'mail.message'
    _inherit = ['mail.message', 'cadra.test.fixture.mixin']


class NRSAssetPhoto(models.Model):
    """Photos sent by the suite say so on their face (handoff 61 §5).

    The model is append-only — `write` and `unlink` raise, and it holds its
    asset with `ondelete='restrict'` — so a photo a test run uploads to a
    tenant is PERMANENT there, which is exactly the property that put this
    label on the change request. Its `source` column says which app a photo
    came through (`web`/`mobile`), declared by the caller; whether a test
    credential sent it is this field, derived. The append-only guard's
    `create` runs first (it is earlier in the class's bases) and calls this
    mixin's, which stamps the label.
    """
    _name = 'nrs.asset.photo'
    _inherit = ['nrs.asset.photo', 'cadra.test.fixture.mixin']


class NRSAiSuggestion(models.Model):
    """A suggestion a test credential asked for says so (handoff 64 §2).

    Append-only, like the photo it is about: a row the suite writes on a
    tenant is permanent there, so it carries the label rather than a
    `source` anybody could claim."""
    _name = 'nrs.ai.suggestion'
    _inherit = ['nrs.ai.suggestion', 'cadra.test.fixture.mixin']


class NRSAiPendingPhoto(models.Model):
    """A photo held for an asset that does not exist yet, sent by a test
    credential, says so (handoff 64 §2) — for the hours before it is
    claimed or purged."""
    _name = 'nrs.ai.pending.photo'
    _inherit = ['nrs.ai.pending.photo', 'cadra.test.fixture.mixin']


class NRSSapImportRun(models.Model):
    """An import of SAP's export run by a test credential says so (handoff
    63). Its rows inherit the run's label: the importer writes them with SQL
    and stamps `is_test_fixture` from the run (`sap_mirror._Writer`)."""
    _name = 'nrs.sap.import.run'
    _inherit = ['nrs.sap.import.run', 'cadra.test.fixture.mixin']


class NRSSapAsset(models.Model):
    """A mirror record imported by a test credential's run says so (handoff
    63) — stamped by the importer from its run, never by a caller."""
    _name = 'nrs.sap.asset'
    _inherit = ['nrs.sap.asset', 'cadra.test.fixture.mixin']
