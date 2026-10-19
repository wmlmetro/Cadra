"""
Cadra bootstrap — one-shot environment setup for a fresh deployment.

Runs INSIDE an `odoo shell` session (see scripts/bootstrap.sh for the
host-side orchestrator). Idempotent: re-running on a fully-bootstrapped
stack is a no-op except for credential output.

Steps:
  1. JWT secret — set ir.config_parameter `myservice_api.jwt_secret`
     from CADRA_JWT_SECRET env var, or generate one if blank.
  2. Admin user groups — add base.user_admin to:
       - myservice_asset_register.group_asset_manager
       - myservice_security.group_security_admin
     (so API calls from the smoke-test client can read every model)
  3. API smoke-test client — create or rotate the test_client record
     (client_id from CADRA_TEST_CLIENT_ID, secret from CADRA_TEST_CLIENT_SECRET
     or generated). Scopes cover every read+write across all 4 resources
     plus integrations.
  4. Seeds — based on CADRA_SEED_PROFILE env var:
       core            = ITSM structure + Nigeria locations + 415 FIRS offices
       fleet           = above + master fleet seed (1,617 vehicles — slow)
       full            = ITSM + locations + offices v3 + master seed + NRS HQ
                         assets (1,272) + HQ location metadata + fleet taxonomy
                         + fleet→location matcher (~12-15 min total)
       full-no-master  = full minus master_seed (use when master already ran;
                         saves ~7 min of idempotent rework)
       full+geo        = full + OSM geocoding (~30 min — exceeds the 20 min
                         bootstrap Job cap; bump the wait timeout first)
       (empty)         = no seeds
     All seeds are idempotent via the get_or_create helpers in the seed
     scripts themselves.

Outputs:
  Prints a marked-up block of credentials at the end (between
  CADRA_BOOTSTRAP_BEGIN and CADRA_BOOTSTRAP_END sentinels) so the host
  orchestrator can capture them for writing to docs/api/.creds.
"""
import logging
import os
import secrets
import sys

_logger = logging.getLogger(__name__)

# The Odoo shell injects `env`, `cr`, `uid`, `openerp` into locals before
# exec'ing this file. We rely on `env` only.
# pylint: disable=undefined-variable


# ─── helpers ────────────────────────────────────────────────────────

#: Mirrors myservice_nrs_base/database_class.py. Duplicated rather than
#: imported because this script runs inside `odoo shell`, where the addons
#: path is available but importing a module for two constants would make
#: bootstrap fail on a database where that addon is not installed yet —
#: which is every database this script is run against for the first time.
_DATABASE_CLASS_PARAM = "cadra.database_class"
_DATABASE_CLASSES = ("test", "client", "production")


def _say(msg, level="INFO"):
    """Stdout banner that the host-side orchestrator can grep."""
    print(f"[bootstrap:{level:>5}] {msg}", flush=True)


def _has_meaningful_secret(value):
    """Reject empty + known placeholders + too-short secrets."""
    if not value or len(value) < 16:
        return False
    placeholders = {"CHANGE_ME__MYservice_API_JWT_SECRET", "CHANGE_ME", "changeme"}
    return value not in placeholders


# ─── step 1: JWT secret ─────────────────────────────────────────────

def ensure_jwt_secret():
    """Set the JWT signing secret in ir.config_parameter.

    Source precedence:
      1. CADRA_JWT_SECRET env var (if meaningful)
      2. Existing ir.config_parameter value (if meaningful)
      3. Generate a new one (48 url-safe chars)

    Returns the secret that's now set. This used to say the host
    orchestrator writes it back to `.env.runtime`; nothing has ever written
    that file, and `.env.example` repeated the same claim. What actually
    happens is that bootstrap.sh captures it from the sentinel-wrapped
    output into `docs/api/.creds.<db>` (mode 600). The secret lives in
    `ir.config_parameter`, per database, and survives a restart on its own.
    """
    param = env["ir.config_parameter"].sudo()
    current = param.get_param("myservice_api.jwt_secret", "")
    from_env = os.environ.get("CADRA_JWT_SECRET", "").strip()

    if _has_meaningful_secret(from_env):
        if current != from_env:
            param.set_param("myservice_api.jwt_secret", from_env)
            _say("JWT secret set from CADRA_JWT_SECRET env var")
        else:
            _say("JWT secret already matches CADRA_JWT_SECRET (no change)")
        return from_env

    if _has_meaningful_secret(current):
        _say("JWT secret already set in ir.config_parameter (preserving)")
        return current

    new_secret = secrets.token_urlsafe(48)
    param.set_param("myservice_api.jwt_secret", new_secret)
    _say("JWT secret generated and stored")
    return new_secret


def ensure_turnstile_secret():
    """Mirror CADRA_TURNSTILE_SECRET into `myservice_api.turnstile_secret`.

    Deliberately one-way: an empty env var leaves whatever is stored alone
    rather than clearing it, so a Job that loses the variable can't silently
    strip bot protection off a live tenant. To actually turn Turnstile off,
    clear the parameter by hand (odoo shell → set_param(..., False)).
    """
    param = env["ir.config_parameter"].sudo()
    current = param.get_param("myservice_api.turnstile_secret", "")
    from_env = os.environ.get("CADRA_TURNSTILE_SECRET", "").strip()

    if not from_env:
        _say("CADRA_TURNSTILE_SECRET is empty — leaving Turnstile config as-is")
    elif current == from_env:
        _say("Turnstile secret already matches CADRA_TURNSTILE_SECRET (no change)")
    else:
        param.set_param("myservice_api.turnstile_secret", from_env)
        _say("Turnstile secret set from CADRA_TURNSTILE_SECRET")


def ensure_ai_key():
    """Mirror CADRA_AI_API_KEY into `myservice_api.ai_api_key` (handoff 64).

    The provider key for *Identify from photo* — the owner's secret, on the
    Turnstile secret's road and one-way for its reason: an empty variable
    leaves whatever is stored alone, so a Job that loses the variable cannot
    silently switch identification off a tenant. Never printed; the
    configuration-change report redacts it by name. The switch
    `cadra.ai.identify` is NOT touched: placing a key turns nothing on.
    """
    param = env["ir.config_parameter"].sudo()
    current = param.get_param("myservice_api.ai_api_key", "")
    from_env = os.environ.get("CADRA_AI_API_KEY", "").strip()
    if not from_env:
        _say("CADRA_AI_API_KEY is empty — leaving the AI provider key as-is")
    elif current == from_env:
        _say("AI provider key already matches CADRA_AI_API_KEY (no change)")
    else:
        param.set_param("myservice_api.ai_api_key", from_env)
        _say("AI provider key set from CADRA_AI_API_KEY (= ***)")


# ─── step 2: admin groups ───────────────────────────────────────────

REQUIRED_ADMIN_GROUPS = [
    "myservice_asset_register.group_asset_manager",
    "myservice_security.group_security_admin",
]


def _groups_field(env):
    """`res.users`' groups field — renamed `groups_id` → `group_ids` on 19.

    The 15 stack is still production, so this script has to speak both.
    """
    return ("group_ids" if "group_ids" in env["res.users"]._fields
            else "groups_id")


def ensure_admin_groups():
    """Add base.user_admin to the operational groups our API needs."""
    admin = env.ref("base.user_admin")
    added = 0
    skipped_missing = []
    # Odoo 19's res.groups refactor renamed `users` → `user_ids`; support both
    # so bootstrap works on the 15 staging and the 19 rebuild.
    for xmlid in REQUIRED_ADMIN_GROUPS:
        try:
            group = env.ref(xmlid)
        except ValueError:
            skipped_missing.append(xmlid)
            continue
        users_field = "user_ids" if "user_ids" in group._fields else "users"
        if admin.id in group[users_field].ids:
            _say(f"admin already in {group.name!r}")
        else:
            group.write({users_field: [(4, admin.id)]})
            added += 1
            _say(f"added admin to {group.name!r}")
    if skipped_missing:
        _say(f"groups not installed (skipped): {skipped_missing}", level="WARN")
    return added


# ─── step 3: API smoke-test client ──────────────────────────────────

def _all_scopes():
    """The canonical scope set, read from the API module rather than copied.

    This used to be a hand-maintained string here, and it drifted: `admin`,
    `approvals:write`, `ingestion:write` and `webhooks:admin` were all added to
    the API and never mirrored, so the CI smoke client silently lacked them and
    every admin-scoped endpoint 403'd in CI while passing locally against a
    wildcard client. Deriving it removes that whole class of bug.
    """
    try:
        from odoo.addons.myservice_api.controllers.utils import ALL_SCOPES as canonical
        return " ".join(sorted(canonical))
    except ImportError as exc:
        # catch-all: optional — narrowed from `Exception`. The case this
        # exists for is `myservice_api` not being on a cold database yet,
        # which is an ImportError and nothing else. A broad catch here would
        # hide a typo in `ALL_SCOPES` behind a hard-coded list that silently
        # stops matching the code — and this list decides what every client
        # in the estate is provisioned with.
        _say(f"could not import canonical scopes ({exc}); falling back", level="WARN")
        return (
            "admin approvals:write assets:read assets:write dashboards:read "
            "identity:read ingestion:write integrations:write locations:read "
            "locations:write requests:read requests:write tagging:write "
            "webhooks:admin"
        )


def ensure_database_class():
    """Record what kind of database this is, so a test can ask.

    `cadra.database_class` is read by the guard in
    `myservice_nrs_base/database_class.py`: a test suite refuses to run
    against any database not marked `test`. Absent refuses, so a database
    nobody classified is never written to by a test.

    **This script is also the PRODUCTION deploy path** — README §Deploy is
    `CADRA_PROFILE=prod scripts/bootstrap.sh` — so stamping `test`
    unconditionally here would mark every client's live database as safe to
    write fixtures into. That is the exact inversion of the control, so the
    class is never guessed from anything but an explicit statement:

      * `CADRA_DATABASE_CLASS` names it outright. CI sets `test` when it
        builds its throwaway database, which is how CI stays green with no
        exemption in the guard — the database CI creates really is a test
        database, and it says so.
      * Failing that, a `prod` profile stamps `production`. Marking a
        production deploy as production is the one inference that cannot make
        the guard weaker.
      * Failing both, NOTHING is written. Fail-closed: a developer's fresh
        tenant refuses test runs until they mark it, and the refusal prints
        the command.

    Idempotent, and it never downgrades silently: an existing mark is left
    alone unless `CADRA_DATABASE_CLASS` explicitly asks for a different one.
    """
    ICP = env["ir.config_parameter"].sudo()
    requested = os.environ.get("CADRA_DATABASE_CLASS", "").strip().lower()
    profile = os.environ.get("CADRA_PROFILE", "").strip().lower()

    if requested and requested not in _DATABASE_CLASSES:
        raise ValueError(
            "CADRA_DATABASE_CLASS=%r is not one of %s"
            % (requested, ", ".join(_DATABASE_CLASSES)))

    # Read with SQL, deliberately, and NOT through `ICP.get_param` — the same
    # choice, for the same reason, as `database_class()` in
    # `myservice_nrs_base/database_class.py` (read its docstring; this is the
    # incident it was written up from). `get_param` is `@ormcache`d PER
    # WORKER: during handoff 25's own proof run one worker reported the class
    # as "client" for a database whose parameter row had been DELETED while a
    # second worker answered "test" for the same instant.
    #
    # It matters HERE and not only in the guard, because `current` is the
    # left-hand side of the downgrade interlock twenty lines below. A stale
    # read of "test" waves through a re-mark that should have been refused; a
    # stale read of "production" aborts a bootstrap that should have run. An
    # interlock fed from a cache is an interlock about a state that has
    # stopped being true, which is the whole reason the guard stopped using
    # `get_param`.
    #
    # The SQL is duplicated rather than imported for the reason already
    # recorded at the top of this file: importing
    # `odoo.addons.myservice_nrs_base.database_class` executes that package's
    # `__init__` (`from . import models`) on a database where the addon is not
    # installed — which is every database this script is run against for the
    # first time.
    env.cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s",
        (_DATABASE_CLASS_PARAM,))
    _row = env.cr.fetchone()
    _raw_class = ((_row[0] if _row else "") or "").strip().lower()

    # An unrecognised value is treated as ABSENT, exactly as `database_class()`
    # treats it — otherwise bootstrap says "already marked 'Test '" and leaves
    # it while the guard, which filters the same value through the same tuple,
    # refuses every test run against that database. The two must not be able
    # to disagree about whether a database is classified. And it is said out
    # loud: a value nobody can act on, passed over in silence, is how a
    # database ends up classified in nobody's opinion but its own.
    if _raw_class and _raw_class not in _DATABASE_CLASSES:
        _say("%s holds %r, which is not one of %s — treating this database as "
             "UNCLASSIFIED, the same way myservice_nrs_base/database_class.py "
             "does. Nothing reads that value."
             % (_DATABASE_CLASS_PARAM, _raw_class, ", ".join(_DATABASE_CLASSES)),
             level="WARNING")
    current = _raw_class if _raw_class in _DATABASE_CLASSES else None

    # ── two interlocks, because `test` is the only value that opens a door ──
    #
    # Both exist because `bootstrap.sh` does `set -a; . ./.env` (line 66) —
    # so ANY value in a `.env` is exported into this run, and a `.env` is
    # routinely copied from a developer's machine onto a server. A developer
    # who put `CADRA_DATABASE_CLASS=test` in theirs and then deployed with
    # `CADRA_PROFILE=prod scripts/bootstrap.sh` would otherwise stamp a
    # client's live database `test`, and every guard in the system would then
    # say yes. A warning line is not enough: nothing gates on a warning.

    if requested == "test" and profile.startswith("prod"):
        raise ValueError(
            "refusing to mark a database `test` on a `prod` profile "
            "(CADRA_PROFILE=%r). One of the two is wrong, and marking a "
            "production database as a test database is the failure this "
            "parameter exists to prevent. Unset CADRA_DATABASE_CLASS to "
            "have a prod bootstrap record `production`, or run this "
            "bootstrap without the prod profile." % profile)

    if (requested == "test" and current in ("client", "production")
            and os.environ.get("CADRA_DATABASE_CLASS_DOWNGRADE", "").strip() != current):
        raise ValueError(
            "refusing to re-mark a database currently recorded as %r as "
            "`test`. Somebody classified it deliberately and a test run "
            "writes fixtures that cannot be removed. If this database really "
            "has been rebuilt and is now a throwaway, say so explicitly by "
            "also setting CADRA_DATABASE_CLASS_DOWNGRADE=%s."
            % (current, current))

    if requested:
        if current and current != requested:
            _say("database class %r -> %r (CADRA_DATABASE_CLASS)"
                 % (current, requested), level="WARNING")
        ICP.set_param(_DATABASE_CLASS_PARAM, requested)
        _say("database marked %r" % requested)
        return requested

    if current:
        _say("database already marked %r; leaving it" % current)
        return current

    if profile.startswith("prod"):
        ICP.set_param(_DATABASE_CLASS_PARAM, "production")
        _say("database marked 'production' (CADRA_PROFILE=%s)" % profile)
        return "production"

    _say("database is NOT classified: test suites will refuse to run against "
         "it. Set CADRA_DATABASE_CLASS=test before bootstrap, or mark it "
         "afterwards with set_param(%r, 'test')." % _DATABASE_CLASS_PARAM,
         level="WARNING")
    return None


#: Env var by which an operator states, outright, that an ARCHIVED API client
#: should be brought back. It names the `client_id` rather than being a bare
#: boolean, for the same reason `CADRA_DATABASE_CLASS_DOWNGRADE` names the
#: class it is overriding: a boolean gets typed into a CI file once and then
#: covers every client forever. Comma-separated for the rare multi-client run.
_REACTIVATE_ARCHIVED_ENV = "CADRA_REACTIVATE_ARCHIVED_CLIENT"


def _find_api_client(Client, client_id):
    """The client holding this `client_id`, ARCHIVED ONES INCLUDED, or empty.

    WHAT THIS FIXES
    ---------------
    `myservice.api.client` carries `active` (`myservice_api/models/api_client.py`
    line 17) and there is NO uniqueness constraint on `client_id`. Both
    provisioning sites below used to search with Odoo's default
    `active_test=True`, so an ARCHIVED client was invisible to them — and the
    `if not rec: rec = Client.create(...)` that follows then minted a SECOND
    row with the same `client_id` and printed a success line. Two rows, one
    credential name, and `/auth/token` afterwards resolves whichever one the
    ordering happens to hand back.

    The rest of this repository already fixed this exact model against this
    exact mistake — `myservice_api/migrations/19.0.3.2.0/post-migrate.py` line
    45 and `19.0.3.3.0/post-migrate.py` line 48 both carry `active_test=False`
    with the comment "an archived client must not be skipped and then start
    minting the wrong uid". Bootstrap, the script that CREATES these records,
    never got it.

    WHY THIS REFUSES RATHER THAN QUIETLY REVIVING
    ---------------------------------------------
    Archiving is how an API credential is revoked in Odoo; there is no other
    button. So an archived `tag_issuing_unit` is somebody's deliberate act,
    and a deploy script that silently un-archives it is a deploy script that
    re-opens a door a person closed — the same shape as the `group_system`
    grant that used to be stripped by the next scope edit, run backwards. A
    WARN line is not enough: nothing gates on a warning, and a bootstrap run
    prints dozens of them past an operator who is watching for the
    credentials block at the end.

    So this raises, and the refusal NAMES the client_id it looked for and the
    row it found. Reactivation is then stated outright:

        CADRA_REACTIVATE_ARCHIVED_CLIENT=tag_issuing_unit scripts/bootstrap.sh

    NOT A REGRESSION ON ANY CORRECT PATH, including `CADRA_PROFILE=prod`.
    Where the client is active, or absent, the behaviour is what it always
    was. The only runs that now stop are the ones that were previously
    creating a duplicate row and calling it a success.
    """
    matches = Client.with_context(active_test=False).search(
        [("client_id", "=", client_id)])

    if len(matches) > 1:
        # The duplicate the old search was capable of minting. Nothing here
        # can tell which row is the real credential — they have the same
        # client_id and each has its own secret hash — so it is named and
        # handed to a person rather than resolved by ordering.
        raise ValueError(
            "%d API clients share client_id %r on this database: %s. Nothing "
            "here can tell which is the real credential. This is the "
            "duplicate the pre-fix bootstrap created: it searched without "
            "`active_test=False`, could not see an archived row, and made a "
            "second one beside it. Delete or re-id the wrong one under "
            "Settings > Technical > API Clients, then re-run."
            % (len(matches), client_id,
               ", ".join("id=%d active=%s" % (c.id, c.active)
                         for c in matches)))

    if not matches:
        # Legitimately zero, said deliberately: a first bootstrap of a fresh
        # tenant has no client, and the caller creates one. This is the ONE
        # empty result in this function that is not a fault.
        return matches

    rec = matches
    if rec.active:
        return rec

    permitted = {name.strip() for name
                 in os.environ.get(_REACTIVATE_ARCHIVED_ENV, "").split(",")
                 if name.strip()}
    if client_id not in permitted:
        raise ValueError(
            "API client %r exists on this database (id=%d) but is ARCHIVED. "
            "Archiving is how a credential is revoked, so bootstrap will "
            "neither reuse it silently nor create a second row beside it — "
            "which is what it used to do, invisibly, leaving two clients with "
            "this client_id. If this credential really should come back, say "
            "so: %s=%s scripts/bootstrap.sh"
            % (client_id, rec.id, _REACTIVATE_ARCHIVED_ENV, client_id))

    rec.active = True
    _say("REACTIVATED archived API client %r (id=%d) because %s names it. Its "
         "stored secret hash survived the archiving and is preserved unless a "
         "CADRA_*_SECRET is supplied; its scopes are re-synced below."
         % (client_id, rec.id, _REACTIVATE_ARCHIVED_ENV), level="WARN")
    return rec


def ensure_test_client():
    """Create or rotate the smoke-test API client.

    Returns (client_id, raw_secret).
    """
    Client = env["myservice.api.client"].sudo()
    client_id = os.environ.get("CADRA_TEST_CLIENT_ID", "").strip() or "test_client"
    requested_secret = os.environ.get("CADRA_TEST_CLIENT_SECRET", "").strip()

    all_scopes = _all_scopes()

    # `_find_api_client`, not a bare `search`: the default search cannot see
    # an archived client, and this `if not rec: create(...)` would then mint a
    # second row carrying the same client_id. See its docstring.
    rec = _find_api_client(Client, client_id)
    if not rec:
        # No `user_id`: the model provisions the client its own res.users.
        # This used to be `base.user_admin`, which is why every tag affix in
        # the estate records "Administrator" as the person who confirmed it.
        rec = Client.create({
            "name": "Smoke Test",
            "client_id": client_id,
            "scopes": all_scopes,
            "token_ttl_seconds": 3600,
            # This credential runs the API test suite against a live tenant,
            # and the suite moves an asset's custodian on purpose — the chain
            # of custody is append-only, so those links are permanent. The
            # flag is what makes them say `source: test` when an auditor
            # reads the chain, instead of passing as history somebody would
            # have to be told about.
            "is_test_credential": True,
        })
        _say(f"created API client {client_id!r} running as {rec.user_id.login!r}")
    else:
        # Always re-sync scopes so we never drift behind the canonical set.
        # This is deliberately NOT chained to the re-homing below: they are
        # independent, and making the scope re-sync conditional on the client
        # still sitting on Administrator would silently stop it happening the
        # moment the identity fix had landed.
        if rec.scopes != all_scopes:
            rec.scopes = all_scopes
            _say(f"updated scopes on existing client {client_id!r}")
        if not rec.is_test_credential:
            rec.is_test_credential = True
            _say(f"marked {client_id!r} as a test credential — its custody "
                 f"links will read `test`")
        if rec.user_id == env.ref("base.user_admin"):
            rec.action_provision_user()
            _say(f"re-homed {client_id!r} off Administrator onto "
                 f"{rec.user_id.login!r}", level="WARN")

    # NO `base.group_system`. Until handoff 44 this block granted it here,
    # unconditionally and last, to every run's smoke-test client user — on
    # the stated reason that "the dashboard routes are the few that do NOT
    # sudo()". They have sudo()'d since handoff 09 (`utils.SCOPE_GROUPS`
    # says so), and handoff 44 stripped the group from this credential on
    # `test19` and drove the whole HTTP suite as it: report 44 §A has the
    # transcript, and the one thing the credential lost is withdrawing a
    # change request somebody ELSE raised — an Odoo-administrator power
    # (`_is_admin()`), not anything its scopes promise. That holds because
    # this credential also holds `approvals:write`, which `SCOPE_GROUPS`
    # turns into Asset Manager, the approver group; a credential holding
    # `admin` ALONE maps to no group and, without the system group, can no
    # longer decide or be asked to decide a change request — the token's
    # wildcard passes the route, the model asks for an approver. The `admin` scope is
    # a wildcard in the TOKEN, where `require_jwt` reads it; the user
    # underneath is an ordinary internal user holding exactly what
    # `utils.groups_for_scopes` gives it, like every other client.
    #
    # A system administrator can execute arbitrary server actions, so a
    # credential holding the group makes the API guard of handoff 42
    # advisory for it. What an API credential is entitled to, and why, is
    # `docs/DECISIONS.md` 2026-10-02 *What an API credential is entitled to*.
    #
    # The `19.0.3.2.0` migration made the same grant to any client holding
    # `admin` and is fixed in the same change;
    # This test fails if either comes back:
    # tests/test_source_guards.py::test_no_provisioning_path_grants_a_credential_system_administrator
    #
    # This does NOT take the group off a client user that already holds it:
    # bootstrap is the production deploy path, and stripping it here would
    # change every live tenant on the next deploy without anybody deciding
    # to. `scripts/strip_credential_system_group.py` does that, dry-run by
    # default, and the owner runs it. Note that `_provision_client_user`
    # replaces the group set wholesale on any scope change, so the next
    # change to ALL_SCOPES would also take it off — silently, which is why
    # the procedure is a script with a log rather than that.

    # Rotate the secret if:
    #   - the env var supplied a specific value and it doesn't match
    #   - no secret has ever been set on this client
    # Otherwise preserve the existing secret (idempotent).
    raw = None
    if requested_secret:
        if not rec.check_client_secret(requested_secret):
            rec.set_client_secret(requested_secret)
            _say(f"client_secret set from CADRA_TEST_CLIENT_SECRET env var")
        raw = requested_secret
    elif not rec.client_secret_hash:
        raw = rec.rotate_secret()
        _say(f"client_secret generated for {client_id!r}")
    else:
        raw = "<UNCHANGED — existing secret preserved>"

    return client_id, raw


# ─── step 3.1: the integration clients ──────────────────────────────
#
# The September Integration Flow gives Cadra two counterparties that are not
# each other and are not us: Vendra, which creates asset records from a goods
# receipt (INT-03), and the Tag-Issuing Unit, which prints the labels, sticks
# them on and confirms the serial-to-tag match (INT-04/05).
#
# That confirmation is the only thing that makes an asset read as genuinely
# tagged — so it is evidence only if the credential confirming the tag is not
# the credential that wrote the asset. The separation therefore has to exist
# as a credential, not as a convention, and it has to be provisioned by the
# same script that provisions everything else. A shell command an operator is
# expected to remember is how a demo ends up authenticating as admin and
# quietly proving nothing.

TAGGING_CLIENT_ID_DEFAULT = "tag_issuing_unit"
VENDRA_CLIENT_ID_DEFAULT = "vendra"
#: What Vendra may do. `myservice_api`'s 19.0.3.32.0 migration adds
#: `candidates:read` to every existing Vendra client, so an existing client
#: and a new one hold the same scopes — keep the two in step.
VENDRA_CLIENT_SCOPES = "assets:read assets:write candidates:read"


def _ensure_scoped_client(*, name, default_client_id, scopes,
                          id_env, secret_env):
    """Create (or re-narrow) a named API client with an exact scope string.

    Returns (client_id, raw_secret). `raw_secret` is a placeholder string when
    an existing secret was preserved — a hash cannot be read back.
    """
    Client = env["myservice.api.client"].sudo()
    client_id = os.environ.get(id_env, "").strip() or default_client_id
    requested_secret = os.environ.get(secret_env, "").strip()

    # `_find_api_client`, not a bare `search` — same reason as
    # `ensure_test_client`, and it bites harder here: these are the two
    # counterparty credentials (Vendra and the Tag-Issuing Unit) whose
    # SEPARATION is the only thing that makes a tag affix evidence. A
    # duplicate `tag_issuing_unit` row is two credentials answering to one
    # name in the record that is supposed to tell them apart.
    rec = _find_api_client(Client, client_id)
    if not rec:
        # No `user_id` — the model provisions this client its own res.users,
        # named for the client and holding only the groups its scopes justify.
        # It used to be `base.user_admin` for every client alike, which made
        # the separation these two clients exist to enforce invisible in the
        # record it exists to produce: a tag affix said "Administrator"
        # whether the Tag-Issuing Unit or Vendra had confirmed it.
        rec = Client.create({
            "name": name,
            "client_id": client_id,
            "scopes": scopes,
            "token_ttl_seconds": 3600,
        })
        _say(f"created API client {client_id!r} (scopes: {scopes}) "
             f"running as {rec.user_id.login!r}")
    else:
        if rec.scopes != scopes:
            # Re-narrowed on every run. Widening a scope by hand to get past a
            # 403 is a permission decision, and it belongs in a commit rather
            # than in a form somebody filled in during an incident.
            _say(f"re-narrowing scopes on {client_id!r}: "
                 f"{rec.scopes!r} -> {scopes!r}", level="WARN")
            rec.scopes = scopes          # write() re-syncs the user's groups
        if rec.user_id == env.ref("base.user_admin"):
            rec.action_provision_user()
            _say(f"re-homed {client_id!r} off Administrator onto "
                 f"{rec.user_id.login!r}", level="WARN")

    if requested_secret:
        if not rec.check_client_secret(requested_secret):
            rec.set_client_secret(requested_secret)
            _say(f"client_secret for {client_id!r} set from {secret_env}")
        raw = requested_secret
    elif not rec.client_secret_hash:
        raw = rec.rotate_secret()
        _say(f"client_secret generated for {client_id!r}")
    else:
        raw = "<UNCHANGED — existing secret preserved>"

    return client_id, raw


def ensure_tagging_client():
    """The Tag-Issuing Unit's client — `tagging:write` and nothing else.

    Not `assets:write`: it does not create assets. Not `assets:read`: the tag
    numbers reach it over INT-04, not by browsing the register. Emphatically
    not `admin`, which is a wildcard over the whole API.
    """
    return _ensure_scoped_client(
        name="Tag-Issuing Unit",
        default_client_id=TAGGING_CLIENT_ID_DEFAULT,
        scopes="tagging:write",
        id_env="CADRA_TAGGING_CLIENT_ID",
        secret_env="CADRA_TAGGING_CLIENT_SECRET",
    )


def ensure_vendra_client():
    """Vendra's client for INT-03 — it creates and reads assets, and that is all.

    Deliberately WITHOUT `tagging:write`: Vendra hands over a classified
    receipt, it does not put labels on things. If Vendra could confirm a tag
    affixed, the affix record would prove only that Vendra said so.

    `candidates:read` since handoff 60 (§1.1): with the receipt gates on, a
    receipt Vendra hands over is a CANDIDATE, and Vendra asks Cadra where
    each of its units is (`GET /assets?register_state=any`). Without the
    scope it saw a unit only once registered, and never a rejection (Vendra
    report 55). Read only. Existing clients receive it from the
    `myservice_api` 19.0.3.32.0 migration, so the two lists agree and a
    later bootstrap does not narrow it away.
    """
    return _ensure_scoped_client(
        name="Vendra (INT-03)",
        default_client_id=VENDRA_CLIENT_ID_DEFAULT,
        scopes=VENDRA_CLIENT_SCOPES,
        id_env="CADRA_VENDRA_CLIENT_ID",
        secret_env="CADRA_VENDRA_CLIENT_SECRET",
    )


# ─── step 3.5: outgoing mail server ────────────────────────────────

SMTP_ENCRYPTION_CHOICES = {"none", "starttls", "ssl"}


def ensure_mail_server():
    """Create or update the default outgoing mail server (ir.mail_server).

    Driven by env vars (all optional — if SMTP_HOST is blank the whole
    step is a no-op):
      SMTP_HOST         — e.g. smtp.zoho.com
      SMTP_PORT         — int, default 587
      SMTP_USER         — auth username (full email address for Zoho/Gmail)
      SMTP_PASS         — auth password / app password
      SMTP_ENCRYPTION   — one of {none, starttls, ssl}, default starttls
      SMTP_FROM_FILTER  — optional From-address filter (Odoo "from_filter")
      EMAIL_FROM        — system-wide default sender, written to
                          ir.config_parameter `mail.default.from`
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        _say("SMTP_HOST not set — skipping mail-server setup")
        return

    Mail = env["ir.mail_server"].sudo()
    encryption = os.environ.get("SMTP_ENCRYPTION", "starttls").strip().lower()
    if encryption not in SMTP_ENCRYPTION_CHOICES:
        _say(f"invalid SMTP_ENCRYPTION={encryption!r} — falling back to starttls", level="WARN")
        encryption = "starttls"

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        _say("invalid SMTP_PORT — falling back to 587", level="WARN")
        port = 587

    vals = {
        "name": "Cadra Default SMTP",
        "smtp_host": host,
        "smtp_port": port,
        "smtp_user": os.environ.get("SMTP_USER", "").strip() or False,
        "smtp_pass": os.environ.get("SMTP_PASS", "") or False,
        "smtp_encryption": encryption,
        "sequence": 10,
    }
    from_filter = os.environ.get("SMTP_FROM_FILTER", "").strip()
    if from_filter:
        vals["from_filter"] = from_filter

    # `active_test=False`, same archived-record shape as `_find_api_client`.
    #
    # VERIFIED, not assumed: Odoo 19's `ir.mail_server` really does carry
    # `active` — `active = fields.Boolean(default=True)` at line 197 of
    # `odoo/addons/base/models/ir_mail_server.py`, read out of the running
    # 19 container on 2026-09-15. Odoo core is not in this repository, and a
    # `with_context(active_test=False)` against a model that has no `active`
    # field would have been a no-op dressed up as a fix — which is the same
    # defect as the one being closed here. There is no uniqueness constraint
    # on `name` either, so the old default search hid an archived "Cadra
    # Default SMTP" and this step created a SECOND one beside it: two servers,
    # one name, both at sequence 10, and which one Odoo sends through is then
    # an ordering accident.
    #
    # REPAIRED rather than refused, unlike an API client, and the difference
    # is what the record IS. A mail server is configuration: nothing
    # authenticates as it and re-enabling it grants nobody access. Archiving
    # one means "stop sending through this", and an operator who has set
    # SMTP_HOST on this run is saying the opposite in the same breath — so
    # the write is what was asked for. It is still announced at WARN, because
    # a mail server that was switched off and has just come back on is a fact
    # somebody has to be able to find in the log afterwards.
    matches = Mail.with_context(active_test=False).search(
        [("name", "=", vals["name"])])
    if len(matches) > 1:
        _say(f"{len(matches)} ir.mail_server records are named "
             f"{vals['name']!r} (ids {matches.ids}) — the pre-fix search could "
             f"not see archived ones and created duplicates. Updating id="
             f"{matches[0].id} and leaving the rest; delete the spares under "
             f"Settings > Technical > Outgoing Mail Servers.", level="WARN")
    rec = matches[:1]
    if rec:
        if not rec.active:
            vals["active"] = True
            _say(f"ir.mail_server {rec.name!r} (id={rec.id}) was ARCHIVED and "
                 f"is being re-enabled because SMTP_HOST is set ({host}). "
                 f"Somebody switched this server off; this run switches it "
                 f"back on.", level="WARN")
        rec.write(vals)
        _say(f"updated ir.mail_server {rec.name!r} → {host}:{port} ({encryption})")
    else:
        Mail.create(vals)
        _say(f"created ir.mail_server {vals['name']!r} → {host}:{port} ({encryption})")

    # Default From address for system-generated mail.
    default_from = os.environ.get("EMAIL_FROM", "").strip()
    if default_from:
        env["ir.config_parameter"].sudo().set_param("mail.default.from", default_from)
        _say(f"set ir.config_parameter mail.default.from = {default_from}")


# ─── step 3.6: email relay (HTTPS bridge for DO SMTP-blocked clusters) ───

def ensure_email_relay():
    """Persist email-relay config so myservice_email_relay's override picks it up.

    Env vars:
      CADRA_EMAIL_RELAY_URL    — full POST URL of the relay
      CADRA_EMAIL_RELAY_SECRET — shared secret the relay validates

    Both must be set for the relay to take effect; otherwise the override
    in myservice_email_relay falls through to native SMTP. Setting an empty
    string explicitly clears any previously-stored values (useful when
    rotating off the relay).
    """
    ICP = env["ir.config_parameter"].sudo()
    url = os.environ.get("CADRA_EMAIL_RELAY_URL", "").strip()
    secret = os.environ.get("CADRA_EMAIL_RELAY_SECRET", "").strip()

    if url:
        ICP.set_param("cadra.email_relay_url", url)
        _say(f"set ir.config_parameter cadra.email_relay_url = {url}")
    if secret:
        ICP.set_param("cadra.email_relay_secret", secret)
        _say("set ir.config_parameter cadra.email_relay_secret = ***")

    if not url and not secret:
        _say("CADRA_EMAIL_RELAY_* not set — relay disabled, native SMTP will be used")


# ─── step 4: seeds ─────────────────────────────────────────────────

SEED_PROFILES = {
    "core": [
        ("ITSM Structure",     "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",  "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices (415)", "/mnt/extra-addons/load_offices.py"),
    ],
    "fleet": [
        ("ITSM Structure",        "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",     "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices (415)",    "/mnt/extra-addons/load_offices.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
    ],
    # Full seed = everything validated against a fresh dev DB on 2026-06-01.
    # Order matters: HQ assets depend on locations, fleet matcher depends on
    # both vehicles + offices. Uses load_offices_v3 (4-level hierarchy) over
    # the legacy v1. Geocoding (~30 min OSM run) stays opt-in via the
    # `full+geo` profile so a normal deploy isn't blocked on rate-limited
    # external calls.
    "full": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # Same as `full` but skips myservice_master_seed.py. Use this when the
    # master seed has already landed and you only need to fill in the four
    # follow-on seeds — saves ~7 min of idempotent rework on the master seed.
    "full-no-master": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    "full+geo": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("Master Seed (ITSM+Fleet)", "/mnt/extra-addons/myservice_master_seed.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Geocode Locations (OSM)",  "/mnt/extra-addons/geocode_locations.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # full-no-master + geocoding. Use on a populated DB that needs lat/lng
    # backfilled for the dashboard map without re-running the 7-min master seed.
    "full-no-master+geo": [
        ("ITSM Structure",           "/mnt/extra-addons/itsm_structure.py"),
        ("Location Skeleton",        "/mnt/extra-addons/load_locations.py"),
        ("FIRS Offices v3 (415)",    "/mnt/extra-addons/load_offices_v3.py"),
        ("NRS HQ Phase 1 Assets",    "/mnt/extra-addons/scripts/nrs_hq_seed.py"),
        ("NRS HQ Location Metadata", "/mnt/extra-addons/scripts/nrs_hq_seed_v4.py"),
        ("Fleet Taxonomy",           "/mnt/extra-addons/fleet_taxonomy_seed.py"),
        ("Geocode Locations (OSM)",  "/mnt/extra-addons/geocode_locations.py"),
        ("Fleet → Location Matcher", "/mnt/extra-addons/fleet_location_matcher.py"),
    ],
    # Guaranty Trust Bank demo tenant. Generic ITSM structure + GTB company
    # branding + 122 GTB branches (41 real from OpenStreetMap with live coords,
    # 81 demo-fill across the remaining states) + light bank-facilities demo
    # requests. Branches load BEFORE the company seed so its demo requests can
    # attach to real branch locations. No FIRS/NRS data.
    "gtb": [
        ("ITSM Structure",              "/mnt/extra-addons/itsm_structure.py"),
        ("GTB Branches (122)",          "/mnt/extra-addons/scripts/load_gtb_locations.py"),
        ("GTB Company + Demo Requests", "/mnt/extra-addons/scripts/gtb_seed.py"),
        ("GTB Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/gtb_data_seed.py"),
    ],
    # Jaiz Bank Plc demo tenant. Generic ITSM structure + 39 real client-supplied
    # branches + company + demo requests + full demo depth (staff/assets/fleet).
    "jaiz": [
        ("ITSM Structure",               "/mnt/extra-addons/itsm_structure.py"),
        ("Jaiz Branches (39)",           "/mnt/extra-addons/scripts/load_jaiz_locations.py"),
        ("Jaiz Company + Demo Requests",  "/mnt/extra-addons/scripts/jaiz_seed.py"),
        ("Jaiz Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/jaiz_data_seed.py"),
    ],
    # Lagos State Ministry of Health demo tenant. Generic ITSM structure + 90
    # real public health facilities (60 PHCs + 30 General hospitals) + company +
    # demo requests + full demo depth (staff w/ 30 real Medical Directors,
    # healthcare-themed assets, ambulance fleet).
    "lasg": [
        ("ITSM Structure",               "/mnt/extra-addons/itsm_structure.py"),
        ("LASG Facilities (90)",         "/mnt/extra-addons/scripts/load_lasg_locations.py"),
        ("LASG Company + Demo Requests", "/mnt/extra-addons/scripts/lasg_seed.py"),
        ("LASG Demo Data (staff/assets/fleet)", "/mnt/extra-addons/scripts/lasg_data_seed.py"),
    ],
}


def _resolve_seed_path(path):
    """Resolve a seed-profile path against both dev and k8s layouts.

    In dev (docker-compose), the whole repo is bind-mounted at
    /mnt/extra-addons, so scripts/ files live at /mnt/extra-addons/scripts/.
    In k8s (Dockerfile.odoo.19.k8s), scripts/ is copied to /opt/cadra/scripts/
    instead. Profile entries are written using the dev layout; this swap
    lets the same profile work in both environments.
    """
    if os.path.exists(path):
        return path
    alt = path.replace("/mnt/extra-addons/scripts/", "/opt/cadra/scripts/")
    if alt != path and os.path.exists(alt):
        return alt
    return None


def run_seeds():
    """Idempotent re-run of the data seed scripts.

    Each seed uses get_or_create-style logic so running on a populated DB
    is a no-op for existing rows + creates anything new. Failures in one
    seed are logged but don't abort the next.
    """
    profile = (os.environ.get("CADRA_SEED_PROFILE", "core") or "").strip()
    if not profile:
        _say("seed profile is empty — skipping all seeds")
        return
    if profile not in SEED_PROFILES:
        _say(f"unknown seed profile {profile!r}; valid: {list(SEED_PROFILES)}",
             level="WARN")
        return

    _say(f"running seed profile: {profile}")
    for label, path in SEED_PROFILES[profile]:
        resolved = _resolve_seed_path(path)
        if not resolved:
            _say(f"  skip {label} — file not present at {path}", level="WARN")
            continue
        _say(f"  → {label} ({resolved})")
        try:
            # Inject our own env into the seed's globals (the seed expects
            # `env` to be available, same as Odoo shell does for us).
            seed_globals = {"env": env}
            exec(compile(open(resolved).read(), resolved, "exec"), seed_globals)
            env.cr.commit()
            _say(f"    ✓ {label}")
        except Exception as e:
            # catch-all: reported — a seed is arbitrary tenant-provisioning
            # code `exec`ed from this process, so its failure surface is
            # whatever that file does. One seed failing must not abort the
            # rest of provisioning, and the failure is announced at ERROR
            # with the seed's own label rather than counted or dropped.
            _say(f"    ✗ {label} failed: {type(e).__name__}: {e}", level="ERROR")


# ─── main ──────────────────────────────────────────────────────────

def main():
    _say("Cadra bootstrap starting")
    try:
        ensure_database_class()
        jwt_secret = ensure_jwt_secret()
        ensure_turnstile_secret()
        ensure_ai_key()
        ensure_admin_groups()
        client_id, raw_secret = ensure_test_client()
        tag_client_id, tag_raw_secret = ensure_tagging_client()
        vendra_client_id, vendra_raw_secret = ensure_vendra_client()
        ensure_mail_server()
        ensure_email_relay()
        env.cr.commit()
        run_seeds()
        env.cr.commit()
    except Exception:
        # catch-all: reported — the outermost handler of the whole script. It
        # RE-RAISES: the rollback and the traceback are the point, not the
        # catching. Without it a half-provisioned tenant would be committed
        # by whatever ran last, which is worse than none.
        env.cr.rollback()
        _logger.exception("bootstrap failed")
        raise

    _say("Cadra bootstrap complete")
    # Output sentinel-wrapped credentials for the host orchestrator to capture.
    # Sentinel format is deliberately simple — grep-friendly.
    print("CADRA_BOOTSTRAP_BEGIN", flush=True)
    print(f"JWT_SECRET={jwt_secret}", flush=True)
    print(f"CLIENT_ID={client_id}", flush=True)
    print(f"CLIENT_SECRET={raw_secret}", flush=True)
    print(f"TAGGING_CLIENT_ID={tag_client_id}", flush=True)
    print(f"TAGGING_CLIENT_SECRET={tag_raw_secret}", flush=True)
    print(f"VENDRA_CLIENT_ID={vendra_client_id}", flush=True)
    print(f"VENDRA_CLIENT_SECRET={vendra_raw_secret}", flush=True)
    print("CADRA_BOOTSTRAP_END", flush=True)


main()
