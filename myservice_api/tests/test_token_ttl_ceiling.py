"""A raised limit may not outlive the decision to lower it again.

Handoff 14 C. Handoff 13 B1 made a reduced pagination limit revoke the
client's refresh families, so the family stops re-minting under the old
ceiling immediately. It left one thing open and said so: the cap is a claim
inside the access JWT, and an access token is unrevocable for its lifetime
by design. Between the moment somebody lowers a limit and the moment the
last token minted under the old one expires, the withdrawn limit is still
in force.

That window cannot be closed. It can be BOUNDED — and the bound is the
TTL. Every client on every tenant carries 3600 today, which is the width
the ruling itself calls acceptable; the 86400 a client can be configured
with is not. So a client whose limits differ from the default is refused a
TTL above an hour, at save, with a message saying why.

The default case (both limits 0) is deliberately untouched: the ceiling
exists to bound a decision, and where no limit has been raised no decision
has been made. This is why the first test below matters as much as the
refusals — it is the proof that nothing in production changes today.
"""
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestTokenTtlCeiling(CadraTransactionCase):

    def _make(self, suffix, **overrides):
        vals = {"name": f"ttl ceiling probe {suffix}",
                "client_id": f"ttlprobe_{suffix}",
                "scopes": "assets:read"}
        vals.update(overrides)
        record = self.create_api_client(vals)
        record.flush_recordset()
        return record

    def _refuses(self, record, vals):
        """Write `vals` and require the constraint to stop it.

        The write happens inside a savepoint so the rollback that a failed
        constraint implies actually happens here rather than poisoning the
        rest of the test; the savepoint is INSIDE assertRaises so it rolls
        back first and re-raises for the assertion to catch.
        """
        with self.assertRaises(ValidationError) as caught, self.env.cr.savepoint():
            record.write(vals)
            record.flush_recordset()
        return str(caught.exception)

    # ── Nothing changes today ─────────────────────────────────────────

    def test_default_limits_carry_no_ceiling_at_all(self):
        """Both limits at 0 is the external default and is not a decision.

        If this ever fails, the change is no longer invisible to the eight
        tenants that are all sitting on 0/0 — which was the whole basis for
        accepting it.
        """
        record = self._make("default", token_ttl_seconds=86400)
        self.assertEqual(record.token_ttl_seconds, 86400)

    def test_the_shape_every_tenant_actually_has_still_saves(self):
        """`vendra` on nrs19: total_record_cap -1, token_ttl_seconds 3600.

        Measured before this constraint was written. A rule that rejects a
        row already in production is not a bound, it is an outage.
        """
        record = self._make("livelike", total_record_cap=-1,
                            token_ttl_seconds=3600)
        self.assertEqual(record.total_record_cap, -1)
        self.assertEqual(record.token_ttl_seconds, 3600)

    def test_exactly_the_ceiling_is_allowed(self):
        record = self._make("atceiling", max_page_limit=500)
        record.write({"token_ttl_seconds": 3600})
        record.flush_recordset()
        self.assertEqual(record.token_ttl_seconds, 3600)

    # ── The refusals ──────────────────────────────────────────────────

    def test_a_raised_page_limit_refuses_a_two_hour_token(self):
        record = self._make("page", max_page_limit=500)
        message = self._refuses(record, {"token_ttl_seconds": 7200})
        self.assertIn("3600", message)
        self.assertIn("7200", message)
        self.assertIn("500", message)
        self.assertIn("outlives the decision to lower it again", message)

    def test_uncapped_is_a_non_default_limit_not_an_exemption(self):
        """-1 with a 24-hour token is the indefensible case, not the
        excused one: an unbounded view of the register on a credential
        nobody can call back until tomorrow."""
        record = self._make("uncapped", total_record_cap=-1)
        message = self._refuses(record, {"token_ttl_seconds": 7200})
        self.assertIn("-1", message)

    def test_a_lowered_limit_is_still_a_non_default_one(self):
        """The ceiling is not "a limit above the default" — it is "a limit
        somebody chose". A cap of 10 is a decision like any other."""
        record = self._make("narrow", total_record_cap=10)
        self._refuses(record, {"token_ttl_seconds": 7200})

    def test_it_refuses_on_create_too(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._make("oncreate", max_page_limit=250,
                       token_ttl_seconds=86400)

    # ── Whichever field is written last ───────────────────────────────

    def test_the_ttl_may_not_be_raised_first_and_the_limit_second(self):
        """The order the operator happens to use is not a loophole.

        Raising the TTL on a defaulted client is legal, so the write goes
        through; the constraint has to fire on the LIMIT write afterwards,
        which it only does because all three fields are in the trigger
        list. Trigger on token_ttl_seconds alone and this passes silently.
        """
        record = self._make("orderb", token_ttl_seconds=7200)
        self.assertEqual(record.token_ttl_seconds, 7200,
                         "the setup write must succeed, or the assertion "
                         "below proves nothing")
        message = self._refuses(record, {"max_page_limit": 500})
        self.assertIn("7200", message)

    def test_it_fires_when_both_move_in_one_write(self):
        record = self._make("together")
        self._refuses(record, {"max_page_limit": 500,
                               "token_ttl_seconds": 7200})

    def test_returning_the_limits_to_the_default_releases_the_ceiling(self):
        """The bound follows the decision. Withdraw the raised limit and
        the client is an ordinary one again."""
        record = self._make("released", max_page_limit=500)
        self._refuses(record, {"token_ttl_seconds": 7200})
        record.write({"max_page_limit": 0, "token_ttl_seconds": 7200})
        record.flush_recordset()
        self.assertEqual(record.token_ttl_seconds, 7200)
