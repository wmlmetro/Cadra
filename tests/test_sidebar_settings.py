"""`/api/v1/settings/sidebar` — what this tenant's sidebar shows (handoff 48).

Presentation, not permission. What is proved here, over HTTP:

* any signed-in caller reads it — the sidebar needs it on every screen, for
  every role, a tagger holding nothing but `tagging:write` included — and
  the payload says, in words and as a boolean, that it is not a permission;
* only `admin` changes it;
* every refusal comes before any write, and the lockout (the Sidebar screen
  and its group) is one of them;
* a group is a master switch: off hides its items and leaves their own
  switches as they were; on restores them;
* switching on what nobody switched off writes no row; switching back on
  writes `on` rather than deleting, so the configuration-change report keeps
  the row and names who wrote it;
* a switched-off item's API still answers, because nothing reads the switch.

Every test that switches something puts it back, in `finally`.
"""
import datetime
import os

import pytest
import requests

from .conftest import ApiClient, assert_envelope_err, assert_envelope_ok

SIDEBAR = "/api/v1/settings/sidebar"

# The Tag-Issuing-Unit-only person handoff 41 seeded (`test_users.py`).
_TAGGER_LOGIN = os.environ.get("CADRA_H41_TAGGER_LOGIN", "h41_tagger")
_TAGGER_PASSWORD = os.environ.get("CADRA_H41_TAGGER_PASSWORD",
                                  "h41-tagger-pass")


def _read(client):
    return assert_envelope_ok(client.get(SIDEBAR))["data"]


def _item(data, key):
    for g in data["groups"]:
        for it in g["items"]:
            if it["key"] == key:
                return it
    raise AssertionError("no item %r in %s" % (key, SIDEBAR))


def _group(data, key):
    for g in data["groups"]:
        if g["key"] == key:
            return g
    raise AssertionError("no group %r in %s" % (key, SIDEBAR))


@pytest.fixture
def restore(client, admin_scope):
    """Put every switch a test touched back where it WAS — not merely on: a
    tenant whose administrator had switched something off keeps it off."""
    before = _read(client)
    touched = {"items": set(), "groups": set()}
    yield touched
    body = {}
    if touched["items"]:
        body["items"] = {k: _item(before, k)["enabled"] for k in touched["items"]}
    if touched["groups"]:
        body["groups"] = {k: _group(before, k)["enabled"] for k in touched["groups"]}
    if body:
        assert_envelope_ok(client.patch(SIDEBAR, json=body))
    after = _read(client)
    assert after["hidden_items"] == before["hidden_items"], (
        "the switches were not put back: %s -> %s"
        % (before["hidden_items"], after["hidden_items"]))


@pytest.fixture(scope="module")
def tagger(api_base):
    r = requests.post(f"{api_base}/api/v1/auth/login",
                      json={"login": _TAGGER_LOGIN,
                            "password": _TAGGER_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip("cannot sign in as %r (HTTP %s): no tagger-only account "
                    "on this tenant" % (_TAGGER_LOGIN, r.status_code))
    return ApiClient(api_base, r.json()["data"]["access_token"])


def test_the_payload_says_it_is_not_a_permission(client, capture):
    r = client.get(SIDEBAR)
    capture("settings/sidebar-get", r)
    data = assert_envelope_ok(r)["data"]
    assert data["is_a_permission"] is False
    assert "not a permission" in data["statement"]
    assert "by its address" in data["statement"]
    assert data["default_when_unset"] is True
    assert data["parameter_prefix"] == "cadra.sidebar."
    keys = [it["key"] for g in data["groups"] for it in g["items"]]
    assert len(keys) == len(set(keys)) == 28, keys
    assert len(data["groups"]) == 10
    hidden = [it["key"] for g in data["groups"] for it in g["items"]
              if not it["shown"]]
    assert data["hidden_items"] == hidden


def test_anyone_signed_in_reads_it_and_only_admin_writes_it(tagger, unauthed_client):
    data = _read(tagger)
    assert data["is_a_permission"] is False
    body = assert_envelope_err(
        tagger.patch(SIDEBAR, json={"items": {"staff_bus": True}}),
        403, "forbidden")
    assert "admin" in body["error"].get("details", {}).get("required_scopes", [])
    assert_envelope_err(unauthed_client.get(SIDEBAR), 401)


def test_the_lockout_is_refused_and_nothing_is_written(client, admin_scope):
    before = _read(client)
    for body in ({"groups": {"settings": False}},
                 {"items": {"sidebar_settings": False}},
                 # A legitimate switch in the same body is not written either.
                 {"items": {"sidebar_settings": False, "staff_bus": False}},
                 {"groups": {"settings": False, "fleet_transport": False}}):
        err = assert_envelope_err(client.patch(SIDEBAR, json=body), 400,
                                  "invalid_request")["error"]
        assert "Nothing was written" in err["message"], err
        assert err["details"]["locked_items"] == ["sidebar_settings"]
        assert err["details"]["locked_groups"] == ["settings"]
    assert _read(client) == before
    assert _item(before, "sidebar_settings")["locked"] is True
    assert _group(before, "settings")["locked"] is True
    # Switching a locked switch ON is not a lockout; it changes nothing.
    assert_envelope_ok(client.patch(SIDEBAR, json={
        "items": {"sidebar_settings": True}, "groups": {"settings": True}}))
    assert _read(client) == before


@pytest.mark.parametrize("body,needle", [
    ({"items": {"staff_bus": False}, "colour": "red"}, "does not accept"),
    ({}, "Name at least one"),
    ({"items": {}}, "Name at least one"),
    ({"items": {"no_such_item": False}}, "Unknown item: no_such_item"),
    ({"groups": {"no_such_group": False}}, "Unknown group: no_such_group"),
    # A group key is not an item key, and the other way round.
    ({"items": {"fleet_transport": False}}, "Unknown item"),
    ({"items": {"staff_bus": "off"}}, "true (shown) or false"),
    ({"items": {"staff_bus": 0}}, "true (shown) or false"),
    ({"items": ["staff_bus"]}, "must be an object"),
    # A FALSY non-object beside a valid switch is refused too — it was
    # dropped with a 200 and the valid switch written (verification pass).
    ({"items": {"staff_bus": False}, "groups": False}, "must be an object"),
    ({"items": {"staff_bus": False}, "groups": []}, "must be an object"),
    ({"items": {"staff_bus": False}, "groups": ""}, "must be an object"),
    ({"groups": 0}, "must be an object"),
])
def test_every_refusal_before_any_write(client, admin_scope, body, needle):
    before = _read(client)
    err = assert_envelope_err(client.patch(SIDEBAR, json=body), 400,
                              "invalid_request")["error"]
    assert needle in err["message"], err["message"]
    assert "Nothing was written" in err["message"]
    assert _read(client) == before


def test_a_group_is_a_master_switch(client, admin_scope, restore):
    restore["groups"].add("fleet_transport")
    data = assert_envelope_ok(client.patch(
        SIDEBAR, json={"groups": {"fleet_transport": False}}))["data"]
    group = _group(data, "fleet_transport")
    assert group["enabled"] is False
    for it in group["items"]:
        # Hidden by the group, own switch untouched.
        assert it["shown"] is False and it["enabled"] is True, it
        assert it["key"] in data["hidden_items"]
    data = assert_envelope_ok(client.patch(
        SIDEBAR, json={"groups": {"fleet_transport": True}}))["data"]
    assert [it["shown"] for it in _group(data, "fleet_transport")["items"]] \
        == [True, True]


def test_an_item_off_under_a_group_off_stays_off_when_the_group_returns(
        client, admin_scope, restore):
    restore["groups"].add("fleet_transport")
    restore["items"].add("staff_bus")
    assert_envelope_ok(client.patch(SIDEBAR, json={
        "items": {"staff_bus": False}, "groups": {"fleet_transport": False}}))
    data = assert_envelope_ok(client.patch(
        SIDEBAR, json={"groups": {"fleet_transport": True}}))["data"]
    assert _item(data, "fleet")["shown"] is True
    assert _item(data, "staff_bus")["shown"] is False
    assert data["hidden_items"].count("staff_bus") == 1


def test_switching_on_what_nobody_switched_off_writes_nothing(client, admin_scope):
    # `barcode_station` is never switched by this suite or the browser spec.
    before = _item(_read(client), "barcode_station")
    if before["configured"]:
        pytest.skip("barcode_station already has a row on this tenant")
    assert_envelope_ok(client.patch(
        SIDEBAR, json={"items": {"barcode_station": True}}))
    after = _item(_read(client), "barcode_station")
    assert after["configured"] is False and after["changed_by"] is None


def test_a_switch_names_who_changed_it_and_the_report_agrees(
        client, admin_scope, restore, suite_user):
    restore["items"].add("staff_bus")
    data = assert_envelope_ok(client.patch(
        SIDEBAR, json={"items": {"staff_bus": False}}))["data"]
    item = _item(data, "staff_bus")
    assert item["enabled"] is False and item["configured"] is True
    assert item["changed_by"]["id"] == suite_user["id"], item

    # Back on: the row stays, reads `on`, and is still this caller's.
    data = assert_envelope_ok(client.patch(
        SIDEBAR, json={"items": {"staff_bus": True}}))["data"]
    item = _item(data, "staff_bus")
    assert item["enabled"] is True and item["configured"] is True
    assert item["changed_by"]["id"] == suite_user["id"]

    today = datetime.date.today()
    rows, cursor = [], None
    while True:
        params = {"from": str(today - datetime.timedelta(days=1)),
                  "to": str(today + datetime.timedelta(days=1)),
                  "limit": 100}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(
            "/api/v1/reports/configuration-changes", params=params))
        rows += body["data"]["parameters"]
        cursor = (body.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    row = next((r for r in rows if r["key"] == "cadra.sidebar.item.staff_bus"),
               None)
    assert row, "the switch is not in the configuration-change report"
    assert row["current_value"] == "on"
    assert row["value_is_redacted"] is False
    assert row["last_written_by"]["id"] == suite_user["id"]


def test_a_hidden_item_still_answers(client, admin_scope, restore):
    """The whole claim of the screen, at the API: switch the register list
    off and the register still answers, row for row."""
    restore["items"].add("all_assets")
    before = assert_envelope_ok(client.get("/api/v1/assets", params={"limit": 5}))
    assert_envelope_ok(client.patch(SIDEBAR, json={"items": {"all_assets": False}}))
    after = assert_envelope_ok(client.get("/api/v1/assets", params={"limit": 5}))
    assert [a["id"] for a in after["data"]] == [a["id"] for a in before["data"]]
