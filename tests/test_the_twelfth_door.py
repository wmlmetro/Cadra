"""The two routes that create a record out of `**kwargs`. Handoff 32 §B.

Handoff 31 made a field a write route does not accept a 400 on eleven routes,
and `tests/test_rejected_fields_are_refused.py` is where the eleven are held
to one answer. **These two were not among them, and grepping for allow-lists
could not find them, because neither declares one.** They build a record by
passing the body straight into a function taking `**kwargs`:

    POST /api/v1/home/quick-submit
        → NRSHomepageAPI.quick_submit(**body)
    POST /api/v1/integrations/sap/employee-sync
        → nrs.sap.sync.log.process_sap_payload(employee)

So each read the keys it knew and said nothing about the rest. Send
quick-submit `request_text` — the sibling `POST /api/v1/requests` key, the
one this suite's own fixture sends — and it raised a request with **no
description at all** and answered 201. Send employee-sync `status`, which its
own published schema, the endpoint reference's canonical example, the demo
card and `tests/test_integrations.py` all sent, and the employment status
went nowhere: the model reads `employmentStatus` or `sap_status`, and always
has.

**Three properties are asserted here and each of them is a separate defect:**

1. A key the route does not accept is the same 400 as the other eleven —
   `details.rejected_fields`, `details.writable` — and NOTHING is written,
   read back rather than assumed, with a control so a search that had stopped
   matching could not make every such assertion pass alone.
2. A value that cannot be resolved is refused too. quick-submit swallowed a
   non-integer `service_id` with a bare `except (ValueError, TypeError):
   pass` and an id naming no record with an unchecked `.exists()`, and
   submitted the request without it. A known key silently dropped is
   `CLAUDE.md` rule 3 verbatim.
3. **The refusal a member of the public reads is a sentence.** quick-submit
   answers a second door — the unauthenticated homepage form at
   `/api/myservice/quick-submit`, whose `res.error` goes straight into the
   error box under the Submit button. One validator, two renderings: the key
   names belong in `details.rejected_fields` where a developer reads them,
   and a person on a phone gets English.
"""
import time
import uuid

import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused, ids_matching)

#: Every key `POST /api/v1/home/quick-submit` accepts, and the whole of it.
#: Declared in `myservice_website_theme/controllers/api.py` as
#: `QUICK_SUBMIT_FIELDS`; repeated here because the property under test is
#: that the route PUBLISHES this exact set in `details.writable`.
QUICK_SUBMIT_FIELDS = sorted([
    "type_id", "service_id", "location_id", "priority",
    "description", "reporter_name", "reporter_contact",
])

#: The 22 keys `nrs.sap.sync.log.process_sap_payload` reads. `status` is not
#: among them and never was.
SAP_FIELDS = sorted([
    "ir_number", "userId", "personIdExternal",
    "displayName", "firstName", "lastName",
    "email", "phone", "mobile",
    "department", "jobTitle", "costCenter", "gradeCode", "managerIR",
    "hireDate", "terminationDate",
    "locationName", "location",
    "employmentStatus", "sap_status", "previous_status",
    "event",
])


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


# ─── quick-submit: the key it does not accept ────────────────────────


def _submit(client, **body):
    return client.post("/api/v1/home/quick-submit", json=body)


def test_quick_submit_refuses_the_sibling_routes_key_and_writes_nothing(
        client, test_location):
    """`request_text` — 201 with no description at all, until now.

    It is the single most likely key to be sent here by mistake: it is what
    `POST /api/v1/requests` calls the same thing, it is what the model calls
    it, and quick-submit does not accept it — it composes `request_text`
    itself out of `description` plus the reporter's name and contact.
    """
    marker = _uniq("pytest-twelfth-door-refused")
    before = ids_matching(client, "/api/v1/requests", marker)
    assert before == [], "the marker matched something before the test ran"

    r = _submit(client, type_id=1, location_id=test_location["id"],
                request_text=f"<p>{marker}</p>")
    details = assert_fields_refused(r, "request_text")
    assert details["rejected_fields"] == ["request_text"]
    assert details["writable"] == QUICK_SUBMIT_FIELDS

    assert ids_matching(client, "/api/v1/requests", marker) == [], (
        "the refusal created a request anyway — `err()` returns a response, "
        "it does not roll back, so the refusal has to come first")


def test_the_same_submission_without_the_refused_key_creates_one(
        client, test_location):
    """The CONTROL for the assertion above.

    Without it, a `?q=` that had quietly stopped matching would make "nothing
    was written" pass on a route that wrote every time.
    """
    marker = _uniq("pytest-twelfth-door-control")
    r = _submit(client, type_id=1, location_id=test_location["id"],
                description=marker)
    assert_envelope_ok(r, expected_status=201)
    assert len(ids_matching(client, "/api/v1/requests", marker)) == 1


def test_quick_submit_refuses_every_key_it_does_not_accept_at_once(
        client):
    """A body is refused whole, and the names come back in the order sent."""
    r = _submit(client, request_text="x", subject="y", name="z",
                description="pytest — should never be written")
    details = assert_fields_refused(r, "request_text", "subject", "name")
    assert details["rejected_fields"] == ["request_text", "subject", "name"]


def test_the_four_keys_this_suite_used_to_send_are_named(client):
    """`tests/test_home.py` sent `name`, `email`, `phone` and `subject`.

    Four keys, none of them accepted, and the route answered 201 to all four
    for as long as the file has existed — which is how a test asserting "the
    caller gets a branchable envelope" stayed green over a request raised
    with a reporter nobody could contact.
    """
    r = _submit(client, name="pytest homepage", email="pytest@example.com",
                phone="+2348000000000", subject="Smoke test",
                description="pytest — should never be written")
    details = assert_fields_refused(r, "name", "email", "phone", "subject")
    assert details["rejected_fields"] == ["name", "email", "phone", "subject"]


# ─── quick-submit: the value it cannot resolve ───────────────────────


@pytest.mark.parametrize("value", ["not-an-integer", "12.5", {"id": 3}])
def test_quick_submit_refuses_a_service_id_that_is_not_a_number(
        client, value):
    """The bare `except (ValueError, TypeError): pass`, closed.

    The key IS accepted, so this is not `rejected_fields` — the value is
    unusable, which is a different sentence and a different details key, and
    the same 400.
    """
    r = _submit(client, type_id=1, service_id=value,
                description="pytest — should never be written")
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["unusable_fields"] == ["service_id"]
    assert "data" not in body


def test_quick_submit_refuses_an_id_that_names_no_record(client):
    """The unchecked `.exists()`, closed — the same silence, later.

    A location id that resolves to nothing used to be dropped and the request
    raised without a location. Handoff 31 found this route's sibling had
    NEVER saved one; this is how the sibling would have got away with it
    again.
    """
    marker = _uniq("pytest-twelfth-door-ghost-loc")
    r = _submit(client, type_id=1, location_id=2147483000,
                description=marker)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["unusable_fields"] == ["location_id"]
    assert ids_matching(client, "/api/v1/requests", marker) == []


def test_an_unusable_id_is_not_reported_as_an_unwritable_field(client):
    """The two refusals must not be confused: one is repaired by dropping the
    key, the other by fixing the value. A caller told `service_id` is not
    writable would drop it."""
    r = _submit(client, type_id=1, service_id="not-an-integer",
                description="pytest — should never be written")
    details = assert_envelope_err(r, 400, "invalid_request")["error"]["details"]
    assert "rejected_fields" not in details
    assert "service_id" in details["writable"]


# ─── quick-submit: the accepted body still works ─────────────────────


def test_an_accepted_body_still_creates_and_still_saves_the_location(
        client, test_location):
    """Handoff 31's fix, not regressed.

    The model's field is `generic_location_id`; the published key is
    `location_id`. The whole of handoff 31 was that the two had been out of
    step since the move to Odoo 19 on the sibling route, and this route
    resolves the id itself — so a rename underneath it is exactly as
    invisible here as it was there unless something reads the row back.
    """
    marker = _uniq("pytest-twelfth-door-accepted")
    r = _submit(client, type_id=1, service_id=None,
                location_id=test_location["id"], priority="2",
                description=marker, reporter_name="Pytest Reporter",
                reporter_contact="pytest@example.com")
    data = assert_envelope_ok(r, expected_status=201)["data"]

    request_id = data["request_id"]
    row = assert_envelope_ok(
        client.get(f"/api/v1/requests/{request_id}"))["data"]
    location = row.get("location")
    assert location, (
        "the location was accepted and answered 201 and is not on the row — "
        "which is handoff 31's defect, one route across")
    assert (location["id"] if isinstance(location, dict) else location) == \
        test_location["id"]


# ─── quick-submit: the two fields the schema always called required ──


def test_quick_submit_refuses_a_body_without_a_type(client):
    """The schema has declared `type_id` required since the route was
    annotated; the route now does too (handoff 37, closing 33 §C). Until
    now an absent type fell back to whichever request type happened to be
    first and active."""
    marker = _uniq("pytest-h37-no-type")
    r = _submit(client, description=marker)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["missing_fields"] == ["type_id"]
    assert ids_matching(client, "/api/v1/requests", marker) == [], (
        "the refusal created the request anyway")


def test_quick_submit_refuses_a_body_without_a_description(client):
    """An absent description used to create a record titled "Quick
    facilities request" — a request that says nothing, counted like one
    that says something."""
    r = _submit(client, type_id=1)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["missing_fields"] == ["description"]


def test_a_blank_description_is_a_missing_one(client):
    """Whitespace satisfies `required` in name only."""
    r = _submit(client, type_id=1, description="   ")
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["missing_fields"] == ["description"]


def test_an_empty_body_is_refused_and_writes_nothing(client):
    """Handoff 33 §C's opening sentence, closed: an empty body no longer
    creates anything."""
    r = _submit(client)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["missing_fields"] == [
        "type_id", "description"]
    assert body["error"]["details"]["required"] == ["type_id", "description"]


def test_a_missing_field_is_neither_rejected_nor_unusable(client):
    """Three refusals, three repairs: a rejected key is dropped, an unusable
    value is fixed, a missing field is supplied. A caller told the wrong one
    repairs the wrong thing."""
    r = _submit(client, type_id=1)
    details = assert_envelope_err(r, 400, "invalid_request")["error"]["details"]
    assert "rejected_fields" not in details
    assert "unusable_fields" not in details
    assert "description" in details["writable"]


def test_the_public_form_is_told_what_is_missing_in_words(unauthed_client):
    """The live form enforces both fields in JavaScript, so the only person
    who can read this arrived through a stale tab or a modified page — and
    they read words, not field names."""
    result = _public_quick_submit(unauthed_client)
    assert result["success"] is False
    assert result["missing_fields"] == ["type_id", "description"]
    message = result["error"]
    assert "`" not in message
    for key in ["type_id", "description", "_id", "missing_fields"]:
        assert key not in message, (
            f"the public form's refusal names `{key}`: {message!r}")
    assert message == (
        "Please choose a request type from the list on the form and "
        "describe what you need, then send your request again.")


def test_the_public_forms_one_missing_field_is_one_clause(unauthed_client):
    result = _public_quick_submit(unauthed_client, type_id=1)
    assert result["success"] is False
    assert result["error"] == (
        "Please describe what you need, then send your request again.")


def test_an_absent_optional_id_is_not_an_unusable_one(client):
    """The live homepage form sends `service_id: null` when nothing is picked.

    `homepage/index.html` reads `document.getElementById('qfService').value
    || null`, so a null arrives on every submission where the visitor did not
    choose a service. A refusal here would have taken the public form down.
    """
    marker = _uniq("pytest-twelfth-door-nulls")
    r = _submit(client, type_id=1, service_id=None, location_id=None,
                description=marker, priority="2")
    assert_envelope_ok(r, expected_status=201)


# ─── quick-submit: what a person on the form reads ───────────────────


def _public_quick_submit(unauthed_client, **params):
    """The OTHER door — `/api/myservice/quick-submit`, `auth='public'`.

    An Odoo `type='json'` route, so the body is JSON-RPC and the answer is
    under `result`. This is the endpoint the homepage form posts to, and
    `res.error` is what it puts in the error box under the button.
    """
    r = unauthed_client.post("/api/myservice/quick-submit", json={
        "jsonrpc": "2.0", "method": "call", "params": params})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "result" in body, body
    return body["result"]


def test_the_public_form_is_refused_in_words_not_field_names(
        unauthed_client):
    """**The sentence a member of the public reads on a phone.**

    Held to the rule a standing in-registry test holds the asset-history
    statements to (`myservice_api/tests/test_asset_history.py::
    test_the_statements_are_words_not_field_names`): these are shown to a
    person on a screen, and a field name is not something a person can read.
    Nothing they typed is wrong — the page sent a key the server does not
    accept — so the sentence tells them to reload rather than to correct
    something.
    """
    result = _public_quick_submit(
        unauthed_client, type_id=1, request_text="x",
        description="pytest — should never be written")
    assert result["success"] is False
    message = result["error"]
    assert "`" not in message
    for key in ["request_text", "rejected_fields", "type_id", "_id"]:
        assert key not in message, (
            f"the public form's refusal names `{key}`: {message!r}")
    assert message.endswith("."), message
    assert message[0].isupper(), message


def test_the_public_form_is_told_which_list_to_choose_from(unauthed_client):
    """An unusable id is the one refusal the visitor CAN act on."""
    result = _public_quick_submit(
        unauthed_client, type_id=1, service_id="not-an-integer",
        description="pytest — should never be written")
    assert result["success"] is False
    message = result["error"]
    assert "`" not in message
    assert "service_id" not in message
    assert "service" in message, message
    assert message.endswith("."), message
    assert message == ("Please choose the service from the list on the form, "
                       "then send your request again.")


def test_two_unusable_ids_are_one_grammatical_sentence(unauthed_client):
    """Two of them, and the sentence still reads as one — "the lists", not
    "the list", because a person reads this and a `", ".join` does not."""
    result = _public_quick_submit(
        unauthed_client, type_id=1, service_id="not-an-integer",
        location_id=2147483000,
        description="pytest — should never be written")
    assert result["error"] == (
        "Please choose the service and location from the lists on the form, "
        "then send your request again.")


def test_the_public_form_still_submits(unauthed_client):
    """The public door is not collateral damage: an accepted body still works.

    Ruled 2026-09-16 (`docs/DECISIONS.md`, close-out, §11.1): the public path
    does not change in respect of the acting user. It still creates with
    `with_user(SUPERUSER_ID)`; what is new is only that it reads the body
    before it writes.
    """
    result = _public_quick_submit(
        unauthed_client, type_id=1,
        description=_uniq("pytest-twelfth-door-public"),
        reporter_name="Pytest Public", priority="2")
    assert result["success"] is True, result
    assert result["request_name"]


# ─── employee-sync ───────────────────────────────────────────────────

_SYNC = "/api/v1/integrations/sap/employee-sync"


def _employee(client, ir_number):
    r = client.get(f"/api/v1/identity/employees/by-ir/{ir_number}")
    if r.status_code == 404:
        return None
    return assert_envelope_ok(r)["data"]


def test_employee_sync_refuses_an_unknown_key_and_writes_no_employee(client):
    ir = _uniq("PYTEST-TWELFTH").upper()
    assert _employee(client, ir) is None, "this IR number already exists"

    r = client.post(_SYNC, json={
        "ir_number": ir, "firstName": "Py", "lastName": "Test",
        "not_a_key_sap_sends": "x"})
    details = assert_fields_refused(r, "not_a_key_sap_sends")
    assert details["rejected_fields"] == ["not_a_key_sap_sends"]
    assert details["writable"] == SAP_FIELDS

    assert _employee(client, ir) is None, (
        "the refusal created the employee anyway — `process_sap_payload` "
        "creates its log row and its employee as it goes, so the refusal "
        "has to come before the call")


def test_employee_sync_refuses_status_which_it_has_never_read(client):
    """**BREAKING, and the point of the handoff.**

    `status` is in the published `SapEmployee` schema, in the endpoint
    reference's canonical example, in the demo card and in
    `tests/test_integrations.py`. `nrs.sap.sync.log` reads `employmentStatus`
    or `sap_status` and has never read `status` — so every one of those
    examples taught an integrator to send an employment status that went
    nowhere, under a 200.
    """
    ir = _uniq("PYTEST-TWELFTH-STATUS").upper()
    details = assert_fields_refused(
        client.post(_SYNC, json={"ir_number": ir, "status": "active"}),
        "status")
    assert "employmentStatus" in details["writable"]
    assert "sap_status" in details["writable"]
    assert _employee(client, ir) is None


def test_employee_sync_refuses_the_whole_batch_not_the_bad_row(client):
    """A list is ONE request.

    Refusing the second employee after the first is written would leave a
    partial sync under an idempotency key that replays the same answer on
    every retry — which is the property Vendra needs and the reason handoff
    31 made a refusal whole-body rather than per-field.
    """
    good = _uniq("PYTEST-TWELFTH-BATCH-A").upper()
    bad = _uniq("PYTEST-TWELFTH-BATCH-B").upper()
    r = client.post(_SYNC, json=[
        {"ir_number": good, "firstName": "Good", "lastName": "Row"},
        {"ir_number": bad, "firstName": "Bad", "lastName": "Row",
         "officeCode": "HQ"},
    ])
    assert_fields_refused(r, "officeCode")
    assert _employee(client, good) is None, (
        "the first employee of the batch was written before the second was "
        "refused")
    assert _employee(client, bad) is None


def test_employee_sync_accepts_its_documented_keys_unchanged(client):
    """The control, and the regression net: what SAP actually sends still
    syncs, and still returns the same 200 envelope."""
    ir = _uniq("PYTEST-TWELFTH-OK").upper()
    r = client.post(_SYNC, json={
        "ir_number": ir,
        "userId": "pytest.twelfth@example.com",
        "firstName": "Py",
        "lastName": "Test",
        "department": "Pytest",
        "jobTitle": "Smoke Tester",
        "employmentStatus": "active",
    })
    data = assert_envelope_ok(r)["data"]
    assert data["processed"] == 1
    assert data["results"][0]["ir_number"] == ir
    assert data["results"][0]["status"] in ("success", "skipped")
    assert _employee(client, ir) is not None


def test_a_refused_quick_submit_does_not_burn_its_idempotency_key(
        client, test_location):
    """The sequence Vendra needs, one door across.

    Only a SUCCESS is stored under an `X-Idempotency-Key`, so the repair is
    to fix the body and deliver again under the SAME key. Handoff 31 pinned
    this on `POST /api/v1/assets`; both routes here are `idempotent=True` and
    would have the same defect from the other side, since the lenient answer
    was a 201 that every retry then replayed.
    """
    key = _uniq("pytest-twelfth-idem")
    marker = _uniq("pytest-twelfth-idem-req")
    good = {"type_id": 1, "location_id": test_location["id"],
            "description": marker}
    headers = {"X-Idempotency-Key": key}

    first = client.post("/api/v1/home/quick-submit",
                        json={**good, "request_text": "x"}, headers=headers)
    assert_fields_refused(first, "request_text")
    second = client.post("/api/v1/home/quick-submit",
                         json={**good, "request_text": "x"}, headers=headers)
    assert_fields_refused(second, "request_text")
    assert (second.json()["error"]["request_id"]
            != first.json()["error"]["request_id"]), (
        "the second 400 is a replay, so the refusal was stored under the key")
    assert ids_matching(client, "/api/v1/requests", marker) == []

    landed = assert_envelope_ok(
        client.post("/api/v1/home/quick-submit", json=good, headers=headers),
        201)["data"]
    assert ids_matching(client, "/api/v1/requests", marker) == \
        [landed["request_id"]], "one key, one request"


def test_a_batch_of_documented_keys_writes_every_row(client):
    """The other half of the batch property — the refusal is not a blanket
    one, and a clean list still syncs whole."""
    first = _uniq("PYTEST-TWELFTH-OKA").upper()
    second = _uniq("PYTEST-TWELFTH-OKB").upper()
    r = client.post(_SYNC, json=[
        {"ir_number": first, "firstName": "One", "lastName": "Row"},
        {"ir_number": second, "firstName": "Two", "lastName": "Row"},
    ])
    data = assert_envelope_ok(r)["data"]
    assert data["processed"] == 2
    assert _employee(client, first) is not None
    assert _employee(client, second) is not None
