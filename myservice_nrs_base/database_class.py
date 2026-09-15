"""Which database is this, and may a test write to it?

WHY THIS EXISTS
---------------
Handoff 24 §B measured what the test suites write and where. On this machine,
on 2026-09-15: 3,584 of 4,056 assets in `jaizbankplc` — a register derived
from a live client's data — were named `pytest-*`, 354 of 420 entries in the
PUBLIC homepage location dropdown were fixtures, and six fabricated approved
disposals sat in the auditor-facing disposal report. Accumulated over 154
sessions.

Nothing reached production, and that was luck rather than design. The only
control the HTTP suite had was `CADRA_API_BASE`, an environment variable: the
suite read it and wrote wherever it pointed. One word typed differently and
the same run does all of the above to a live tenant, and the first anyone
would know is an auditor asking about `pytest-1756203841`.

THE RULING (handoff 25 §A)
--------------------------
**Safety is a property of the DATABASE, recorded IN the database.** Nothing
else counts, and each rejected candidate was rejected for a reason:

  * Not the NAME. `test19` reads safe and `cadra19` does not, and both are
    wrong the day somebody restores a client dump into one.
  * Not an ENVIRONMENT VARIABLE. That is the control that just failed.
  * Not a path, a hostname or a branch. None of them survive a restore
    either, and a hostname is the same mistake as a name with extra steps.

So: a system parameter in the target database, set deliberately by a person.

    cadra.database_class = test | client | production

**Absent means refuse.** A database nobody has classified is a database
nobody has thought about, and the whole failure being fixed here is a default
that wrote rather than asked.

**There is no bypass flag and no override variable, deliberately.** A flag
added for one legitimate afternoon becomes the way everyone runs the suite by
the end of the month, and then this module never happened. If a database
should accept test writes, mark it — the refusal prints the command.

WHAT THIS IS NOT
----------------
It is not a permission system and it changes nothing about who may write what
at runtime. It refuses to let a TEST RUN start against a database that has not
been marked as a test database. Ordinary application writes, module upgrades,
seeds and migrations are untouched: the guard is only ever asked by a test.
"""

PARAM = "cadra.database_class"

TEST = "test"
CLIENT = "client"
PRODUCTION = "production"

#: Every value a person may set. Anything else is treated exactly like absent
#: — a typo must not be able to open the door that a blank cannot.
CLASSES = (TEST, CLIENT, PRODUCTION)


class DatabaseClassRefused(Exception):
    """A test run asked to write to a database that is not marked `test`."""


def database_class(env):
    """The class recorded in THIS database, or None if absent or unknown.

    **Read with SQL, deliberately, and NOT through `get_param`.**

    `ir.config_parameter.get_param` is `@ormcache`d per worker. Under the
    committed `workers = 2` the cache is per PROCESS, and the invalidation
    signal does not reliably reach a worker that is between requests — so
    `get_param` can keep answering with a value the database no longer holds.

    That is not a theory. The first cut of this guard used `get_param`, and
    during its own proof run the route reported `database_class = "client"`
    for a database whose parameter row had been DELETED, while a second
    worker still answered `"test"` for the same instant — and the suite,
    pointed at a database carrying no mark at all, ran 24 writing tests to a
    green pass. A guard served from a stale cache is a guard that says yes
    about a state that has stopped being true, which is the whole failure
    class this module exists to close.

    So the guard asks the database. One row, by primary key, once per test
    session or test class — the cost is irrelevant and the correctness is
    the entire point.
    """
    env.cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s", (PARAM,))
    row = env.cr.fetchone()
    value = ((row[0] if row else "") or "").strip().lower()
    return value if value in CLASSES else None


def mark_command(dbname):
    """The exact command a person runs to mark a database as a test database.

    Printed inside the refusal. An error that names a remedy the reader then
    has to go and look up is a worse error than one that names none, because
    it implies the lookup will be quick.
    """
    return (
        "docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\\n"
        "  odoo shell -c /etc/odoo/odoo.conf -d %s --no-http \\\n"
        "  --http-port=8099 --gevent-port=8098 <<< \\\n"
        "  \"env['ir.config_parameter'].sudo().set_param('%s', 'test'); env.cr.commit()\""
        % (dbname, PARAM)
    )


def refusal_message(dbname, found, *, surface):
    """The words a person reads when a run is refused.

    Names the database, names what its class actually is, and names the
    remedy in full. `surface` says which suite refused, because the two run
    from different commands and a reader who cannot tell which one stopped
    cannot tell which command to re-run.
    """
    if found is None:
        raw = "not set (or set to a value this code does not recognise)"
        why = (
            "A database nobody has classified is a database nobody has thought\n"
            "about. This guard is fail-closed on purpose: the control it\n"
            "replaces was an environment variable that defaulted to writing."
        )
    else:
        raw = repr(found)
        why = (
            "This database is marked as holding real data. A test run writes\n"
            "fixtures with no teardown — the API publishes one DELETE route in\n"
            "total — so anything written here stays, in a register somebody\n"
            "reads."
        )
    return (
        "\n"
        "REFUSED: %s will not run against database %r.\n"
        "\n"
        "  %s = %s\n"
        "\n"
        "%s\n"
        "\n"
        "If %r is a throwaway database that may be written to, mark it once:\n"
        "\n"
        "%s\n"
        "\n"
        "There is no bypass flag, deliberately — see myservice_nrs_base/"
        "database_class.py.\n"
        "If you meant a different database, change the target rather than the "
        "mark.\n"
        % (surface, dbname, PARAM, raw, why, dbname, mark_command(dbname))
    )


def assert_test_database(env, *, surface):
    """Raise unless THIS database is explicitly marked as a test database.

    Called before the first write of a test session, from both suites.
    """
    dbname = env.cr.dbname
    found = database_class(env)
    if found != TEST:
        raise DatabaseClassRefused(refusal_message(dbname, found, surface=surface))
