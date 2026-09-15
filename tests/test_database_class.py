"""`GET /api/v1/meta/database` — the question a test suite has to ask first.

Handoff 25 §A. Report 24 §B measured what these suites write and where: 3,584
of 4,056 assets in `jaizbankplc`, a register derived from a live client's
data, were named `pytest-*`; 354 of 420 entries in the PUBLIC homepage
location dropdown were fixtures; six fabricated approved disposals sat in the
auditor-facing disposal report. Accumulated over 154 sessions by a suite whose
only control was an environment variable.

The control is now a system parameter in the target database, read by
`conftest.database_accepts_test_writes` before anything can mint a token. If
this route stops answering honestly the guard stops working, so its shape is
under test like any other published contract.
"""
from .conftest import assert_envelope_ok


def test_meta_database_reports_this_database(client, capture):
    r = client.get("/api/v1/meta/database")
    capture("meta/database", r)
    assert r.status_code == 200
    body = assert_envelope_ok(r)
    data = body["data"]

    assert isinstance(data["database"], str) and data["database"], \
        "the route must name the database it answered for"
    assert data["database_class"] in ("test", "client", "production", None)
    assert isinstance(data["accepts_test_writes"], bool)
    assert isinstance(data["credential_is_test"], bool)


def test_accepts_test_writes_is_derived_and_not_independent(client):
    """`accepts_test_writes` is true for `test` and for nothing else.

    A client must not have to re-derive the policy — that is how two callers
    end up disagreeing about which databases are safe.
    """
    data = client.get("/api/v1/meta/database").json()["data"]
    assert data["accepts_test_writes"] is (data["database_class"] == "test")


def test_the_suite_is_running_where_it_is_allowed_to(client):
    """The guard's own conclusion, asserted rather than assumed.

    If this suite is running at all, `conftest` already refused every other
    answer before the first token was minted. Asserting it here means a
    future change that loosens the fixture shows up as a red test rather than
    as a quiet return to writing wherever `CADRA_API_BASE` points.
    """
    data = client.get("/api/v1/meta/database").json()["data"]
    assert data["accepts_test_writes"] is True, (
        "this suite reached a test against database %r, which is marked %r"
        % (data["database"], data["database_class"]))
    assert data["credential_is_test"] is True, (
        "the credential running this suite is not flagged `is_test_credential`, "
        "so nothing it writes will identify itself as a fixture")


def test_the_route_needs_a_token(unauthed_client):
    """No scope, but not unauthenticated.

    Whether a database is production is not a fact to hand to anyone who can
    reach the port.
    """
    r = unauthed_client.get("/api/v1/meta/database")
    assert r.status_code == 401, \
        "expected 401 without a bearer token, got %s" % r.status_code
