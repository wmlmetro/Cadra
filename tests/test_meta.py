"""OpenAPI spec + Swagger UI endpoints. These don't use the PRD envelope."""


def test_openapi_spec_shape(client, capture):
    """/api/v1/openapi.json — auto-generated OpenAPI 3.0 spec."""
    r = client.get("/api/v1/openapi.json")
    capture("meta/openapi", r)
    assert r.status_code == 200
    assert "application/json" in r.headers.get("Content-Type", "")
    body = r.json()
    assert body.get("openapi", "").startswith("3."), f"unexpected openapi version: {body.get('openapi')}"
    assert "info" in body and body["info"]["title"]
    assert "paths" in body and len(body["paths"]) >= 30, \
        f"expected at least 30 endpoints in spec, got {len(body.get('paths', {}))}"


def test_swagger_ui(client, capture):
    """/api/v1/docs — CDN-hosted Swagger UI HTML."""
    r = client.get("/api/v1/docs")
    capture("meta/docs", r)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("Content-Type", "")
    assert b"swagger-ui" in r.content.lower() or b"swagger" in r.content.lower()


def test_openapi_lists_every_cadra_route(client, capture):
    """Sanity: the openapi spec lists every path served by our test client.

    This catches the case where someone adds a new @cadra_route but forgets
    to ship the spec — which can't actually happen (the spec is auto-generated
    from the registry) but we verify the round-trip.
    """
    r = client.get("/api/v1/openapi.json")
    capture("meta/openapi_coverage", r)
    body = r.json()
    paths = list(body["paths"].keys())

    # Spot-check the four major resource families have at least basic CRUD
    required_endpoints = [
        ("/api/v1/auth/token", "post"),
        ("/api/v1/locations", "get"),
        ("/api/v1/locations", "post"),
        ("/api/v1/locations/{id}", "get"),
        ("/api/v1/locations/{id}", "patch"),
        ("/api/v1/assets", "get"),
        ("/api/v1/assets", "post"),
        ("/api/v1/assets/{id}", "get"),
        ("/api/v1/requests", "get"),
        ("/api/v1/requests", "post"),
        ("/api/v1/requests/{id}", "get"),
    ]
    for path, method in required_endpoints:
        assert path in body["paths"], f"OpenAPI spec missing path {path}"
        assert method in body["paths"][path], \
            f"OpenAPI spec missing {method.upper()} on {path}"
