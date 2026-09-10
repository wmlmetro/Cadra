"""Who made this request, and how much that answer is worth.

**Why this lives in `myservice_nrs_base` and not in the API module.**
It was written in handoff 13 for `POST /auth/token` and sat in
`myservice_api/controllers/utils.py`. Handoff 17 needed exactly the same
answer on two routes outside `/api/v1` — the WorkSpace callback in
`myservice_workflow` and the Redhubs CSV export in `myservice_identity` —
and neither of those modules can import from `myservice_api`, because
`myservice_api` depends on both of them and the import would be a cycle.

The alternative was a second copy of the log-injection guard in each
controller. A security helper with three implementations has three
behaviours the day one of them is edited, and the whole point of
`caller_ip_label` is that a header value never reaches a log line
un-parsed. One implementation, in the module every first-party addon can
reach. `myservice_api.controllers.utils` re-exports these names, so every
existing caller is unchanged.
"""
import ipaddress

from odoo.http import request


def caller_ip():
    """Return (address, source) for whoever made this request.

    Odoo's `proxy_mode` is NOT enough to rely on `remote_addr`: Odoo 19
    applies werkzeug's ProxyFix only when the request also carries
    `X-Forwarded-Host` (`odoo/http.py`, `Application.__call__`). The dev
    stack's nginx sets `X-Forwarded-For` and `X-Forwarded-Proto` but not
    `X-Forwarded-Host`, so ProxyFix never runs there and `remote_addr` is
    the proxy container — which is why `last_used_ip` reads 172.20.0.4 on
    every client row in every local tenant.

    So resolve it the same way in both environments. The RIGHT-MOST entry
    of `X-Forwarded-For` is the one our own nearest proxy appended
    (`$proxy_add_x_forwarded_for` in nginx, the equivalent in
    ingress-nginx); everything to its left is caller-supplied and forgeable.
    That is exactly ProxyFix's `x_for=1` rule, applied whether or not
    ProxyFix ran.

    `source` says how much the value is worth:
      `peer`    — the socket's own peer; no proxy header at all.
      `xff`     — one declared hop, so this is the caller.
      `xff+N`   — N further hops were declared to the left. The value is
                  still the nearest trusted one, but the caller is behind
                  another proxy and this is not it.
    """
    httprequest = getattr(request, "httprequest", None)
    if httprequest is None:
        return None, "none"
    forwarded = (httprequest.headers.get("X-Forwarded-For") or "").strip()
    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if hops:
        return hops[-1], ("xff" if len(hops) == 1 else "xff+%d" % (len(hops) - 1))
    return httprequest.remote_addr, "peer"


def _is_infrastructure(parsed):
    """True when the address is ours, not a caller's.

    Loopback, link-local and RFC1918 all mean the same thing here: the
    value identifies a proxy, an ingress or a sidecar. Saying so is the
    point — a field that always reads the same is worse than no field, and
    "this is the ingress" is the answer somebody needs, not `10.244.1.7`.
    """
    return (parsed.is_private or parsed.is_loopback
            or parsed.is_link_local or parsed.is_reserved)


def caller_ip_label():
    """`ip=... ip_source=...` for one log line.

    When the value comes from a header it is caller-supplied text on an
    unauthenticated request — the same category as the client id, and the
    reason `log_safe` exists. It gets a stricter rule than `log_safe`: an
    IP field may contain an IP or nothing. A header value is only printed
    once `ipaddress` has parsed it, so `X-Forwarded-For: 1.2.3.4
    outcome=ok` cannot append a field to our own log line — spaces are
    legal in a header value and `ip=` is the last thing on the line, which
    is exactly the shape a forger would reach for.
    """
    address, source = caller_ip()
    if not address:
        return "ip=- ip_source=%s" % source
    try:
        parsed = ipaddress.ip_address(str(address).strip())
    except ValueError:
        # Something arrived and it was not an address. Say that; do not
        # repeat it.
        return "ip=? ip_source=%s,unparsable" % source
    if _is_infrastructure(parsed):
        source += ",infra"
    return "ip=%s ip_source=%s" % (parsed.compressed, source)
