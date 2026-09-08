"""Every scheduled action in this database calls a method that exists.

**The defect this exists for arrived as a database row, not as source.**

Handoff 08 found two `ir.cron` rows on `nrs19` and `jaizbankplc` scheduling
`nrs.asset.pm._cron_refresh_overdue()` and `nrs.asset._cron_refresh_verification()`.
Both methods existed — in commit `c673ed1` on `feat/rfp-phase1-authorisation`,
a branch that was never merged. Those two databases had been upgraded from it.
The rows survived; the code did not. On `dev` the crons named methods that were
nowhere in the tree, and the first scheduler tick after handoff 08's fix would
have raised `AttributeError` on both, on both tenants, every day.

`tests/test_source_guards.py::test_every_scheduled_method_exists` reads the XML
we ship and could never have caught this: on the branch where those crons were
written, the XML and the Python were perfectly consistent. What was inconsistent
was one database against one checkout. **Only a test that walks `ir.cron` in a
live registry can see that**, and this is that test.

It is deliberately narrow — it does not run any cron, and it does not care what
a cron does. It asks one question of every row: if the scheduler picked this up
right now, would the call resolve? That is the question the two orphans failed.

Run with:
    odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_nrs_base \\
         --test-enable --stop-after-init --http-port=8099 --gevent-port=8098
"""
import ast

from odoo.tests import TransactionCase, tagged

# The names a `state='code'` server action is evaluated with, and what each one
# is bound to, from ir_actions.py::IrActionsServer._get_eval_context:
#
#     model   = self.env[action.model_id.model]
#     record  = model.browse(active_id)      -- same model
#     records = model.browse(active_ids)     -- same model
#     env     = self.env
#
# Anything else in that namespace (`log`, `datetime`, `Command`, `UserError`,
# ...) is not a recordset and is not resolved here.
_MODEL_NAMES = ("model", "record", "records")

# Recordset methods that return a recordset of the SAME model, so a call
# chained off one of them can still be resolved against that model. Without
# this, the extremely common `model.sudo()._do_the_thing()` would be written off
# as unresolvable and the guard would quietly cover less than it appears to.
_CHAINABLE = frozenset({
    "sudo", "with_context", "with_user", "with_company", "with_env",
    "browse", "search", "exists", "filtered", "filtered_domain", "sorted",
    "mapped", "with_prefetch",
})


@tagged("post_install", "-at_install")
class TestScheduledActions(TransactionCase):

    # ── the walker, shared by the guard and by its own proof ─────────────

    def _cron_problems(self, crons):
        """Return (problems, resolved_count) for a recordset of ir.cron.

        `problems` is a list of human-readable strings, one per defect, so the
        caller can report all of them in a single assertion. `resolved_count` is
        how many attribute calls were actually checked against a live model — a
        walker that resolves nothing reports no problems and would otherwise
        pass forever.

        The code is parsed with `ast`, never evaluated. Running a cron's body to
        find out whether it resolves would post events, send mail and write to
        eight tenants' data; the question here is answerable statically.
        """
        problems = []
        resolved = 0

        for cron in crons:
            action = cron.ir_actions_server_id
            xmlid = self._xmlid(cron)
            label = "%s (id=%s%s)" % (
                cron.cron_name or action.name or "<unnamed>",
                cron.id,
                ", xmlid=%s" % xmlid if xmlid else "",
            )

            if action.state != "code":
                # Non-code server actions (object_write, webhook, multi, ...)
                # name no method; there is nothing to resolve.
                continue

            # Defensive, and deliberately not covered by a fixture below:
            # ir.actions.server.model_id is required=True and therefore NOT
            # NULL, so this state cannot be constructed through the ORM. It is
            # checked because _get_eval_context binds `model` from it before
            # the body is evaluated, so if it ever IS null — a hand-written SQL
            # fix, a botched restore — the cron raises with nothing in the
            # message naming which cron it was.
            model_name = action.model_id.model if action.model_id else None
            if not model_name:
                problems.append(
                    "%s: state='code' but no model_id — the eval context binds "
                    "`model` from action.model_id.model, so this raises before "
                    "the body runs" % label)
                continue
            if model_name not in self.env:
                problems.append(
                    "%s: model %r is not in the registry (its module is not "
                    "installed on this database)" % (label, model_name))
                continue

            code = action.code or ""
            try:
                tree = ast.parse(code)
            except SyntaxError as exc:
                problems.append("%s: code does not parse — %s" % (label, exc))
                continue

            target = self.env[model_name]
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                root = self._resolve_root(node.func.value)
                if root is None:
                    continue  # not statically resolvable; not a finding
                obj = target if root in _MODEL_NAMES else self.env
                attr = node.func.attr
                resolved += 1
                if not hasattr(obj, attr):
                    problems.append(
                        "%s: model %s has no attribute %r (called as %s.%s())"
                        % (label, model_name, attr, root, attr))

        return problems, resolved

    def _resolve_root(self, node):
        """Name at the root of an attribute chain, if it is one we can resolve.

        `model._foo()`                     -> "model"
        `model.sudo()._foo()`              -> "model"   (sudo preserves model)
        `env.ref(...)`                     -> "env"
        `self.pool.something()`            -> None      (not in the namespace)
        `some_var._foo()`                  -> None      (bound at runtime)
        """
        while True:
            if isinstance(node, ast.Name):
                name = node.id
                return name if name in _MODEL_NAMES or name == "env" else None
            # `model.sudo()._foo()` — step through the chained call.
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _CHAINABLE):
                node = node.func.value
                continue
            return None

    def _xmlid(self, cron):
        data = self.env["ir.model.data"].sudo().search(
            [("model", "=", "ir.cron"), ("res_id", "=", cron.id)], limit=1)
        return "%s.%s" % (data.module, data.name) if data else ""

    # ── the guard ────────────────────────────────────────────────────────

    def test_every_scheduled_action_in_this_database_resolves(self):
        """No ir.cron row schedules a method that does not exist.

        **Inactive crons are checked too, and a broken one fails the test.**
        Exempting them would blind the guard exactly where it matters most:
        Odoo's own scheduler DEACTIVATES a cron after repeated failures
        (`ir_cron.py`, MIN_FAILURE_COUNT_BEFORE_DEACTIVATION), so `active=False`
        is the state a broken cron ends up in, not a state that proves it is
        harmless. A row is also one checkbox in Settings → Technical away from
        running, and nothing about that checkbox records why it was off. If a
        cron is genuinely retired, delete it — that was handoff 08's ruling on
        the two orphans, and the reason it did not deactivate them instead.
        """
        crons = self.env["ir.cron"].sudo().with_context(
            active_test=False).search([])
        self.assertTrue(crons, "no ir.cron rows at all — the walk proves nothing")

        problems, resolved = self._cron_problems(crons)

        self.assertGreater(
            resolved, 0,
            "the walker resolved zero calls across %d crons — it is not "
            "checking anything, so a green result means nothing" % len(crons))

        self.assertFalse(
            problems,
            "%d of %d scheduled actions do not resolve against the live "
            "registry (%d calls checked):\n  - %s"
            % (len(problems), len(crons), resolved, "\n  - ".join(problems)))

    def test_the_guard_reports_a_cron_whose_method_does_not_exist(self):
        """Prove the guard has teeth, without breaking a real cron.

        A guard that walks a healthy registry and finds nothing is
        indistinguishable from a guard whose walker is broken — a typo in the
        namespace names, an ast node shape it never matches, an exception
        swallowed somewhere. So construct the exact defect handoff 08 found (a
        cron row naming a method that is not in the code) inside the test
        transaction, and assert the walker names it.

        The row is created and rolled back with the test; no real cron is
        touched and nothing is left behind. The two chained variants are here
        because `model.sudo()._foo()` is how most of our own crons would be
        written, and a walker that only understood the bare form would cover
        far less than its green result implies.
        """
        model = self.env["ir.model"]._get("ir.cron")

        def _fake(code):
            return self.env["ir.cron"].create({
                "name": "Cadra guard fixture",
                "model_id": model.id,
                "state": "code",
                "code": code,
                "interval_number": 1,
                "interval_type": "days",
                "active": False,
            })

        bare = _fake("model._cadra_method_that_does_not_exist()")
        chained = _fake("model.sudo()._cadra_other_missing_method()")
        healthy = _fake("model._cadra_disable_third_party_crons()")

        problems, resolved = self._cron_problems(bare | chained | healthy)

        self.assertEqual(
            resolved, 4,
            "expected 4 resolvable calls (1 bare + sudo() + its chained call + "
            "1 healthy), got %d" % resolved)
        self.assertEqual(
            len(problems), 2,
            "expected exactly the two fabricated defects, got:\n  - %s"
            % "\n  - ".join(problems))
        joined = "\n".join(problems)
        self.assertIn("_cadra_method_that_does_not_exist", joined)
        self.assertIn("_cadra_other_missing_method", joined)
        self.assertNotIn("_cadra_disable_third_party_crons", joined,
                         "the healthy cron must not be reported")
