"""`cadra.receipt.gated` — the switch that makes a received unit a candidate.

Handoff 57, kept by handoff 58: the gates ride on
`nrs.asset.register_state` (evaluation §8). What is proved here, over HTTP,
is the switch alone — the gates themselves are `test_receipt_gates.py` and
`test_gates_kept.py`:

* `GET /api/v1/settings` says whether receipts are gated, as a boolean and
  as a block that tells *never set* from *set off*, with the sentence the
  Settings screen shows;
* `PATCH /api/v1/settings/receipt-gate` takes `enabled`, a boolean, and
  nothing else — every refusal before any write;
* a change is a configuration-record event: the row is in the
  configuration-change report with the person who made it.

Every test that switches it puts it back, in `finally`. One thing cannot be
put back: a tenant on which nobody had ever set the switch has a `false` row
afterwards — the same behaviour (absent means off), and a row the report
shows written by the suite.
"""
import datetime

from .conftest import assert_envelope_err, assert_envelope_ok

SETTINGS = "/api/v1/settings"
PATCH = "/api/v1/settings/receipt-gate"
PARAM = "cadra.receipt.gated"


def _read(client):
    return assert_envelope_ok(client.get(SETTINGS))["data"]


def test_the_settings_read_says_whether_receipts_are_gated(client):
    data = _read(client)
    assert isinstance(data["receipt_gated"], bool)
    block = data["receipt_gate"]
    assert block["enabled"] is data["receipt_gated"]
    assert block["parameter"] == PARAM
    assert block["default_when_unset"] is False
    assert isinstance(block["configured"], bool)
    # The sentence describes the state it is in, not both.
    assert block["statement"].startswith("On:" if block["enabled"] else "Off:")


def test_a_key_other_than_enabled_is_refused_and_nothing_is_written(client):
    before = _read(client)["receipt_gate"]
    r = client.patch(PATCH, json={"enabled": not before["enabled"],
                                  "not_a_field_on_anything": 1})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["rejected_fields"] == [
        "not_a_field_on_anything"]
    assert _read(client)["receipt_gate"]["enabled"] is before["enabled"]


def test_enabled_must_be_a_boolean(client):
    before = _read(client)["receipt_gate"]
    for bad in ("true", 1, None):
        r = client.patch(PATCH, json={"enabled": bad})
        assert_envelope_err(r, 400, "invalid_request")
    assert _read(client)["receipt_gate"]["enabled"] is before["enabled"]


def test_switching_it_is_recorded_with_who_did_it(client, suite_user):
    original = _read(client)["receipt_gate"]["enabled"]
    try:
        flipped = assert_envelope_ok(
            client.patch(PATCH, json={"enabled": not original}))["data"]
        assert flipped["enabled"] is (not original)
        assert flipped["configured"] is True
        assert flipped["changed_by"]["id"] == suite_user["id"]
        assert _read(client)["receipt_gated"] is (not original)

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
        row = next((r for r in rows if r["key"] == PARAM), None)
        assert row, "the switch is not in the configuration-change report"
        assert row["current_value"] == ("true" if not original else "false")
        assert row["last_written_by"]["id"] == suite_user["id"]
    finally:
        assert_envelope_ok(client.patch(PATCH, json={"enabled": original}))
    assert _read(client)["receipt_gated"] is original
