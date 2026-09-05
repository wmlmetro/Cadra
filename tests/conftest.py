"""
Cadra API test fixtures + reporting hooks.

Session-scoped fixtures (mint once, reuse across tests):
  - api_base       : http://localhost:8069 (env-overridable via CADRA_API_BASE)
  - creds          : reads docs/api/.creds
  - token          : mints a JWT via POST /auth/token, returns the access_token
  - client         : ApiClient wrapper around requests.Session with auth pre-set
  - test_location  : creates one location via POST, reused as FK by asset/request tests
  - test_asset     : creates one asset against test_location
  - test_request   : creates one service request against test_location + test_asset

Function-scoped:
  - capture        : helper that writes (request, response) pairs to docs/api/test-responses/

Hooks:
  - pytest_runtest_makereport  : record each test's outcome for the report
  - pytest_terminal_summary    : generate docs/api/test-report.md at session end
"""
import datetime
import json
import os
import pathlib
import time
from collections import defaultdict

import pytest
import requests


# ─── locations on disk ───────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CREDS_FILE = REPO_ROOT / "docs" / "api" / ".creds"
RESPONSES_DIR = REPO_ROOT / "docs" / "api" / "test-responses"
REPORT_FILE = REPO_ROOT / "docs" / "api" / "test-report.md"

# Collected at session end into the markdown report.
_test_results = []           # list of {nodeid, outcome, duration, method, path, status, capture_path}
_session_started_at = None


# ─── fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api_base():
    return os.environ.get("CADRA_API_BASE", "http://localhost:8069").rstrip("/")


@pytest.fixture(scope="session")
def creds():
    if not CREDS_FILE.exists():
        pytest.fail(
            f"credentials file not found at {CREDS_FILE}.\n"
            "Run docs/api/setup_api_smoke.py first to create a test client."
        )
    out = {}
    for line in CREDS_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            out[k] = v
    if "CLIENT_ID" not in out or "CLIENT_SECRET" not in out:
        pytest.fail(f"{CREDS_FILE} is missing CLIENT_ID or CLIENT_SECRET")
    return out


@pytest.fixture(scope="session")
def token(api_base, creds):
    """Mint a JWT once per test session and cache it."""
    try:
        r = requests.post(
            f"{api_base}/api/v1/auth/token",
            json={
                "client_id": creds["CLIENT_ID"],
                "client_secret": creds["CLIENT_SECRET"],
            },
            timeout=10,
        )
    except requests.exceptions.ConnectionError as e:
        pytest.fail(
            f"Could not connect to Cadra API at {api_base}.\n"
            f"Is the docker stack up? (docker compose -f docker-compose.dev.yml up -d)\n"
            f"Underlying error: {e}"
        )
    if r.status_code != 200:
        pytest.fail(
            f"Failed to mint test token: HTTP {r.status_code}\n{r.text[:500]}"
        )
    body = r.json()
    return body["data"]["access_token"]


class ApiClient:
    """Thin wrapper around requests.Session that pre-sets the bearer header
    and resolves relative URLs against api_base. Used by all tests via the
    `client` fixture below."""

    def __init__(self, base, token):
        self.base = base
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _url(self, path):
        return path if path.startswith("http") else self.base + path

    def get(self, path, **kw):
        return self.session.get(self._url(path), timeout=30, **kw)

    def post(self, path, **kw):
        return self.session.post(self._url(path), timeout=30, **kw)

    def patch(self, path, **kw):
        return self.session.patch(self._url(path), timeout=30, **kw)

    def delete(self, path, **kw):
        return self.session.delete(self._url(path), timeout=30, **kw)


@pytest.fixture(scope="session")
def client(api_base, token):
    return ApiClient(api_base, token)


@pytest.fixture(scope="session")
def unauthed_client(api_base):
    """A client with NO Authorization header — used by negative tests."""
    return ApiClient(api_base, token=None)


# ─── response capture ────────────────────────────────────────────────

@pytest.fixture
def capture(request):
    """Returns a function `capture(name, response)` that writes the full
    request/response pair to docs/api/test-responses/<name>.json.

    `name` is treated as a relative path under the responses dir — use
    forward slashes to group by resource: capture("locations/list", r).
    """
    def _capture(name, response):
        path = RESPONSES_DIR / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Pull the request that produced this response (requests stores it
        # on the Response object).
        req = response.request
        req_body = None
        if req.body is not None:
            try:
                req_body = json.loads(req.body) if isinstance(req.body, (str, bytes)) else req.body
            except Exception:
                req_body = req.body.decode("utf-8", errors="replace") if isinstance(req.body, bytes) else str(req.body)

        # Parse response body if possible
        try:
            resp_body = response.json()
        except Exception:
            text = response.text
            resp_body = text[:2000] + (" ... <truncated>" if len(text) > 2000 else "")

        payload = {
            "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            "request": {
                "method": req.method,
                "url": req.url,
                "headers": {k: ("<redacted>" if k.lower() == "authorization" else v) for k, v in req.headers.items()},
                "body": req_body,
            },
            "response": {
                "status": response.status_code,
                "headers": dict(response.headers),
                "elapsed_seconds": response.elapsed.total_seconds(),
                "body": resp_body,
            },
        }
        path.write_text(json.dumps(payload, indent=2, default=str))

        # Attach metadata so the report hook can render the row.
        nodeid = request.node.nodeid
        capture_relpath = path.relative_to(RESPONSES_DIR.parent).as_posix()
        request.node.user_properties.append(
            ("cadra_endpoint", {
                "method": req.method,
                "url": req.url,
                "path": _extract_path(req.url),
                "status": response.status_code,
                "capture": capture_relpath,
            })
        )

    return _capture


def _extract_path(url):
    """Strip protocol/host/query from URL → just the path."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return parts.path


# ─── shared test resources (created once per session) ────────────────

@pytest.fixture(scope="session")
def test_location(client):
    """Create one location at session start; reused as FK by asset/request tests."""
    r = client.post("/api/v1/locations", json={
        "name": f"pytest-loc-{int(time.time())}",
        "description": "Created by tests/conftest.py — leave in dev DB",
    })
    if r.status_code != 201:
        pytest.fail(f"test_location fixture failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]


@pytest.fixture(scope="session")
def test_asset(client, test_location):
    """Create one asset at session start; reused by request tests."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-asset-{ts}",
        "asset_tag": f"PYTEST-{ts}",
        "category_id": 1,  # first asset category (seed has many)
        "condition": "new",
        "state": "active",
        "location_id": test_location["id"],
    })
    if r.status_code != 201:
        pytest.fail(f"test_asset fixture failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]


@pytest.fixture(scope="session")
def test_request(client, test_location, test_asset):
    """Create one service request at session start; reused by action tests."""
    r = client.post("/api/v1/requests", json={
        "type_id": 1,        # Incident (first seeded type)
        "category_id": 5,    # First existing category (1-4 skipped by seed)
        "priority": "2",
        "request_text": f"<p>pytest fixture request created at {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z</p>",
        "location_id": test_location["id"],
        "nrs_asset_id": test_asset["id"],
    })
    if r.status_code != 201:
        pytest.fail(f"test_request fixture failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]


# ─── reporting hooks ────────────────────────────────────────────────

def pytest_sessionstart(session):
    global _session_started_at
    _session_started_at = datetime.datetime.now(datetime.timezone.utc)
    # Clear the responses dir so stale captures don't accumulate.
    # `missing_ok` because two sessions started against one instance race
    # here: both enumerate the same files and the loser crashes the whole
    # session with FileNotFoundError before a single test runs. The captures
    # are throwaway artefacts, so losing the race is harmless — crashing on
    # it is not.
    if RESPONSES_DIR.exists():
        for p in RESPONSES_DIR.rglob("*.json"):
            p.unlink(missing_ok=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Collect per-test outcome + endpoint metadata into _test_results.

    Uses hookwrapper to read pytest's resolved outcome — that way xfail
    tests are correctly classified as 'xfailed' (not 'failed')."""
    out = yield
    report = out.get_result()
    if report.when != "call":
        return

    # Pull endpoint metadata captured via user_properties
    endpoint_meta = None
    for k, v in item.user_properties:
        if k == "cadra_endpoint":
            endpoint_meta = v
            break

    # Classify outcome using pytest's authoritative report fields
    if getattr(report, "wasxfail", None) is not None:
        outcome = "xfailed" if report.outcome == "skipped" else "xpassed"
    elif report.outcome == "passed":
        outcome = "passed"
    elif report.outcome == "skipped":
        outcome = "skipped"
    else:
        outcome = "failed"

    _test_results.append({
        "nodeid": item.nodeid,
        "outcome": outcome,
        "duration": call.stop - call.start,
        "endpoint": endpoint_meta,
        "error": str(call.excinfo.value)[:300] if call.excinfo else None,
        "xfail_reason": getattr(report, "wasxfail", None) or None,
    })


_OUTCOME_ICON = {
    "passed":  "✅",
    "failed":  "❌",
    "xfailed": "⚠️ ",  # expected failure (known upstream issue)
    "xpassed": "❗",   # unexpectedly passing — investigate
    "skipped": "⏭️ ",
}


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Write the markdown report at session end."""
    if not _test_results:
        return

    total = len(_test_results)
    counts = defaultdict(int)
    for t in _test_results:
        counts[t["outcome"]] += 1
    duration_total = sum(t["duration"] for t in _test_results)

    # Group by resource (first path segment after /api/v1/)
    by_resource = defaultdict(lambda: defaultdict(int))
    for t in _test_results:
        ep = t["endpoint"]
        if ep and ep.get("path"):
            parts = [p for p in ep["path"].split("/") if p]
            res = parts[2] if len(parts) >= 3 else "other"
        else:
            res = "non-endpoint"
        by_resource[res]["total"] += 1
        by_resource[res][t["outcome"]] += 1

    lines = [
        "# Cadra API Test Report",
        "",
        f"**Run:** {_session_started_at.isoformat()}  ",
        f"**Total tests:** {total}  ",
        f"**Passed:** {counts['passed']}  "
        f"**Failed:** {counts['failed']}  "
        f"**xfailed (known upstream issues):** {counts['xfailed']}  "
        f"**xpassed:** {counts['xpassed']}  "
        f"**skipped:** {counts['skipped']}  ",
        f"**Duration:** {duration_total:.2f}s",
        "",
        "## Per-resource summary",
        "",
        "| Resource | Tests | ✅ Passed | ❌ Failed | ⚠️ xfailed |",
        "|---|---:|---:|---:|---:|",
    ]
    for res, c in sorted(by_resource.items()):
        lines.append(
            f"| {res} | {c['total']} | {c['passed']} | {c['failed']} | {c['xfailed']} |"
        )

    lines += [
        "",
        "## Endpoint coverage",
        "",
        "| Method | Path | Status | Test | Response |",
        "|---|---|---:|---|---|",
    ]
    for t in _test_results:
        ep = t.get("endpoint") or {}
        method = ep.get("method", "-")
        path = ep.get("path", "-")
        status = ep.get("status", "-")
        nodeid = t["nodeid"]
        test_label = nodeid.replace("tests/", "")
        icon = _OUTCOME_ICON.get(t["outcome"], "?")
        capture = ep.get("capture")
        cap_link = f"[json]({capture.replace('docs/api/', '')})" if capture else "-"
        lines.append(
            f"| {method} | `{path}` | {icon} {status} | `{test_label}` | {cap_link} |"
        )

    # xfailed (known upstream issues) — surface reasons
    xfailed = [t for t in _test_results if t["outcome"] == "xfailed"]
    if xfailed:
        lines += [
            "",
            "## ⚠️ Known upstream issues (xfailed)",
            "",
            "These tests fail as expected because of bugs in modules other "
            "than `myservice_api`. The API layer routes the call correctly "
            "and returns a PRD-shaped error envelope; the underlying logic "
            "in a delegated controller is broken. See each test's xfail "
            "reason for the upstream fix needed.",
            "",
        ]
        for t in xfailed:
            lines.append(f"### `{t['nodeid']}`")
            lines.append("")
            if t.get("xfail_reason"):
                lines.append(f"> {t['xfail_reason']}")
                lines.append("")
            ep = t.get("endpoint") or {}
            if ep:
                lines.append(f"- **Endpoint:** `{ep.get('method')} {ep.get('path')}`")
                lines.append(f"- **Returned status:** {ep.get('status')}")
                cap = ep.get('capture')
                if cap:
                    lines.append(f"- **Captured response:** [{cap}]({cap.replace('docs/api/', '')})")
                lines.append("")

    # Real failures
    failures = [t for t in _test_results if t["outcome"] == "failed"]
    if failures:
        lines += ["", "## ❌ Failures", ""]
        for t in failures:
            lines.append(f"### `{t['nodeid']}`")
            lines.append("")
            lines.append(f"```\n{t['error']}\n```")
            lines.append("")

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines) + "\n")

    terminalreporter.write_sep("=", "cadra api test report",
                               green=(counts['failed'] == 0))
    terminalreporter.write_line(f"Report: {REPORT_FILE}")
    terminalreporter.write_line(f"Captured responses: {RESPONSES_DIR}/")


# ─── helpers used by tests (importable) ──────────────────────────────

@pytest.fixture(scope="session")
def admin_scope(client):
    """Skip a test when the token has no `admin` scope.

    Configuration endpoints are admin-scoped on purpose — changing a category's
    useful life restates book value across a whole class of assets, and
    branding changes what every user sees. A token without it should produce a
    clear skip, not a wall of 403s that reads as a broken feature.
    """
    r = client.get("/api/v1/auth/whoami")
    if r.status_code != 200:
        pytest.skip("cannot determine token scopes")
    scopes = (r.json().get("data") or {}).get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    if "admin" not in scopes and "*" not in scopes:
        pytest.skip(f"token lacks the `admin` scope (has: {sorted(scopes)})")
    return True


def assert_envelope_ok(response, expected_status=200):
    """Assert response is the PRD success envelope at the given status."""
    assert response.status_code == expected_status, (
        f"expected {expected_status}, got {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    assert "data" in body, f"missing `data` in envelope: {body}"
    assert "meta" in body, f"missing `meta` in envelope: {body}"
    meta = body["meta"]
    assert "request_id" in meta and meta["request_id"], "missing request_id"
    assert "timestamp" in meta, "missing timestamp"
    assert "version" in meta, "missing version"
    return body


def assert_envelope_err(response, expected_status, expected_code=None):
    """Assert response is the PRD error envelope at the given status."""
    assert response.status_code == expected_status, (
        f"expected {expected_status}, got {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    assert "error" in body, f"missing `error` in envelope: {body}"
    err = body["error"]
    assert "code" in err and err["code"], "missing error.code"
    assert "message" in err and err["message"], "missing error.message"
    assert "request_id" in err and err["request_id"], "missing error.request_id"
    if expected_code:
        assert err["code"] == expected_code, (
            f"expected code={expected_code}, got {err['code']}"
        )
    return body
