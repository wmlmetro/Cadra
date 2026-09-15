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
and what gives them `identity:read` and `settings:read` instead of
`assets:read`.

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

from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    SCOPE_IDENTITY_READ,
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
                    "(YYYY-MM-DD)."},
    {"name": "to", "required": True,
     "schema": {"type": "string", "format": "date"},
     "description": ("REQUIRED. Last day of the period, INCLUSIVE — the "
                     "whole of that day. An auditor asks for a quarter by "
                     "naming its first and last day, and an exclusive upper "
                     "bound would silently lose everything that happened on "
                     "31 March.")},
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


class CadraAuditReportsV1(http.Controller):

    # ── Access changes: GET /api/v1/reports/access-changes ─────────

    @cadra_route("/api/v1/reports/access-changes", method="GET",
                 summary="Access events in a period, and the statement that "
                         "group changes are not among them",
                 scopes=[SCOPE_IDENTITY_READ],
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
        is the most recent of them. `summary.group_changes_in_period` is `0`
        and it is a STRUCTURAL zero — it is in the payload precisely so that
        a consumer reading counts sees the absence rather than inferring it
        from a missing key.

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
