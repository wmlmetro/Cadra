"""A deactivation and a reactivation appear in the access-changes report —
handoff 45 §1, over HTTP.

`POST /api/v1/users/<id>/deactivate` then `/reactivate` on a person this test
creates itself (`POST /api/v1/users`, no letter), then
`GET /api/v1/reports/access-changes` for today: both events, in that order,
naming the suite credential's user as the actor, with no group, and counted
in `summary.account_state_changes_in_period` rather than in the group count.

The recording itself is on `res.users.write`, not on the routes, and is
proved without the API in `myservice_api/tests/test_access_record_account_state.py`.
This file proves the route reaches it and the report publishes it.

**Nothing created here can be deleted** (`res.users.unlink` is refused over
the API, handoff 42). The person is created under a `pytest-` name, carries
`is_test_fixture` because the suite's credential is a test credential, and is
left DEACTIVATED in a `finally`.
"""
import datetime
import uuid

import pytest

from .conftest import assert_envelope_ok

USERS = "/api/v1/users"
USER = "/api/v1/users/{id}"
DEACTIVATE = "/api/v1/users/{id}/deactivate"
REACTIVATE = "/api/v1/users/{id}/reactivate"
ACCESS = "/api/v1/reports/access-changes"

ACCOUNT_STATE_EVENTS = ("deactivated", "reactivated")
COVERAGE = {"none", "partial", "recorded"}


def _period():
    today = datetime.date.today()
    return ((today - datetime.timedelta(days=1)).isoformat(),
            (today + datetime.timedelta(days=1)).isoformat())


def _whole_report(client, roster=False):
    """Every page for the period: events page by ACCOUNT, so a person can sit
    on any page. Returns (summary, fidelity, events)."""
    frm, to = _period()
    events, cursor, first, accounts, truncated = [], None, None, [], None
    for _ in range(200):
        params = {"from": frm, "to": to, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(ACCESS, params=params))
        first = first or body["data"]
        truncated = truncated or (body.get("_warnings") or {}).get("truncated")
        events += body["data"]["events"]
        accounts += body["data"]["roster"]
        cursor = (body.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    else:
        raise AssertionError("the access report did not stop paging")
    if roster:
        return first["summary"], first["fidelity"], events, accounts, truncated
    return first["summary"], first["fidelity"], events


def _evidence_id(e):
    return int(e["evidence"].rsplit("=", 1)[1])


def _visible_inactive_fixture(client, suite_user):
    """An inactive `pytest-` account the suite's credential can SEE.

    An API credential sees at most the external record cap of accounts in
    this report (`utils.EXTERNAL_TOTAL_CAP`, announced in `_warnings`), and a
    person created now has the highest id — so on a tenant past the cap a
    fresh fixture is always the one cut off (`test19` crossed 100 accounts
    on 2026-10-02, with handoff 45's own fixtures). So the test acts on an
    OLDER fixture inside the window, reactivating then deactivating it,
    which leaves it exactly as it was found.
    """
    _summary, _fidelity, events, roster, truncated = _whole_report(client, roster=True)
    for row in sorted(roster, key=lambda r: -r["user_id"]):
        login = row.get("login") or ""
        if (login.startswith("pytest-") and row.get("active") is False
                and row["user_id"] != suite_user["id"]):
            return row
    if truncated:
        pytest.skip("0 of %d accounts this credential can see are inactive "
                    "`pytest-` fixtures, and a new one would be past the "
                    "record cap (%r)" % (len(roster), truncated))
    # A fresh database (CI) has no older fixture — and no cap in the way, so
    # a person made now is visible. Made, then switched off, so the test
    # starts from the same shape it finds on a long-lived tenant (CI run
    # 37106496918 crashed here: the skip above had no `import pytest`).
    marker = "pytest-deactivation-%s" % uuid.uuid4().hex[:10]
    made = assert_envelope_ok(client.post(USERS, json={
        "name": marker, "email": "%s@example.invalid" % marker,
        "roles": ["asset_user"], "send_invitation": False}), 201)["data"]
    assert_envelope_ok(client.post(DEACTIVATE.format(id=made["id"])))
    return {"user_id": made["id"], "login": made["login"], "active": False}


def test_a_deactivation_and_a_reactivation_are_in_the_report(
        client, admin_scope, suite_user):
    subject = _visible_inactive_fixture(client, suite_user)
    uid = subject["user_id"]
    before, _fid, before_events = _whole_report(client)
    mark = max([_evidence_id(e) for e in before_events
                if e.get("evidence", "").startswith("myservice_api_access_change.id=")]
               or [0])
    try:
        on = assert_envelope_ok(client.post(REACTIVATE.format(id=uid)))
        assert on["data"]["active"] is True
        off = assert_envelope_ok(client.post(DEACTIVATE.format(id=uid)))
        assert off["data"]["active"] is False

        summary, fidelity, events = _whole_report(client)
        mine = [e for e in events
                if e["user_id"] == uid and e["event"] in ACCOUNT_STATE_EVENTS
                and _evidence_id(e) > mark]
        assert [e["event"] for e in mine] == ["reactivated", "deactivated"], (
            "the report published %r for the account this test reactivated "
            "and deactivated (of %d events in the period)"
            % ([e["event"] for e in mine], len(events)))
        for e in mine:
            assert e["precision"] == "exact", e
            assert "group" in e and e["group"] is None, e
            assert e["attributable"] is True, e
            assert e["actor"]["id"] == suite_user["id"], e
            assert e["actor"]["name"] == suite_user["name"], e
            assert e["login"] == subject["login"], e
            assert e["evidence"].startswith(
                "myservice_api_access_change.id="), e

        # Counted on their own. `>=`, because another run against the same
        # tenant may land in the same day.
        assert summary["account_state_changes_in_period"] >= \
            before["account_state_changes_in_period"] + 2, (before, summary)
        assert summary["account_state_coverage"] in COVERAGE
        assert summary["account_state_coverage"] != "none", (
            "the tenant now holds a deactivation row, so the account-state "
            "record has begun; `none` would claim it has not")
        assert fidelity["account_state_record_starts_at"], fidelity
        assert fidelity["account_state_record_rows"] >= 2
        assert "account_state" in fidelity["notes"]
    finally:
        current = client.get(USER.format(id=uid)).json().get("data") or {}
        if current.get("active"):
            client.post(DEACTIVATE.format(id=uid))


def test_a_refused_deactivation_records_nothing(client, admin_scope, suite_user):
    """A 409 (already deactivated) writes nothing, so the report must not
    gain a `deactivated` row for it."""
    subject = _visible_inactive_fixture(client, suite_user)
    uid = subject["user_id"]
    _s, _f, before = _whole_report(client)
    count = sum(1 for e in before if e["user_id"] == uid
                and e["event"] in ACCOUNT_STATE_EVENTS)
    r = client.post(DEACTIVATE.format(id=uid))
    assert r.status_code == 409, r.text[:300]
    _s, _f, after = _whole_report(client)
    now = sum(1 for e in after if e["user_id"] == uid
              and e["event"] in ACCOUNT_STATE_EVENTS)
    assert now == count, (
        "a refused repeat changed the account's recorded state events "
        "from %d to %d" % (count, now))
