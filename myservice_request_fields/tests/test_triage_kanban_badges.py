"""A breached request is not less urgent for having breached.

The triage kanban card carried its two status badges as one `t-if` / `t-elif`
chain: "Breached" first, "Urgent" second. A chain answers ONE question, and
these are two — a deadline (has this run out of time?) and a priority (how much
does it matter?). They are independent facts about a request, so chaining them
meant the card dropped "Urgent" from exactly the records that had both, which
is the moment the word carries the most information. A triage board exists to
be scanned; a Critical request that has also breached looked, at a glance,
identical to a Low one that had.

These tests guard the split in two ways, because either alone passes for the
wrong reason:

  * structurally — the "Urgent" badge sits under its own `t-if` whose
    condition does not mention `sla_breached`, and no badge anywhere in the
    card hangs off a `t-elif` chained behind the breach test. This catches a
    re-chaining, including one arriving through an inheriting view.
  * behaviourally — the conditions are lifted verbatim out of the shipped arch
    and walked THE WAY QWEB WALKS THEM (a `t-elif` is skipped when its chain
    already took a branch) over a real request that has breached its SLA and
    is marked Critical. Evaluating the two conditions in isolation would not
    do: both are true of that request even in the broken arch. Only honouring
    the chain makes the missing badge visible.

Both halves are regression guards, checked against the pre-fix arch: three of
the five tests here fail on it and pass on the fix.

What they do NOT prove: that a browser paints two badges. That needs an Owl
render, which is a tour, not a unit test. And the walk evaluates the shipped
expressions as PYTHON, an approximation of the QWeb/JS the browser runs — safe
only for the subset these conditions use (attribute access, `==` on string
literals, `or`). Anything outside it raises here rather than passing quietly;
see `_evaluate`.

Run with:
    odoo -d <db> -u myservice_request_fields --test-enable \\
         --test-tags /myservice_request_fields --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
from datetime import timedelta

from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tests.common import freeze_time


class _KanbanValue:
    """One field as the kanban record proxy exposes it: `.raw_value`."""

    def __init__(self, raw_value):
        self.raw_value = raw_value


class _KanbanRecord:
    """`record` as a kanban template sees it — `record.<field>.raw_value`.

    Only the handful of fields the badge conditions read are populated; an
    expression reaching for anything else raises rather than quietly
    evaluating to a falsy default, which is the point.
    """

    def __init__(self, rec, field_names):
        for name in field_names:
            setattr(self, name, _KanbanValue(rec[name]))


@tagged("post_install", "-at_install")
class TestTriageKanbanBadges(TransactionCase):

    XMLID = "myservice_request_fields.view_request_triage_kanban"

    def setUp(self):
        super().setUp()
        self.Request = self.env["request.request"]

    # ── reading the arch ─────────────────────────────────────────────────────

    def _arch(self):
        """The COMBINED arch, not the record's stored one.

        `get_view` applies every inheriting view, so a later `xpath` that
        re-chains the badges — in this module or a downstream brand module —
        fails these tests. Reading `ir.ui.view.arch_db` off the record would
        see only what this file ships and would call that proof.
        """
        view = self.env.ref(self.XMLID)
        arch = self.Request.get_view(view.id, "kanban")["arch"]
        return etree.fromstring(arch.encode("utf-8"))

    def _badge_conditional(self, root, label):
        """The nearest enclosing conditional around the badge reading `label`.

        Found by locating the badge itself and walking UP to the first node
        carrying a condition — not by scanning for `<t>` elements that contain
        the text, which also matches `t-name="kanban-box"` and every other
        wrapper on the way to the root.

        Fails rather than returns None when the badge cannot be found: a
        locator that silently matches nothing turns every assertion below into
        a no-op, which is the failure mode this repo watches for.
        """
        spans = [span for span in root.iter("span")
                 if (span.text or "").strip() == label]
        self.assertEqual(
            len(spans), 1,
            "expected exactly one %r badge in the triage kanban; found %d. If "
            "the badge was renamed, rename it here too — these tests cannot "
            "guard a badge they cannot find." % (label, len(spans)))

        node = spans[0]
        while node is not None:
            if self._condition(node)[0]:
                return node
            node = node.getparent()
        self.fail("the %r badge renders unconditionally — it has no `t-if` at "
                  "all, so these tests have nothing to check" % label)

    @staticmethod
    def _condition(node):
        """The node's condition and which attribute carried it."""
        for attr in ("t-if", "t-elif"):
            if attr in node.attrib:
                return attr, " ".join(node.attrib[attr].split())
        return None, None

    # ── the regression this file exists for ──────────────────────────────────

    def test_the_urgent_badge_does_not_hang_off_the_breach_test(self):
        """The two badges answer two questions, so they take two conditions.

        Read against the COMBINED arch, so a re-chaining arriving through an
        inheriting view fails here too.
        """
        root = self._arch()
        breached = self._badge_conditional(root, "Breached")
        urgent = self._badge_conditional(root, "Urgent")

        breached_attr, breached_cond = self._condition(breached)
        urgent_attr, urgent_cond = self._condition(urgent)

        self.assertEqual(breached_attr, "t-if")
        self.assertIn("sla_breached", breached_cond)

        self.assertEqual(
            urgent_attr, "t-if",
            "the Urgent badge must stand on its own `t-if`. As a `t-elif` it "
            "renders only when the request has NOT breached, so a request "
            "that is both breached and Critical shows one badge and the "
            "board cannot tell it from a breached Low one.")
        self.assertNotIn(
            "sla_breached", urgent_cond,
            "urgency must not be a function of the deadline: %s" % urgent_cond)

        self.assertIs(
            urgent.getparent(), breached.getparent(),
            "both badges must sit in the same container so both can render")

    def test_no_badge_is_chained_behind_the_breach_test(self):
        """The general form of the ruling, independent of any badge's text.

        A future badge added as a `t-elif` after the breach test would be
        invisible on breached cards for the same reason "Urgent" was. Rungs
        that genuinely answer the same question as their `t-if` are still
        allowed — this only forbids chaining behind `sla_breached`, which is
        an answer to a different question from anything else on the card.
        """
        root = self._arch()
        offenders = []
        for node in root.iter():
            attrib = getattr(node, "attrib", {})
            if "t-elif" not in attrib and "t-else" not in attrib:
                continue
            # Walk back to the `t-if` that opened this chain, stepping over
            # the other `t-elif` rungs and any comments between them.
            previous = node.getprevious()
            while previous is not None:
                attr, cond = self._condition(previous)
                if attr == "t-if":
                    if "sla_breached" in cond:
                        offenders.append(
                            etree.tostring(node, encoding="unicode")[:200])
                    break
                previous = previous.getprevious()
        self.assertFalse(
            offenders,
            "these branches are unreachable whenever a request has breached, "
            "which is when the card matters most: %s" % offenders)

    def _rendered_badges(self, root, record):
        """The badge labels a QWeb engine would emit for `record`, in order.

        This walks the badge container the way QWeb does — evaluating each
        `t-if`, and skipping a `t-elif` whose chain already took a branch —
        rather than evaluating the two conditions in isolation. That
        distinction is the whole point: read on their own, both conditions are
        true of a breached Critical request even in the BROKEN arch. Only by
        honouring the chain does the missing badge become visible.

        Comments are transparent: they neither render nor break a chain.
        """
        container = self._badge_conditional(root, "Breached").getparent()
        rendered = []
        chain_taken = None
        for node in container:
            attrib = getattr(node, "attrib", {})
            if "t-if" in attrib:
                show = self._evaluate(
                    " ".join(attrib["t-if"].split()), record)
                chain_taken = show
            elif "t-elif" in attrib:
                show = (not chain_taken) and self._evaluate(
                    " ".join(attrib["t-elif"].split()), record)
                chain_taken = chain_taken or show
            elif "t-else" in attrib:
                show = not chain_taken
                chain_taken = True
            else:
                continue
            if show:
                rendered.extend(
                    (span.text or "").strip() for span in node.iter("span")
                    if (span.text or "").strip())
        return rendered

    def _proxy(self, priority_display):
        """A request that has breached its SLA, at the given priority."""
        rec = self.Request.create({
            "name": "New",
            "sla_tier": "low",  # low == a 24-hour deadline
            "priority_display": priority_display,
        })
        rec.flush_recordset()
        return rec

    def test_a_breached_and_critical_request_shows_BOTH_badges(self):
        """The regression, stated as behaviour rather than as structure.

        A structural assertion says the arch is shaped right; this says the
        card is. It walks the real chain over a real record that has breached
        its SLA and is marked Critical, and requires both words to survive —
        which on the `t-elif` arch this replaces they did not.
        """
        root = self._arch()
        rec = self._proxy("3")  # Critical

        with freeze_time(rec.sla_deadline + timedelta(minutes=1)):
            self.Request._cron_refresh_sla_breached()
            self.assertTrue(rec.sla_breached, "fixture must be breached")
            self.assertEqual(rec.priority_display, "3",
                             "fixture must be Critical")

            self.assertEqual(
                self._rendered_badges(
                    root,
                    _KanbanRecord(rec, ("sla_breached", "priority_display"))),
                ["Breached", "Urgent"],
                "a breached Critical request must carry BOTH badges, breached "
                "first. Exactly one badge here means the two have been chained "
                "again and the board can no longer tell a breached Critical "
                "request from a breached Low one.")

    def test_a_breached_but_low_priority_request_shows_only_breached(self):
        """Splitting the chain must not turn one badge into a badge on
        everything. `Urgent` still means high priority and nothing else."""
        root = self._arch()
        rec = self._proxy("0")  # Low

        with freeze_time(rec.sla_deadline + timedelta(minutes=1)):
            self.Request._cron_refresh_sla_breached()
            self.assertTrue(rec.sla_breached)
            self.assertEqual(
                self._rendered_badges(
                    root,
                    _KanbanRecord(rec, ("sla_breached", "priority_display"))),
                ["Breached"],
                "a Low request must not be labelled Urgent for breaching")

    def test_an_urgent_request_inside_its_window_shows_only_urgent(self):
        """The other side of the independence: urgency does not wait on a
        deadline. This one never passed through the breach branch at all, so
        it is the case the old chain got right — it is here to stay right."""
        root = self._arch()
        rec = self._proxy("2")  # High

        self.assertFalse(rec.sla_breached, "fixture must still be in time")
        self.assertEqual(
            self._rendered_badges(
                root,
                _KanbanRecord(rec, ("sla_breached", "priority_display"))),
            ["Urgent"])

    # ── evaluating a template expression ─────────────────────────────────────

    def _evaluate(self, expression, record):
        """Evaluate a kanban condition as Python.

        These conditions are attribute access, `==` on string literals and
        `or` — spelled identically in the QWeb/JS the browser runs and in
        Python. That overlap is what makes this test possible and it is not
        guaranteed: a condition rewritten with `&&`, `!` or a ternary raises
        here and fails the test loudly. That is the intended outcome. It is a
        signal to re-express the condition or to replace this evaluation with
        a real render, never to weaken the assertion into a skip.
        """
        try:
            return bool(eval(expression, {"__builtins__": {}},
                             {"record": record}))
        except SyntaxError as exc:
            self.fail(
                "the badge condition %r is no longer valid Python, so this "
                "test can no longer evaluate what the browser evaluates: %s"
                % (expression, exc))
