"""
Force /api/v1/* requests through Odoo's HttpRequest dispatcher.

WHY THIS EXISTS
---------------
Odoo 15's `http.Root.get_request()` selects the request dispatcher based on
the inbound `Content-Type` header:

    application/json or application/json-rpc → JsonRequest (type='json' routes)
    everything else                          → HttpRequest (type='http' routes)

If a route is declared `type='http'` but the client sends Content-Type
`application/json` (which any well-behaved REST client does), Odoo dispatches
via JsonRequest, the type check at `_call_function` fails, and the caller
gets a 400 with:

    "Function declared as capable of handling request of type 'http'
     but called with a request of type 'json'"

The only proper way to escape this is to override the dispatcher selection
for the URL space we control. We do that by wrapping `Root.get_request()`
so it always returns an HttpRequest for paths under `/api/v1/`, regardless
of Content-Type. Inside our handlers we then read the JSON body manually via
`request.httprequest.get_json(silent=True)` (see utils.get_params).

This patch is scoped tightly: it only changes behaviour for our own URL
prefix. All other Odoo behaviour (the backend UI, the website, the existing
type='json' RPC endpoints used by the Odoo JS client) is untouched.

Applied at module import time — must run before any controller class is
defined, which it does via the `from . import http_patch` line at the top
of myservice_api/__init__.py.
"""
import logging

from odoo import http

_logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1/"

# ── Odoo 19 rebuild ────────────────────────────────────────────────────────
# Odoo 17+ rewrote HTTP dispatching: the dispatcher is chosen by the ROUTE's
# declared ``type`` (http vs jsonrpc), NOT by the inbound Content-Type. A
# ``type='http'`` route therefore handles a JSON body natively, so the 15.0
# ``http.Root.get_request`` monkeypatch below is no longer needed — and
# ``http.Root`` no longer exists. Keep this as a guarded no-op for history.
if hasattr(http, "Root") and hasattr(http.Root, "get_request"):
    _ORIGINAL_GET_REQUEST = http.Root.get_request

    def _cadra_get_request(self, httprequest):
        """Force HttpRequest for /api/v1/* paths; delegate everything else."""
        if httprequest.path.startswith(API_PREFIX):
            return http.HttpRequest(httprequest)
        return _ORIGINAL_GET_REQUEST(self, httprequest)

    if http.Root.get_request is not _cadra_get_request:
        http.Root.get_request = _cadra_get_request
        _logger.info("Cadra API: HttpRequest dispatcher forced for %s* paths", API_PREFIX)
else:
    _logger.info("Cadra API: http.Root absent (Odoo 17+); dispatcher patch not needed")
