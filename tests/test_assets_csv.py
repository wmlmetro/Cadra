"""GET /api/v1/assets/export.csv — CSV export. Doesn't use the PRD envelope."""


def test_export_csv(client, capture):
    r = client.get("/api/v1/assets/export.csv")
    capture("assets/export_csv", r)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("Content-Type", "")
    assert "attachment" in r.headers.get("Content-Disposition", "")
    # Must at least have the CSV header row
    first_line = r.text.split("\n", 1)[0]
    assert "Asset Code" in first_line, f"unexpected CSV header: {first_line!r}"


def test_export_csv_no_auth(unauthed_client, capture):
    """No bearer → 401 with PRD-shape error JSON (not CSV)."""
    r = unauthed_client.get("/api/v1/assets/export.csv")
    capture("assets/export_csv_no_auth", r)
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "unauthorized"
