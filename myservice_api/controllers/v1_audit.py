"""The last two of specification §13.4's five standard audit reports.

    Asset register snapshot at a historical date   handoff 16
    Custodianship chain for any asset              handoff 14
    Disposal report with documentation refs        handoff 16
    Access changes for any user, per period        HERE
    Configuration change log                       HERE

Both are in their own controller rather than bolted onto `v1_assets.py`, and
that is a statement about what they are: these two do not report the
register. One reports who holds access to the system, the other reports how
the system is configured. The scope ruling in `v1_assets.py` — *the same data
takes the same scope, whatever the route is called* — is what puts them here
and what gives them `access:read` and `settings:read` instead of
`assets:read`. (The access report took `identity:read` until handoff 47,
which split that name: the employee picker a custodian needs and the record
of who granted whom which role are different questions, and under one scope
every Asset User could read this report while the Auditor could not find
it. BREAKING for any credential that held `identity:read` to read it.)

**Both publish their boundary on their own face, and the boundary is
MEASURED at request time.** The access report's honest answer today is that
Cadra holds no record of group grants at all, and it establishes that by
reading the schema of the membership table and the tracking counts on every
request rather than by carrying a constant that would go stale the day
somebody fixed it. See the two model docstrings; the reasoning is there
because that is where the queries are.

Neither writes. Proved by fingerprint, not by inspection —
`myservice_api/tests/test_audit_access_report.py` and
`test_audit_configuration_report.py`.
"""
import logging
from datetime import datetime, timedelta

import pytz

from odoo import http
from odoo.http import request

from ..models.audit_access import record_order

from .query_params import BadFilter, parse_enum
from .utils import (
    ERR_INVALID_REQUEST,
    SCOPE_ACCESS_READ,
    SCOPE_SETTINGS_READ,
    decode_cursor,
    encode_cursor,
    err,
    flag_truncation,
    get_params,
    ok,
    parse_limit,
    record_cap,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
# Imported rather than re-implemented, underscore and all. `from` and `to`
# must mean here exactly what they mean on the disposal report — including
# that an ABSENT required parameter is a 400 of its own rather than a silent
# default — and two copies of a date parser is how two endpoints start
# disagreeing about what a quarter is.
from .v1_assets import _parse_report_date

_logger = logging.getLogger(__name__)


_PERIOD_QUERY_PARAMS = (
    {"name": "from", "required": True,
     "schema": {"type": "string", "format": "date"},
     "description": "REQUIRED. First day of the period, INCLUSIVE "
                    "(YYYY-MM-DD). A LAGOS day: it opens at Lagos midnight, "
                    "23:00 UTC the day before. Both reports that take this "
                    "period bound Lagos days — configuration since handoff "
                    "63b, access since 65 — as every other date the register "
                    "publishes is."},
    {"name": "to", "required": True,
     "schema": {"type": "string", "format": "date"},
     "description": ("REQUIRED. Last day of the period, INCLUSIVE — the "
                     "whole of that day. An auditor asks for a quarter by "
                     "naming its first and last day, and an exclusive upper "
                     "bound would silently lose everything that happened on "
                     "31 March. A LAGOS day, to its last microsecond "
                     "(22:59:59.999999 UTC).")},
)


#: `limit` and `cursor` for the access report, spelled out rather than taken
#: from `PAGINATION_QUERY_PARAMS`. The names and the parsing are identical —
#: `parse_limit` and `decode_cursor`, same clamping, same 400 on a cursor we
#: did not issue — but the UNIT is not a row, it is an ACCOUNT, and the
#: shared description says "page size" without saying of what.
#:
#: That distinction is the whole reason this list exists: `?limit=1` returns
#: one account and BOTH of that account's events, which reads as the
#: parameter being ignored unless the contract says what a page is made of.
#: A published parameter whose behaviour surprises its reader is the same
#: defect as one that does nothing.
_ACCOUNT_PAGE_QUERY_PARAMS = (
    {"name": "limit", "schema": {"type": "integer", "default": 50,
                                 "minimum": 1},
     "description": (
         "Page size in ACCOUNTS, default 50 — not in events. One page is a "
         "window of accounts; `roster` is that window and `events` is every "
         "event belonging to it, so a page of one account may carry two "
         "events. `pagination.total_estimate` counts accounts for the same "
         "reason. Silently clamped to the ceiling for your credential.")},
    {"name": "cursor", "schema": {"type": "string"},
     "description": (
         "Opaque cursor from a previous response's `pagination.next_cursor`, "
         "walking ascending account id. A cursor this API did not issue is a "
         "400 rather than a silent restart at page one. A null "
         "`next_cursor` means either the end or that your credential's "
         "record cap is exhausted — `_warnings.truncated` tells them "
         "apart.")},
)


def _page(rows, key, qs, total):
    """Cap, then cursor, then limit — the disposal report's order exactly.

    The cap is applied FIRST and to the whole period, so the window a capped
    credential sees is stable across pages rather than shifting as it walks.
    `flag_truncation` is what makes `ok()` say so; a shortened schedule that
    does not announce itself is the defect the record cap exists to avoid
    creating.

    `key` reads the ascending integer every row is ordered by. Cursor
    pagination walks ascending ids, so these reports order by id and not by
    timestamp — the same trade `/reports/disposals` makes, and for the same
    reason. Every row carries its own `at`/`last_written_at`, so a caller
    that has walked the whole period can order it however it likes.
    """
    cap = record_cap()
    if cap is not None:
        rows = rows[:cap]
        flag_truncation(cap, total)

    cursor_data = decode_cursor(qs.get("cursor"))
    if "last_id" in cursor_data:
        # No coercion and no fallback: `decode_cursor` has already proved
        # `last_id` is an int or refused the request with a 400 (handoff 22).
        rows = [r for r in rows if key(r) > cursor_data["last_id"]]

    limit = parse_limit(qs)
    page = rows[:limit]
    next_cursor = None
    if page and len(rows) > limit:
        next_cursor = encode_cursor({"last_id": key(page[-1])})
    return page, {"next_cursor": next_cursor, "previous_cursor": None,
                  "total_estimate": total}


def _period(qs):
    """Both bounds, or one 400 that names the parameter that was wrong."""
    date_from, error = _parse_report_date(qs, "from", required=True)
    if error:
        return None, None, error
    date_to, error = _parse_report_date(qs, "to", required=True)
    if error:
        return None, None, error
    if date_from > date_to:
        # `invalid_request`, not `validation_failed`: an integration
        # branching on `error.code` must be told its REQUEST was wrong
        # rather than that a record failed validation.
        return None, None, err(
            ERR_INVALID_REQUEST,
            "The period ends before it starts: `from` must be on or before "
            "`to`",
            details={"from": qs.get("from"), "to": qs.get("to")})
    return date_from, date_to, None


# ── Administrator overrides (handoff 70 §5) ─────────────────────────

_OVERRIDE_KINDS = ("gate", "audit")
_LAGOS = pytz.timezone("Africa/Lagos")

#: The audit rules an override lifts, in words. `%s` is the campaign.
_AUDIT_RULE_WORDS = {
    "not_a_capturer": "they were not named a capturer on campaign %s",
    "own_capture": "they captured the item themselves",
    "not_a_reviewer": "they were not named a reviewer on campaign %s",
}

#: An act, in words, by its gate action or its audit act.
_ACT_WORDS = {
    "submit": "submit", "verify": "verify", "query": "query",
    "approve": "approve", "reject": "reject",
    "request-tagging": "request tagging", "affix": "affix",
    "register": "register", "approve-registration": "approve registration",
    "return-registration": "return registration", "resubmit": "resubmit",
    "issue-tag": "issue tag", "skip-tagging": "skip tagging",
    "capture": "capture", "accept": "accept capture",
    "return_capture": "return capture",
}

#: A SAP link's act shares its verb with a gate's; the words tell them apart.
_SAP_LINK_ACT_WORDS = {
    "propose": "propose SAP link", "approve": "approve SAP link",
    "return": "return SAP link",
    "propose_undo": "propose undoing SAP link",
    "approve_undo": "approve undoing SAP link",
    "return_undo": "return undoing SAP link",
}

_OVERRIDE_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "at": {"type": "string", "format": "date-time",
               "description": "Lagos time, with its offset."},
        "kind": {"type": "string", "enum": list(_OVERRIDE_KINDS)},
        "act": {"type": "string"},
        "act_words": {"type": "string"},
        "by": {"type": "object", "nullable": True,
               "properties": {"id": {"type": "integer"},
                              "name": {"type": "string"}}},
        "asset": {"type": "object", "nullable": True,
                  "properties": {"id": {"type": "integer"},
                                 "asset_code": {"type": "string"}}},
        "capture": {"type": "object", "nullable": True,
                    "properties": {
                        "id": {"type": "integer"},
                        "capture_id": {"type": "string"},
                        "campaign": {"type": "object"},
                        "room": {"type": "object"}}},
        "rules": {"type": "array", "items": {"type": "string"},
                  "description": "An audit act's lifted rules: "
                                 "`not_a_capturer`, `own_capture`, "
                                 "`not_a_reviewer`. Empty for a gate."},
        "override_of": {"type": "string",
                        "description": "What the rule would have said, in "
                                       "words."},
    },
}


def _lagos_midnight(day):
    """The UTC instant (naive, as Odoo stores it) a Lagos day opens."""
    start = _LAGOS.localize(datetime.combine(day, datetime.min.time()))
    return start.astimezone(pytz.utc).replace(tzinfo=None)


def _lagos_iso(moment):
    return pytz.utc.localize(moment).astimezone(_LAGOS).isoformat()


def _in_period(domain, field, lo, hi):
    if lo:
        domain.append((field, ">=", lo))
    if hi:
        domain.append((field, "<", hi))
    return domain


def _by(user, name=None):
    if user:
        return {"id": user.id, "name": user.name}
    return {"id": None, "name": name} if name else None


def _gate_override_rows(env, lo, hi):
    Event = env["nrs.asset.event"].sudo().with_context(active_test=False)
    events = Event.search(_in_period(
        [("admin_override", "=", True)], "occurred_at", lo, hi))
    rows = []
    for ev in events:
        sentence = ev.override_of or ""
        if sentence.startswith("You "):
            sentence = "They " + sentence[4:]
        asset = ev.asset_id
        rows.append({
            "_at": ev.occurred_at.isoformat(), "_key": "e%012d" % ev.id,
            "at": _lagos_iso(ev.occurred_at), "kind": "gate",
            "act": ev.gate_action or "",
            "act_words": (_SAP_LINK_ACT_WORDS if ev.event_type == "sap_link"
                          else _ACT_WORDS).get(ev.gate_action,
                                               ev.gate_action or ""),
            "by": _by(ev.actor_id, ev.actor_name),
            "asset": ({"id": asset.id, "asset_code": asset.asset_code}
                      if asset else None),
            "capture": None, "rules": [], "override_of": sentence,
        })
    return rows


def _audit_override_rows(env, lo, hi):
    Capture = env["nrs.audit.capture"].sudo()
    rows = []
    for flag, at_field, codes_field, actor in (
            ("captured_as_admin", "received_at", "capture_override_of",
             "operator_id"),
            ("reviewed_as_admin", "reviewed_at", "review_override_of",
             "reviewed_by_id")):
        for cap in Capture.search(_in_period(
                [(flag, "=", True)], at_field, lo, hi)):
            at = cap[at_field]
            codes = [c for c in (cap[codes_field] or "").split(",") if c]
            if flag == "captured_as_admin":
                act = "capture"
            else:
                act = "accept" if cap.state != "returned" else "return_capture"
            words = []
            for c in codes:
                text = _AUDIT_RULE_WORDS.get(c, c)
                words.append(text % cap.campaign_id.name if "%s" in text
                             else text)
            said = "; ".join(words)
            rows.append({
                "_at": at.isoformat(),
                "_key": "%s%012d" % ("c" if act == "capture" else "r", cap.id),
                "at": _lagos_iso(at), "kind": "audit", "act": act,
                "act_words": _ACT_WORDS[act],
                "by": _by(cap[actor]),
                "asset": None,
                "capture": {
                    "id": cap.id, "capture_id": cap.capture_uuid,
                    "campaign": {"id": cap.campaign_id.id,
                                 "name": cap.campaign_id.name},
                    "room": {"id": cap.location_id.id,
                             "name": cap.location_id.display_name}},
                "rules": codes,
                "override_of": (said[:1].upper() + said[1:] + ".")
                if said else "",
            })
    return rows


class CadraAuditReportsV1(http.Controller):

    # ── Access changes: GET /api/v1/reports/access-changes ─────────

    @cadra_route("/api/v1/reports/access-changes", method="GET",
                 summary="Access events in a period — role grants and "
                         "removals, and accounts deactivated or reactivated "
                         "— and how much of the period the record covers",
                 scopes=[SCOPE_ACCESS_READ],
                 response_schema={
                     "$ref": "#/components/schemas/AccessChangeReport"},
                 query_params=[*_PERIOD_QUERY_PARAMS,
                               *_ACCOUNT_PAGE_QUERY_PARAMS])
    def access_changes_report(self, **kwargs):
        """*"Who was granted or removed from what, when, and by whom?"*

        **Read `data.summary.statement` before `data.events`.** The honest
        answer to the question as asked is that Cadra cannot answer it:
        group membership lives in a two-column table with no timestamp and no
        actor, and the groups field carries no tracking, so a grant writes
        nothing that outlives it. No query against this database produces a
        grant history, and none is synthesised here.

        What IS evidenced is reported: an account created, with its exact
        timestamp and creator; an account last modified, with the caveat that
        one write stamp covers every change ever made to the record and this
        is the most recent of them.

        `summary.group_changes_in_period` is a REAL COUNT since handoff 24,
        read from the append-only access record rather than from the
        membership table — which, being two integer columns, can never be
        queried for a history. A zero therefore means one of two different
        things, and the count alone cannot tell them apart: nothing happened
        in the period, or the record does not reach back to it. `coverage`
        is what separates them, and `fidelity.record_starts_at` is the
        instant the record begins on this tenant — `null` until the first
        change is recorded here.

        `data.roster` is the present-tense answer to the adjacent question
        the auditor will ask next — *who has access now* — carrying each
        account's groups and, where it is an integration, its API scopes.
        It is labelled as current state throughout and is never presented as
        history.

        ── A page is a window of ACCOUNTS, and both lists describe it ──

        `roster` and `events` are two views of the SAME accounts, paged
        together on one cursor over ascending account id. Paging them
        independently would let a caller hold an event for an account whose
        roster row is three pages away, and there is no honest way to name
        that state. So `?limit=1` returns one account and every event
        belonging to it — which is why this route spells out its own `limit`
        and `cursor` descriptions instead of taking the shared ones.

        `summary` and `fidelity` describe the WHOLE PERIOD on every page, so
        the statement above the table does not change under a reader who has
        paged; `pagination.total_estimate` counts accounts.

        **Events come back in ascending ACCOUNT ID, then time** — not in
        time order across the whole period. Cursor pagination walks
        ascending ids, so a chronological list cannot be paged honestly with
        the cursor this API issues; `/reports/disposals` makes the identical
        trade for the identical reason. Every event carries `at`, so a
        caller that has walked the period can sort it however it likes.

        ── Why `data` is an OBJECT ──

        The same reason the register snapshot's is. There is nowhere honest
        to put a boundary declaration on an array, and a boundary a consumer
        can miss by reading the obvious key is not a boundary. The events sit
        INSIDE the declaration at `data.events`, so it is not possible to
        receive them without receiving `data.fidelity` and
        `data.summary.statement` alongside.

        ── Scope ──

        `identity:read`, because this is the identity register: logins,
        names, group membership and API scopes. Not `assets:read` — no row
        here touches an asset — and not an `audit:read` of its own, for the
        reason `v1_assets.py` sets out at the other two reports.
        """
        qs = get_params()
        date_from, date_to, error = _period(qs)
        if error:
            return error

        report = request.env["res.users"].sudo().access_change_report(
            date_from, date_to)

        # ONE window of users, two views of it. `roster` and `events`
        # describe the SAME page — paging them independently would let a
        # caller hold an event for a user whose roster row is three pages
        # away, and there is no honest way to name that state. `summary` and
        # `fidelity` describe the whole period on every page.
        roster = sorted(report["roster"], key=lambda r: r["user_id"])
        page, pagination = _page(roster, lambda r: r["user_id"], qs,
                                 report["summary"]["accounts"])
        # ROW ORDER IS ASCENDING ACCOUNT ID, not chronological. The model
        # returns the events in `(at, user_id, event)` order; they are
        # re-sorted here because the cursor walks ascending ids and a
        # time-ordered list cannot be paged honestly with the cursor this
        # API publishes — the same trade `/reports/disposals` makes and
        # documents. Every event carries `at`, so a caller that has walked
        # the whole period can order it however it likes.
        on_page = {r["user_id"] for r in page}
        events = [e for e in sorted(report["events"],
                                    key=lambda e: (e["user_id"], e["at"],
                                                   record_order(e),
                                                   e["event"]))
                  if e["user_id"] in on_page]

        return ok(
            data={
                "period": {"date_from": str(date_from), "date_to": str(date_to),
                           "inclusive": "both"},
                "summary": report["summary"],
                "fidelity": report["fidelity"],
                "events": events,
                "roster": page,
            },
            pagination=pagination,
        )

    # ── Configuration: GET /api/v1/reports/configuration-changes ───

    @cadra_route("/api/v1/reports/configuration-changes", method="GET",
                 summary="Configuration parameters touched in a period, with "
                         "who last wrote each and what cannot be recovered",
                 scopes=[SCOPE_SETTINGS_READ],
                 response_schema={
                     "$ref": "#/components/schemas/ConfigurationChangeReport"},
                 query_params=[*_PERIOD_QUERY_PARAMS,
                               *PAGINATION_QUERY_PARAMS])
    def configuration_changes_report(self, **kwargs):
        """*"Who changed what setting, and when?"*

        Partly, and the report says which part. `ir.config_parameter` carries
        real audit columns but is last-write-wins and untracked, so for each
        key exactly three facts survive: the current value, the last writer,
        the last write time. The previous value is gone, the number of
        changes is gone, and a key deleted since leaves no tombstone.

        **Values whose key names a credential are redacted**, replaced by a
        truncated sha256 so two deployments can be compared without either
        revealing what it holds. That is not politeness: `ir_config_parameter`
        is where `myservice_api.jwt_secret` lives — the key every access
        token in the tenant is signed with — and an audit credential is
        exactly the broad, long-lived, widely-shared credential that must not
        be carrying it. `summary.redacted_values` counts them and each row
        says `value_is_redacted`.

        Scoped on `settings:read` rather than `settings:write`: an auditor
        whose only way to read what the settings are is to hold the right to
        change them is an auditor the control has been handed to.
        """
        qs = get_params()
        date_from, date_to, error = _period(qs)
        if error:
            return error

        report = request.env["ir.config_parameter"].sudo(
        ).configuration_change_report(date_from, date_to)
        rows = sorted(report["rows"], key=lambda r: r["id"])
        page, pagination = _page(rows, lambda r: r["id"], qs,
                                 report["summary"]["parameters_in_period"])

        return ok(
            data={
                "period": {"date_from": str(date_from), "date_to": str(date_to),
                           "inclusive": "both"},
                "summary": report["summary"],
                "fidelity": report["fidelity"],
                "parameters": page,
            },
            pagination=pagination,
        )

    # ── Administrator overrides: GET /api/v1/reports/admin-overrides ─

    @cadra_route("/api/v1/reports/admin-overrides", method="GET",
                 summary="Every act an administrator could do only because "
                         "the tenant's override lifted a two-person rule",
                 # `settings:read`, so the Auditor reads it (handoff 70 §5);
                 # `admin` passes as the wildcard it is.
                 scopes=[SCOPE_SETTINGS_READ],
                 query_params=[
                     {"name": "since", "schema": {"type": "string",
                                                  "format": "date"},
                      "description": "First Lagos day, inclusive."},
                     {"name": "until", "schema": {"type": "string",
                                                  "format": "date"},
                      "description": "Last Lagos day, inclusive — the whole "
                                     "of it."},
                     {"name": "kind", "schema": {"type": "string",
                                                 "enum": list(_OVERRIDE_KINDS)},
                      "description": "`gate` (receipt gates and the SAP "
                                     "link) or `audit` (captures and "
                                     "reviews). Both when absent."},
                     *PAGINATION_QUERY_PARAMS,
                 ],
                 response_schema={"type": "array",
                                  "items": _OVERRIDE_ROW_SCHEMA})
    def admin_overrides_report(self, **kwargs):
        """Newest first. An act that broke no rule — the administrator was
        simply the first person at that gate — is not here, because it was
        never an override (handoff 70, ruling 3)."""
        qs = get_params()
        bounds = {}
        for param in ("since", "until"):
            day, error = _parse_report_date(qs, param)
            if error:
                return error
            bounds[param] = day
        if bounds["since"] and bounds["until"] \
                and bounds["since"] > bounds["until"]:
            return err(ERR_INVALID_REQUEST,
                       "The period ends before it starts: `since` must be on "
                       "or before `until`",
                       details={"since": qs.get("since"),
                                "until": qs.get("until")})
        try:
            kind = parse_enum("kind", qs.get("kind"), _OVERRIDE_KINDS)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        lo = _lagos_midnight(bounds["since"]) if bounds["since"] else None
        hi = (_lagos_midnight(bounds["until"] + timedelta(days=1))
              if bounds["until"] else None)
        rows = []
        if kind in (None, "gate"):
            rows += _gate_override_rows(request.env, lo, hi)
        if kind in (None, "audit"):
            rows += _audit_override_rows(request.env, lo, hi)
        rows.sort(key=lambda r: (r["_at"], r["_key"]), reverse=True)
        total = len(rows)
        cap = record_cap()
        if cap is not None:
            rows = rows[:cap]
            flag_truncation(cap, total)
        decoded = decode_cursor(qs.get("cursor"))
        after = decoded.get("before")
        if decoded and after is None:
            # Another route's cursor: a 400, never a silent page one.
            return err(ERR_INVALID_REQUEST,
                       "`cursor` is not a cursor this API issued.",
                       details={"cursor": qs.get("cursor")})
        if after is not None:
            if not (isinstance(after, list) and len(after) == 2
                    and all(isinstance(v, str) for v in after)):
                return err(ERR_INVALID_REQUEST,
                           "`cursor` is not a cursor this API issued.",
                           details={"cursor": qs.get("cursor")})
            rows = [r for r in rows if (r["_at"], r["_key"]) < tuple(after)]
        limit = parse_limit(qs)
        page = rows[:limit]
        next_cursor = (encode_cursor({"before": [page[-1]["_at"],
                                                 page[-1]["_key"]]})
                       if page and len(rows) > limit else None)
        for r in page:
            r.pop("_at")
            r.pop("_key")
        return ok(data=page, pagination={"next_cursor": next_cursor,
                                         "previous_cursor": None,
                                         "total_estimate": total})
