"""Handoff 63 over HTTP — the SAP mirror, driven as the people who use it.

Every record below is INVENTED in the October export's shapes
(`myservice_asset_register/tests/sap_export_shapes.py`, loaded by path: this
virtualenv has no openpyxl); no row of NRS's export is in this repository.
Each test makes its own numbers, tags, offices and words, so another run's
records — or another test's — never answer for it. An import marks every
OTHER record on the tenant "not in the latest export"; nothing here counts
those.

* the import, as the System Administrator: `202`, the run read by the
  background job, the counts, the upload not kept; an Asset Manager (who
  holds `settings:write`) refused, and the Store Officer; a file with a
  header removed refused naming it, and no run recorded;
* a re-import is `unchanged`, and `updated_since` hands back nothing;
* the matcher: each reason, and a refusal when nothing is said;
* the slice: by office and class, paged;
* the coverage report: every count has its definition;
* who reads: the Asset Controller, the Register Maker and Checker, the
  Auditor and the System Administrator served; the Store Officer and an
  Asset User (the tagger) refused (Vendra's scopes: in-registry,
  `myservice_api/tests/test_sap_mirror_scope.py`);
* the register does not move when the mirror does.
"""
import datetime
import importlib.util
import pathlib
import time
import uuid

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

_SHAPES = (pathlib.Path(__file__).resolve().parent.parent
           / "myservice_asset_register" / "tests" / "sap_export_shapes.py")
_spec = importlib.util.spec_from_file_location("sap_export_shapes", _SHAPES)
shapes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shapes)

READERS = ("asset_controller", "register_maker", "register_checker",
           "auditor", "administrator")
REFUSED = ("storekeeper", "tagger")


def _u():
    return uuid.uuid4().hex[:6].upper()


def _as(client, key, method, path, **kw):
    return requests.request(
        method, f"{client.base}/api/v1{path}", timeout=120,
        headers={"Authorization": f"Bearer {gates._token(client, key)}"},
        **kw)


def _upload(client, key, data, name="export.xlsx", mark_absent=None):
    return _as(client, key, "POST", "/sap-assets/imports",
               files={"file": (name, data)},
               data=({"mark_absent": mark_absent}
                     if mark_absent is not None else None))


def _import(client, rows, mark_absent="true", **kw):
    """Upload as the administrator and wait for the background job.

    `mark_absent` (handoff 65 §3): an invented file of a few records over
    the tenant's mirror would mark nearly all of it absent, so these tests
    say "Yes, mark them absent" unless the guard is what they test."""
    deadline = time.time() + 240
    while True:
        r = _upload(client, "administrator", shapes.build_xlsx(rows, **kw),
                    mark_absent=mark_absent)
        if r.status_code != 409 or time.time() > deadline:
            break
        time.sleep(3)   # another run (a previous test's) is still reading
    assert r.status_code == 202, r.text
    run_id = r.json()["data"]["id"]
    while time.time() < deadline:
        run = _as(client, "administrator", "GET",
                  f"/sap-assets/imports/{run_id}").json()["data"]
        if run["state"] in ("done", "failed", "held"):
            return run
        time.sleep(2)
    pytest.fail(f"import {run_id} did not finish in 240 s: {run}")


@pytest.fixture(scope="module")
def loaded(client):
    """One import every read-test below shares: an office, a shared tag,
    a placeholder, a retired record."""
    u = _u()
    office, word = f"P{u}", f"ZW{u}"
    rows = [
        shapes.record(f"2P{u}001", tag=f"FIRS/{office}/0001",
                      description=f"{word} CHAIR", serial=f"SN-{u}-A"),
        shapes.record(f"2P{u}002", tag=f"FIRS/{office}/0002",
                      description=f"{word} CHAIR"),
        shapes.record(f"2P{u}003", tag=f"FIRS/{office}/0002",
                      description=f"{word} TABLE", serial="XXXX"),
        shapes.record(f"2P{u}004", description=f"{word} CABINET",
                      cls="4000"),
        shapes.record(f"2P{u}005", tag=f"FIRS/{office}/0005",
                      retired=datetime.date(2021, 6, 30)),
        shapes.record("", description="NO NUMBER"),
    ]
    run = _import(client, rows)
    return {"u": u, "office": office, "word": word, "rows": rows, "run": run}


def test_the_import_reads_counts_and_keeps_no_file(loaded):
    run = loaded["run"]
    assert run["state"] == "done", run
    assert (run["rows_read"], run["created"], run["refused"]) == (6, 5, 1)
    assert run["refused_reasons"] == [{"reason": "no asset number", "rows": 1}]
    assert run["file_kept"] is False
    assert run["uploaded_by"]["name"]
    assert run["duration_seconds"] is not None


def test_a_reimport_is_unchanged_and_hands_a_sync_nothing(client, loaded):
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    time.sleep(1.1)
    run = _import(client, loaded["rows"])
    assert (run["created"], run["updated"], run["unchanged"]) == (0, 0, 5)
    r = _as(client, "administrator", "GET", "/sap-assets",
            params={"office": loaded["office"], "updated_since": since})
    assert_envelope_ok(r)
    assert r.json()["data"] == [], "an unchanged record moved updated_at"


def test_a_file_with_a_header_removed_is_refused_naming_it(client):
    before = _as(client, "administrator", "GET", "/sap-assets/imports",
                 params={"limit": 1}).json()["pagination"]["total_estimate"]
    r = _upload(client, "administrator",
                shapes.build_xlsx([shapes.record(f"2H{_u()}1")],
                                  drop=("Inventory number",)))
    body = assert_envelope_err(r, 400, "validation_failed")
    assert '"Inventory number"' in body["error"]["message"]
    assert "Nothing was imported" in body["error"]["message"]
    assert body["error"]["details"]["missing"] == ["Inventory number"]
    after = _as(client, "administrator", "GET", "/sap-assets/imports",
                params={"limit": 1}).json()["pagination"]["total_estimate"]
    assert after == before, "a refused file is not a run"


def test_not_an_xlsx_and_not_a_form_are_refused(client):
    r = _upload(client, "administrator", b"Asset,Description\n1,chair\n",
                name="export.csv")
    assert "not an .XLSX workbook" in assert_envelope_err(
        r, 400, "validation_failed")["error"]["message"]
    r = _as(client, "administrator", "POST", "/sap-assets/imports",
            json={"file": "x"})
    assert_envelope_err(r, 400, "invalid_request")


@pytest.mark.parametrize("key", ["asset_manager", "storekeeper"])
def test_importing_is_the_system_administrators(client, key):
    r = _upload(client, key, shapes.build_xlsx([shapes.record(f"2Q{_u()}1")]))
    body = assert_envelope_err(r, 403, "forbidden")
    if key == "asset_manager":
        # Holds `settings:write`, so the route's own scope passes; the
        # refusal says what is missing, in words.
        assert "System Administrator's act" in body["error"]["message"]


@pytest.mark.parametrize("key", READERS)
def test_the_readers_are_served(client, loaded, key):
    for path, params in (("/sap-assets", {"office": loaded["office"]}),
                         ("/sap-assets/imports", {"limit": 1}),
                         ("/sap-assets/match", {"description": loaded["word"]}),
                         ("/reports/sap-coverage", None)):
        assert_envelope_ok(_as(client, key, "GET", path, params=params))


@pytest.mark.parametrize("key", REFUSED)
def test_the_store_officer_and_an_asset_user_are_refused(client, key):
    for path in ("/sap-assets", "/sap-assets/imports", "/sap-assets/match",
                 "/reports/sap-coverage"):
        body = assert_envelope_err(_as(client, key, "GET", path), 403,
                                   "forbidden")
        assert "sap_mirror:read" in body["error"]["message"]


def _match(client, **params):
    r = _as(client, "register_maker", "GET", "/sap-assets/match",
            params=params)
    assert_envelope_ok(r)
    return r.json()["data"]


def test_the_matcher_says_why_each_answer_ranked(client, loaded):
    u, office, word = loaded["u"], loaded["office"], loaded["word"]
    a = _match(client, old_tag=f" firs\\{office.lower()}\\0001 ")
    top = a["results"][0]
    assert (top["reason"], top["sap_asset"]["asset_number"]) == (
        "old tag, unique", f"2P{u}001")
    a = _match(client, old_tag=f"FIRS/{office}/0002", description="table")
    assert a["results"][0]["reason"] == \
        "old tag, shared by 2; description matches"
    assert a["results"][0]["sap_asset"]["asset_number"] == f"2P{u}003"
    a = _match(client, old_tag="FIRS/NOWHERE/1", serial=f"sn-{u.lower()}-a")
    assert a["results"][0]["reason_code"] == "serial_unique"
    a = _match(client, old_tag=f"FIRS/{office}/9999",
               description=f"{word} chair")
    assert (a["office_used"], a["office_from"]) == (office, "tag")
    assert a["results"][0]["reason"] == f"description; office {office}"
    assert a["tied_at_top"] == 2
    a = _match(client, description=f"{word} cabinet", **{"class": "4000"})
    assert a["results"][0]["reason"] == "description and class; office unknown"
    # The retired record is never offered.
    a = _match(client, old_tag=f"FIRS/{office}/0005")
    assert a["results"] == []


def test_the_matcher_asks_to_be_told_something(client):
    body = assert_envelope_err(
        _as(client, "register_maker", "GET", "/sap-assets/match",
            params={"office": "HQ"}), 400, "invalid_request")
    assert "Say something about the item" in body["error"]["message"]


def test_a_placeholder_is_stored_aside_and_never_matched(client, loaded):
    r = _as(client, "auditor", "GET", "/sap-assets",
            params={"office": loaded["office"], "class": "2000"})
    rows = {x["asset_number"]: x for x in r.json()["data"]}
    ph = rows[f"2P{loaded['u']}003"]
    assert (ph["serial_kind"], ph["serial_number"],
            ph["serial_placeholder"]) == ("placeholder", None, "XXXX")
    a = _match(client, serial="XXXX")
    assert "placeholder" in a["notes"][0]


def test_the_slice_pages_by_office_and_class(client, loaded):
    r = _as(client, "auditor", "GET", "/sap-assets",
            params={"office": loaded["office"], "limit": 2})
    assert_envelope_ok(r)
    page = r.json()
    assert len(page["data"]) == 2
    assert page["pagination"]["total_estimate"] == 4
    assert page["pagination"]["next_cursor"]
    r = _as(client, "auditor", "GET", "/sap-assets",
            params={"office": loaded["office"], "active": "false"})
    assert [x["asset_number"] for x in r.json()["data"]] == [
        f"2P{loaded['u']}005"]
    assert_envelope_err(_as(client, "auditor", "GET", "/sap-assets",
                            params={"active": "maybe"}), 400,
                        "invalid_request")


def test_one_record_and_the_asset_side_of_the_link(client, loaded):
    r = _as(client, "auditor", "GET", "/sap-assets",
            params={"office": loaded["office"], "limit": 1})
    rec = r.json()["data"][0]
    one = _as(client, "auditor", "GET", f"/sap-assets/{rec['id']}")
    assert one.json()["data"]["asset_number"] == rec["asset_number"]
    assert_envelope_err(_as(client, "auditor", "GET", "/sap-assets/999999999"),
                        404, "not_found")
    asset = _as(client, "auditor", "GET", "/assets",
                params={"limit": 1}).json()["data"][0]
    link = _as(client, "auditor", "GET", f"/assets/{asset['id']}/sap-record")
    assert_envelope_ok(link)
    assert link.json()["data"]["sentence"]


def test_every_coverage_count_says_what_it_counts(client, loaded):
    d = _as(client, "auditor", "GET", "/reports/sap-coverage").json()["data"]
    for key in ("sap_active", "linked", "not_linked", "sap_retired",
                "cadra_assets", "cadra_with_sap_number",
                "cadra_sap_number_not_in_mirror", "cadra_without_sap_number",
                "held", "reconcilable_today", "by_office"):
        assert d["definitions"].get(key), f"no definition for {key}"
    assert d["sentence"].startswith("Cadra holds")
    row = next(r for r in d["by_office"] if r["office"] == loaded["office"])
    assert (row["sap_active"], row["linked"]) == (3, 0)
    assert row["cadra_assets"] is None
    assert set(d["reconcilable_today"]) >= {
        "total", "uncontested", "contested_assets", "by_unique_old_tag",
        "by_unique_serial"}


def test_the_register_does_not_move_when_the_mirror_does(client):
    """No row of the mirror is an asset: an imported record's number and
    words are nowhere on the register, candidates included, while the
    mirror has them. (Searched rather than counted: another session may be
    registering units on this tenant while the suite runs.)"""
    u = _u()
    _import(client, [shapes.record(f"2R{u}{i:03d}",
                                   description=f"ZR{u} DESK")
                     for i in range(20)])
    for params in ({"q": f"2R{u}"}, {"q": f"ZR{u}"},
                   {"q": f"ZR{u}", "register_state": "any"}):
        r = _as(client, "administrator", "GET", "/assets", params=params)
        assert_envelope_ok(r)
        assert r.json()["pagination"]["total_estimate"] == 0, params
    mirror = _as(client, "administrator", "GET", "/sap-assets/match",
                 params={"description": f"ZR{u}"}).json()["data"]
    assert mirror["pool"] == 20
