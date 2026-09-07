#!/usr/bin/env python3
"""A mock SAP fixed-asset receiver for the Cadra asset legs — INT-06/07/09.

WHY THIS EXISTS
---------------
NRS has not yet given us a SAP endpoint, an asset class list, a cost centre
list or a company code — every one of those is an open item in
`docs/integrations/INT-06-07-09-sap-requirements.md` §8. Waiting for them
would mean writing the outbound queue, the payload builders and the INT-07
response handler with nothing to point them at, and discovering on the day
SAP appears that the retry classifier, the idempotency echo and the
dual-code write-back have never once been exercised end to end.

So the SAP legs are built behind an adapter and this is what sits on the far
side of it in development. It is not a simulation of SAP; it is a receiver
that keeps the contract the requirements document asks SAP to keep, plus a
control surface that lets a test drive the failure modes Cadra classifies —
down, rejected, timed out, below the capitalisation threshold — without
killing the process or editing config between assertions. **The real
connector is a backend swap**: when SAP gives us a URL, the only thing that
changes is `workflow.config.rest_base_url`. Nothing in Cadra knows this
script exists.

Standard library only, deliberately. A mock that needs `pip install` in a
container nobody wants to rebuild is a mock that stops getting run.

WHAT IT IMPLEMENTS
------------------
  POST /fixed-assets          INT-06 asset master create → 201 with the §2.6
                              body, `cadra_asset_code` genuinely echoed.
                              A repeat `X-Idempotency-Key` replays the
                              original body with 409.
  POST /fixed-assets/events   INT-09 lifecycle events → 202. Same idempotency.
  GET  /fixed-assets          INT-07 route 2c reconciliation query, by
                              `cadra_asset_codes=` or `capitalised_from`/`_to`.
  GET  /health                liveness, always answers whatever the mode.
  GET  /__ledger              everything received, for test assertions.
  GET  /__mode                the current failure mode.
  POST /__mode                set it: {"mode": "ok"|"down"|"reject"|"slow"|
                              "not_capitalised"}.

The `__`-prefixed routes are the control surface and are NOT part of the SAP
contract — no SAP will ever expose them. They are prefixed so that nothing in
Cadra can accidentally depend on a route the real system does not have.

RUNNING IT
----------
    python3 docs/api/mock_sap.py                     # 0.0.0.0:8899, mode ok
    python3 docs/api/mock_sap.py --port 9000 --mode down

    curl -s localhost:8899/health
    curl -s -XPOST localhost:8899/__mode -d '{"mode":"down"}'
    curl -s localhost:8899/__ledger | python3 -m json.tool

REACHING IT FROM THE ODOO CONTAINER
-----------------------------------
Odoo runs in Docker; this script runs on the host. **The container reaches
the host as `host.docker.internal`** (Docker Desktop provides it on macOS and
Windows; on Linux add `extra_hosts: ["host.docker.internal:host-gateway"]` to
the odoo service). `localhost` inside the container is the container, so a
base URL of `http://localhost:8899` fails with a connection error that looks
exactly like SAP being down — which is the one failure this mock exists to
let you tell apart from a real one.

Point the tenant's SAP config at it:

    workflow.config  (purpose = 'sap_assets')
      adapter_type        = 'rest'
      rest_base_url       = 'http://host.docker.internal:8899'
      rest_endpoint_event = '/fixed-assets'
      rest_auth_type      = 'none'
      sap_company_code    = 'NRS1'

Bind on 0.0.0.0 (the default) and not 127.0.0.1, or the container's packets
arrive at an address nothing is listening on.

Cadra currently holds ONE endpoint per config row, so INT-06 and INT-09 both
arrive at `rest_endpoint_event`. `POST /fixed-assets` therefore reads the
`event` discriminator and hands a lifecycle event to the INT-09 handler
rather than trying to capitalise it — the requirements document asks SAP for
two endpoints (§2.1, §4.1) and this keeps working whichever way Cadra ends up
addressing them.

STATE
-----
Everything is in memory and dies with the process. That is the point: a test
run starts from a known-empty register, and there is no file to clean up
between runs. Restarting resets the SAP asset number sequence too.
"""
import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

# ─── Contract constants ──────────────────────────────────────────────

#: Sequential, zero-padded to 12 digits — the shape SAP asset numbers take,
#: and the shape the worked example in §2.6 uses. Starts where that example
#: leaves off so a payload copied out of the document is recognisable in the
#: ledger.
FIRST_SAP_ASSET_NUMBER = 12345

#: High-water mark for issued asset numbers, kept beside this script so a
#: restart cannot re-issue a number a previous run already handed out.
SEQUENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "mock_sap_sequence")

DEFAULT_COMPANY_CODE = "NRS1"

# Cadra sends `sap_asset_class` and `sap_cost_center` as NULL today, on
# purpose: the mapping is blocked on NRS (§5.1, §5.2) and Cadra will not
# guess a class. A strict SAP would reject those outright — and a mock that
# did the same would dead-letter every single message, leaving the whole
# chain behind an answer we are still waiting for. So the mock posts a
# default and RETURNS IT, which is exactly what §2.6 asks for ("asset_class
# as posted... if it differs from what we sent, our mapping is wrong and we
# want to know"). Use `--mode reject` to exercise the rejection path.
DEFAULT_ASSET_CLASS = "3100"
DEFAULT_COST_CENTER = "CC-ICT-001"

# Valuation is SAP's, not Cadra's — §2.4 is explicit that Cadra sends no
# useful life and no depreciation key precisely so two systems do not compute
# the same number. The mock returns fixed ones rather than modelling an asset
# class table; what is under test is that Cadra STORES what it is given and
# never calculates its own.
DEFAULT_USEFUL_LIFE_MONTHS = 48
DEFAULT_DEPRECIATION_KEY = "LINR"

LIFECYCLE_EVENTS = (
    "asset.transferred",
    "asset.custodian_changed",
    "asset.disposed",
)
EVENT_ASSET_MASTER_CREATE = "asset.master.create"

MODES = ("ok", "down", "reject", "slow", "not_capitalised")

#: Longer than Cadra's default `rest_timeout` of 30s, so `slow` actually
#: trips the read timeout rather than merely being irritating. The connect
#: timeout is separate and short (10s), which is why the socket must ACCEPT
#: promptly and stall on the response — sleeping in the handler does exactly
#: that, whereas refusing to listen would be a connection error instead.
SLOW_SECONDS = 40


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Server state ────────────────────────────────────────────────────

class State(object):
    """Everything the mock remembers, behind one lock.

    ThreadingHTTPServer serves each request on its own thread, and `slow`
    mode deliberately parks one of them for 40 seconds while other requests
    keep arriving — so the ledger, the sequence and the idempotency store are
    genuinely concurrent and not theoretically so.
    """

    def __init__(self, mode="ok"):
        self.lock = threading.Lock()
        self.mode = mode
        self.started_at = _now_iso()
        self.seq = 0
        self._next_number = FIRST_SAP_ASSET_NUMBER
        # cadra_asset_code → the §2.6 asset object. This IS the mock's fixed
        # asset register; the reconciliation query reads it back.
        self.fixed_assets = {}
        # idempotency key → {"status", "body", "path"}. Replayed verbatim.
        self.idempotency = {}
        self.events = []
        self.requests = []

    def next_sap_asset_number(self):
        """Issue the next number, and never issue one twice across restarts.

        The in-memory counter alone was not enough, and the way that showed
        is worth keeping: this mock was restarted mid-test, resumed at
        `000000012345`, and handed Cadra an asset number it had already given
        to a different asset. Cadra took it — which found a genuine missing
        constraint on the register, but only by accident, and next time the
        accident would be somebody debugging a duplicate for an hour.

        A real SAP does not forget what it has issued. The high-water mark is
        kept in a file beside this script so the mock does not either. Delete
        `mock_sap_sequence` to reset the register.
        """
        number = max(self._next_number, self._load_high_water() + 1)
        self._next_number = number + 1
        self._save_high_water(number)
        return "%012d" % number

    def _load_high_water(self):
        try:
            with open(SEQUENCE_FILE) as fh:
                return int(fh.read().strip() or 0)
        except (OSError, ValueError):
            return FIRST_SAP_ASSET_NUMBER - 1

    def _save_high_water(self, number):
        try:
            with open(SEQUENCE_FILE, "w") as fh:
                fh.write(str(number))
        except OSError:
            # A mock that cannot write its counter is still a usable mock;
            # it just loses the cross-restart guarantee. Say so once rather
            # than failing the request the tester is actually running.
            print("WARNING: could not persist the SAP number sequence to %s"
                  % SEQUENCE_FILE, file=sys.stderr, flush=True)


STATE = State()


# ─── Request handler ─────────────────────────────────────────────────

class MockSAPHandler(BaseHTTPRequestHandler):

    # Keep-alive with an accurate Content-Length on every response. `requests`
    # (which is what Cadra's adapter uses) pools connections, and a handler
    # that closes after every reply makes the retry timings in a test read as
    # network noise.
    protocol_version = "HTTP/1.1"
    server_version = "MockSAP/1.0"

    # ── plumbing ─────────────────────────────────────────────────────

    def log_message(self, fmt, *args):
        """Silence BaseHTTPRequestHandler's own stderr line.

        We log one line per request ourselves, after the status is known and
        with the idempotency key on it — which is the field you actually need
        when working out why a retry did or did not create a second asset.
        """
        return

    def _log(self, status, note=""):
        key = self.headers.get("X-Idempotency-Key") or "-"
        print("%s  %-6s %-34s idem=%-34s → %s%s"
              % (_now_iso(), self.command, self.path, key, status,
                 ("  " + note) if note else ""),
              flush=True)

    def _split(self):
        parts = urlsplit(self.path)
        return parts.path.rstrip("/") or "/", parse_qs(parts.query)

    def _read_json(self):
        """Returns (parsed, error_message). An empty body parses as {}."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "Content-Length is not a number"
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw.strip():
            return {}, None
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError) as exc:
            return None, str(exc)

    def _respond(self, status, payload, note=""):
        """Write a response. `payload` is JSON unless it is already a str."""
        if isinstance(payload, str):
            body = payload.encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        else:
            body = json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")
            content_type = "application/json"
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The DESIGNED outcome of `slow` mode: Cadra's read timeout fired
            # and it hung up before the answer arrived. Still log the status
            # the mock would have returned — that the receiver eventually
            # answered 201 to a call the sender had already abandoned is
            # exactly the fact a retry test needs to be able to see.
            note = (note + " " if note else "") + "(client hung up)"
        self._log(status, note)

    def _record(self, status, body, note=""):
        """Append one line to the received-requests ledger."""
        asset = (body or {}).get("asset") or {}
        with STATE.lock:
            STATE.seq += 1
            STATE.requests.append({
                "seq": STATE.seq,
                "at": _now_iso(),
                "method": self.command,
                "path": self.path,
                "mode": STATE.mode,
                "idempotency_key": self.headers.get("X-Idempotency-Key"),
                "event_id": self.headers.get("X-Event-Id")
                            or (body or {}).get("event_id"),
                "request_id": self.headers.get("X-Request-Id"),
                "event": (body or {}).get("event"),
                "cadra_asset_code": asset.get("cadra_asset_code"),
                "status": status,
                "note": note or None,
                "body": body,
            })

    # ── failure injection ────────────────────────────────────────────

    def _mode_gate(self):
        """Apply the current mode to a business route.

        Returns True when it has already answered on the caller's behalf.

        The gate runs BEFORE the idempotency replay on purpose: a test needs
        to be able to knock the receiver over *between* two deliveries of the
        same event_id, which is precisely the sequence the retry queue exists
        to survive.
        """
        with STATE.lock:
            mode = STATE.mode

        if mode == "down":
            # 503. Cadra records this as failed-and-retryable and backs off.
            # A short text body, not JSON, because a load balancer standing in
            # front of a dead app server is what this imitates and those do
            # not return your API's error shape.
            self._record(503, None, note="mode=down")
            self._respond(503, "SAP is unavailable\n", note="mode=down")
            return True

        if mode == "reject":
            # 422 → dead-lettered on the FIRST attempt, no retries (§6). The
            # body names the field, because §2.7 asks SAP for exactly that and
            # a mock that returns a bare status teaches nobody anything.
            body = {
                "error": "asset_class is not valid for company code %s"
                         % DEFAULT_COMPANY_CODE,
                "field": "asset.asset_class.sap_asset_class",
                "message": "Supply a mapped SAP asset class; see §5.1.",
            }
            self._record(422, None, note="mode=reject")
            self._respond(422, body, note="mode=reject")
            return True

        if mode == "slow":
            # Stall past the read timeout and then answer normally. The point
            # is not the eventual answer but that Cadra gave up first and
            # retried — which is only safe because the event carries an
            # idempotency key, and this is where that gets proven.
            time.sleep(SLOW_SECONDS)

        return False

    # ── INT-06 ───────────────────────────────────────────────────────

    def _create_fixed_asset(self, body):
        """Mint a SAP asset number and build the §2.6 success body."""
        asset = body.get("asset") or {}
        cap = asset.get("capitalisation") or {}
        location = asset.get("location") or {}
        asset_class = asset.get("asset_class") or {}

        amount = cap.get("amount")
        if not isinstance(amount, (int, float)):
            amount = 0.0
        amount = round(float(amount), 2)

        with STATE.lock:
            sap_number = STATE.next_sap_asset_number()

        return {
            "status": "created",
            # ECHOED, never regenerated. §2.6: a response carrying only SAP's
            # number forces Cadra to correlate on request ordering, and Cadra
            # refuses a mismatched echo outright — `_apply_sap_master_response`
            # will not write a SAP number onto an asset SAP answered about by
            # a different code. Getting this wrong here would silently make
            # every reconciliation test pass for the wrong reason.
            "cadra_asset_code": asset.get("cadra_asset_code"),
            "sap_asset_number": sap_number,
            # "0000" = no sub-numbering. §8 Q12 is still open; until NRS
            # answers, everything is a main number.
            "sap_asset_subnumber": "0000",
            "company_code": body.get("company_code") or DEFAULT_COMPANY_CODE,
            "asset_class": asset_class.get("sap_asset_class")
                           or DEFAULT_ASSET_CLASS,
            # AS POSTED, derived from the proposal Cadra sent (§2.5). A real
            # SAP overrides this where period-close rules require; the mock
            # accepts the proposal, which is the honest default — inventing a
            # divergence would make every test assert against a fiction.
            "capitalisation_date": cap.get("proposed_capitalisation_date"),
            "capitalised_amount": amount,
            "currency": cap.get("currency") or "NGN",
            "acquisition_value": amount,
            # A freshly capitalised asset has run no depreciation, so NBV is
            # the acquisition value. Cadra's ERP-managed depreciation mode
            # displays these and computes nothing.
            "accumulated_depreciation": 0.00,
            "net_book_value": amount,
            "useful_life_months": DEFAULT_USEFUL_LIFE_MONTHS,
            "depreciation_key": DEFAULT_DEPRECIATION_KEY,
            "cost_center": location.get("sap_cost_center") or DEFAULT_COST_CENTER,
        }

    def _post_fixed_assets(self):
        if self._mode_gate():
            return

        body, parse_error = self._read_json()
        if parse_error is not None:
            self._record(400, None, note="unparseable body")
            return self._respond(400, {
                "error": "request body is not valid JSON",
                "field": "body",
                "detail": parse_error,
            })

        # One configurable endpoint on the Cadra side today, so a lifecycle
        # event can legitimately arrive here. Route on the discriminator
        # rather than 422-ing something that is a perfectly valid INT-09
        # message that happened to use the other URL.
        if body.get("event") in LIFECYCLE_EVENTS:
            return self._handle_event(body)

        with STATE.lock:
            mode = STATE.mode
        if mode == "not_capitalised":
            # §5.5. The distinguishable answer we asked SAP for: a 200 that
            # says "correctly not capitalised" rather than a silence Cadra
            # would have to read as "missing its SAP code". Those are different
            # facts and an auditor has to be able to tell them apart — Cadra
            # records this on the asset instead of writing a code.
            payload = {
                "status": "not_capitalised",
                "reason": "below_threshold",
                "cadra_asset_code": (body.get("asset") or {}).get(
                    "cadra_asset_code"),
            }
            self._record(200, body, note="mode=not_capitalised")
            return self._respond(200, payload, note="mode=not_capitalised")

        asset = body.get("asset") or {}
        code = asset.get("cadra_asset_code")
        if not code:
            self._record(422, body, note="no cadra_asset_code")
            return self._respond(422, {
                "error": "cadra_asset_code is required",
                "field": "asset.cadra_asset_code",
                "message": "The dual-code control is built on it; an asset "
                           "master without it cannot be reconciled.",
            })

        key = self.headers.get("X-Idempotency-Key")
        replay = self._replay(key)
        if replay is not None:
            return replay

        with STATE.lock:
            existing = STATE.fixed_assets.get(code)
        if existing is not None:
            # Deduped on the asset code as well as on the key. The key
            # protects a retry of one delivery; the code protects against a
            # second delivery of the same asset under a NEW event_id — a Cadra
            # restore from backup, or a manual re-queue. §2.4 makes
            # `cadra_asset_code` unique and NOT NULL, so SAP is entitled to
            # rely on it, and "capitalises the same laptop twice" is the exact
            # failure §6 names.
            self._record(409, body, note="duplicate cadra_asset_code")
            return self._respond(409, existing, note="duplicate asset code")

        result = self._create_fixed_asset(body)
        with STATE.lock:
            STATE.fixed_assets[code] = result
            if key:
                STATE.idempotency[key] = {
                    "status": 201, "body": result, "path": "/fixed-assets"}
        self._record(201, body)
        self._respond(201, result)

    # ── INT-09 ───────────────────────────────────────────────────────

    def _post_event(self):
        if self._mode_gate():
            return
        body, parse_error = self._read_json()
        if parse_error is not None:
            self._record(400, None, note="unparseable body")
            return self._respond(400, {
                "error": "request body is not valid JSON",
                "field": "body",
                "detail": parse_error,
            })
        return self._handle_event(body)

    def _handle_event(self, body):
        event = body.get("event")
        if event not in LIFECYCLE_EVENTS:
            # Including `asset.master.create` arriving on the events URL:
            # capitalising from the lifecycle endpoint would let a
            # misconfigured endpoint field create asset masters that no
            # reconciliation is expecting.
            self._record(422, body, note="unknown event")
            hint = ("%s belongs on POST /fixed-assets."
                    % EVENT_ASSET_MASTER_CREATE
                    if event == EVENT_ASSET_MASTER_CREATE else
                    "Expected one of: %s." % ", ".join(LIFECYCLE_EVENTS))
            return self._respond(422, {
                "error": "unsupported event %r on /fixed-assets/events" % event,
                "field": "event",
                "message": hint,
            })

        key = self.headers.get("X-Idempotency-Key")
        replay = self._replay(key)
        if replay is not None:
            return replay

        event_id = body.get("event_id") or key
        asset = body.get("asset") or {}
        with STATE.lock:
            reference = "SAP-EVT-%04d" % (len(STATE.events) + 1)
            STATE.events.append({
                "reference": reference,
                "event_id": event_id,
                "event": event,
                "received_at": _now_iso(),
                "cadra_asset_code": asset.get("cadra_asset_code"),
                "sap_asset_number": asset.get("sap_asset_number"),
                "change": body.get("change"),
            })
        # 202, not 201: a lifecycle change is applied to an existing asset
        # master, and §6 already treats a 2xx carrying an identifier as
        # acknowledged — so Cadra stores `reference` and stops.
        result = {"status": "accepted", "event_id": event_id,
                  "reference": reference}
        if key:
            with STATE.lock:
                STATE.idempotency[key] = {
                    "status": 202, "body": result,
                    "path": "/fixed-assets/events"}
        self._record(202, body)
        self._respond(202, result)

    # ── idempotency ──────────────────────────────────────────────────

    def _replay(self, key):
        """Answer a repeated `X-Idempotency-Key` with the ORIGINAL result.

        409, because §6 tells SAP that Cadra reads a 409 as *acknowledged —
        a duplicate is a successful dedupe, not a failure*. Returning the
        original body with it means a retry that crossed with a slow success
        still lands the SAP asset number on the register instead of leaving
        the asset permanently awaiting a code.

        Keyed on the header alone rather than on (key, path): the key equals
        `event_id`, which is unique across every event Cadra raises, so the
        same key arriving on two different routes is a fault worth surfacing
        as a duplicate rather than quietly processing twice.

        Returns a truthy sentinel when it answered, None when it did not.
        """
        if not key:
            return None
        with STATE.lock:
            stored = STATE.idempotency.get(key)
        if stored is None:
            return None
        self._record(409, None, note="idempotent replay of %s" % stored["path"])
        self._respond(409, stored["body"], note="idempotent replay")
        return True

    # ── INT-07 route 2c ──────────────────────────────────────────────

    def _get_fixed_assets(self, query):
        if self._mode_gate():
            return

        def first(name):
            values = query.get(name) or []
            return values[0].strip() if values and values[0].strip() else None

        def as_int(name, default):
            raw = first(name)
            if raw is None:
                return default
            try:
                value = int(raw)
            except ValueError:
                return default
            return value if value > 0 else default

        codes_raw = first("cadra_asset_codes")
        codes = None
        if codes_raw:
            codes = set(c.strip() for c in codes_raw.split(",") if c.strip())
        company_code = first("company_code")
        cap_from = first("capitalised_from")
        cap_to = first("capitalised_to")
        page = as_int("page", 1)
        page_size = as_int("page_size", 100)

        with STATE.lock:
            rows = list(STATE.fixed_assets.values())

        matched = []
        for row in rows:
            if codes is not None and row.get("cadra_asset_code") not in codes:
                continue
            if company_code and row.get("company_code") != company_code:
                continue
            posted = row.get("capitalisation_date") or ""
            # ISO `YYYY-MM-DD` sorts lexicographically, so no date parsing and
            # no timezone to get wrong. An asset with no posted date is
            # excluded from a windowed query rather than defaulted into it:
            # §3.3 point 3 uses this sweep to find money on the books with no
            # physical thing behind it, and a null date in that answer is
            # noise pretending to be a finding.
            if cap_from and (not posted or posted < cap_from):
                continue
            if cap_to and (not posted or posted > cap_to):
                continue
            matched.append(row)

        start = (page - 1) * page_size
        window = matched[start:start + page_size]
        self._record(200, None, note="recon %d/%d" % (len(window), len(matched)))
        # §3.3 point 4 accepts either a cursor or a total. This answers with a
        # total and says so by pinning `next_cursor` to null, so a client that
        # reads the wrong one gets None rather than a plausible-looking cursor
        # that never advances.
        self._respond(200, {
            "page": page,
            "page_size": page_size,
            "total": len(matched),
            "next_cursor": None,
            "fixed_assets": window,
        })

    # ── control surface ──────────────────────────────────────────────

    def _get_mode(self):
        with STATE.lock:
            mode = STATE.mode
        self._respond(200, {"mode": mode, "modes": list(MODES)})

    def _set_mode(self):
        body, parse_error = self._read_json()
        if parse_error is not None:
            return self._respond(400, {"error": "body is not valid JSON",
                                       "detail": parse_error})
        mode = (body or {}).get("mode")
        if mode not in MODES:
            return self._respond(400, {
                "error": "unknown mode %r" % mode,
                "field": "mode",
                "modes": list(MODES),
            })
        with STATE.lock:
            previous, STATE.mode = STATE.mode, mode
        self._respond(200, {"mode": mode, "previous": previous})

    def _get_ledger(self):
        with STATE.lock:
            payload = {
                "mode": STATE.mode,
                "started_at": STATE.started_at,
                "counts": {
                    "requests": len(STATE.requests),
                    "fixed_assets": len(STATE.fixed_assets),
                    "events": len(STATE.events),
                    "idempotency_keys": len(STATE.idempotency),
                },
                "fixed_assets": list(STATE.fixed_assets.values()),
                "events": list(STATE.events),
                "idempotency_keys": sorted(STATE.idempotency),
                "requests": list(STATE.requests),
            }
        self._respond(200, payload)

    # ── dispatch ─────────────────────────────────────────────────────

    def do_GET(self):
        path, query = self._split()
        if path == "/health":
            # Deliberately outside `_mode_gate`: a health check that goes down
            # with the injected failure gives a test no way to tell "the mock
            # is in `down` mode" from "the mock is not running", and those need
            # different fixes.
            with STATE.lock:
                mode = STATE.mode
            return self._respond(200, {"status": "ok", "mode": mode})
        if path == "/__mode":
            return self._get_mode()
        if path == "/__ledger":
            return self._get_ledger()
        if path == "/fixed-assets":
            return self._get_fixed_assets(query)
        self._respond(404, {"error": "no such route: %s" % path})

    def do_POST(self):
        path, _query = self._split()
        if path == "/__mode":
            return self._set_mode()
        if path == "/fixed-assets":
            return self._post_fixed_assets()
        if path == "/fixed-assets/events":
            return self._post_event()
        self._respond(404, {"error": "no such route: %s" % path})


class MockSAPServer(ThreadingHTTPServer):
    """A threading server that does not turn `slow` mode into a traceback.

    A client that gave up waiting is the DESIGNED outcome of `slow` mode, and
    socketserver's default `handle_error` answers it with a full traceback on
    stderr — for the one test whose entire point is that the sender timed out
    and retried. A reader who sees that reasonably concludes the mock broke.
    One line instead, and every other exception still gets its traceback,
    because a real fault in here must not be swallowed to keep the log tidy.
    """

    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            print("%s  --     client went away before the response landed (%s)"
                  % (_now_iso(), type(exc).__name__), flush=True)
            return
        ThreadingHTTPServer.handle_error(self, request, client_address)


# ─── main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Mock SAP fixed-asset receiver for Cadra INT-06/07/09.")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Bind address. Leave as 0.0.0.0 for the Odoo container to reach "
             "it as host.docker.internal; 127.0.0.1 is host-only.")
    parser.add_argument("--mode", choices=MODES, default="ok",
                        help="Initial failure mode.")
    args = parser.parse_args()

    STATE.mode = args.mode

    # `daemon_threads` on the class: otherwise a request parked in `slow`
    # mode keeps the process alive for 40 seconds after Ctrl-C, which reads
    # as a hang.
    server = MockSAPServer((args.host, args.port), MockSAPHandler)

    print("mock SAP listening on http://%s:%d  (mode=%s)"
          % (args.host, args.port, args.mode), flush=True)
    print("  from the Odoo container: http://host.docker.internal:%d"
          % args.port, flush=True)
    print("  routes: POST /fixed-assets · POST /fixed-assets/events · "
          "GET /fixed-assets · GET /health · GET /__ledger · "
          "GET|POST /__mode", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
