"""All 4 Identity endpoints (read-only)."""
from .conftest import assert_envelope_err, assert_envelope_ok


def test_list(client, capture):
    """GET /api/v1/identity/employees — list with pagination."""
    r = client.get("/api/v1/identity/employees", params={"limit": 5})
    capture("identity/list", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 5
    assert "pagination" in body
    assert body["pagination"]["total_estimate"] >= 0
    if body["data"]:
        emp = body["data"][0]
        for key in ("id", "name", "sap", "employment", "assets", "location"):
            assert key in emp, f"missing {key!r} in employee shape: {emp.keys()}"
        for forbidden in ("private_email", "private_phone", "bank_account_id",
                          "identification_id", "passport_id", "birthday",
                          "marital", "spouse_birthdate", "spouse_complete_name"):
            assert forbidden not in emp, f"sensitive field {forbidden!r} leaked"


def test_list_filter_active(client, capture):
    """active=false should not return active employees."""
    r = client.get("/api/v1/identity/employees",
                   params={"active": "false", "limit": 5})
    capture("identity/list_inactive", r)
    body = assert_envelope_ok(r)
    for emp in body["data"]:
        assert emp["active"] is False


def test_list_filter_sap_status(client, capture):
    """sap_status filter narrows to a single status."""
    r = client.get("/api/v1/identity/employees",
                   params={"sap_status": "active", "limit": 5})
    capture("identity/list_sap_active", r)
    body = assert_envelope_ok(r)
    for emp in body["data"]:
        assert emp["sap"]["status"] == "active"


def test_list_pagination_cursor(client, capture):
    """Two pages with cursor — IDs should be disjoint."""
    r1 = client.get("/api/v1/identity/employees", params={"limit": 3})
    capture("identity/list_page1", r1)
    body1 = assert_envelope_ok(r1)
    cursor = body1["pagination"]["next_cursor"]
    if not cursor:
        return  # too few employees seeded — nothing to paginate
    r2 = client.get("/api/v1/identity/employees",
                    params={"limit": 3, "cursor": cursor})
    capture("identity/list_page2", r2)
    body2 = assert_envelope_ok(r2)
    ids1 = {item["id"] for item in body1["data"]}
    ids2 = {item["id"] for item in body2["data"]}
    assert not (ids1 & ids2), f"page 1 and page 2 overlap: {ids1 & ids2}"


def test_get_by_id(client, capture):
    """GET /api/v1/identity/employees/<id> — single record, manager resolved."""
    list_r = client.get("/api/v1/identity/employees", params={"limit": 1})
    seed = list_r.json()["data"]
    if not seed:
        return  # empty employees table; smoke-only env
    emp_id = seed[0]["id"]
    r = client.get(f"/api/v1/identity/employees/{emp_id}")
    capture("identity/get_by_id", r)
    body = assert_envelope_ok(r)
    assert body["data"]["id"] == emp_id
    assert "manager" in body["data"], "detail view should resolve manager"


def test_get_not_found(client, capture):
    """GET nonexistent id → 404 not_found."""
    r = client.get("/api/v1/identity/employees/99999999")
    capture("identity/get_not_found", r)
    assert_envelope_err(r, expected_status=404, expected_code="not_found")


def test_by_ir_not_found(client, capture):
    """GET /by-ir/<unknown> → 404 not_found."""
    r = client.get("/api/v1/identity/employees/by-ir/NO-SUCH-IR-9999")
    capture("identity/by_ir_not_found", r)
    assert_envelope_err(r, expected_status=404, expected_code="not_found")


def test_by_ir_found(client, capture):
    """GET /by-ir/<ir> resolves when an IR exists in the seed data."""
    list_r = client.get("/api/v1/identity/employees", params={"limit": 50})
    with_ir = next((e for e in list_r.json()["data"] if e.get("ir_number")), None)
    if not with_ir:
        return  # seed has no employees with ir_number set; can't exercise
    r = client.get(f"/api/v1/identity/employees/by-ir/{with_ir['ir_number']}")
    capture("identity/by_ir_found", r)
    body = assert_envelope_ok(r)
    assert body["data"]["ir_number"] == with_ir["ir_number"]
    assert body["data"]["id"] == with_ir["id"]


def test_employee_assets(client, capture):
    """GET /api/v1/identity/employees/<id>/assets — custodial assets list."""
    list_r = client.get("/api/v1/identity/employees", params={"limit": 1})
    seed = list_r.json()["data"]
    if not seed:
        return
    emp_id = seed[0]["id"]
    r = client.get(f"/api/v1/identity/employees/{emp_id}/assets",
                   params={"limit": 5})
    capture("identity/employee_assets", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert "pagination" in body
    for asset in body["data"]:
        assert asset.get("current_custodian", {}).get("id") == emp_id, (
            "asset returned does not have this employee as custodian"
        )


def test_employee_assets_not_found(client, capture):
    """Assets for nonexistent employee → 404."""
    r = client.get("/api/v1/identity/employees/99999999/assets")
    capture("identity/employee_assets_not_found", r)
    assert_envelope_err(r, expected_status=404, expected_code="not_found")
