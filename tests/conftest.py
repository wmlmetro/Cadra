"""
Cadra API test fixtures + reporting hooks.

Session-scoped fixtures (mint once, reuse across tests):
  - api_base       : http://localhost:8069 (env-overridable via CADRA_API_BASE)
  - creds          : reads docs/api/.creds.<tenant> for the tenant CADRA_API_BASE names
  - token          : mints a JWT via POST /auth/token, returns the access_token
  - client         : ApiClient wrapper around requests.Session with auth pre-set
  - test_location  : creates one location via POST, reused as FK by asset/request tests
  - test_asset     : creates one asset against test_location
  - test_request   : creates one service request against test_location + test_asset
  - approval_settings : GET /settings/approvals — does a move need two people?
  - suite_user     : the user behind this suite's own credential (whoami)
  - second_person  : the two people a move takes since handoff 35, and the
                     `.move()` / `.transfer_custody()` helpers that raise a
                     request and approve it so an asset actually moves

Function-scoped:
  - capture        : helper that writes (request, response) pairs to docs/api/test-responses/

Hooks:
  - pytest_runtest_makereport  : record each test's outcome for the report
  - pytest_terminal_summary    : generate docs/api/test-report.md at session end
"""
import datetime
import json
import os
import pathlib
import time
import urllib.parse
from collections import defaultdict

import pytest
import requests


# ─── locations on disk ───────────────────────────────────────────────

# The published set (myservice_api/controllers/utils.py). An endpoint that
# answers with anything else has invented a code no integration can branch on.
CANONICAL_ERROR_CODES = frozenset({
    "unauthorized", "forbidden", "invalid_request", "validation_failed",
    "not_found", "conflict", "rate_limited", "internal_error",
    "not_implemented", "idempotency_mismatch", "server_misconfigured",
})

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CREDS_DIR = REPO_ROOT / "docs" / "api"
RESPONSES_DIR = REPO_ROOT / "docs" / "api" / "test-responses"
REPORT_FILE = REPO_ROOT / "docs" / "api" / "test-report.md"

# Printed verbatim inside a refusal. An error naming a remedy the reader then
# has to go and look up is worse than one naming none, because it implies the
# lookup will be quick.
_ODOO_SHELL = (
    "docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\\n"
    "  odoo shell -c /etc/odoo/odoo.conf -d %s --no-http \\\n"
    "  --http-port=8099 --gevent-port=8098 <<< \\\n"
    "  \"%s\""
)

_MARK_COMMAND = _ODOO_SHELL % (
    "%s",
    "env['ir.config_parameter'].sudo().set_param("
    "'cadra.database_class', 'test'); env.cr.commit()",
)

#: Targets the ONE credential that failed, by client_id. The first version
#: said `search([])` — flag everything — which on a test tenant also carrying
#: a copied integration credential would relabel that credential's records as
#: test artefacts: a false self-label in the one mechanism this guard defends.
_FLAG_COMMAND = _ODOO_SHELL % (
    "%s",
    "env['myservice.api.client'].sudo().with_context(active_test=False)"
    ".search([('client_id','=','%s')])"
    ".write({'is_test_credential': True}); env.cr.commit()",
)

# Collected at session end into the markdown report.
_test_results = []           # list of {nodeid, outcome, duration, method, path, status, capture_path}
_session_started_at = None


# ─── fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api_base():
    return os.environ.get("CADRA_API_BASE", "http://localhost:8069").rstrip("/")


def tenant_from_base(base):
    """The database name Cadra will route this base URL to.

    Tenancy is host-based: http://<db>.localhost:8069 and https://<db>.cadra.ng
    both resolve to database <db>. A bare host with no leading label (plain
    `localhost`, an IP) names no tenant, and the caller falls back to the
    lone per-tenant file if a single-tenant checkout has exactly one.
    """
    host = urllib.parse.urlsplit(base).hostname or ""
    label = host.split(".")[0].strip()
    if not label or label == host or label in ("localhost", "127", "0"):
        return None
    return label


def _parse_creds(path):
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            out[k] = v
    return out


@pytest.fixture(scope="session")
def _creds_unchecked(api_base):
    """Credentials for the tenant `CADRA_API_BASE` points at.

    Secrets are per-database — one Odoo process serves them all, but each
    holds its own `myservice.api.client` rows and its own `jwt_secret`. A
    single global creds file therefore points at whichever tenant was
    bootstrapped last, and aiming the suite anywhere else fails at the first
    call with a bare 401 that looks like a code fault. So: `.creds.<tenant>`,
    and nothing else.

    The shared `docs/api/.creds` is gone as of handoff 05. Nothing wrote it
    any more (`bootstrap.sh` has written per-tenant files since handoff 04),
    and the only branch that could still reach it was the no-tenant one
    below — which cannot authenticate against this stack anyway, because a
    bare `localhost` host answers "No database is selected". Keeping a
    world-readable file holding a live secret as a fallback nobody could
    reach was the worse half of both trades.
    """
    tenant = tenant_from_base(api_base)
    if tenant:
        # A named tenant takes ITS file or nothing. Falling back to a shared
        # file here would hand the suite another database's secret and
        # produce exactly the bare 401 this whole change exists to stop —
        # the failure would just have moved, not gone.
        candidates = [CREDS_DIR / f".creds.{tenant}"]
    else:
        # No tenant in the host (bare `localhost`, an IP). A single-tenant
        # checkout — CI, a fresh clone — where bootstrap wrote exactly one
        # per-tenant file and there is nothing to be ambiguous about. Two or
        # more and we do NOT guess.
        candidates = []
        only = sorted(CREDS_DIR.glob(".creds.*"))
        if len(only) == 1:
            candidates.append(only[0])

    path = next((c for c in candidates if c.exists()), None)
    if path is None:
        looked = "\n  ".join(str(c) for c in candidates)
        pytest.fail(
            f"no credentials file for {api_base}"
            + (f" (tenant {tenant!r})" if tenant else "")
            + ".\nLooked for:\n  " + looked
            + "\n\nCreate a client on that database with\n"
              "  docker compose -f docker-compose.yml -f docker-compose.19.yml "
              "run --rm -T odoo bash -c \\\n"
              "    \"odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http <<< \\\n"
              "      \\\"exec(open('/mnt/extra-addons/docs/api/setup_api_smoke.py')"
              ".read())\\\"\"\n"
              "and save the printed credentials as that file. "
              "(scripts/bootstrap.sh takes its database from POSTGRES_DB in "
              ".env, not an argument.)"
        )

    out = _parse_creds(path)
    if "CLIENT_ID" not in out or "CLIENT_SECRET" not in out:
        pytest.fail(
            f"{path} is missing CLIENT_ID or CLIENT_SECRET.\n\n"
            "If the file holds only comments, bootstrap preserved a secret it "
            "cannot read back and had no previous value to keep. Re-running "
            "bootstrap will do the same thing again. Either:\n"
            "  - set CADRA_TEST_CLIENT_SECRET to a known value and re-run "
            "bootstrap, or\n"
            "  - rotate the client's secret (Settings -> API Clients, or "
            "CADRA_SMOKE_ROTATE=1 with docs/api/setup_api_smoke.py against "
            "this database) and paste the new value in."
        )
    if out["CLIENT_SECRET"].startswith("<"):
        # bootstrap.py prints a placeholder rather than the secret when it
        # preserves an existing one; a shell that captured stdout blindly
        # used to write that placeholder into the file.
        pytest.fail(
            f"{path} holds a placeholder, not a secret: "
            f"{out['CLIENT_SECRET']!r}. Re-run bootstrap with "
            "CADRA_TEST_CLIENT_SECRET set to a known value, or rotate the "
            "client's secret from Settings → API Clients."
        )
    out["_source"] = str(path)
    return out


@pytest.fixture(scope="session")
def token(api_base, creds):
    """Mint a JWT once per test session and cache it.

    Depends on `database_accepts_test_writes` so that no test can hold a
    bearer token for a database that has not been marked as a test
    database. Every writing path in the suite reaches the API through
    `client`, and `client` reaches it through here.
    """
    try:
        r = requests.post(
            f"{api_base}/api/v1/auth/token",
            json={
                "client_id": creds["CLIENT_ID"],
                "client_secret": creds["CLIENT_SECRET"],
            },
            timeout=10,
        )
    except requests.exceptions.ConnectionError as e:
        pytest.fail(
            f"Could not connect to Cadra API at {api_base}.\n"
            f"Is the docker stack up?\n"
            f"  ODOO_DBFILTER='^%d$' docker compose -f docker-compose.yml -f docker-compose.19.yml up -d\n"
            f"Underlying error: {e}"
        )
    if r.status_code != 200:
        pytest.fail(
            f"Failed to mint test token: HTTP {r.status_code}\n{r.text[:500]}"
        )
    body = r.json()
    return body["data"]["access_token"]


# ─── which database is this, and may we write to it? ─────────────────

@pytest.fixture(scope="session")
def database_accepts_test_writes(api_base, _creds_unchecked):
    """Refuse the whole session unless the target database is marked `test`.

    WHY THIS IS THE FIRST THING THAT HAPPENS
    ----------------------------------------
    Handoff 24 §B measured what this suite writes and where. On 2026-09-15,
    in `jaizbankplc` — a register derived from a live client's data — 3,584 of
    4,056 assets were named `pytest-*`, 354 of 420 entries in the PUBLIC
    homepage location dropdown were fixtures, and six fabricated approved
    disposals sat in the auditor-facing disposal report. Accumulated over 154
    sessions.

    The only control was `CADRA_API_BASE`: this suite read one environment
    variable and wrote wherever it pointed, with no teardown — the API
    publishes exactly one DELETE route in total, so nothing it creates can be
    removed afterwards. Nothing reached production, and that was luck.

    So the question is asked of the DATABASE, which is the only party to it
    that survives a restore: `cadra.database_class`, a system parameter a
    person set deliberately. Not the name — `test19` reads safe and `cadra19`
    does not, and both are wrong the day a client dump lands in one. Not the
    environment variable, which is the control that failed.

    **Absent refuses.** A database nobody classified is a database nobody
    thought about.

    **`creds` depends on THIS fixture**, so nothing in the suite can
    authenticate without passing through it — see that fixture's docstring
    for the second door this closes.

    **What it writes before it can refuse, stated rather than glossed.**
    Classifying the database needs a bearer token, and `POST /auth/token`
    is NOT a read: `_session_payload` issues a refresh token, which
    `myservice.api.refresh_token._issue` CREATEs and the request commits. So
    one refresh-token row lands in the target database before the refusal
    prints, and handoff 25's acceptance criterion — "refuses before writing
    anything" — is met for the register and NOT met literally.

    Closing it completely needs an unauthenticated classification route, and
    `cadra_route` has no public mode: auth is enforced in `cadra_endpoint`
    for every route in the API without exception. Adding one is a change to
    the central auth decorator, which is the "nine pre-envelope routes"
    backlog item's territory and not something to do in passing in a handoff
    about test safety. The row is operational, indistinguishable from any
    integration authenticating, and carries no fixture data — but it is a
    write, and calling it a read (which this docstring did until a review
    caught it) is exactly the kind of convenient sentence this repository
    keeps finding in its own comments.

    It is deliberately NOT `autouse`. An autouse session fixture also
    fires for the static suites — `test_source_guards.py`,
    `test_deployment_profile.py` — which assert things about the source
    and are documented to run with no instance up. Gating authentication
    rather than gating every test keeps that true while covering strictly
    more: an unauthenticated test cannot write.

    **This fails, it does not skip.** Report 23 §3 established the rule for
    this repository: a skip is a guard that passes, and a suite that quietly
    skips its way to green against a client's register is the failure it was
    written to stop.
    """
    probe = requests.post(
        f"{api_base}/api/v1/auth/token",
        json={"client_id": _creds_unchecked["CLIENT_ID"],
              "client_secret": _creds_unchecked["CLIENT_SECRET"]},
        timeout=10,
    )
    if probe.status_code != 200:
        pytest.exit(
            "\nREFUSED: could not authenticate against %s to establish "
            "which database it is.\n\n  POST /api/v1/auth/token -> HTTP "
            "%s\n  %s\n" % (api_base, probe.status_code, probe.text[:300]),
            returncode=1)

    r = ApiClient(api_base, probe.json()["data"]["access_token"]).get(
        "/api/v1/meta/database")
    if r.status_code != 200:
        pytest.exit(
            "\nREFUSED: cannot establish which database %s is.\n\n"
            "  GET /api/v1/meta/database -> HTTP %s\n  %s\n\n"
            "This suite will not write to a database it cannot classify. If "
            "the server predates handoff 25 the route does not exist yet; "
            "upgrade `myservice_api` on that database.\n"
            % (api_base, r.status_code, r.text[:300]),
            returncode=1)

    info = r.json()["data"]
    if not info["accepts_test_writes"]:
        pytest.exit(
            "\nREFUSED: the HTTP test suite will not run against database "
            "%r (%s).\n\n"
            "  cadra.database_class = %s\n\n"
            "Every record this suite creates stays: there is no teardown and "
            "the API publishes one DELETE route in total. If %r is a "
            "throwaway database, mark it once:\n\n"
            "%s\n\n"
            "There is no bypass flag, deliberately.\n"
            % (info["database"], api_base,
               info["database_class"] or "not set",
               info["database"], _MARK_COMMAND % info["database"]),
            returncode=1)

    if not info["credential_is_test"]:
        pytest.exit(
            "\nREFUSED: the credential this suite authenticates with is not "
            "flagged `is_test_credential`.\n\n"
            "  database: %s   credentials: %s\n\n"
            "The flag is what makes a fixture identifiable afterwards — it "
            "drives `nrs.asset.custody.source = 'test'`, which is why the "
            "chain of custody self-labels without anyone curating it. "
            "Handoff 23 minted one credential without it and its six approved "
            "disposals are the only artefacts in that register a reader "
            "cannot identify from the record itself.\n\n"
            "Flag it:\n\n%s\n"
            % (info["database"], _creds_unchecked["_source"],
               _FLAG_COMMAND % (info["database"], _creds_unchecked["CLIENT_ID"])),
            returncode=1)

    return info


@pytest.fixture(scope="session")
def creds(_creds_unchecked, database_accepts_test_writes):
    """The tenant's credentials — handed out only once the database is cleared.

    **This is the gate, and it is here rather than on `token` for a reason
    a review found the hard way.** Gating `token` looked sufficient, because
    every writing path reaches the API through `client` and `client` through
    `token`. It was not: four tests take `api_base` + `creds` and POST to
    `/api/v1/auth/token` with bare `requests` — `test_auth.py` three times
    and `test_negative.py` once — so `pytest tests/test_auth.py` against a
    client-derived register ran green, never instantiated the guard, and
    wrote a refresh-token row per call.

    Gating the CREDENTIALS closes that by construction: there is no way to
    authenticate against this API without them, so there is no second door to
    find. `tests/test_source_guards.py` fails on any test module that reaches
    for `_creds_unchecked`, which exists only so the guard itself can read the
    file without depending on its own output.
    """
    return _creds_unchecked


class ApiClient:
    """Thin wrapper around requests.Session that pre-sets the bearer header
    and resolves relative URLs against api_base. Used by all tests via the
    `client` fixture below."""

    def __init__(self, base, token):
        self.base = base
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _url(self, path):
        return path if path.startswith("http") else self.base + path

    def get(self, path, **kw):
        return self.session.get(self._url(path), timeout=30, **kw)

    def post(self, path, **kw):
        return self.session.post(self._url(path), timeout=30, **kw)

    def patch(self, path, **kw):
        return self.session.patch(self._url(path), timeout=30, **kw)

    def put(self, path, **kw):
        return self.session.put(self._url(path), timeout=30, **kw)

    def delete(self, path, **kw):
        return self.session.delete(self._url(path), timeout=30, **kw)


@pytest.fixture(scope="session")
def client(api_base, token):
    return ApiClient(api_base, token)


@pytest.fixture(scope="session")
def unauthed_client(api_base):
    """A client with NO Authorization header — used by negative tests."""
    return ApiClient(api_base, token=None)


# ─── nobody moves an asset alone (handoff 35) ────────────────────────
#
# On a tenant where `cadra.approval.required` is on — and ABSENT MEANS ON, so
# an unconfigured tenant like `test19` is one — `POST /assets/<id>/move` and
# `POST /assets/<id>/transfer-custody` no longer move anything. They raise an
# `nrs.asset.change.request`, answer 200 with `pending_approval: true` and the
# asset UNCHANGED, and the change happens when a SECOND person approves.
#
# That is a breaking change for this suite, because a dozen tests across four
# modules exist to assert what happens AFTER an asset has moved: the
# append-only movement row, the custody chain, the history event, the transfer
# document's reference number. Every one of them needs a real move, and a real
# move now needs two people.
#
# So this is the one place that knows how. Each module having its own would
# be four copies of a rule that will change the first time NRS reshapes who
# may approve what — which the handoff says out loud is coming.

#: The second person, by login. Overridable because this is an environment
#: fact and not a property of the API: `admin`/`admin` is accepted on all
#: eight local tenants (verified 2026-09-15, `docs/GO-LIVE.md` §8.1) and is
#: what `scripts/bootstrap.sh` provisions in CI, but a tenant whose admin
#: password has been changed is a legitimate target for this suite and should
#: not need a code edit to run against.
SECOND_PERSON_LOGIN = os.environ.get("CADRA_SECOND_PERSON_LOGIN", "admin")
SECOND_PERSON_PASSWORD = os.environ.get("CADRA_SECOND_PERSON_PASSWORD", "admin")


@pytest.fixture(scope="session")
def approval_settings(client):
    """`GET /api/v1/settings/approvals`, once — read, never assumed.

    Whether this tenant requires a second person is a fact about the
    DATABASE, not about the code: the switch is a system parameter read with
    raw SQL (`myservice_asset_register/approval_policy.py`), absent means on,
    and there is no environment variable that changes it. So the suite asks,
    and every helper below branches on the answer rather than on what
    `test19` happened to say the day this was written.
    """
    r = client.get("/api/v1/settings/approvals")
    if r.status_code != 200:
        pytest.fail(
            "GET /api/v1/settings/approvals answered HTTP %s.\n%s\n\n"
            "This suite cannot tell whether a move needs a second person, "
            "and every move it makes would be guesswork. If the server "
            "predates handoff 35 the route does not exist yet; upgrade "
            "`myservice_api` on that database."
            % (r.status_code, r.text[:300]))
    return r.json()["data"]


@pytest.fixture(scope="session")
def suite_user(client):
    """The user behind this suite's own credential.

    NOT called `me`: `tests/test_rejected_fields_are_refused.py` already
    defines a module-scoped `me`, and a session fixture of the same name
    would be shadowed there — so `second_person` would silently receive that
    module's narrower dict the moment anything in that file asked for it.
    """
    r = client.get("/api/v1/auth/whoami")
    assert r.status_code == 200, r.text[:300]
    return r.json()["data"]


@pytest.fixture(scope="session")
def second_person(api_base, client, suite_user, approval_settings):
    """The two people a move takes, and which of them does what.

    **The suite's credential APPROVES; the second person RAISES.** That is
    the way round it is, and the reason is the provenance of the row rather
    than the story: the append-only `nrs.asset.movement` and
    `nrs.asset.custody` rows are written by `action_approve`, under the
    APPROVER's user, and `myservice_api/models/append_only.py` relabels a row
    written under a credential flagged `is_test_credential` as `source:
    "test"`. These rows are permanent — `write` and `unlink` raise — so a
    suite whose moves came back labelled `approval` would be leaving
    artefacts in a register that a reader cannot tell from real history.
    That is the property handoffs 26 and 28 built and
    `test_custody.test_a_link_this_suite_wrote_says_so` guards, and it is
    worth more than the alternative arrangement's prize.

    **What that costs, said rather than glossed:** the
    `nrs.asset.change.request` rows this helper creates are raised by the
    second person, who is NOT an API credential, so they are not stamped
    `is_test_fixture`. The request rows raised in `tests/test_approvals.py`
    are raised by the suite's own credential and are stamped. One or the
    other — a person cannot both raise and approve, which is the whole point
    of the feature.

    Fails rather than skips when the tenant needs a second person and there
    is nobody to be one. Report 23 §3: a skip is a guard that passes, and a
    dozen tests quietly skipping their way to green would leave the recorder
    they exist to exercise untested on exactly the tenants where the control
    is on.
    """
    r = requests.post(
        f"{api_base}/api/v1/auth/login",
        json={"login": SECOND_PERSON_LOGIN,
              "password": SECOND_PERSON_PASSWORD},
        timeout=30,
    )
    other = None
    if r.status_code == 200:
        other_client = ApiClient(api_base, r.json()["data"]["access_token"])
        who = other_client.get("/api/v1/auth/whoami")
        if who.status_code == 200:
            data = who.json()["data"]
            if data["id"] != suite_user["id"]:
                other = {"client": other_client, "id": data["id"],
                         "name": data["name"]}

    if other is None and approval_settings["required"]:
        pytest.fail(
            "This register requires a second person to approve a move or a "
            "custody change (`%s` = %r), and this session could not sign one "
            "in.\n\n"
            "  POST /api/v1/auth/login as %r -> HTTP %s\n  %s\n\n"
            "Every test that needs an asset to actually MOVE needs two "
            "different users. Set CADRA_SECOND_PERSON_LOGIN and "
            "CADRA_SECOND_PERSON_PASSWORD to a user who holds "
            "`myservice_asset_register.group_asset_manager` and is not the "
            "suite's own credential (%s, id %s)."
            % (approval_settings["parameter"], approval_settings["setting"],
               SECOND_PERSON_LOGIN, r.status_code, r.text[:200],
               suite_user["login"], suite_user["id"]))
    return SecondPerson(suite=client, suite_id=suite_user["id"], other=other,
                        required=bool(approval_settings["required"]))


class SecondPerson:
    """How this session moves an asset, on either kind of tenant.

    `move()` and `transfer_custody()` answer the same normalised dict
    whichever way the change got made, so a caller asserting *the asset ended
    up there and the append-only row says so* does not have to know which
    tenant it is running against:

        pending             did this go through an approval at all
        raised              the Response from /move or /transfer-custody
        decision            the Response from /approvals/<id>/approve, or None
        request             the decided approval request, or None
        asset               the asset AFTER, as the API returned it
        movement_id         the `nrs.asset.movement` row, or None
        custody_id          the `nrs.asset.custody` row, or None
        transfer_id         the `nrs.asset.transfer` document, or None
        transfer_reference  its reference, or None

    The two shapes it normalises are genuinely different and both are
    published contract: `/move` answers `{asset, movement_id, transfer:
    {id, reference, from_location, to_location, movement_id}}` and
    `/approvals/<id>/approve` answers `{request, asset}` with the ids on the
    request. A test that needs the route-specific shape asserts on `raised`
    or `decision` itself; a test that needs the asset moved uses these keys.
    """

    def __init__(self, suite, suite_id, other, required):
        self.suite = suite
        self.suite_id = suite_id
        self.other = other
        self.required = required

    @property
    def requester(self):
        """Whoever asks. The second person when approval is on."""
        return self.other["client"] if self.required else self.suite

    @property
    def approver_id(self):
        return self.suite_id if self.required else None

    def move(self, asset_id, to_location_id, reason=None, **kw):
        return self._act(asset_id, "move",
                         {"to_location_id": to_location_id}, reason, **kw)

    def transfer_custody(self, asset_id, to_custodian_id, reason=None, **kw):
        return self._act(asset_id, "transfer-custody",
                         {"to_custodian_id": to_custodian_id}, reason, **kw)

    def _act(self, asset_id, verb, body, reason, headers=None):
        body = dict(body)
        if reason is not None:
            body["reason"] = reason
        if self.required:
            body["approver_id"] = self.approver_id
        raised = self.requester.post(f"/api/v1/assets/{asset_id}/{verb}",
                                     json=body, headers=headers or {})
        if not self.required:
            data = assert_envelope_ok(raised)["data"]
            custody = data.get("custody_change") or {}
            transfer = data.get("transfer") or {}
            return {
                "pending": False, "raised": raised, "decision": None,
                "request": None, "asset": data["asset"],
                "movement_id": data.get("movement_id"),
                "custody_id": custody.get("custody_id"),
                "transfer_id": transfer.get("id"),
                "transfer_reference": transfer.get("reference"),
            }

        data = assert_envelope_ok(raised)["data"]
        assert data["pending_approval"] is True, (
            "this tenant requires approval and %s answered without "
            "`pending_approval`: %r" % (verb, data))
        # The SUITE approves — see the fixture's docstring for why that is
        # the way round, and why it is not merely a coincidence of who holds
        # which credential on `test19`.
        decision = self.suite.post(
            "/api/v1/approvals/%s/approve" % data["request"]["id"], json={})
        decided = assert_envelope_ok(decision)["data"]
        req = decided["request"]
        assert req["state"] == "approved", req
        return {
            "pending": True, "raised": raised, "decision": decision,
            "request": req, "asset": decided["asset"],
            "movement_id": req["movement_id"],
            "custody_id": req["custody_id"],
            "transfer_id": (req["transfer"] or {}).get("id"),
            "transfer_reference": req["transfer_reference"],
        }


# ─── response capture ────────────────────────────────────────────────

@pytest.fixture
def capture(request):
    """Returns a function `capture(name, response)` that writes the full
    request/response pair to docs/api/test-responses/<name>.json.

    `name` is treated as a relative path under the responses dir — use
    forward slashes to group by resource: capture("locations/list", r).
    """
    def _capture(name, response):
        path = RESPONSES_DIR / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Pull the request that produced this response (requests stores it
        # on the Response object).
        req = response.request
        req_body = None
        if req.body is not None:
            try:
                req_body = json.loads(req.body) if isinstance(req.body, (str, bytes)) else req.body
            except Exception:
                req_body = req.body.decode("utf-8", errors="replace") if isinstance(req.body, bytes) else str(req.body)

        # Parse response body if possible
        try:
            resp_body = response.json()
        except Exception:
            text = response.text
            resp_body = text[:2000] + (" ... <truncated>" if len(text) > 2000 else "")

        payload = {
            "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            "request": {
                "method": req.method,
                "url": req.url,
                "headers": _redact_headers(req.headers),
                "body": _redact(req_body),
            },
            "response": {
                "status": response.status_code,
                "headers": _redact_headers(response.headers),
                "elapsed_seconds": response.elapsed.total_seconds(),
                "body": _redact(resp_body),
            },
        }
        path.write_text(json.dumps(payload, indent=2, default=str))

        # Attach metadata so the report hook can render the row.
        nodeid = request.node.nodeid
        capture_relpath = path.relative_to(RESPONSES_DIR.parent).as_posix()
        request.node.user_properties.append(
            ("cadra_endpoint", {
                "method": req.method,
                "url": req.url,
                "path": _extract_path(req.url),
                "status": response.status_code,
                "capture": capture_relpath,
            })
        )

    return _capture


# Anything in a request or response body whose name says "secret". The
# Authorization header was already redacted; the BODY was not, so every
# captured /auth/token call wrote the live client secret to disk — and CI
# uploads docs/api/test-responses/ as a 14-day artifact. Captures are
# evidence, not a credential store.
_SECRET_KEYS = frozenset({
    "client_secret", "access_token", "refresh_token", "password",
    "jwt_secret", "secret",
})

# Headers carrying a credential. `Set-Cookie` on an /auth/* response holds an
# Odoo session id, which is as much a credential as the bearer token — and the
# response headers were being written verbatim.
_SECRET_HEADERS = frozenset({"authorization", "cookie", "set-cookie",
                             "x-api-key", "proxy-authorization"})


def _redact_headers(headers):
    return {k: ("<redacted>" if k.lower() in _SECRET_HEADERS else v)
            for k, v in headers.items()}


def _redact(value):
    """Recursively replace secret-named values. Structure is preserved so the
    capture still documents the request's shape."""
    if isinstance(value, dict):
        return {k: ("<redacted>" if k.lower() in _SECRET_KEYS else _redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _extract_path(url):
    """Strip protocol/host/query from URL → just the path."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return parts.path


# ─── shared test resources (created once per session) ────────────────

@pytest.fixture(scope="session")
def any_location(client):
    """The id of a location that EXISTS in this register, whatever it is.

    Four location tests used to ask for `/api/v1/locations/1` outright. That
    passed for as long as the suite was pointed at one richly-seeded register
    and broke the moment handoff 25 moved it onto a marked test tenant, where
    row 1 is not a location. The id of a row is not a fact about the API — it
    is a fact about one database's insert order — so the tests now read one
    off the register instead of assuming it.

    Falls back to the fixture location, so this works on an empty tenant too.
    """
    r = client.get("/api/v1/locations", params={"limit": 1})
    if r.status_code == 200:
        items = r.json().get("data") or []
        if items:
            return items[0]["id"]
    created = client.post("/api/v1/locations",
                          json={"name": "pytest-any-location"})
    if created.status_code != 201:
        pytest.fail("no location exists and one could not be created: HTTP %s %s"
                    % (created.status_code, created.text[:200]))
    return created.json()["data"]["id"]


@pytest.fixture(scope="session")
def test_location(client):
    """Create one location at session start; reused as FK by asset/request tests."""
    r = client.post("/api/v1/locations", json={
        "name": f"pytest-loc-{int(time.time())}",
        "description": "Created by tests/conftest.py — leave in dev DB",
    })
    if r.status_code != 201:
        pytest.fail(f"test_location fixture failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]


@pytest.fixture(scope="session")
def test_asset(client, test_location):
    """Create one asset at session start; reused by request tests.

    ON THE REGISTER whichever way the tenant's receipt switch is set
    (handoff 58 §2): every test using it is about an asset already
    registered, so with the gates on it is walked through them by
    `tests/gates.py`, the one helper. Switch off, that is the plain create
    this always was."""
    from . import gates
    ts = int(time.time())
    return gates.new_registered_asset(
        client,
        name=f"pytest-asset-{ts}",
        category_id=1,  # first asset category (seed has many)
        condition="new",
        state="active",
        location_id=test_location["id"],
    )


@pytest.fixture(scope="session")
def test_request(client, test_location, test_asset):
    """Create one service request at session start; reused by action tests.

    It sends `location_id`, and FAILS unless the location comes back.

    This fixture sent one from the day it was written and for all that time
    it was NEVER saved. The request model's field was renamed in the move to
    Odoo 19 (`generic_location_id`); `POST /requests` went on asking the
    model for `location_id`, refused the key because the model did not
    define it, and answered 201 with
    `data._warnings.rejected_fields == ["location_id"]` — which nobody read,
    this fixture included. Handoff 31 turned the silent drop into a 400, the
    fixture broke, and that is how it was found. The route now translates
    the published key onto the model's field.

    So the assertion below is the one nobody ever made: that what was sent
    was KEPT. A 201 is not evidence of that, and for the life of this suite
    it was mistaken for it.
    """
    r = client.post("/api/v1/requests", json={
        "type_id": 1,        # Incident (first seeded type)
        "category_id": 5,    # First existing category (1-4 skipped by seed)
        "priority": "2",
        "request_text": f"<p>pytest fixture request created at {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z</p>",
        "location_id": test_location["id"],
        "nrs_asset_id": test_asset["id"],
    })
    if r.status_code != 201:
        pytest.fail(f"test_request fixture failed: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()["data"]
    if (data.get("location") or {}).get("id") != test_location["id"]:
        pytest.fail("test_request fixture: the request was created and its "
                    "`location_id` was NOT kept — data.location is %r"
                    % (data.get("location"),))
    return data


# ─── reporting hooks ────────────────────────────────────────────────

def pytest_sessionstart(session):
    global _session_started_at
    _session_started_at = datetime.datetime.now(datetime.timezone.utc)
    # Clear the responses dir so stale captures don't accumulate.
    # `missing_ok` because two sessions started against one instance race
    # here: both enumerate the same files and the loser crashes the whole
    # session with FileNotFoundError before a single test runs. The captures
    # are throwaway artefacts, so losing the race is harmless — crashing on
    # it is not.
    if RESPONSES_DIR.exists():
        for p in RESPONSES_DIR.rglob("*.json"):
            p.unlink(missing_ok=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Collect per-test outcome + endpoint metadata into _test_results.

    Uses hookwrapper to read pytest's resolved outcome — that way xfail
    tests are correctly classified as 'xfailed' (not 'failed')."""
    out = yield
    report = out.get_result()
    if report.when != "call":
        return

    # Pull endpoint metadata captured via user_properties
    endpoint_meta = None
    for k, v in item.user_properties:
        if k == "cadra_endpoint":
            endpoint_meta = v
            break

    # Classify outcome using pytest's authoritative report fields
    if getattr(report, "wasxfail", None) is not None:
        outcome = "xfailed" if report.outcome == "skipped" else "xpassed"
    elif report.outcome == "passed":
        outcome = "passed"
    elif report.outcome == "skipped":
        outcome = "skipped"
    else:
        outcome = "failed"

    _test_results.append({
        "nodeid": item.nodeid,
        "outcome": outcome,
        "duration": call.stop - call.start,
        "endpoint": endpoint_meta,
        "error": str(call.excinfo.value)[:300] if call.excinfo else None,
        "xfail_reason": getattr(report, "wasxfail", None) or None,
    })


_OUTCOME_ICON = {
    "passed":  "✅",
    "failed":  "❌",
    "xfailed": "⚠️ ",  # expected failure (known upstream issue)
    "xpassed": "❗",   # unexpectedly passing — investigate
    "skipped": "⏭️ ",
}


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Write the markdown report at session end."""
    if not _test_results:
        return

    total = len(_test_results)
    counts = defaultdict(int)
    for t in _test_results:
        counts[t["outcome"]] += 1
    duration_total = sum(t["duration"] for t in _test_results)

    # Group by resource (first path segment after /api/v1/)
    by_resource = defaultdict(lambda: defaultdict(int))
    for t in _test_results:
        ep = t["endpoint"]
        if ep and ep.get("path"):
            parts = [p for p in ep["path"].split("/") if p]
            res = parts[2] if len(parts) >= 3 else "other"
        else:
            res = "non-endpoint"
        by_resource[res]["total"] += 1
        by_resource[res][t["outcome"]] += 1

    lines = [
        "# Cadra API Test Report",
        "",
        f"**Run:** {_session_started_at.isoformat()}  ",
        f"**Total tests:** {total}  ",
        f"**Passed:** {counts['passed']}  "
        f"**Failed:** {counts['failed']}  "
        f"**xfailed (known upstream issues):** {counts['xfailed']}  "
        f"**xpassed:** {counts['xpassed']}  "
        f"**skipped:** {counts['skipped']}  ",
        f"**Duration:** {duration_total:.2f}s",
        "",
        "## Per-resource summary",
        "",
        "| Resource | Tests | ✅ Passed | ❌ Failed | ⚠️ xfailed |",
        "|---|---:|---:|---:|---:|",
    ]
    for res, c in sorted(by_resource.items()):
        lines.append(
            f"| {res} | {c['total']} | {c['passed']} | {c['failed']} | {c['xfailed']} |"
        )

    lines += [
        "",
        "## Endpoint coverage",
        "",
        "| Method | Path | Status | Test | Response |",
        "|---|---|---:|---|---|",
    ]
    for t in _test_results:
        ep = t.get("endpoint") or {}
        method = ep.get("method", "-")
        path = ep.get("path", "-")
        status = ep.get("status", "-")
        nodeid = t["nodeid"]
        test_label = nodeid.replace("tests/", "")
        icon = _OUTCOME_ICON.get(t["outcome"], "?")
        capture = ep.get("capture")
        cap_link = f"[json]({capture.replace('docs/api/', '')})" if capture else "-"
        lines.append(
            f"| {method} | `{path}` | {icon} {status} | `{test_label}` | {cap_link} |"
        )

    # xfailed (known upstream issues) — surface reasons
    xfailed = [t for t in _test_results if t["outcome"] == "xfailed"]
    if xfailed:
        lines += [
            "",
            "## ⚠️ Known upstream issues (xfailed)",
            "",
            "These tests fail as expected because of bugs in modules other "
            "than `myservice_api`. The API layer routes the call correctly "
            "and returns a PRD-shaped error envelope; the underlying logic "
            "in a delegated controller is broken. See each test's xfail "
            "reason for the upstream fix needed.",
            "",
        ]
        for t in xfailed:
            lines.append(f"### `{t['nodeid']}`")
            lines.append("")
            if t.get("xfail_reason"):
                lines.append(f"> {t['xfail_reason']}")
                lines.append("")
            ep = t.get("endpoint") or {}
            if ep:
                lines.append(f"- **Endpoint:** `{ep.get('method')} {ep.get('path')}`")
                lines.append(f"- **Returned status:** {ep.get('status')}")
                cap = ep.get('capture')
                if cap:
                    lines.append(f"- **Captured response:** [{cap}]({cap.replace('docs/api/', '')})")
                lines.append("")

    # Real failures
    failures = [t for t in _test_results if t["outcome"] == "failed"]
    if failures:
        lines += ["", "## ❌ Failures", ""]
        for t in failures:
            lines.append(f"### `{t['nodeid']}`")
            lines.append("")
            lines.append(f"```\n{t['error']}\n```")
            lines.append("")

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines) + "\n")

    terminalreporter.write_sep("=", "cadra api test report",
                               green=(counts['failed'] == 0))
    terminalreporter.write_line(f"Report: {REPORT_FILE}")
    terminalreporter.write_line(f"Captured responses: {RESPONSES_DIR}/")


# ─── helpers used by tests (importable) ──────────────────────────────

@pytest.fixture(scope="session")
def admin_scope(client):
    """Skip a test when the token has no `admin` scope.

    Configuration endpoints are admin-scoped on purpose — changing a category's
    useful life restates book value across a whole class of assets, and
    branding changes what every user sees. A token without it should produce a
    clear skip, not a wall of 403s that reads as a broken feature.
    """
    r = client.get("/api/v1/auth/whoami")
    if r.status_code != 200:
        pytest.skip("cannot determine token scopes")
    scopes = (r.json().get("data") or {}).get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    if "admin" not in scopes and "*" not in scopes:
        pytest.skip(f"token lacks the `admin` scope (has: {sorted(scopes)})")
    return True


@pytest.fixture
def receipt_switch(client, admin_scope):
    """Yields a setter for the tenant's receipt-gate switch
    (`PATCH /api/v1/settings/receipt-gate`) and puts the tenant's OWN value
    back afterwards, whatever happens.

    For a test ABOUT the receipt path — `POST /assets` as INT-03 — whose
    answer depends on the switch (handoff 58 §2): it is parametrised over
    both states and sets the one it is asserting. Every other test leaves the
    switch alone and gets its asset from `tests/gates.py`."""
    def _gated():
        data = assert_envelope_ok(client.get("/api/v1/settings"))["data"]
        return bool(data.get("receipt_gated"))

    def _set(on):
        assert_envelope_ok(client.patch("/api/v1/settings/receipt-gate",
                                        json={"enabled": bool(on)}))

    was = _gated()
    try:
        yield _set
    finally:
        _set(was)


def lagos_today():
    """Today's date IN LAGOS — UTC+1, fixed; Nigeria keeps no summer time.

    Not `time.strftime`, which is the date of whatever machine runs the
    suite: Lagos on the bench, UTC in CI. Every day the register publishes
    is a Lagos day, so a test asking for "today's" rows asks for this one.
    """
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)).date()


def assert_envelope_ok(response, expected_status=200):
    """Assert response is the PRD success envelope at the given status."""
    assert response.status_code == expected_status, (
        f"expected {expected_status}, got {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    assert "data" in body, f"missing `data` in envelope: {body}"
    assert "meta" in body, f"missing `meta` in envelope: {body}"
    meta = body["meta"]
    assert "request_id" in meta and meta["request_id"], "missing request_id"
    assert "timestamp" in meta, "missing timestamp"
    assert "version" in meta, "missing version"
    return body


def assert_envelope_err(response, expected_status, expected_code=None):
    """Assert response is the PRD error envelope at the given status."""
    assert response.status_code == expected_status, (
        f"expected {expected_status}, got {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    assert "error" in body, f"missing `error` in envelope: {body}"
    err = body["error"]
    assert "code" in err and err["code"], "missing error.code"
    assert "message" in err and err["message"], "missing error.message"
    assert "request_id" in err and err["request_id"], "missing error.request_id"
    if expected_code:
        assert err["code"] == expected_code, (
            f"expected code={expected_code}, got {err['code']}"
        )
    return body


def assert_fields_refused(response, *named):
    """Assert the refusal a write route gives a field it does not accept.

    **400 `invalid_request`, `details.rejected_fields`, `details.writable` —
    and nothing written** (handoff 31 §B). Until then the answer was a 2xx
    with the dropped keys named in `data._warnings.rejected_fields`, which
    for most of this API's life nothing read: this suite's own `test_request`
    fixture sent a key that was never once saved, and found out from the 400.

    Every field in `named` must be among the rejected; returns `details`, so
    a caller can assert the list exactly where that is the property. What
    this CANNOT assert is the half that matters — that nothing was written.
    That takes a read of the record, and each caller owes one.
    """
    body = assert_envelope_err(response, 400, "invalid_request")
    assert "data" not in body, (
        "a refusal that also carries the record it says it did not write")
    details = body["error"].get("details") or {}
    rejected = details.get("rejected_fields")
    assert isinstance(rejected, list), (
        f"`details.rejected_fields` is not a list: {details}")
    for name in named:
        assert name in rejected, (
            f"`{name}` was not named in `details.rejected_fields` "
            f"({rejected}). A caller repairs itself from that list.")
    writable = details.get("writable")
    assert isinstance(writable, list), (
        f"`details.writable` is not a list: {details}")
    assert writable == sorted(writable), "`details.writable` is not sorted"
    assert not set(rejected) & set(writable), (
        f"{sorted(set(rejected) & set(writable))} refused and listed as "
        "writable in the same response")
    return details


def ids_matching(client, path, marker):
    """The ids `GET <path>?q=<marker>` finds — how a test proves a refused
    CREATE created nothing.

    A create has no record to read back, so "nothing was written" is asked
    of the list: a marker unique to the test, searched before and after.
    Whoever uses this owes a CONTROL — the same marker created without the
    refused key must then be found — or an `?q=` that had quietly stopped
    matching would make every "created nothing" pass on its own.
    """
    params = {"q": marker, "limit": 5}
    if path.rstrip("/") == "/api/v1/assets":
        # Handoff 58: with the receipt gates on, a create makes a CANDIDATE,
        # which the register hides. Asked of the register alone, "nothing
        # was created" would pass with a candidate sitting there — so the
        # question is asked of every register state. Switch off, every row
        # is `registered` and `any` is the same set.
        params["register_state"] = "any"
    body = assert_envelope_ok(client.get(path, params=params))
    return [row["id"] for row in body["data"]]
