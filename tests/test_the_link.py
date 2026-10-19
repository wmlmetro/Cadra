"""The link — a register asset given its SAP number from the mirror, by two
people (handoff 65 §1–§4).

Every SAP record here is INVENTED (`sap_export_shapes`, imported through the
real upload route), and every Cadra asset is a fixture made for the test,
walked onto the register through the gates when the tenant's switch is on
(`tests/gates.py`). An asset is matched to its record by an old tag that
exists nowhere else, so a test never depends on what the tenant held before.

What is pinned:
* the maker's list shows a confident, uncontested match with its reason;
* a proposal is a batch of single acts with a dry run; the checker approves;
  the number is SAP's, the source `linked_from_sap_mirror`, the history line
  the handoff's sentence;
* one person may not propose and approve (409 `segregation_of_duties`);
* a return needs a reason and leaves the asset alone;
* an undo is the same two acts with a reason, and takes the number off;
* a contested record is refused on the plain route, chosen on the
  contested route, flagged once, and the flag shows on each asset;
* the coverage report's class evidence counts the link;
* an import that would mark more than 5% of the mirror absent is HELD
  before writing, and goes through with `mark_absent=true`, recorded.
"""
import importlib.util
import pathlib
import time
import uuid

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

_SHAPES = (pathlib.Path(__file__).resolve().parents[1]
           / "myservice_asset_register" / "tests" / "sap_export_shapes.py")
_spec = importlib.util.spec_from_file_location("sap_export_shapes", _SHAPES)
shapes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shapes)


def _u():
    return uuid.uuid4().hex[:6].upper()


def _as(client, key, method, path, **kw):
    headers = {"Authorization": f"Bearer {gates._token(client, key)}"} \
        if key else {"Authorization": client.session.headers.get(
            "Authorization", "")}
    return requests.request(method, f"{client.base}/api/v1{path}",
                            timeout=120, headers=headers, **kw)


def _upload(client, rows, mark_absent="true"):
    data = {"mark_absent": mark_absent} if mark_absent is not None else None
    return _as(client, "administrator", "POST", "/sap-assets/imports",
               files={"file": ("export.xlsx", shapes.build_xlsx(rows))},
               data=data)


def _import(client, rows, mark_absent="true"):
    deadline = time.time() + 240
    while True:
        r = _upload(client, rows, mark_absent)
        if r.status_code != 409 or time.time() > deadline:
            break
        time.sleep(3)
    assert r.status_code == 202, r.text
    run_id = r.json()["data"]["id"]
    while time.time() < deadline:
        run = _as(client, "administrator", "GET",
                  f"/sap-assets/imports/{run_id}").json()["data"]
        if run["state"] in ("done", "failed", "held"):
            return run
        time.sleep(2)
    pytest.fail(f"import {run_id} did not finish: {run}")


def _asset_with_tag(client, tag):
    return gates.new_registered_asset(
        client, name=f"pytest-link {tag}", legacy_asset_code=tag)


@pytest.fixture(scope="module")
def world(client):
    """Four register assets and the invented SAP records they point at:
    `a` and `b` each at their own record (old tag, unique); `c1` and `c2`
    both at ONE record (contested)."""
    u = _u()
    office = f"L{u}"
    tags = {k: f"FIRS/{office}/{i:04d}"
            for i, k in enumerate(("a", "b", "c"), 1)}
    assets = {"a": _asset_with_tag(client, tags["a"]),
              "b": _asset_with_tag(client, tags["b"]),
              "c1": _asset_with_tag(client, tags["c"]),
              # The same tag typed with a backslash and lower case: the
              # matcher's normalisation makes it the same old tag.
              "c2": _asset_with_tag(client, tags["c"].lower().replace(
                  "/", "\\"))}
    numbers = {k: f"3L{u}{i:03d}" for i, k in enumerate(("a", "b", "c"), 1)}
    run = _import(client, [
        shapes.record(numbers["a"], cls="3000", tag=tags["a"],
                      description="LAPTOP"),
        shapes.record(numbers["b"], cls="3000", tag=tags["b"],
                      description="DESKTOP"),
        shapes.record(numbers["c"], cls="2000", tag=tags["c"],
                      description="OFFICE CHAIR"),
    ])
    assert run["state"] == "done", run
    return {"office": office, "assets": assets, "numbers": numbers}


def _candidates(client, office, key="register_maker", **params):
    r = _as(client, key, "GET", "/sap-links/candidates",
            params=dict(office=office, **params))
    assert_envelope_ok(r)
    return r.json()["data"]


def _history(client, asset_id):
    r = client.get(f"/api/v1/assets/{asset_id}/history")
    assert r.status_code == 200, r.text
    return r.json()["data"]["events"]


def _asset(client, asset_id):
    return client.get(f"/api/v1/assets/{asset_id}").json()["data"]


def test_the_makers_list_shows_the_confident_match_and_why(client, world):
    data = _candidates(client, world["office"])
    ids = {i["asset"]["id"]: i for i in data["items"]}
    a = world["assets"]["a"]
    assert a["id"] in ids and world["assets"]["b"]["id"] in ids
    row = ids[a["id"]]
    assert row["sap"]["asset_number"] == world["numbers"]["a"]
    assert row["sap"]["class"] == "3000"
    assert row["sap"]["capitalized_on"] == "2019-03-14"
    assert (row["reason_code"], row["reason"]) == ("old_tag_unique",
                                                   "old tag, unique")
    assert row["link"] is None
    # The contested pair is not on this list.
    assert world["assets"]["c1"]["id"] not in ids
    assert world["assets"]["c2"]["id"] not in ids
    assert {"office": world["office"], "assets": 2} in data["by_office"]


def test_a_store_officer_cannot_read_the_list(client, world):
    assert_envelope_err(_as(client, "storekeeper", "GET",
                            "/sap-links/candidates"), 403, "forbidden")


def test_propose_approve_writes_sap_number_and_sends_nothing(client, world):
    a = world["assets"]["a"]
    # The dry run says what would happen and writes nothing.
    dry = _as(client, "register_maker", "POST", "/sap-links/propose",
              json={"asset_ids": [a["id"]], "dry_run": True})
    assert_envelope_ok(dry)
    assert dry.json()["data"]["results"][0]["outcome"] == "would_do"
    assert _candidates(client, world["office"], status="proposed")[
        "total"] == 0
    r = _as(client, "register_maker", "POST", "/sap-links/propose",
            json={"asset_ids": [a["id"], 999999999]})
    body = r.json()["data"]
    assert (body["done"], body["refused"]) == (1, 1), body
    assert body["results"][1]["status"] == 404
    link_id = body["results"][0]["link_id"]
    # The maker may not decide; the checker's queue shows it.
    assert_envelope_err(_as(client, "register_maker", "POST",
                            "/sap-links/approve",
                            json={"link_ids": [link_id]}), 403, "forbidden")
    queue = _as(client, "register_checker", "GET", "/sap-links",
                params={"asset_id": a["id"]}).json()["data"]
    assert [q["id"] for q in queue] == [link_id]
    assert queue[0]["can_decide"] is True
    ok = _as(client, "register_checker", "POST", "/sap-links/approve",
             json={"link_ids": [link_id]}).json()["data"]
    assert ok["done"] == 1, ok
    sap = _asset(client, a["id"])["sap"]
    assert sap["asset_number"] == world["numbers"]["a"]
    assert sap["code_source"] == "linked_from_sap_mirror"
    assert sap["reconciliation_state"] == "reconciled"
    # Nothing was queued for SAP: the master already exists there.
    assert sap["posting_state"] == "none"
    lines = [e["summary"] for e in _history(client, a["id"])
             if e["type"] == "sap_link"]
    maker = queue[0]["proposed_by"]["name"]
    checker = _as(client, "register_checker", "GET", "/sap-links",
                  params={"asset_id": a["id"], "state": "approved"}
                  ).json()["data"][0]["decided_by"]["name"]
    assert ("Linked to SAP asset %s (old tag, unique), proposed by %s, "
            "approved by %s." % (world["numbers"]["a"], maker, checker)
            ) in lines, lines
    # The record now shows the asset on the SAP side.
    rec = _as(client, "auditor", "GET", f"/assets/{a['id']}/sap-record")
    assert rec.json()["data"]["linked"] is True
    # And it is off the maker's list.
    assert a["id"] not in {i["asset"]["id"] for i in _candidates(
        client, world["office"], status="all")["items"]}


def test_one_person_cannot_propose_and_approve(client, world):
    """The admin credential holds both scopes; the no-two-gates rule is
    what refuses it, naming the earlier act."""
    b = world["assets"]["b"]
    r = client.post("/api/v1/sap-links/propose",
                    json={"asset_ids": [b["id"]]})
    assert r.status_code == 200, r.text
    link_id = r.json()["data"]["results"][0]["link_id"]
    assert link_id, r.json()
    line = client.post("/api/v1/sap-links/approve",
                       json={"link_ids": [link_id]}).json()["data"][
        "results"][0]
    assert line["status"] == 409, line
    assert line["details"]["reason"] == "segregation_of_duties"
    assert "proposed a change to this unit's SAP link" in line["message"]
    # A return needs a reason, and leaves the asset as it was.
    no_reason = _as(client, "register_checker", "POST", "/sap-links/return",
                    json={"link_ids": [link_id]}).json()["data"]["results"][0]
    assert no_reason["status"] == 400, no_reason
    back = _as(client, "register_checker", "POST", "/sap-links/return",
               json={"link_ids": [link_id], "reason": "wrong building"}
               ).json()["data"]
    assert back["done"] == 1, back
    assert _asset(client, b["id"])["sap"]["asset_number"] is None
    # Returned is final for that proposal; the asset is on the list again.
    again = _as(client, "register_checker", "POST", "/sap-links/approve",
                json={"link_ids": [link_id]}).json()["data"]["results"][0]
    assert again["status"] == 409
    assert b["id"] in {i["asset"]["id"] for i in _candidates(
        client, world["office"])["items"]}


def test_an_undo_is_two_people_with_a_reason(client, world):
    a = world["assets"]["a"]
    assert _asset(client, a["id"])["sap"]["code_source"] == \
        "linked_from_sap_mirror", "runs after the approval test"
    assert_envelope_err(_as(client, "register_maker", "POST",
                            f"/assets/{a['id']}/sap-link/undo", json={}),
                        400, "validation_failed")
    r = _as(client, "register_maker", "POST",
            f"/assets/{a['id']}/sap-link/undo",
            json={"reason": "the tag was read off the wrong laptop"})
    assert_envelope_ok(r)
    link = r.json()["data"]
    assert (link["kind"], link["state"]) == ("unlink", "proposed")
    done = _as(client, "register_checker", "POST", "/sap-links/approve",
               json={"link_ids": [link["id"]]}).json()["data"]
    assert done["done"] == 1, done
    sap = _asset(client, a["id"])["sap"]
    assert (sap["asset_number"], sap["code_source"]) == (None, None)
    lines = [e["summary"] for e in _history(client, a["id"])
             if e["type"] == "sap_link"]
    assert any(l.startswith("Link to SAP asset %s undone (the tag was read "
                            "off the wrong laptop)" % world["numbers"]["a"])
               for l in lines), lines


def test_a_contested_record_is_chosen_or_flagged(client, world):
    c1, c2 = world["assets"]["c1"], world["assets"]["c2"]
    plain = _as(client, "register_maker", "POST", "/sap-links/propose",
                json={"asset_ids": [c1["id"]]}).json()["data"]["results"][0]
    assert plain["status"] == 409 and plain["details"]["contested"], plain
    data = _as(client, "register_maker", "GET", "/sap-links/contested",
               params={"office": world["office"]}).json()["data"]
    assert data["total_groups"] == 1, data
    group = data["items"][0]
    assert group["sap"]["asset_number"] == world["numbers"]["c"]
    assert sorted(m["id"] for m in group["assets"]) == sorted(
        [c1["id"], c2["id"]])
    member = group["assets"][0]
    for key in ("asset_code", "name", "location", "custodian", "created_at",
                "photos", "old_tag"):
        assert key in member, key
    row = next(r for r in data["by_office"] if r["office"] == world["office"])
    assert (row["groups"], row["assets"]) == (1, 2)
    # Flag the group: a note is required, and then each asset shows it.
    sap_id = group["sap"]["id"]
    assert_envelope_err(_as(client, "register_maker", "POST",
                            f"/sap-links/contested/{sap_id}/flag", json={}),
                        400, "validation_failed")
    f = _as(client, "register_maker", "POST",
            f"/sap-links/contested/{sap_id}/flag",
            json={"note": "two chairs on one SAP record"})
    assert_envelope_ok(f)
    for asset in (c1, c2):
        flag = _asset(client, asset["id"])["sap"]["duplicate_flag"]
        assert flag["sap_asset_number"] == world["numbers"]["c"]
        assert flag["note"] == "two chairs on one SAP record"
    again = _as(client, "register_maker", "POST",
                f"/sap-links/contested/{sap_id}/flag",
                json={"note": "again"})
    assert_envelope_err(again, 409, "conflict")
    # Choose one: the other is left unlinked.
    chosen = _as(client, "register_maker", "POST",
                 f"/sap-links/contested/{sap_id}/propose",
                 json={"asset_id": c2["id"]})
    assert_envelope_ok(chosen)
    link = chosen.json()["data"]
    assert link["reason"] == "old tag, unique; chosen from 2 Cadra assets"
    ok = _as(client, "register_checker", "POST", "/sap-links/approve",
             json={"link_ids": [link["id"]]}).json()["data"]
    assert ok["done"] == 1, ok
    assert _asset(client, c2["id"])["sap"]["asset_number"] == \
        world["numbers"]["c"]
    assert _asset(client, c1["id"])["sap"]["asset_number"] is None
    # Nothing was merged or retired: both are still on the register.
    for asset in (c1, c2):
        assert _asset(client, asset["id"])["register_state"] == "registered"


def test_the_coverage_report_shows_the_class_evidence(client, world):
    d = _as(client, "auditor", "GET", "/reports/sap-coverage").json()["data"]
    assert d["definitions"]["class_evidence"]
    rows = d["class_evidence"]
    assert rows and all(r["sentence"] for r in rows)
    linked = sum(r["via_link"] for r in rows)
    assert linked >= 1, rows


def test_an_import_that_would_mark_too_much_absent_is_held(client):
    u = _u()
    rows = [shapes.record(f"3G{u}{i:03d}", tag=f"FIRS/G{u}/{i:04d}")
            for i in range(40)]
    assert _import(client, rows)["state"] == "done"
    # One record of the forty: 39 of 40 would be marked absent.
    held = _import(client, rows[:1], mark_absent=None)
    assert held["state"] == "held", held
    assert held["absent_guard"]["would_mark_absent"] == 39
    assert held["absent_guard"]["mirror_records_before"] == 40
    assert "truncated" in held["message"]
    assert held["marked_not_in_latest_export"] == 0
    assert held["file_kept"] is False
    slice_ = _as(client, "auditor", "GET", "/sap-assets",
                 params={"office": f"G{u}", "in_latest_export": "true",
                         "limit": 100}).json()
    assert slice_["pagination"]["total_estimate"] == 40, \
        "a held run wrote nothing"
    # "Yes, mark them absent": it goes through, and the run says who.
    done = _import(client, rows[:1], mark_absent="true")
    assert done["state"] == "done", done
    assert done["marked_not_in_latest_export"] == 39
    assert done["absent_guard"]["confirmed"] is True
    assert done["absent_guard"]["confirmed_by"]["name"]
    assert_envelope_err(_upload(client, rows[:1], mark_absent="maybe"),
                        400, "invalid_request")
