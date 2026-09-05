#!/usr/bin/env python3
"""Dev smoke test for the Cadra REST API. Reads creds from docs/api/.creds.

The API is now properly RESTful:
  - GET    /resource              → list (query string filters)
  - GET    /resource/<id>         → single
  - POST   /resource              → create (201 Created)
  - PATCH  /resource/<id>         → partial update
  - POST   /resource/<id>/<verb>  → action endpoint

Responses are the PRD envelope directly — no `.result` JSON-RPC wrapper:
  success: {"data": ..., "meta": {...}, "pagination": {...}?}
  error:   {"error": {...}}
"""
import json
import os
import sys
import urllib.parse
import urllib.request

# The dev stack is multi-tenant on the hostname (`http://<db>.localhost:8069`);
# bare localhost answers "No database is selected". Same env var the pytest
# suite uses, so one export points both at the same instance.
API_BASE = os.environ.get("CADRA_API_BASE", "http://localhost:8069").rstrip("/")


# ─── HTTP helpers ────────────────────────────────────────────────────

class HTTPError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


def load_creds():
    creds = {}
    with open("docs/api/.creds") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k] = v
    return creds


def call(method, path, *, query=None, body=None, token=None, idempotency_key=None):
    """Generic HTTP call. Returns (status, parsed_body_dict)."""
    url = f"{API_BASE}{path}"
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"error": {"code": "unparseable", "message": str(e)}}


# Aliases for readability
def GET(path, *, query=None, token=None):
    return call("GET", path, query=query, token=token)


def POST(path, *, body=None, token=None, idempotency_key=None):
    return call("POST", path, body=body or {}, token=token, idempotency_key=idempotency_key)


def PATCH(path, *, body=None, token=None, idempotency_key=None):
    return call("PATCH", path, body=body or {}, token=token, idempotency_key=idempotency_key)


# ─── renderer ────────────────────────────────────────────────────────

def render(status, r):
    if "error" in r:
        print(f"  HTTP {status}  ERROR  {r['error']['code']}: {r['error']['message']}")
        return False

    def label(it):
        return it.get("name") or it.get("reference") or "?"

    data = r.get("data")
    pag = r.get("pagination")
    if isinstance(data, list):
        print(f"  HTTP {status}  list of {len(data)} item(s)")
        for it in data[:5]:
            print(f"    id={it['id']:4d}  {label(it)!r}")
        if pag:
            print(f"  total_estimate={pag['total_estimate']}, "
                  f"next_cursor={'set' if pag['next_cursor'] else 'none'}")
    elif isinstance(data, dict):
        print(f"  HTTP {status}  single  id={data.get('id')}  {label(data)!r}")
        for opt in ("children", "ancestors"):
            if opt in data:
                print(f"    {opt}: {len(data[opt])} entries")
    else:
        print(f"  HTTP {status}  {data!r}")
    return True


def section(title):
    print()
    print("═" * 70)
    print(f"  {title}")
    print("═" * 70)


def step(title):
    print(f"─── {title} ───")


# ─── main ────────────────────────────────────────────────────────────

def main():
    creds = load_creds()

    # Auth
    section("AUTH")
    step("POST /api/v1/auth/token  (flat body, no params wrapper)")
    status, r = POST("/api/v1/auth/token", body={
        "client_id": creds["CLIENT_ID"],
        "client_secret": creds["CLIENT_SECRET"],
    })
    if status != 200 or "error" in r:
        print(f"  ABORTING: token mint failed: HTTP {status} {r}")
        return 1
    token = r["data"]["access_token"]
    print(f"  HTTP {status}  token: {token[:30]}...  expires_in={r['data']['expires_in']}")
    print(f"  request_id={r['meta']['request_id']}, version={r['meta']['version']}")

    # ─── Locations ─────────────────────────────────────────────────
    section("LOCATIONS")

    step("GET /api/v1/locations?limit=3")
    status, r = GET("/api/v1/locations", query={"limit": 3}, token=token)
    render(status, r)

    step("GET /api/v1/locations?q=ZZZZZZ  (impossible match)")
    status, r = GET("/api/v1/locations", query={"q": "ZZZZZZ", "limit": 5}, token=token)
    render(status, r)

    step("GET /api/v1/locations?q=Lagos")
    status, r = GET("/api/v1/locations", query={"q": "Lagos", "limit": 5}, token=token)
    render(status, r)

    step("GET /api/v1/locations/1?include=children,ancestors")
    status, r = GET("/api/v1/locations/1", query={"include": "children,ancestors"}, token=token)
    render(status, r)

    step("GET /api/v1/locations/1/children")
    status, r = GET("/api/v1/locations/1/children", token=token)
    render(status, r)

    step("GET /api/v1/locations/1/descendants?limit=3")
    status, r = GET("/api/v1/locations/1/descendants", query={"limit": 3}, token=token)
    render(status, r)

    step("POST /api/v1/locations  (create — expect 201)")
    status, r = POST("/api/v1/locations", body={
        "name": "Smoke Test HQ",
        "description": "via REST API",
        "latitude": 6.5244, "longitude": 3.3792,
    }, token=token)
    if not render(status, r):
        return 1
    created_loc_id = r["data"]["id"]
    print(f"  created_loc_id={created_loc_id}")

    step(f"PATCH /api/v1/locations/{created_loc_id}  (update description + lat)")
    status, r = PATCH(f"/api/v1/locations/{created_loc_id}", body={
        "description": "patched", "latitude": 9.0,
    }, token=token)
    render(status, r)

    step("pagination cursor: page 1 + page 2 disjoint")
    _, p1 = GET("/api/v1/locations", query={"limit": 3}, token=token)
    ids1 = [it["id"] for it in p1["data"]]
    cursor = p1["pagination"]["next_cursor"]
    _, p2 = GET("/api/v1/locations", query={"limit": 3, "cursor": cursor}, token=token)
    ids2 = [it["id"] for it in p2["data"]]
    print(f"  page 1 ids: {ids1}")
    print(f"  page 2 ids: {ids2}")
    print(f"  pages disjoint: {not (set(ids1) & set(ids2))}")

    step("idempotency: two POST creates with same X-Idempotency-Key")
    key = f"smoke-loc-{int(__import__('time').time())}"
    _, a = POST("/api/v1/locations",
                body={"name": f"Idem-{key}", "description": "first"},
                token=token, idempotency_key=key)
    _, b = POST("/api/v1/locations",
                body={"name": f"Idem-{key}", "description": "SECOND"},
                token=token, idempotency_key=key)
    a_id, b_id = a["data"]["id"], b["data"]["id"]
    if a_id == b_id and a["meta"]["request_id"] == b["meta"]["request_id"]:
        print(f"  ✓ idempotency working — both calls returned id={a_id}")
    else:
        print(f"  ✗ idempotency broken — got id={a_id} vs id={b_id}")

    # ─── Assets ────────────────────────────────────────────────────
    section("ASSETS")

    step("GET /api/v1/assets?limit=3")
    status, r = GET("/api/v1/assets", query={"limit": 3}, token=token)
    render(status, r)

    step("POST /api/v1/assets  (create — expect 201)")
    asset_tag = f"SMOKE-LP-{int(__import__('time').time()) % 1000000:06d}"
    status, r = POST("/api/v1/assets", body={
        "name": "Dell Latitude Smoke Laptop",
        "asset_tag": asset_tag,
        "make": "Dell", "model_name": "Latitude 5520",
        "serial_number": f"SN-{int(__import__('time').time()) % 1000000}",
        "category_id": 1,
        "condition": "new", "state": "active",
        "purchase_value": 850000.0,
        "location_id": created_loc_id,
    }, token=token)
    if not render(status, r):
        return 1
    asset_id = r["data"]["id"]
    print(f"  asset_id={asset_id}, tag={r['data']['tag']!r}")

    step(f"GET /api/v1/assets/{asset_id}?include=transfers")
    status, r = GET(f"/api/v1/assets/{asset_id}", query={"include": "transfers"}, token=token)
    render(status, r)

    step(f"GET /api/v1/assets/by-tag/{asset_tag}")
    status, r = GET(f"/api/v1/assets/by-tag/{asset_tag}", token=token)
    render(status, r)

    step(f"PATCH /api/v1/assets/{asset_id}  (set condition=good, add notes)")
    status, r = PATCH(f"/api/v1/assets/{asset_id}", body={
        "condition": "good", "notes": "Smoke-tested via REST API",
    }, token=token)
    if "error" not in r:
        print(f"  HTTP {status}  condition={r['data']['condition']!r}, notes={r['data']['notes']!r}")
    else:
        render(status, r)

    step(f"POST /api/v1/assets/{asset_id}/move  to location id=2")
    status, r = POST(f"/api/v1/assets/{asset_id}/move", body={
        "to_location_id": 2, "reason": "Smoke test move",
    }, token=token)
    if "error" not in r:
        t = r["data"]["transfer"]
        from_name = t["from_location"]["name"] if t["from_location"] else None
        print(f"  HTTP {status}  moved: {from_name!r} → {t['to_location']['name']!r}, ref={t['reference']}")
    else:
        render(status, r)

    step(f"POST /api/v1/assets/{asset_id}/transfer-custody  to employee id=1")
    status, r = POST(f"/api/v1/assets/{asset_id}/transfer-custody", body={
        "to_custodian_id": 1, "reason": "Smoke test custody",
    }, token=token)
    if "error" not in r:
        c = r["data"]["custody_change"]
        from_name = c["from_custodian"]["name"] if c["from_custodian"] else None
        print(f"  HTTP {status}  custody: {from_name!r} → {c['to_custodian']['name']!r}, message_id={c['message_id']}")
    else:
        render(status, r)

    step("GET /api/v1/assets?q=Smoke")
    status, r = GET("/api/v1/assets", query={"q": "Smoke", "limit": 5}, token=token)
    render(status, r)

    step("idempotency: two POST asset creates with same key")
    akey = f"smoke-asset-{int(__import__('time').time())}"
    _, a = POST("/api/v1/assets",
                body={"name": f"IdemAsset-{akey}", "category_id": 1, "location_id": created_loc_id},
                token=token, idempotency_key=akey)
    _, b = POST("/api/v1/assets",
                body={"name": f"IdemAsset-DIFFERENT-{akey}", "category_id": 1, "location_id": created_loc_id},
                token=token, idempotency_key=akey)
    if "error" in a or "error" in b:
        print(f"  ERROR a={a.get('error')} b={b.get('error')}")
    else:
        if a["data"]["id"] == b["data"]["id"]:
            print(f"  ✓ idempotency working — both returned id={a['data']['id']}")
        else:
            print(f"  ✗ broken — got {a['data']['id']} vs {b['data']['id']}")

    # ─── Service Requests ──────────────────────────────────────────
    section("SERVICE REQUESTS")

    step("GET /api/v1/requests?limit=3")
    status, r = GET("/api/v1/requests", query={"limit": 3}, token=token)
    render(status, r)

    step("POST /api/v1/requests  (create — expect 201)")
    status, r = POST("/api/v1/requests", body={
        "type_id": 1,
        "category_id": 5,
        "priority": "2",
        "request_text": "<p>Smoke test: REST API request.</p>",
        "location_id": created_loc_id,
        "nrs_asset_id": asset_id,
    }, token=token)
    if not render(status, r):
        return 1
    req_id = r["data"]["id"]
    req_ref = r["data"]["reference"]
    routes = r["data"].get("available_routes", [])
    print(f"  req_id={req_id}, ref={req_ref!r}, stage={r['data']['stage']['name']!r}")
    print(f"  available routes: {len(routes)}")
    for rt in routes[:3]:
        print(f"    route_id={rt['id']:3d}  {rt['from_stage']['name']!r} → {rt['to_stage']['name']!r}")

    step(f"GET /api/v1/requests/{req_id}?include=routes")
    status, r = GET(f"/api/v1/requests/{req_id}", query={"include": "routes"}, token=token)
    render(status, r)

    step(f"GET /api/v1/requests/by-reference/{req_ref}")
    status, r = GET(f"/api/v1/requests/by-reference/{req_ref}", token=token)
    render(status, r)

    step(f"PATCH /api/v1/requests/{req_id}  (priority + response_text)")
    status, r = PATCH(f"/api/v1/requests/{req_id}", body={
        "priority": "3",
        "response_text": "<p>Acknowledged via REST.</p>",
    }, token=token)
    if "error" not in r:
        print(f"  HTTP {status}  priority={r['data']['priority']!r}")
    else:
        render(status, r)

    step(f"PATCH /api/v1/requests/{req_id}  (try stage_id — should be rejected)")
    status, r = PATCH(f"/api/v1/requests/{req_id}", body={"stage_id": 99}, token=token)
    if "data" in r and "_warnings" in r["data"]:
        print(f"  HTTP {status}  rejected: {r['data']['_warnings'].get('rejected_fields')}")
        print(f"           hint: {r['data']['_warnings'].get('hint')}")
    else:
        render(status, r)

    step(f"POST /api/v1/requests/{req_id}/assign  to user_id=2")
    status, r = POST(f"/api/v1/requests/{req_id}/assign", body={"user_id": 2}, token=token)
    if "error" not in r:
        a = r["data"]["assignee"]
        print(f"  HTTP {status}  assignee: {a['name'] if a else None!r}")
    else:
        render(status, r)

    step(f"POST /api/v1/requests/{req_id}/transition  via first available route")
    if routes:
        status, r = POST(f"/api/v1/requests/{req_id}/transition", body={
            "route_id": routes[0]["id"],
        }, token=token)
        if "error" not in r:
            t = r["data"]["transition"]
            print(f"  HTTP {status}  {t['from_stage']['name']!r} → {t['to_stage']['name']!r} (route: {t['route_name']!r})")
        else:
            render(status, r)
    else:
        print("  SKIPPED: no available routes on initial stage")

    step(f"POST /api/v1/requests/{req_id}/comment  (internal)")
    status, r = POST(f"/api/v1/requests/{req_id}/comment", body={
        "body": "<p>Smoke test note via REST.</p>",
        "internal": True,
    }, token=token)
    if "error" not in r:
        c = r["data"]["comment"]
        print(f"  HTTP {status}  comment_id={c['id']}, internal={c['internal']}")
    else:
        render(status, r)

    step("GET /api/v1/requests?q=INCIDENT")
    status, r = GET("/api/v1/requests", query={"q": "INCIDENT", "limit": 5}, token=token)
    render(status, r)

    step("idempotency: two POST request creates with same key")
    rkey = f"smoke-req-{int(__import__('time').time())}"
    _, a = POST("/api/v1/requests",
                body={"type_id": 1, "category_id": 5, "request_text": f"<p>IdemReq-{rkey}</p>"},
                token=token, idempotency_key=rkey)
    _, b = POST("/api/v1/requests",
                body={"type_id": 1, "category_id": 5, "request_text": f"<p>IdemReq-DIFFERENT-{rkey}</p>"},
                token=token, idempotency_key=rkey)
    if "error" in a or "error" in b:
        print(f"  ERROR a={a.get('error')} b={b.get('error')}")
    else:
        if a["data"]["id"] == b["data"]["id"]:
            print(f"  ✓ idempotency working — both returned id={a['data']['id']}")
        else:
            print(f"  ✗ broken — got {a['data']['id']} vs {b['data']['id']}")

    # ─── Negative checks ──────────────────────────────────────────
    section("NEGATIVE CHECKS")

    step("GET /api/v1/locations  (no Authorization header — expect 401)")
    status, r = GET("/api/v1/locations")
    print(f"  HTTP {status}  code={r['error']['code']!r}")

    step("GET /api/v1/locations/99999999  (nonexistent id — expect 404)")
    status, r = GET("/api/v1/locations/99999999", token=token)
    print(f"  HTTP {status}  code={r['error']['code']!r}")

    step("POST /api/v1/locations  (missing required `name` — expect 400)")
    status, r = POST("/api/v1/locations", body={"description": "no name"}, token=token)
    print(f"  HTTP {status}  code={r['error']['code']!r}  message={r['error']['message']!r}")

    print()
    print("═" * 70)
    print("  SMOKE TEST COMPLETE")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
