"""2 homepage endpoints: /home/form-data and /home/quick-submit."""
from .conftest import CANONICAL_ERROR_CODES, assert_envelope_ok


def test_form_data(client, capture):
    """GET /api/v1/home/form-data — dropdown data for the homepage form."""
    r = client.get("/api/v1/home/form-data")
    capture("home/form_data", r)
    assert_envelope_ok(r)


def test_quick_submit(client, capture):
    """POST /api/v1/home/quick-submit — submit a request via the homepage path.

    This was an xfail because the delegated controller failed in a way that
    escaped the envelope entirely and returned a werkzeug HTML 500 — no code,
    no request_id, nothing an integration could branch on. `_http_response`
    now recognises a handler that returned a bare `{"error": "<string>"}` and
    renders it as an `internal_error` envelope carrying the original message,
    so the CONTRACT holds regardless of the upstream defect.

    **The upstream defect is now closed** (handoff 15). The website-theme
    controller this delegates to wrote `website_id`, which `request.request`
    does not have, and called a `crnd_wsd` method that no longer exists on
    Odoo 19 — both swallowed by a bare `except Exception`, so every homepage
    submission since the 19 port answered `{"success": false}` and the
    visitor was shown Cadra's own bug as if it were their mistake.

    So the success branch below runs for the first time, and it turned out to
    be wrong: it expected 200, and this is a CREATE — `cadra_route` renders
    201. A branch that has never executed is not tested code, however green
    the file has been.

    The test still does not pin the endpoint to success. It asserts the only
    thing that is ours to guarantee either way: the caller gets a branchable
    envelope — a canonical code, a request_id, and a status that agrees with
    the body.

    **And the body it sent was wrong for the whole of that time** (handoff
    32 §B). `name`, `email`, `phone` and `subject` are not keys this route
    accepts — it takes `reporter_name`, `reporter_contact` and `description`
    — so every submission this test ever made raised a request with no
    reporter and a subject nobody could read, and answered 201. The route
    took `**kwargs` and dropped what it did not recognise, which is why the
    branchable-envelope assertion below stayed green over it. An unaccepted
    key is now a 400 naming it, so the body is corrected here and the
    refusals have a file of their own:
    `tests/test_the_twelfth_door.py`.
    """
    # `type_id` is here because handoff 37 made the schema's `required` pair
    # real: a body without one is now a designed 400, and this test exists to
    # capture the SUBMIT path, not the refusal — the refusals have their own
    # file (`tests/test_the_twelfth_door.py`).
    r = client.post("/api/v1/home/quick-submit", json={
        "type_id": 1,
        "reporter_name": "pytest homepage",
        "reporter_contact": "pytest@example.com",
        "description": "Created by the pytest suite — please ignore.",
    })
    capture("home/quick_submit", r)
    assert r.headers.get("Content-Type", "").startswith("application/json"), \
        f"expected JSON response, got: {r.headers.get('Content-Type')!r}\nBody:\n{r.text[:300]}"
    body = r.json()

    if "error" in body:
        # Whatever went wrong, it has to be branchable: a canonical code, a
        # request_id to quote, and a status that agrees with the envelope.
        assert r.status_code >= 400, (
            f"an error envelope at HTTP {r.status_code} — an integration "
            f"reading the status would treat this as success"
        )
        assert body["error"]["code"] in CANONICAL_ERROR_CODES, (
            f"uncanonical error code {body['error']['code']!r}"
        )
        assert body["error"]["request_id"]
        assert body["error"]["details"]["http_status"] == r.status_code
    else:
        # 201: this endpoint creates a request. See the docstring — this
        # branch had never run until the upstream defect was fixed.
        assert_envelope_ok(r, expected_status=201)
