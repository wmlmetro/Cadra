"""Test base classes that know which database they are in.

Every first-party Odoo test case derives from one of these rather than from
`odoo.tests.common` directly, so that the question *may I write here?* is
asked once, in `setUpClass`, before any test method or any subclass fixture
runs.

WHY setUpClass AND NOT SOMETHING EARLIER
----------------------------------------
There is no earlier point that reliably has an environment. Odoo runs a
module's tests from inside `load_module_graph` (`odoo/modules/loading.py:279`),
immediately after that module is installed or upgraded and long BEFORE
`_register_hook` fires at STEP 9 (`loading.py:588`) — so a `_register_hook`
guard, which is the obvious one-line answer, runs after every test in the
registry has already finished. The test loader imports `<module>.tests` at
`odoo/tests/loader.py:61`, but at import time there is no cursor to ask.

`setUpClass` is therefore the first moment the question can be asked at all,
and it is early enough: it runs before every test method in the class, and
before any `setUpClass` body in a subclass provided that subclass calls
`super().setUpClass()` first — which is the Odoo convention and is enforced
by `tests/test_source_guards.py`.

**A class that escapes these bases escapes the guard**, which is why the
static check in `tests/test_source_guards.py` fails on any first-party test
class deriving straight from `TransactionCase` or `HttpCase`. That guard was
proved to fail before it was trusted; see report 25.
"""
from odoo.tests import common

from ..database_class import assert_test_database

#: Named in the refusal so a reader can tell which of the two suites stopped.
SURFACE = "the in-registry Odoo test suite"


class _DatabaseClassGuard:
    """Mixin: refuse the class unless this database is marked `test`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        assert_test_database(cls.env, surface=SURFACE)

    # ── the one sanctioned way to mint an API credential in a test ──

    @classmethod
    def create_api_client(cls, vals=None, **extra):
        """Create a `myservice.api.client` that says it is a test credential.

        WHY THIS EXISTS RATHER THAN A DIRECT `create()`
        -----------------------------------------------
        `is_test_credential` is what makes a fixture identifiable after the
        fact. It drives `nrs.asset.custody.source = 'test'`, which is why the
        chain of custody is honest without anyone curating it: 330 of its rows
        self-label because the credential that wrote them does.

        Handoff 23 minted `Handoff23 Approver` with a direct `create()` and
        the flag defaulted off. The six disposals it approved are the one
        class of artefact in `jaizbankplc` that a reader CANNOT identify from
        the record itself — they had to be found by name pattern and marked by
        hand afterwards (`scripts/mark_test_fixtures.py`). Every other fixture
        class was identifiable, and the difference was one unset boolean.

        So the flag is not a default here, it is forced: a caller passing
        `is_test_credential=False` gets it overridden, because a test has no
        legitimate reason to mint a credential that lies about itself. The
        behaviour of the flag is itself under test — see
        `myservice_api/tests/test_custody_is_not_capped.py`, which toggles it
        on a record it already holds rather than minting a dishonest one.

        `tests/test_source_guards.py` fails on any first-party test that calls
        `create()` on this model directly, so the hole cannot be reopened by
        someone who has not read this docstring.
        """
        values = dict(vals or {}, **extra)
        values["is_test_credential"] = True
        return cls.env["myservice.api.client"].sudo().create(values)


class CadraTransactionCase(_DatabaseClassGuard, common.TransactionCase):
    pass


class CadraHttpCase(_DatabaseClassGuard, common.HttpCase):
    pass


#: `SingleTransactionCase` is unused in first-party code today. It is exported
#: anyway so that the day somebody needs one they reach for a guarded base
#: rather than importing the raw one and tripping the source guard.
class CadraSingleTransactionCase(_DatabaseClassGuard, common.SingleTransactionCase):
    pass
