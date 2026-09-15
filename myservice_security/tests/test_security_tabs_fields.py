"""Every search_read in security_tabs.js names a model and fields that exist.

The guarantee:

    For each `rpc.query({model: X, method: 'search_read', ... fields: [...],
    order: '...'})` in myservice_security/static/src/js/security_tabs.js,
    X resolves in the registry and every name in `fields` and in `order`
    is a field on X.

Why this has to be an in-registry test and not a source guard
-------------------------------------------------------------
The defect is a mismatch between two files that never mention each other: a
JavaScript literal on one side and a Python field declaration on the other.
Nothing in the JS is wrong when read on its own — 'shift_start' is a
perfectly good string — and nothing in security_guard.py is wrong either.
Only the registry knows that security.guard has no such field, so only a
test that has a registry can see it. Grepping the models directory would
also miss every related, inherited and mail.thread field, and would then
have to be taught which of those are real; fields_get() already knows.

Why it matters more than a blank column
---------------------------------------
search_read validates the whole `fields` list before it reads anything, so
ONE absent name raises for the entire call. The tab does not render that
column empty — the promise never resolves, the `.then` never runs, and the
panel sits on its "Loading..." placeholder for ever with an error in the
browser console nobody is watching. Handoff 09 open question 4 found one
such name; a live-registry audit found seven more across three tabs, plus
six models that no longer exist at all.

`order` is checked for the same reason: an ORDER BY naming an absent column
raises out of the same call, so an order clause left pointing at a renamed
field breaks the tab just as completely as the field list does.

Deliberately NOT covered: security_dashboard.js
------------------------------------------------
Its sibling static/src/js/security_dashboard.js has the same class of
defect and worse — it reads security.watchlist, ai.pattern.alert,
acled.sync.log and security.osint.feed, none of which exist, and calls
/myservice/security/osint and /myservice/security/state_threats, neither of
which is a route in this module's controllers. Widening JS_PATH to that file
today would make this test red, so it is named here rather than left for the
next reader to assume it is covered. Neither file is in any asset bundle
(see __manifest__.py) and both are written in Odoo 15 `odoo.define` module
syntax, so nothing in either runs on 19 as things stand; that is a separate
decision from whether the code they contain is true.

Run with:
    odoo -d <db> -u myservice_security --test-enable \\
         --test-tags /myservice_security --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
import os
import re

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

JS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "src", "js", "security_tabs.js",
)

# The shape this parser assumes, and the only one the file uses:
#
#     rpc.query({
#         model: 'security.guard', method: 'search_read', args: [[]],
#         kwargs: {
#             fields: ['name', 'badge_number'],
#             limit: 50, order: 'name',
#         },
#     })
#
# `model:` and `method:` are adjacent and single-quoted; `fields:` is a
# single-quoted array literal and `order:` a single-quoted string, both
# somewhere after them and before the next `model:` in the file. Anything
# that does not match — a computed model name, a fields list built at
# runtime — is invisible to this test rather than silently accepted, which
# is what MIN_CALLS below is for.
CALL_RE = re.compile(
    r"model:\s*'(?P<model>[\w.]+)'\s*,\s*method:\s*'search_read'")
FIELDS_RE = re.compile(r"fields:\s*\[(?P<body>[^\]]*)\]", re.S)
ORDER_RE = re.compile(r"order:\s*'(?P<body>[^']*)'")
NAME_RE = re.compile(r"'([\w.]+)'")

# A parser that matches nothing passes every assertion it never makes. This
# is the floor the file is known to sit above; if a refactor drops it below,
# the test says so instead of going quietly green.
MIN_CALLS = 5


def _parse_calls(source):
    """Return [(model, [field names], [order names], char offset)]."""
    calls = []
    starts = [m for m in CALL_RE.finditer(source)]
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        region = source[match.end():end]
        fields_match = FIELDS_RE.search(region)
        fields = NAME_RE.findall(fields_match.group("body")) if fields_match else []
        order_match = ORDER_RE.search(region)
        order = []
        if order_match:
            for term in order_match.group("body").split(","):
                term = term.strip().split()
                if term:
                    order.append(term[0])
        calls.append((match.group("model"), fields, order, match.start()))
    return calls


@tagged("post_install", "-at_install")
class TestSecurityTabsFields(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        with open(JS_PATH, encoding="utf-8") as handle:
            self.source = handle.read()
        self.calls = _parse_calls(self.source)

    def _line_of(self, offset):
        return self.source.count("\n", 0, offset) + 1

    def test_the_parser_still_finds_the_calls_it_is_guarding(self):
        """A regex guard over someone else's file is only as real as its
        matches. If the file is rewritten in Odoo 19 module syntax the
        `rpc.query` shape will change, and this test must fail loudly rather
        than assert nothing about the new one."""
        self.assertGreaterEqual(
            len(self.calls), MIN_CALLS,
            "Parsed only %d search_read call(s) from %s. Either the calls "
            "were removed or the file no longer has the shape CALL_RE "
            "assumes — update the parser, do not lower MIN_CALLS."
            % (len(self.calls), JS_PATH))

    def test_every_search_read_names_a_model_that_exists(self):
        """A model absent from the registry is not a lesser version of a
        wrong field name — the RPC 500s before it reads anything.

        There is deliberately no allow-list of 'models that will come back'.
        Six such references were removed rather than excused (osint.feed.entry,
        osint.source.config, ai.pattern.alert, ai.daily.brief,
        security.watchlist, security.state.threat): they survive only as
        Odoo 15 CSV extracts under docs/upgrade/archive/, and a tab whose
        RPC can only raise is not a placeholder for one that will work.
        """
        missing = []
        for model, _fields, _order, offset in self.calls:
            if model not in self.env:
                installed = self.env["ir.module.module"].sudo().search_count(
                    [("state", "=", "installed")])
                missing.append(
                    "%s:%d references model %r, which is not in the registry "
                    "of database %r (%d modules installed). Either it is a "
                    "typo, or it belongs to a module this tenant does not "
                    "have — in which case the call needs a guard, not a "
                    "silent skip."
                    % (JS_PATH, self._line_of(offset), model,
                       self.env.cr.dbname, installed))
        self.assertFalse(missing, "\n".join(missing))

    def test_every_search_read_names_fields_that_exist(self):
        """search_read validates the whole fields list up front, so one bad
        name costs the entire tab, not one column."""
        problems = []
        for model, fields, _order, offset in self.calls:
            if model not in self.env:
                continue  # reported by the model test above
            known = set(self.env[model].fields_get().keys())
            self.assertTrue(fields, "%s:%d — %s search_read has no fields list"
                            % (JS_PATH, self._line_of(offset), model))
            bad = [name for name in fields if name not in known]
            if bad:
                problems.append(
                    "%s:%d — %s has no field(s): %s"
                    % (JS_PATH, self._line_of(offset), model, ", ".join(bad)))
        self.assertFalse(problems, "\n".join(problems))

    def test_every_search_read_orders_by_a_field_that_exists(self):
        """An ORDER BY on an absent column raises out of the same call."""
        problems = []
        for model, _fields, order, offset in self.calls:
            if model not in self.env:
                continue
            known = set(self.env[model].fields_get().keys())
            bad = [name for name in order if name not in known]
            if bad:
                problems.append(
                    "%s:%d — %s cannot be ordered by: %s"
                    % (JS_PATH, self._line_of(offset), model, ", ".join(bad)))
        self.assertFalse(problems, "\n".join(problems))
