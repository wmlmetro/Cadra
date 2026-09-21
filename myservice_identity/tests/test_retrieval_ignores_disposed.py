"""A disposed asset is not outstanding. Handoff 31 §C4.

When an employee leaves, everything they hold is flagged for retrieval and
their clearance stays open — `has_pending_retrieval` — until each flagged
asset has been handed back. Two things were wrong with a DISPOSED asset in
that list, and the second made the first permanent:

    1. It left the estate. There is nothing to hand back, and a leaver's
       clearance list that names a laptop scrapped two years ago is asking
       them to return something the register itself says is gone.
    2. Since handoff 30 it could never be cleared. *Mark retrieved* clears
       the custodian, and a disposed asset keeps whoever held it when it was
       disposed of — the register refuses that write. So an asset flagged and
       THEN disposed would have held a clearance open for ever, with the only
       button that closes it raising an error.

The ruling was to widen into this module far enough to stop the flag, and no
further: the asset keeps its custodian, the flag already on a disposed asset
is left where it is as a fact about what happened, and only what COUNTS as
pending changed.

Run with:
    odoo -d <db> -u myservice_identity --test-enable \\
         --test-tags /myservice_identity --stop-after-init
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestRetrievalIgnoresDisposedAssets(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Retrieval test category"})
        self.leaver = self.env["hr.employee"].create(
            {"name": "Retrieval Leaver"})

    def _asset(self, name, **vals):
        return self.Asset.create(dict(
            {"name": name, "category_id": self.category.id,
             "custodian_id": self.leaver.id}, **vals))

    def _disposed(self, name):
        """Disposed of WHILE HELD, which is the ordinary case: the asset
        keeps its custodian, by the terminal rule, so it stays in
        `nrs_asset_ids` for good."""
        asset = self._asset(name)
        asset.action_condemn(reason="beyond economic repair")
        self.assertEqual(asset.state, "disposed")
        self.assertEqual(asset.custodian_id, self.leaver)
        return asset

    # ── the exit ─────────────────────────────────────────────────────

    def test_an_exit_flags_what_is_held_and_not_what_is_gone(self):
        live = self._asset("Retrieval live laptop")
        gone = self._disposed("Retrieval scrapped laptop")
        # The subject is asserted, not assumed: the disposed asset is still
        # recorded against the leaver, which is why it was ever in question.
        self.assertEqual(self.leaver.nrs_asset_ids, live | gone)

        self.leaver.action_flag_retrieval()

        self.assertTrue(live.retrieval_flag)
        self.assertEqual(live.retrieval_reason, "employee_exit")
        self.assertFalse(
            gone.retrieval_flag,
            "a disposed asset was put on a leaver's clearance list")
        self.assertFalse(gone.retrieval_reason)
        self.assertEqual(gone.custodian_id, self.leaver)
        self.assertTrue(self.leaver.has_pending_retrieval)

    def test_every_other_status_is_still_flagged(self):
        """Only `disposed` is exempt. A MISSING asset in particular is
        exactly what a leaver should be asked about."""
        held = {
            state: self._asset("Retrieval %s asset" % state, state=state)
            for state in ("active", "in_repair", "missing", "transferred")}
        self.leaver.action_flag_retrieval()
        for state, asset in held.items():
            with self.subTest(state=state):
                self.assertTrue(asset.retrieval_flag)

    def test_a_leaver_who_holds_only_disposed_assets_has_nothing_pending(
            self):
        self._disposed("Retrieval scrapped desk")
        self._disposed("Retrieval scrapped chair")
        self.leaver.action_flag_retrieval()
        self.assertFalse(self.leaver.has_pending_retrieval)

    # ── flagged, and THEN disposed ───────────────────────────────────

    def test_a_flagged_asset_that_is_then_disposed_stops_being_pending(self):
        """The case that would have been permanent. The flag is set while
        the asset is live; the asset is then written off; the clearance
        must close WITHOUT anybody touching the flag — `state` is a
        dependency of the stored compute, which is what is proved here."""
        asset = self._asset("Retrieval flagged then scrapped")
        self.leaver.action_flag_retrieval()
        self.assertTrue(asset.retrieval_flag)
        self.assertTrue(self.leaver.has_pending_retrieval)

        asset.action_condemn(reason="written off after the exit")

        self.assertTrue(
            asset.retrieval_flag,
            "the flag is a fact about what happened and is left standing; "
            "what changed is whether it counts")
        self.assertFalse(
            self.leaver.has_pending_retrieval,
            "a disposed asset is holding a leaver's clearance open")
        # Read from the COLUMN as well: the field is stored, and a list
        # view filtered on it reads the row, not the cache.
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT has_pending_retrieval FROM hr_employee WHERE id = %s",
            (self.leaver.id,))
        self.assertFalse(self.env.cr.fetchone()[0])

    def test_a_disposal_by_a_bare_write_closes_it_too(self):
        """The compute depends on `state`, not on which door changed it."""
        asset = self._asset("Retrieval flagged then PATCHed")
        self.leaver.action_flag_retrieval()
        asset.write({"state": "disposed"})
        self.assertFalse(self.leaver.has_pending_retrieval)

    def test_the_live_asset_beside_it_still_holds_the_clearance_open(self):
        """The control: the rule is about DISPOSED, not about flags. A live
        flagged asset still holds the clearance open after a DIFFERENT asset
        is condemned — and closes it the ordinary way."""
        live = self._asset("Retrieval live phone")
        scrapped = self._asset("Retrieval scrapped phone")
        self.leaver.action_flag_retrieval()
        scrapped.action_condemn(reason="written off")
        self.assertTrue(self.leaver.has_pending_retrieval)

        live.action_mark_retrieved()
        self.assertFalse(self.leaver.has_pending_retrieval)

    def test_the_last_one_outstanding_being_condemned_closes_the_clearance(
            self):
        """The same two assets in the OTHER order, which is the order it
        happens in: flagged on the day they left, the laptop handed back,
        and the one nobody could find condemned the week after. The
        recompute is then triggered by `state` on the last outstanding
        asset, with nothing else left to move."""
        live = self._asset("Retrieval returned laptop")
        other = self._asset("Retrieval never-returned laptop")
        self.leaver.action_flag_retrieval()
        self.assertTrue(self.leaver.has_pending_retrieval)

        live.action_mark_retrieved()
        self.assertTrue(
            self.leaver.has_pending_retrieval,
            "the other flagged asset is still outstanding")

        other.action_condemn(reason="written off after the exit")
        self.assertFalse(
            self.leaver.has_pending_retrieval,
            "a disposed asset is holding a leaver's clearance open, and "
            "nothing can ever clear it")

    def test_why_it_could_never_have_been_cleared(self):
        """The second half of the argument, pinned so that nobody "fixes"
        §C4 by pointing people at the button: *Mark retrieved* clears the
        custodian, and the register refuses that on a disposed asset."""
        asset = self._asset("Retrieval uncloseable")
        self.leaver.action_flag_retrieval()
        asset.action_condemn(reason="written off")
        with self.assertRaises(UserError):
            asset.action_mark_retrieved()
        self.assertEqual(asset.custodian_id, self.leaver)
