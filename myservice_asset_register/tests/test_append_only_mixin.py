"""One guard, three records — that it IS one, and that each still speaks for
itself. Handoff 31 §A.

`nrs.asset.custody`, `nrs.asset.movement` and `nrs.asset.event` each refuse
to be edited, deleted or written by hand, and each decides what `source` a
row may carry. Until handoff 31 custody and movement carried their OWN copy
of that, and the copies had already disagreed: custody honoured any `source`
a caller put in the context — `test` and `tracking_backfill` included — for
twelve days after movement, copied from it, was written without the hole.
The copy was fixed and the original was not. Nobody decided that; it is what
two copies of a safety rule do.

So what is asserted here is not the guarantee — `test_custody_chain.py`,
`test_movement_record.py` and `test_asset_event.py` each hold their own
model's, and those tests passed on the day the two copies disagreed. It is
the thing those three files cannot see from inside one model:

    1. The guard is THE MIXIN'S. No model defines a `create`, `write`,
       `unlink` or `_resolve_source` of its own, so there is no second copy
       to drift.
    2. Adopting it cost nothing a reader would notice: each model still
       refuses in ITS OWN words, and each model's flag opens only itself.
    3. The one rule about labels holds on all three, asked the same way.

Every property is looped over the three models, deliberately. A test per
model is three tests that can be edited apart, which is the defect.

WHY THE GATED WRITES BELOW SAY `cadra_approval_exempt="test"`
-------------------------------------------------------------
Handoff 35 put a gate under every writer of `location_id` and
`custodian_id`: on a tenant that has not turned the rule off — and absent
means ON, so `test19` has not — a write that CHANGES either field raises
unless a second person approved it. These fixtures are not a person
deciding to move something, so each gated write declares itself with the
reason `approval_policy.EXEMPT_REASONS` reserves for exactly this.

**Per call, never once for the file or the class.** A module-level default
would be the bypass flag `database_class.py` argues against at length: it
becomes the way everything here is written by the end of the month, and
then a test that should have discovered the gate never meets it. Spelling
it at each site also means a grep for the constant finds every test that
is standing outside the rule. Writes that do NOT change the two fields are
left exactly as they were — a fixture that stops needing the declaration
is a fixture whose meaning has changed.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

_MIXIN = "nrs.asset.append.only.mixin"

# model → (the python module that declares it, the words only ITS refusal
#          uses, the words only its hand-written-row refusal uses)
_MODELS = {
    "nrs.asset.custody": (
        "odoo.addons.myservice_asset_register.models.asset_custody",
        "chain of custody", "chain-of-custody record"),
    "nrs.asset.movement": (
        "odoo.addons.myservice_asset_register.models.asset_movement",
        "where an asset has been", "movement record"),
    "nrs.asset.event": (
        "odoo.addons.myservice_asset_register.models.asset_event",
        "what has happened", "asset event"),
}

_GUARD_METHODS = ("create", "write", "unlink", "_resolve_source")

# The context key each model reads a CLAIMED source from.
_SOURCE_KEYS = {
    "nrs.asset.custody": "cadra_custody_source",
    "nrs.asset.movement": "cadra_movement_source",
    "nrs.asset.event": "cadra_event_source",
}

# The flag each model's `_record` sets on itself.
_APPEND_KEYS = {
    "nrs.asset.custody": "cadra_custody_append",
    "nrs.asset.movement": "cadra_movement_append",
    "nrs.asset.event": "cadra_event_append",
}


class AppendOnlyCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Append-only test category"})
        Location = self.env["generic.location"]
        self.room = Location.create({"name": "Append-only test room"})
        self.elsewhere = Location.create(
            {"name": "Append-only test elsewhere"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Append-only Alice"})
        self.bob = Employee.create({"name": "Append-only Bob"})

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Append-only test asset",
             "category_id": self.category.id}, **vals))

    def _rows(self, model, asset):
        return self.env[model].search([("asset_id", "=", asset.id)],
                                      order="id")

    def _one_row_of_each(self):
        """An asset with exactly one custody link, one movement and one
        event, each written the only way one can be: by the thing it records
        actually happening."""
        asset = self._asset(custodian_id=self.alice.id,
                            location_id=self.room.id)
        asset.write({"state": "in_repair"})
        rows = {model: self._rows(model, asset) for model in _MODELS}
        for model, found in rows.items():
            self.assertEqual(len(found), 1, model)
        return asset, rows

    def _hand_written(self, model, asset):
        """Vals that would be a VALID row of `model`, so that a refusal is
        the guard's and not a missing required column's."""
        return {
            "nrs.asset.custody": {
                "asset_id": asset.id,
                "to_custodian_id": self.bob.id,
                "to_custodian_name": "Somebody Senior",
                "changed_at": "2020-01-01 00:00:00",
                "changed_by_name": "Somebody Senior",
                "source": "api_transfer"},
            "nrs.asset.movement": {
                "asset_id": asset.id,
                "to_location_id": self.elsewhere.id,
                "to_location_name": "A room it was never in",
                "moved_at": "2020-01-01 00:00:00",
                "moved_by_name": "Somebody Senior",
                "source": "api_move"},
            "nrs.asset.event": {
                "asset_id": asset.id,
                "event_type": "verified",
                "to_value": "2020-01-01",
                "occurred_at": "2020-01-01 00:00:00",
                "actor_name": "Somebody Senior",
                "source": "api_verify"},
        }[model]


@tagged("post_install", "-at_install")
class TestTheGuardIsWrittenOnce(AppendOnlyCase):
    """The class of `env[model]` is not the class in the model's file.

    Odoo assembles a REGISTRY class per model and gives it, as bases, every
    python class that declares or extends the model plus the registry class
    of each model named in `_inherit`. So `type(env["nrs.asset.custody"])`
    defines nothing itself, and asking IT whether it has a `write` answers
    yes for every model in the system. The question here is WHICH python
    class supplies it, and that is read off the MRO:

    - `vars(klass)` is a class's OWN body — what was typed inside that
      `class` statement — with nothing inherited in it.
    - A class written in an addon has an `__module__` under `odoo.addons.`;
      the assembled registry classes do not.

    So "the model defines no guard of its own" is: the one class in the MRO
    whose `__module__` is the model's own file has none of the four names in
    its `vars()`. And "the guard is the mixin's" is: walking the MRO from
    the front, the FIRST class with the name in its `vars()` lives in a file
    called `append_only.py` — this module's, or `myservice_api`'s extension
    of it where that is installed. Nothing nearer the front can exist
    without being found first, which is what makes it a guard against a
    future override as well as a description of today.
    """

    def _declared_in(self, model, module):
        return [klass for klass in type(self.env[model]).__mro__
                if klass.__module__ == module]

    def test_each_model_is_declared_once_and_this_test_can_see_it(self):
        """Non-vacuity. If the MRO stopped carrying the declaring class —
        a different Odoo, a moved file — every `assertNotIn` below would
        pass having inspected nothing."""
        for model, (module, _words, _row) in _MODELS.items():
            with self.subTest(model=model):
                declared = self._declared_in(model, module)
                self.assertEqual(
                    len(declared), 1,
                    "%s: expected exactly one class from %s in the MRO, "
                    "found %s" % (model, module, declared))
                self.assertEqual(vars(declared[0]).get("_name"), model)

    def test_no_model_defines_a_guard_of_its_own(self):
        for model, (module, _words, _row) in _MODELS.items():
            own = vars(self._declared_in(model, module)[0])
            for method in _GUARD_METHODS:
                with self.subTest(model=model, method=method):
                    self.assertNotIn(
                        method, own,
                        "%s defines its own `%s` again. That is a second "
                        "copy of the append-only guard, and the last time "
                        "there were two, one of them let a caller file a "
                        "real change of custody under `test`."
                        % (model, method))

    def test_the_guard_each_model_runs_is_the_mixins(self):
        for model in _MODELS:
            for method in _GUARD_METHODS:
                with self.subTest(model=model, method=method):
                    first = next(
                        klass for klass in type(self.env[model]).__mro__
                        if method in vars(klass))
                    self.assertTrue(
                        first.__module__.startswith("odoo.addons.")
                        and first.__module__.endswith(".models.append_only"),
                        "%s.%s resolves to %s.%s — something sits in front "
                        "of the mixin" % (model, method, first.__module__,
                                          first.__qualname__))

    def test_nothing_but_these_three_adopts_the_guard(self):
        """The list this file loops over is the whole list. A fourth
        append-only record is welcome — and it is added HERE, with its own
        words, on the day it adopts the mixin."""
        # Asked of the classes rather than of `_inherit_children`: a model
        # adopts the guard exactly when the mixin's registry class is among
        # its ancestors, whatever bookkeeping Odoo keeps beside that.
        guard = type(self.env[_MIXIN])
        adopters = sorted(
            name for name in self.env.registry
            if name != _MIXIN
            and issubclass(type(self.env[name]), guard))
        self.assertEqual(adopters, sorted(set(_MODELS) | set(_NOT_ASSET_KEYED)))


#: Append-only records that adopt the mixin but are not keyed on an ASSET, so
#: the asset-shaped loops above (`_one_row_of_each`, `_rows(model, asset)`)
#: cannot write or find one. Each is held to the same four properties in its
#: own file, named here, so this list is the whole list.
#:
#: Handoff 45: `nrs.asset.change.request.renomination` — one row per pending
#: approval request re-pointed at a different approver. Keyed on the REQUEST.
#: `test_renomination.TestTheRowIsAppendOnly` asserts its refusals in its own
#: words, that another model's flag does not open it, and that its guard
#: resolves to the mixin rather than to a copy.
_NOT_ASSET_KEYED = {
    "nrs.asset.change.request.renomination": "test_renomination.py",
    # Handoff 61 §5: keyed on an asset, but a row is written only by
    # `_upload` with real image bytes, which the asset-shaped loops here
    # cannot supply; held to the same properties in its own file.
    "nrs.asset.photo": "myservice_api/tests/test_asset_photos.py",
    # Handoff 64 §2: keyed on a PHOTO (or a held photo), never on an asset,
    # and written only by `_record` after a provider call. Its guard is
    # proved in its own file.
    "nrs.ai.suggestion": "myservice_api/tests/test_ai_suggestion.py",
}


@tagged("post_install", "-at_install")
class TestEachModelStillSpeaksForItself(AppendOnlyCase):
    """The mixin has a wording of its own, and no reader should ever meet
    it: "this record is append-only" tells somebody refused on a custody
    link nothing about what to do instead."""

    def test_an_edit_is_refused_under_sudo_in_the_models_own_words(self):
        _asset, rows = self._one_row_of_each()
        for model, (_module, words, _row) in _MODELS.items():
            with self.subTest(model=model):
                with self.assertRaises(UserError) as refused:
                    rows[model].sudo().write({"reason": "rewritten"})
                self.assertIn(words, str(refused.exception))
                self.assertIn("sudo", str(refused.exception))

    def test_a_delete_is_refused_under_sudo_in_the_models_own_words(self):
        _asset, rows = self._one_row_of_each()
        for model, (_module, words, _row) in _MODELS.items():
            with self.subTest(model=model):
                with self.assertRaises(UserError) as refused:
                    rows[model].sudo().unlink()
                self.assertIn(words, str(refused.exception))
                self.assertTrue(rows[model].exists())

    def test_a_hand_written_row_is_refused_in_the_models_own_words(self):
        asset, _rows = self._one_row_of_each()
        for model, (_module, _words, row_words) in _MODELS.items():
            with self.subTest(model=model):
                with self.assertRaises(UserError) as refused:
                    self.env[model].sudo().create(
                        self._hand_written(model, asset))
                self.assertIn(row_words, str(refused.exception))
                self.assertIn("cannot be created directly",
                              str(refused.exception))
                self.assertEqual(len(self._rows(model, asset)), 1)

    def test_one_models_flag_does_not_open_another(self):
        """The flag is per model, and sharing the guard must not have made
        it one key for three locks. `_record` sets its own model's flag and
        then writes as sudo — so a flag that opened all three would let the
        context of a genuine custody change carry a hand-written event in
        with it."""
        asset, _rows = self._one_row_of_each()
        for model in _MODELS:
            others = {key: True for owner, key in _APPEND_KEYS.items()
                      if owner != model}
            with self.subTest(model=model):
                self.assertEqual(self.env[model]._append_key,
                                 _APPEND_KEYS[model])
                with self.assertRaises(UserError):
                    self.env[model].sudo().with_context(**others).create(
                        self._hand_written(model, asset))
                self.assertEqual(len(self._rows(model, asset)), 1)


@tagged("post_install", "-at_install")
class TestOneRuleAboutLabels(AppendOnlyCase):
    """`test` says a row is an artefact and `tracking_backfill` says it is a
    reconstruction. Both are statements about the EVIDENCE, and a context is
    something an RPC caller supplies — so neither may be claimed through
    one, on any of the three. Custody's copy of this rule was the one that
    did not hold."""

    def test_a_claimed_label_is_direct_on_all_three(self):
        for claimed in ("test", "tracking_backfill"):
            asset = self._asset(custodian_id=self.alice.id,
                                location_id=self.room.id)
            # One write that moves custody, moves the asset and changes its
            # status, with the label claimed on all three keys at once.
            asset.with_context(
                cadra_approval_exempt="test",
                **{key: claimed for key in _SOURCE_KEYS.values()}
            ).write({"custodian_id": self.bob.id,
                     "location_id": self.elsewhere.id,
                     "state": "missing"})
            for model in _MODELS:
                with self.subTest(claimed=claimed, model=model):
                    self.assertEqual(
                        self._rows(model, asset)[-1].source, "direct",
                        "a caller filed a real change on %s under `%s`"
                        % (model, claimed))

    def test_nothing_a_caller_may_claim_is_a_statement_about_the_evidence(
            self):
        """Read off each model, so a source added to a `_context_sources`
        later is checked here on the day it is added."""
        for model, key in _SOURCE_KEYS.items():
            Model = self.env[model]
            published = dict(Model._fields["source"].selection)
            with self.subTest(model=model):
                self.assertEqual(Model._source_key, key)
                self.assertFalse(
                    {"test", "tracking_backfill"}
                    & set(Model._context_sources))
                self.assertLessEqual(
                    set(Model._context_sources), set(published),
                    "a claimable source that is not a published value "
                    "would fail the row, not label it")
                self.assertIn("direct", Model._context_sources)

    def test_custody_lets_a_caller_claim_exactly_what_it_did_before(self):
        """Pinned, because custody is the model whose behaviour CHANGED by
        adopting the mixin: its own `_resolve_source` took anything. These
        were the four its routes and `nrs.asset.transfer` declare; a fifth
        is a decision, not a convenience.

        **`approval` is that fifth, and it was a decision** — handoff 35.
        `nrs.asset.change.request.action_approve` declares it while it writes
        the asset, so a link written because a second person agreed does not
        read as an anonymous direct edit. It is claimable from the context
        like the other four, which is safe for the same reason they are: it
        is a statement about HOW the change was asked for, not about the
        evidence. The two labels that ARE statements about the evidence —
        `test` and `tracking_backfill` — are still unclaimable, which
        `test_nothing_a_caller_may_claim_is_a_statement_about_the_evidence`
        asserts by reading `_context_sources` off the model.

        The pin stays a pin: a sixth is the next person's decision to argue
        for, in a docstring, here."""
        self.assertEqual(
            tuple(self.env["nrs.asset.custody"]._context_sources),
            ("api_transfer", "api_write", "transfer", "approval", "direct"))

    def test_first_party_code_may_still_say_a_row_is_a_reconstruction(self):
        """Refused from the CONTEXT, accepted as an ARGUMENT: the backfill
        passes `source=` explicitly, and that is first-party code. Asked of
        `_resolve_source` itself rather than by writing a row, because the
        event record publishes no such value and the rule is the same rule
        whether or not a model has a use for it yet."""
        for model in _MODELS:
            with self.subTest(model=model):
                Model = self.env[model]
                self.assertEqual(
                    Model._resolve_source("tracking_backfill", self.env.user),
                    "tracking_backfill")
                self.assertEqual(tuple(Model._never_relabelled),
                                 ("tracking_backfill",))
