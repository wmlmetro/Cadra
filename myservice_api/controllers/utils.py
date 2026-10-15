"""
Cadra API shared utilities — envelope, JWT, scopes, idempotency, request-id.

This module is imported by every Cadra controller. The intent is that the
controller layer stays thin: parse request -> call a service function ->
serialize via these helpers. Nothing here should reach into Odoo internals
that aren't documented; the goal is portability to a non-Odoo runtime later.
"""
import base64
import datetime as _dt
import functools
import hashlib
import hmac
import json
import logging
import re
import time
import uuid

import psycopg2
import requests

from odoo import fields
from odoo.exceptions import (
    AccessError,
    ConcurrencyError,
    MissingError,
    UserError,
    ValidationError,
)
from odoo.http import request

from .query_params import BadFilter, parse_int

# A receipt-gate refusal carries its own kind; `cadra_route` maps it in one
# place (`gate_refusal`). `myservice_api` depends on the asset register.
from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused,
)

_logger = logging.getLogger(__name__)

API_VERSION = "v1"


# ─── envelope ────────────────────────────────────────────────────────

def _meta():
    """Common `meta` block on every success response (PRD §10.7)."""
    return {
        "request_id": getattr(request, "cadra_request_id", None) or _new_request_id(),
        "timestamp": fields.Datetime.now().isoformat(),
        "version": API_VERSION,
    }


def ok(data=None, pagination=None):
    """Wrap a successful response in the PRD envelope.

    Use as the sole return value of a JSON endpoint:
        return ok({"id": 42, "name": "..."})

    For list endpoints, pass `pagination`:
        return ok(items, pagination={"next_cursor": "...", "total_estimate": 1200})

    A truncation warning raised by `paginate()` (or by an export route that
    applied the record cap by hand) is attached here rather than by the
    caller. `ok()` is the sole envelope builder for every route — rule 1 —
    so putting it here is the only placement no endpoint can forget.
    """
    body = {"data": data, "meta": _meta()}
    if pagination is not None:
        body["pagination"] = pagination
    truncation = truncation_warning()
    if truncation:
        body["_warnings"] = {"truncated": truncation}
    return body


def err(code, message, *, status=400, details=None):
    """Wrap an error response in the PRD envelope.

    Codes are stable, lowercase_snake strings. Reuse existing codes where
    possible (see ERR_*); only add new codes when no existing one fits.

    `status` is an HTTP-style code the caller can use to set the response
    status — Odoo's JSON-RPC layer always returns 200, so we surface the
    intended status inside the error object too (under `details.http_status`)
    for clients that want to act on it.
    """
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": _meta()["request_id"],
        }
    }
    extras = dict(details or {})
    extras["http_status"] = status
    body["error"]["details"] = extras
    return body


# Canonical error codes — keep this list short and reuse before adding.
ERR_UNAUTHORIZED         = "unauthorized"
ERR_FORBIDDEN            = "forbidden"
ERR_INVALID_REQUEST      = "invalid_request"
ERR_VALIDATION_FAILED    = "validation_failed"
ERR_NOT_FOUND            = "not_found"
ERR_CONFLICT             = "conflict"
ERR_RATE_LIMITED         = "rate_limited"
ERR_INTERNAL             = "internal_error"
ERR_NOT_IMPLEMENTED      = "not_implemented"
ERR_IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
ERR_MISCONFIGURED        = "server_misconfigured"


def refuse_unwritable(rejected, writable, *, hint=None):
    """The answer to a body naming a field this route does not accept. A 400.

    **Until handoff 31 this was a 2xx.** The route wrote what it could, dropped
    the rest, and named the dropped keys in `data._warnings.rejected_fields` —
    which for most of this API's life nothing read. Rule 3 of `CLAUDE.md` had
    called that a defect from the start; what settled it was reading the
    consumer. Vendra ALREADY treats a rejected field as terminal and
    dead-letters the receipt — AFTER Cadra has created the asset, incomplete,
    under an idempotency key that replays the same 201 on every retry. So the
    lenient answer cost the only integrator a manual repair and bought nobody
    anything. And on the day the Cadra app first showed those warnings to a
    person, it turned out a category's depreciation method had never been
    changeable from its own settings screen: the screen sent the one key the
    API refused, got a 200, and said "policy saved".

    `details.writable` is there so a caller can repair itself from the
    response, the way `allowed_values` lets one repair a filter. A route calls
    this BEFORE it writes anything: `err()` returns a response and does not
    roll back.
    """
    rejected = list(rejected)
    details = {"rejected_fields": rejected, "writable": sorted(writable)}
    if hint:
        details["hint"] = hint
    return err(
        ERR_INVALID_REQUEST,
        "This route does not accept: %s. Nothing was written."
        % ", ".join("`%s`" % k for k in rejected),
        details=details)


# ─── request id ──────────────────────────────────────────────────────

def _new_request_id():
    """Mint or recover the per-request correlation id.

    Pulls from `X-Request-Id` if the client sent one; otherwise generates a
    fresh UUID. Stored on `request.cadra_request_id` so subsequent helpers
    (logging, envelope) all see the same value.
    """
    if not hasattr(request, "cadra_request_id") or not request.cadra_request_id:
        inbound = (request.httprequest.headers.get("X-Request-Id") or "").strip()
        request.cadra_request_id = inbound or uuid.uuid4().hex
    return request.cadra_request_id


def log_safe(value, max_length=128):
    """Make caller-supplied text safe to put in a single log line.

    A `client_id` arrives from an unauthenticated request body, so it is
    attacker-controlled: a newline in it would let the caller forge log
    lines under our own logger name, and a megabyte of it would be a cheap
    way to fill the disk. Strip anything that is not printable ASCII,
    truncate, and mark the truncation so a real long id is not mistaken
    for a short one.
    """
    if value is None:
        return "-"
    text = str(value)
    text = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)
    if not text:
        return "-"
    if len(text) > max_length:
        return text[:max_length] + "...(truncated)"
    return text


# `caller_ip`, `_is_infrastructure` and `caller_ip_label` MOVED to
# `myservice_nrs_base/caller_ip.py` in handoff 17 and are re-exported here so
# that every existing caller in this module and in `v1.py` is unchanged.
#
# They moved because two routes outside `/api/v1` need the same answer — the
# WorkSpace callback in `myservice_workflow` and the Redhubs CSV export in
# `myservice_identity` — and neither module can import from `myservice_api`
# without a dependency cycle. The file they moved to explains the rest.
from odoo.addons.myservice_nrs_base.caller_ip import (  # noqa: E402,F401
    caller_ip,
    caller_ip_label,
    _is_infrastructure,
)


# ─── scopes ──────────────────────────────────────────────────────────
#
# Match the resource tags in docs/cadra-api-docs.html. Format is
# `<resource>:<action>` where action is one of read | write | admin.
# `*` is a wildcard reserved for trusted internal tooling.

SCOPE_ASSETS_READ        = "assets:read"
SCOPE_ASSETS_WRITE       = "assets:write"
# Taking a copy of the whole register (`/assets/export`, `/assets/export.csv`)
# and reading a page of it are different acts, and until handoff 50
# `assets:read` meant both — the same one-name-two-meanings defect handoff 47
# split twice for (ruling 1 there, ruling 1 here). Named `export:read` rather
# than `assets:export` because the Auditor is pinned read-only — every scope
# the Auditor holds ends `:read` (`test_auditor_access.py`) — and an export
# changes nothing about the register; it only copies it.
SCOPE_EXPORT_READ        = "export:read"
SCOPE_LOCATIONS_READ     = "locations:read"
SCOPE_LOCATIONS_WRITE    = "locations:write"
SCOPE_REQUESTS_READ      = "requests:read"
SCOPE_REQUESTS_WRITE     = "requests:write"
SCOPE_APPROVALS_WRITE    = "approvals:write"
SCOPE_INGESTION_WRITE    = "ingestion:write"
SCOPE_INTEGRATIONS_WRITE = "integrations:write"
SCOPE_WEBHOOKS_ADMIN     = "webhooks:admin"
# The asset register's own figures: `/dashboard/kpis`, `/dashboard/map`,
# `/reports/depreciation`. Until handoff 50 §2.1 the MAP was not entirely an
# aggregate — its payload carried one row per geocoded vehicle (plate,
# driver) beside the locations, a recorded Architect finding (report 47,
# GO-LIVE §25). 50 closed it: the vehicle rows moved to `/fleet/map` under
# `operations:read`, and this scope's map answers locations only.
# Until handoff 47 this one name also opened every fleet, staff-bus, FM and
# security screen; that half is `operations:read` below. One name was
# carrying two meanings, which is the defect this API keeps finding in
# other people's work (handoff 47, ruling 1).
SCOPE_DASHBOARDS_READ    = "dashboards:read"
# The operational dashboards OUTSIDE the asset register: fleet, staff bus,
# facilities (FM) and security. Split out of `dashboards:read` by handoff 47
# so an Asset User or an Auditor reading the register's figures is not also
# handed every fleet and security screen. NOT named `fleet:read` because the
# security and FM dashboards take it too; distinct from the SIDEBAR group
# key `operations` (which holds the Locations screens) — that is a published
# switch key, not a scope, and the two must not be read as one thing.
SCOPE_OPERATIONS_READ    = "operations:read"
SCOPE_IDENTITY_READ      = "identity:read"
# The record of who granted whom which role, who was deactivated and by whom
# (`/reports/access-changes`). Carved out of `identity:read` by handoff 47,
# ruling 1: the employee picker a custodian needs and the access record an
# auditor reads are different questions, and under one name every Asset User
# could read the access record while the Auditor could not find it.
SCOPE_ACCESS_READ        = "access:read"
# Held by the Tag-Issuing Unit, which is deliberately NOT the team that
# creates asset records (INT-04/05). Its own scope is what keeps "affixed"
# evidence of an independent act rather than a field someone can set.
SCOPE_TAGGING_WRITE      = "tagging:write"
# Tenant configuration: the category taxonomy, branding, depreciation policy.
# Carved out of `admin` so an Asset Manager can keep the Settings screens
# without being handed a wildcard — see GROUP_SCOPES below.
SCOPE_SETTINGS_WRITE     = "settings:write"
# Reading the configuration change log (specification §13.4's fifth report).
# A READ scope rather than reusing `settings:write`, because an auditor whose
# only way to read what the settings are is to hold the right to change them
# is an auditor the control has been handed to. It is granted by two groups
# below, so it is not the "scope nothing grants" that the audit-report scope
# ruling in `v1_assets.py` rightly rejects.
SCOPE_SETTINGS_READ      = "settings:read"
SCOPE_ADMIN              = "admin"
# The receipt gates (handoff 57, kept by handoff 58). `candidates:read`
# lets a caller see a unit that has not yet passed the gates (`GET
# /candidates`, `?register_state=any|<value>`); the other five fire one gate
# each. Their groups are the Addendum A §4 roles.
SCOPE_CANDIDATES_READ    = "candidates:read"
SCOPE_VFM_VERIFY         = "vfm:verify"
SCOPE_VFM_APPROVE        = "vfm:approve"
SCOPE_TAGGING_REQUEST    = "tagging:request"
SCOPE_REGISTER_MAKE      = "register:make"
SCOPE_REGISTER_CHECK     = "register:check"
# Handoff 58 §4: how a class is identified at receipt (Section 12) — a
# class's `identification_mode` and mandatory attributes, and nothing else
# about it. The Asset Controller's, who decides how a unit is tagged; the
# Asset Manager's too, who holds `settings:write` over the whole taxonomy.
# Carved out so the Controller can set a class's mode without being handed
# the depreciation policy, the branding and the sidebar.
SCOPE_SETTINGS_CLASSES   = "settings:classes"
# Handoff 61, ruling 1 on report 60: Internal Audit's working papers — the
# delivery notes, invoices and photographs IAD attaches when it verifies a
# receipt for value for money. Read by IAD (officer and approver), by the
# Register Maker and Checker (who register cost against them) and by the
# Auditor; NOT by every Asset User and NOT by Vendra's credential, both of
# which hold `candidates:read` — which is what guarded the evidence until
# this scope existed. Ends `:read` so the Auditor-is-read-only pin holds.
# One guard, `evidence_readable()` below, in front of every place evidence
# is served; a caller without it is told how many items there are and
# nothing else.
SCOPE_EVIDENCE_READ      = "evidence:read"

ALL_SCOPES = frozenset({
    SCOPE_ASSETS_READ, SCOPE_ASSETS_WRITE,
    SCOPE_EXPORT_READ,
    SCOPE_LOCATIONS_READ, SCOPE_LOCATIONS_WRITE,
    SCOPE_REQUESTS_READ, SCOPE_REQUESTS_WRITE,
    SCOPE_APPROVALS_WRITE,
    SCOPE_INGESTION_WRITE,
    SCOPE_INTEGRATIONS_WRITE,
    SCOPE_WEBHOOKS_ADMIN,
    SCOPE_DASHBOARDS_READ,
    SCOPE_OPERATIONS_READ,
    SCOPE_IDENTITY_READ,
    SCOPE_ACCESS_READ,
    SCOPE_TAGGING_WRITE,
    SCOPE_SETTINGS_WRITE,
    SCOPE_SETTINGS_READ,
    SCOPE_CANDIDATES_READ, SCOPE_VFM_VERIFY, SCOPE_VFM_APPROVE,
    SCOPE_TAGGING_REQUEST, SCOPE_REGISTER_MAKE, SCOPE_REGISTER_CHECK,
    SCOPE_SETTINGS_CLASSES,
    SCOPE_EVIDENCE_READ,
    SCOPE_ADMIN,
})


# ─── Odoo group → API scope (session tokens only) ────────────────────
#
# `POST /auth/login` used to mint `["*"]` for anybody who could authenticate,
# so the INT-04/05 separation the Tag-Issuing Unit's client exists to enforce
# held for API clients and not for session users: a storekeeper with an Odoo
# password could confirm the tag on an asset they had just created. A control
# that is walked around by logging in is not a control.
#
# Each entry maps an Odoo group to the scopes that group's job actually needs.
# A user's token carries the UNION over the groups they hold. `has_group`
# follows `implied_ids`, so Asset Manager automatically picks up Asset User's
# reads and only the delta is listed here.
#
# Two rules this table is built on:
#
#   1. `tagging:write` is granted by ONE group and is implied by no other.
#      In particular Asset Manager does not get it — that is the whole point.
#   2. An internal user holding none of these groups gets NO scopes. Every
#      list endpoint runs `sudo()`, so a scope is the only gate between a
#      logged-in user and the register; defaulting to read access would hand
#      the whole asset base to anyone with an Odoo login.
GROUP_SCOPES = (
    # Odoo system administrators. `admin` is a wildcard in `require_jwt`, so
    # this line does grant `tagging:write` — accepted deliberately: a member
    # of `base.group_system` can execute arbitrary server actions and is
    # omnipotent by construction, so withholding one scope from them would be
    # theatre. Every non-administrator now needs the group below.
    ("base.group_system", (SCOPE_ADMIN,)),

    ("myservice_asset_register.group_asset_user", (
        SCOPE_ASSETS_READ,
        SCOPE_LOCATIONS_READ,
        SCOPE_IDENTITY_READ,
        SCOPE_DASHBOARDS_READ,
        SCOPE_REQUESTS_READ,
        # The group's own description is "view assets, log verifications,
        # RAISE REQUESTS", and raising one is a write.
        SCOPE_REQUESTS_WRITE,
        # Handoff 57: seeing a receipt candidate. Inherited by every role
        # that implies Asset User — the Store Officer who submits it among
        # them — and by the five gate roles below.
        SCOPE_CANDIDATES_READ,
    )),
    # The role between reading the register and running it (handoff 47,
    # ruling 3). Registers assets, requests moves and custody changes,
    # records verifications — the storekeeper's actual job — composed of
    # scopes that already existed: Asset User's reads plus `assets:write`.
    # Deliberately NOT `approvals:write` (the second person on every move is
    # the point of handoff 35), NOT `settings:write` or `integrations:write`
    # (running the register is the Asset Manager's job), and NOT
    # `tagging:write` (one grant, below). Implies Asset User in
    # asset_security.xml, so only the delta is listed here.
    ("myservice_asset_register.group_asset_officer", (
        SCOPE_ASSETS_WRITE,
    )),
    ("myservice_asset_register.group_asset_manager", (
        # `assets:write` arrives through the implied Asset Officer since
        # handoff 47 — this row is the delta over that role: approving,
        # configuring, importing.
        SCOPE_LOCATIONS_WRITE,
        SCOPE_APPROVALS_WRITE,
        SCOPE_INGESTION_WRITE,
        SCOPE_SETTINGS_WRITE,
        # Whoever may change the settings may read the log of who changed
        # them; withholding it would leave the change log readable only by
        # the auditor and not by the person answering to them.
        SCOPE_SETTINGS_READ,
        # Handoff 58: a class's identification mode is part of the taxonomy
        # this role already configures under `settings:write`; held here
        # too so the categories screen has ONE scope to declare.
        SCOPE_SETTINGS_CLASSES,
        # The SPA's Bulk Import page (nominal-roll xlsx -> employees) is in
        # the top-level nav and is the only thing that page does. Without
        # this an Asset Manager who imported a roll yesterday gets a 403
        # toast and an inert screen — a silent break, which is exactly what
        # narrowing the login wildcard must not cause.
        SCOPE_INTEGRATIONS_WRITE,
    )),
    # The Tag-Issuing Unit. Deliberately NOT implied by Asset Manager: the
    # team that creates asset records must not be the team that confirms the
    # label went onto the metal, or an affix record proves only that one
    # system said so twice.
    ("myservice_asset_register.group_tag_issuing_unit", (SCOPE_TAGGING_WRITE,)),

    # The receipt gates (handoff 57, kept by 58; Addendum A §4). Each
    # implies Asset User, so `candidates:read` arrives that way too and is
    # repeated here only so the row says what the role is FOR.
    ("myservice_asset_register.group_iad_vfm_officer", (
        SCOPE_CANDIDATES_READ, SCOPE_VFM_VERIFY, SCOPE_EVIDENCE_READ)),
    ("myservice_asset_register.group_iad_vfm_approver", (
        SCOPE_CANDIDATES_READ, SCOPE_VFM_APPROVE, SCOPE_EVIDENCE_READ)),
    ("myservice_asset_register.group_asset_controller", (
        SCOPE_CANDIDATES_READ, SCOPE_TAGGING_REQUEST,
        # Handoff 58 §4: the Controller decides how a class is identified.
        SCOPE_SETTINGS_CLASSES)),
    # Handoff 61: the maker and the checker register cost against IAD's
    # evidence, so they read it (ruling 1 on report 60).
    ("myservice_asset_register.group_register_maker", (
        SCOPE_CANDIDATES_READ, SCOPE_REGISTER_MAKE, SCOPE_EVIDENCE_READ)),
    ("myservice_asset_register.group_register_checker", (
        SCOPE_CANDIDATES_READ, SCOPE_REGISTER_CHECK, SCOPE_EVIDENCE_READ)),

    # The Auditor (specification §3's `audit_viewer`, INT-10 §4.3). READ
    # scopes only, and every one of them already exists — the five §13.4
    # reports are views of the register, the identity roster and the
    # configuration, so they take those things' scopes rather than an
    # `audit:read` of their own. `v1_assets.py` ruled that out and the
    # reasoning holds: a scope no group grants makes a report unreachable on
    # every tenant on the day it ships.
    #
    # Implied by nothing and implying nothing, like the Tag-Issuing Unit and
    # for a related reason: an auditor who is also an Asset Manager is not
    # independent of what they are auditing, and hanging this under either
    # existing group would make that the default rather than a decision.
    # Do not "tidy" it into the hierarchy.
    ("myservice_api.group_auditor", (
        SCOPE_ASSETS_READ,
        SCOPE_LOCATIONS_READ,
        SCOPE_REQUESTS_READ,
        SCOPE_IDENTITY_READ,
        SCOPE_DASHBOARDS_READ,
        SCOPE_SETTINGS_READ,
        # The record of who granted whom which role. The Auditor's job by
        # definition, and until handoff 47 the one §13.4 report the Auditor
        # could NOT find while every Asset User could read it — both halves
        # of the same defect, fixed by the `identity:read` split (ruling 1).
        SCOPE_ACCESS_READ,
        # Taking a copy of the whole register (handoff 50, ruling 1). Held
        # by the Auditor and, through the `admin` wildcard in
        # `_missing_scopes`, the Administrator — and by nobody else: a Store
        # Officer, Asset User, Officer or Manager reads pages, not copies.
        SCOPE_EXPORT_READ,
        # Handoff 57: the auditor sees every record at any state
        # (Addendum A §4, "Auditor (read-only)").
        SCOPE_CANDIDATES_READ,
        # Handoff 61: IAD's evidence (ruling 1 on report 60).
        SCOPE_EVIDENCE_READ,
    )),

    # The employee roster and the SAP/spreadsheet imports that feed it.
    ("myservice_identity.group_identity_manager", (
        SCOPE_IDENTITY_READ,
        SCOPE_INTEGRATIONS_WRITE,
        # `/identity/employees/<id>/assets` — what this person has custody
        # of — is the one route in the API requiring TWO scopes
        # (`identity:read` + `assets:read`). Without the second, an Identity
        # Manager holding no asset group 403s on the custody tab of the
        # employee record they are already looking at.
        SCOPE_ASSETS_READ,
    )),

    # Read-only consumers of the operational dashboards. Until handoff 47
    # they held `dashboards:read`, which was coarse — one name covering the
    # asset register's figures AND the security, fleet and FM dashboards.
    # Their job is the second half, so that is what they hold now: a
    # Security Officer no longer reads the asset dashboard's figures, and an
    # Asset User no longer reads the security map. `operations:read` still
    # covers fleet, staff bus, FM and security as one, which is why these
    # two groups continue to look identical here.
    ("myservice_security.group_security_officer", (SCOPE_OPERATIONS_READ,)),
    ("myservice_staff_bus.group_bus_user", (SCOPE_OPERATIONS_READ,)),
)


# ─── API scope → Odoo group (API CLIENT users only) ──────────────────
#
# Every API client used to run as `base.user_admin`, so a tag affix recorded
# `affixed_by = Administrator` — for the Tag-Issuing Unit's client and for the
# client that created the asset alike. The scope separation held; the record of
# WHO confirmed the label, which is the only reason that separation exists,
# did not. Each client now gets its own `res.users`, and this table says what
# that user is put in.
#
# Deliberately NOT the inverse of GROUP_SCOPES, and not derived from it:
#
#   * `assets:read` is granted by three groups there and `dashboards:read` by
#     two unrelated ones; an automatic inverse has no basis to choose.
#   * `admin` would invert to `base.group_system`. A scope string typed into a
#     form must never be able to mint a system administrator.
#
# These groups are NOT the access control and must not be mistaken for it.
# `require_jwt` is the gate, and a scope refusal is a 403 that names the scope
# it wanted; a record-rule refusal would be a 500 that names nothing, which
# breaks the envelope contract for Vendra. They exist for two narrower
# reasons: `base.group_user` is genuinely load-bearing for the handful of
# controller reads that do not `sudo()` (the `myservice.dashboard` routes and
# `ir.sequence.next_by_code`), and a user form that reads "Tag-Issuing Unit"
# is legible provenance where "Administrator" was not.
SCOPE_GROUPS = {
    SCOPE_ASSETS_READ:        ("myservice_asset_register.group_asset_user",),
    # The Asset Officer, not the Manager, since handoff 47: a client that
    # registers assets (Vendra's INT-03 credential is the live case) is doing
    # an officer's job, and reading "Asset Manager" off its user form implied
    # it could also approve and configure, which its scopes never allowed.
    # `approvals:write` below still maps to the Manager, which is
    # `APPROVER_GROUP` — a credential that decides requests keeps the group
    # the model's `_may_decide` asks for.
    SCOPE_ASSETS_WRITE:       ("myservice_asset_register.group_asset_officer",),
    SCOPE_LOCATIONS_READ:     ("myservice_asset_register.group_asset_user",),
    SCOPE_LOCATIONS_WRITE:    ("myservice_asset_register.group_asset_manager",),
    SCOPE_REQUESTS_READ:      ("myservice_asset_register.group_asset_user",),
    SCOPE_REQUESTS_WRITE:     ("myservice_asset_register.group_asset_user",),
    SCOPE_APPROVALS_WRITE:    ("myservice_asset_register.group_asset_manager",),
    SCOPE_INGESTION_WRITE:    ("myservice_asset_register.group_asset_manager",),
    SCOPE_SETTINGS_WRITE:     ("myservice_asset_register.group_asset_manager",),
    SCOPE_SETTINGS_READ:      ("myservice_api.group_auditor",),
    # These three were load-bearing rather than documentary until handoff 09,
    # because the `myservice.dashboard` routes were the only ones in the API
    # that did not `sudo()`: `get_kpis` reads `fleet.vehicle` and
    # `generic.location` directly, and without these groups the route answered
    # `400 validation_failed` — "You are not allowed to access 'Vehicle'" —
    # naming an Odoo group in the published envelope. It had worked only
    # because every client ran as base.user_admin, which held them.
    # The routes sudo() now (`v1.py`), so the scope is the gate and these
    # groups are back to being documentary. They are kept, derived from the
    # scope so the two cannot drift, as the belt to that braces: nothing else
    # would grant a dashboards-only client the group memberships that make it
    # legible on the user form, and a future dashboard read that forgets to
    # sudo() degrades to working rather than to a leaked group name.
    SCOPE_DASHBOARDS_READ:    ("myservice_security.group_security_officer",
                               "fleet.fleet_group_user",
                               "generic_location.group_generic_location_user_implicit"),
    # Same belt-to-braces reasoning as `dashboards:read` above: the fleet
    # and security routes sudo(), so these are documentary, kept so a future
    # dashboard read that forgets to sudo() degrades to working.
    SCOPE_OPERATIONS_READ:    ("myservice_security.group_security_officer",
                               "fleet.fleet_group_user"),
    SCOPE_IDENTITY_READ:      ("myservice_identity.group_identity_manager",),
    # The Auditor is the one non-wildcard group that grants `access:read`
    # (GROUP_SCOPES above), so it is what the group is FOR — same shape as
    # `settings:read` above it.
    SCOPE_ACCESS_READ:        ("myservice_api.group_auditor",),
    # Same shape again (handoff 50, ruling 1): the Auditor is the one
    # non-wildcard group that grants `export:read`, so it is what the group
    # is FOR.
    SCOPE_EXPORT_READ:        ("myservice_api.group_auditor",),
    # Handoff 57. Each gate scope maps to the one role that holds it; reading
    # candidates to Asset User, which every gate role implies.
    SCOPE_CANDIDATES_READ:    ("myservice_asset_register.group_asset_user",),
    SCOPE_VFM_VERIFY:         ("myservice_asset_register.group_iad_vfm_officer",),
    SCOPE_VFM_APPROVE:        ("myservice_asset_register.group_iad_vfm_approver",),
    SCOPE_TAGGING_REQUEST:    ("myservice_asset_register.group_asset_controller",),
    SCOPE_REGISTER_MAKE:      ("myservice_asset_register.group_register_maker",),
    SCOPE_REGISTER_CHECK:     ("myservice_asset_register.group_register_checker",),
    SCOPE_SETTINGS_CLASSES:   ("myservice_asset_register.group_asset_controller",),
    # Handoff 61. The Auditor, the one read-only group among its five
    # holders: a credential granted the papers is put with the role whose
    # whole job is reading them, never with a gate role (which would carry
    # that role's exclusions and its gate).
    SCOPE_EVIDENCE_READ:      ("myservice_api.group_auditor",),
    SCOPE_INTEGRATIONS_WRITE: ("myservice_identity.group_identity_manager",),
    SCOPE_TAGGING_WRITE:      ("myservice_asset_register.group_tag_issuing_unit",),
    # SCOPE_WEBHOOKS_ADMIN and SCOPE_ADMIN map to nothing on purpose — see the
    # note above. An `admin` client's user is an ordinary internal user; the
    # wildcard lives in the token, where `require_jwt` can see it.
}


def gate_refusal_parts(e):
    """A `GateRefused` (`myservice_asset_register/models/asset_gates.py`) as
    `(status, code, message, details)` — the one place its kinds become
    statuses, shared by the single-unit envelope below and by each unit's
    line in a batch answer (handoff 60 §2), so a unit refused inside a batch
    is refused with the same status, code and sentence as alone.

    * `invalid_state`, `segregation_of_duties`, `not_on_the_register` →
      409 `conflict`, the kind in `details.reason`;
    * `forbidden` → 403;
    * anything else (`validation_failed`) → 400 `validation_failed`.
    """
    details = dict(e.details or {})
    if e.kind in ("invalid_state", "segregation_of_duties",
                  "not_on_the_register"):
        details["reason"] = e.kind
        return 409, ERR_CONFLICT, str(e.args[0]), details
    if e.kind == "forbidden":
        return 403, ERR_FORBIDDEN, str(e.args[0]), details
    return 400, ERR_VALIDATION_FAILED, str(e.args[0]), details


def gate_refusal(e):
    """A `GateRefused` as the envelope (`gate_refusal_parts`)."""
    status, code, message, details = gate_refusal_parts(e)
    return err(code, message, status=status, details=details)


def schema_behind(e):
    """The envelope for a database that has not been upgraded to its code
    (`UndefinedColumn` / `UndefinedTable`), naming what is missing and the
    upgrade — see `GET /api/v1/meta/readiness` for the whole list."""
    missing = (getattr(e, "diag", None) and e.diag.message_primary) or str(e)
    db = request.env.cr.dbname if request else None
    return err(
        ERR_MISCONFIGURED,
        "This tenant's database (%s) has not been upgraded to the code it "
        "is running: %s. Upgrade its modules (the per-tenant fan-out in "
        "CLAUDE.md) before using it; GET /api/v1/meta/readiness lists "
        "everything that is missing." % (db, missing.strip()),
        status=503,
        details={"database": db, "missing": missing.strip(),
                 "remedy": "module_upgrade"})


def groups_for_scopes(env, scopes):
    """The `res.groups` an API client holding `scopes` should run as.

    Always includes `base.group_user`: the client user has to be internal or
    it falls outside every `base.group_user` ACL in the stack, including the
    `ir.sequence` read behind asset transfers, and `share` is computed from
    exactly that group.

    A group whose module is not installed on this tenant is skipped rather
    than raised on — `myservice_identity` and `myservice_staff_bus` are
    optional per deployment, and provisioning must not fail closed on the
    tenants that do without them. Same reasoning as `scopes_for_user`.
    """
    xmlids = {"base.group_user"}
    for scope in scopes:
        xmlids.update(SCOPE_GROUPS.get(scope, ()))

    groups = env["res.groups"].browse()
    for xmlid in sorted(xmlids):
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            groups |= group
        else:
            _logger.info(
                "myservice_api: %s is not installed on this database; "
                "leaving it off the API client user", xmlid)
    return groups


def scopes_for_user(user):
    """The API scopes a session token for `user` should carry.

    Union over GROUP_SCOPES for every group the user holds. Returns a sorted
    list; an empty list is a legitimate answer and means the user has no
    Cadra role — they get a token that authenticates and authorises nothing,
    and every route answers 403 naming the scope it wanted.

    A group whose module is not installed on this tenant simply does not
    match — Odoo 19's `has_group` answers False for an xmlid it cannot
    resolve rather than raising (verified against `res.users._has_group`,
    which looks the id up through `_get_group_definitions().get_id`). The
    try/except is belt-and-braces for the same case on other versions:
    `myservice_identity` and `myservice_staff_bus` are optional per
    deployment, and a missing addon must not fail login closed for everyone.
    """
    granted = set()
    for xmlid, scopes in GROUP_SCOPES:
        try:
            if user.has_group(xmlid):
                granted.update(scopes)
        except Exception:
            # catch-all: unknown — on Odoo 19 the expected case does not
            # raise at all (`has_group` answers False for an xmlid it
            # cannot resolve), so anything arriving here is unaccounted
            # for and the log line is the whole point of the handler.
            #
            # Logged, not swallowed silently: the expected case (an addon
            # that is not installed on this tenant) is uninteresting, but a
            # transient ACL or cursor failure here hands a legitimate user an
            # under-scoped token, and a 403 with no trace of why is the
            # hardest kind of bug to answer a support call about.
            _logger.warning(
                "could not evaluate group %s for uid %s while deriving API "
                "scopes; continuing without it", xmlid, user.id, exc_info=True)
            continue
    return sorted(granted)


# ─── JWT ─────────────────────────────────────────────────────────────

class JwtError(Exception):
    pass


class JwtSecretMissing(Exception):
    """Raised when the server has no JWT signing secret configured.

    Fail-closed: token mint and verify both refuse to operate rather than
    quietly using a placeholder secret. The previous code defaulted to
    "CHANGE_ME__..." which made forged tokens trivial in any deployment
    where the operator forgot to set the config parameter.
    """


_JWT_PLACEHOLDERS = frozenset({
    "", "CHANGE_ME__MYservice_API_JWT_SECRET", "CHANGE_ME", "changeme",
    "secret", "your-secret-here",
})


def jwt_secret(env):
    """Return the JWT signing secret, or raise JwtSecretMissing.

    Read from `myservice_api.jwt_secret` ir.config_parameter. Refuses to
    return a placeholder. Operators should set this to a 32+ char random
    string at deployment:
        odoo config:
          docker exec ... odoo shell:
            env['ir.config_parameter'].sudo().set_param(
                'myservice_api.jwt_secret', secrets.token_urlsafe(48))
    """
    value = env["ir.config_parameter"].sudo().get_param("myservice_api.jwt_secret", "")
    if not value or value in _JWT_PLACEHOLDERS or len(value) < 16:
        raise JwtSecretMissing(
            "myservice_api.jwt_secret is unset or too short. Set it to a "
            "32+ character random string before using the API."
        )
    return value


# ─── Cloudflare Turnstile ────────────────────────────────────────────

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT = 5


def turnstile_secret(env):
    """Return the Turnstile secret key, or "" when protection is off.

    Read from the `myservice_api.turnstile_secret` ir.config_parameter,
    which bootstrap seeds from the CADRA_TURNSTILE_SECRET env var. Empty
    is a valid, deliberate state: it means this tenant has no Turnstile
    site configured and the challenge is skipped entirely. That is the
    default, and it is how every tenant provisioned before this feature
    keeps logging in.
    """
    return (env["ir.config_parameter"].sudo().get_param(
        "myservice_api.turnstile_secret", "") or "").strip()


def turnstile_error(env, token):
    """Verify a Turnstile response token; return an error envelope or None.

    Returns None when the challenge passes *or* when Turnstile is not
    configured — so callers can gate an endpoint with two lines and the
    unprotected path stays the no-op it was before.
    """
    secret = turnstile_secret(env)
    if not secret:
        return None

    if not token:
        return err(ERR_INVALID_REQUEST, "`turnstile_token` is required")

    try:
        # `remoteip` is deliberately omitted. It is optional, and behind the
        # cluster ingress (Cloudflare → load balancer → ingress → Odoo)
        # proxy_mode's ProxyFix only unwinds one hop, so the address we see
        # is a proxy's rather than the visitor's. Sending a mismatched IP
        # makes Cloudflare reject an otherwise valid token; the token is
        # already bound to the sitekey and single-use without it.
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token},
            timeout=TURNSTILE_TIMEOUT,
        )
        body = response.json()
    except (requests.RequestException, ValueError) as e:
        # Narrow on purpose. `requests.RequestException` is every transport
        # failure including `JSONDecodeError`, and `ValueError` is the same
        # thing spelled by the stdlib — between them they are "Cloudflare
        # unreachable, or answering with something that is not JSON", which
        # is the entire expected failure here. A broad catch would also
        # swallow a NameError or an AttributeError in the lines above and
        # report it to the caller as "could not verify the challenge",
        # which is a bug that looks like weather.
        #
        # Fail closed either way — an open failure mode would let anyone
        # turn the challenge off by making siteverify time out.
        _logger.warning("Turnstile siteverify call failed: %s", e)
        return err(ERR_INTERNAL, "Could not verify the Turnstile challenge",
                   status=502)

    if not body.get("success"):
        # Cloudflare's error-codes distinguish a stale token from a bad
        # secret key — useful in the log, not something to hand a caller
        # who may be probing for a misconfiguration.
        _logger.info("Turnstile rejected a challenge: %s",
                     body.get("error-codes") or "no error-codes returned")
        return err(ERR_INVALID_REQUEST, "Turnstile verification failed")

    return None


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw):
    raw_bytes = raw.encode("ascii")
    padding = b"=" * (-len(raw_bytes) % 4)
    return base64.urlsafe_b64decode(raw_bytes + padding)


def jwt_encode(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def jwt_decode(token, secret):
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except (AttributeError, ValueError):
        raise JwtError("Malformed token")

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        # SETTLE THE SHAPE, do not widen the clause. `[]` and `{}` and `"x"`
        # are all valid JSON, and `.get` on any of them raises AttributeError
        # — which is not a ValueError, so it escaped this handler, escaped
        # `require_jwt` (which catches only JwtError), and escaped
        # `cadra_endpoint` (which calls require_jwt OUTSIDE its own try). An
        # unauthenticated caller got a raw Odoo HTML 500 on EVERY route, from
        # `Bearer W10.e30.c2ln`. That is handoff 14's three unauthenticated
        # HTML 500s reintroduced across the whole authenticated surface, and
        # it was introduced by narrowing this very handler.
        #
        # Catching AttributeError as well would have worked and would have
        # been the wrong lesson: the real defect is that a JWT header is
        # required to be an object and nothing said so. Now it does.
        if not isinstance(header, dict):
            raise JwtError("Malformed token")
        if header.get("alg") != "HS256":
            raise JwtError("Unsupported alg")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, actual):
            raise JwtError("Bad signature")

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        # Same reason, and this one was reachable BEFORE this handoff: `exp`
        # is read below, outside the try, so a non-object payload raised
        # AttributeError there whatever this clause caught.
        if not isinstance(payload, dict):
            raise JwtError("Malformed token")
    except JwtError:
        raise
    except (ValueError, TypeError):
        # Base64 padding errors (`binascii.Error`), JSON decode errors and
        # unicode errors are all `ValueError` subclasses; `TypeError` is a
        # non-string component. Together they are exactly "this is not a
        # well-formed JWT", and they map onto JwtError so require_jwt
        # answers 401 rather than 500.
        #
        # Narrow rather than broad because this runs on every authenticated
        # request: a typo in the signature check above would otherwise be
        # reported to every caller as "malformed token" — an authentication
        # outage indistinguishable from clients sending bad tokens.
        raise JwtError("Malformed token")

    exp = payload.get("exp")
    if exp and int(exp) < int(time.time()):
        raise JwtError("Token expired")
    return payload


def _bearer_token():
    auth = request.httprequest.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _set_request_user(uid):
    if hasattr(request, "update_env"):
        request.update_env(user=uid)
    else:
        # Fallback for older Odoo 15.x where update_env wasn't yet exposed.
        request._env = request.env(user=uid)


def _missing_scopes(claims, scopes):
    """`(granted, missing)` — the ONE statement of what a token's scopes allow.

    `admin` and `*` grant everything. Split out of `require_jwt` in handoff
    30 so that a route shaping its RESPONSE by scope (`caller_holds`) asks
    the same question the gate asks, in the same words: a second copy of the
    wildcard rule is how a route comes to show an admin less than it lets
    them do.
    """
    granted = (claims or {}).get("scopes") or []
    if isinstance(granted, str):
        granted = granted.split()
    granted = set(granted)
    if not scopes or SCOPE_ADMIN in granted or "*" in granted:
        return granted, []
    return granted, [s for s in scopes if s not in granted]


def caller_holds(scope):
    """Whether the authenticated caller holds `scope`. For shaping a response.

    `require_jwt` leaves the validated claims on `request.jwt_claims`. Report
    27 said a route could not see its caller's scopes, handoff 28 ruled on
    that as an architectural fact, and it was false (GO-LIVE §14.1).
    """
    claims = getattr(request, "jwt_claims", None) or {}
    return not _missing_scopes(claims, [scope])[1]


def evidence_readable():
    """Whether the caller may read IAD's evidence (handoff 61, ruling 1 on
    report 60) — THE guard, in front of every place evidence is served:
    `GET /assets/<id>/evidence`, its file route, and the evidence items on
    `GET /assets/<id>/photos`. A caller for whom this is False is told how
    many items there are and nothing else (`evidence_count_only`)."""
    return caller_holds(SCOPE_EVIDENCE_READ)


def evidence_count_only(count):
    """What a caller without `evidence:read` is told about IAD's evidence:
    the count, in words, and nothing that opens it."""
    return {
        "readable": False,
        "count": count,
        "summary": "IAD evidence: %d item%s" % (count,
                                                "" if count == 1 else "s"),
        "requires_scope": SCOPE_EVIDENCE_READ,
    }


def require_jwt(scopes=()):
    """Validate the bearer token and apply scope check.

    Returns (claims_dict, None, None) on success.
    Returns (None, err_envelope, _) on failure — caller returns the envelope.
    """
    _new_request_id()  # ensure the id exists before any logging

    token = _bearer_token()
    if not token:
        return None, err(ERR_UNAUTHORIZED, "Missing bearer token", status=401), None

    try:
        secret = jwt_secret(request.env)
    except JwtSecretMissing as e:
        _logger.error("API misconfiguration: %s", e)
        return None, err(ERR_MISCONFIGURED, str(e), status=500), None

    try:
        claims = jwt_decode(token, secret)
    except JwtError as e:
        _logger.info(
            "JWT rejected (%s) — token_prefix=%r token_len=%d dots=%d",
            e, token[:24], len(token), token.count("."),
        )
        return None, err(ERR_UNAUTHORIZED, "Invalid token", status=401), None

    uid = claims.get("uid")
    if not uid:
        return None, err(ERR_UNAUTHORIZED, "Token missing subject", status=401), None

    # Handoff 43: deactivation takes effect NOW, not at `exp`. Until this
    # line a person deactivated at 09:00 kept using the app until their
    # access token expired (3600 s on a login token); only `/auth/refresh`
    # and `/auth/login` looked at `active`. One cached read per request, in
    # the same sentence `/auth/login` uses — BEFORE the scope check, so a
    # deactivated person reads 401 whatever route they call.
    user = request.env["res.users"].sudo().browse(int(uid))
    if not user.exists() or not user.active:
        return None, err(ERR_UNAUTHORIZED, "Account is disabled", status=401), None

    token_scopes, missing = _missing_scopes(claims, scopes)
    if missing:
        return None, err(
            ERR_FORBIDDEN,
            f"Missing required scope(s): {' '.join(missing)}",
            status=403,
            details={"required_scopes": list(scopes), "granted_scopes": sorted(token_scopes)},
        ), None

    _set_request_user(int(uid))
    request.jwt_claims = claims
    return claims, None, None


# ─── idempotency ─────────────────────────────────────────────────────

# ─── cursor pagination ───────────────────────────────────────────────

DEFAULT_PAGE_LIMIT = 50
# Lifted from 200 → 2000 so the frontend can pull resources that have to be
# eager-loaded (Locations, ~1.2k rows, used to build the tree + zone lookups)
# in a single round-trip. The list endpoints don't fan out N+1 work, so a
# bigger page is just a longer SELECT, not a longer wall-clock per record.
# External tokens are still clamped to EXTERNAL_MAX_PAGE_LIMIT (100) below.
MAX_PAGE_LIMIT = 2000
# Hard caps for tokens NOT issued to the Cadra web frontend (service
# accounts via POST /auth/token, partner integrations, ad-hoc curl).
#   - EXTERNAL_MAX_PAGE_LIMIT clamps the per-request `limit=` query param
#     (parse_limit). Asking for more silently returns this many.
#   - EXTERNAL_TOTAL_CAP clamps the *cumulative* records visible across
#     all cursor pages (paginate). External callers can never see more
#     than this many records of any resource — paginating with cursor
#     just exhausts the cap and then next_cursor goes to null. This is
#     the paywall safeguard.
# The Cadra web frontend lifts both limits by carrying `"aud": "frontend"`
# in its JWT claims (stamped by POST /auth/login at issuance time).
EXTERNAL_MAX_PAGE_LIMIT = 100
EXTERNAL_TOTAL_CAP      = 100
FRONTEND_AUDIENCE       = "frontend"

# Per-client overrides of the two external limits. They ride in the access
# token as claims, stamped at mint time from the `myservice.api.client`
# record, so the hot list path reads a claim instead of hitting the database
# on every call.
#
# The stored field, the claim and the resolved ceiling share one convention:
#
#     0   — not configured; use the external default above
#     -1  — uncapped (subject only to MAX_PAGE_LIMIT, which is a performance
#           ceiling on one SELECT, not a commercial one)
#     n>0 — that many
#
# Default 0 everywhere means a client nobody has deliberately provisioned
# behaves exactly as it did before this existed, and a token minted for one
# is byte-identical to the token it used to get.
CLAIM_MAX_PAGE_LIMIT   = "max_page_limit"
CLAIM_TOTAL_RECORD_CAP = "total_record_cap"
LIMIT_UNCAPPED         = -1


def encode_cursor(payload):
    """Opaque base64url JSON cursor. Don't decode on the client side —
    treat as an opaque token."""
    return _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def decode_cursor(token):
    """Decode a cursor token, returning the payload dict.

    Absent or empty → `{}`, which means "start at the beginning". That is a
    different input and it keeps its answer.

    **Anything else that is not a cursor we issued raises `BadFilter`, which
    `cadra_endpoint` turns into a 400.** This used to return `{}` too, and
    that is a BREAKING change made deliberately (docs/api/CHANGELOG.md,
    handoff 22). The old behaviour meant a caller paging with a corrupted
    cursor silently restarted at page one while believing it was on page
    three — walking the same records again, or reading a later page as
    empty and concluding the register had ended. It was documented, and
    documented silent degradation is still silent degradation: an answer
    that looks like an answer is worse than a refusal. A client sending a
    cursor it did not get from us has a bug, and a 400 is the only way it
    finds out.

    The payload's SHAPE is checked here too, not just its encoding. A token
    that decodes to valid JSON which is not an object — `[1,2]`, `"x"`, `7`
    — used to reach `"last_id" in cursor_data`, where a list answered False
    (another silent restart) and an int raised `TypeError` inside
    `paginate` for a 500. And a `last_id` that is not an integer reached a
    bare `int()` in the same place. Both are caller input and both are now
    the same 400.
    """
    if not token:
        return {}
    try:
        payload = json.loads(_b64url_decode(token).decode("utf-8"))
    except (ValueError, TypeError):
        # A cursor is opaque caller input; anything that is not our own
        # base64url JSON is a caller error. Narrowed so it cannot also
        # absorb a fault in `_b64url_decode` itself.
        raise BadFilter(
            "`cursor` is not a cursor this API issued. Omit it to start at "
            "the beginning, or send back the `next_cursor` from your last "
            "page unmodified.",
            details={"cursor": token},
        )
    if not isinstance(payload, dict):
        raise BadFilter(
            "`cursor` is not a cursor this API issued. Omit it to start at "
            "the beginning, or send back the `next_cursor` from your last "
            "page unmodified.",
            details={"cursor": token},
        )
    if "last_id" in payload:
        try:
            payload["last_id"] = int(payload["last_id"])
        except (TypeError, ValueError):
            raise BadFilter(
                "`cursor` is not a cursor this API issued. Omit it to start "
                "at the beginning, or send back the `next_cursor` from your "
                "last page unmodified.",
                details={"cursor": token},
            )
    return payload


def _request_is_frontend():
    """True when the validated JWT claims identify the Cadra web frontend
    (i.e. issued via POST /auth/login with `aud=frontend`). False for
    service accounts, external integrations, or when the auth layer
    didn't run (e.g. open endpoints that don't gate on token claims).

    This is kept as a second route to "uncapped" alongside the per-client
    fields below. It is NOT the primary one any more: `aud` is stamped only
    by /auth/login, so keying the cap on it alone enforced "browsers are
    trusted, programs are not" when the rule intended was "our own systems
    are trusted, third parties are not" — and it pointed a partner paywall
    at Vendra and at the audit client, both of which hold machine
    credentials.
    """
    claims = getattr(request, "jwt_claims", None) or {}
    return claims.get("aud") == FRONTEND_AUDIENCE


def _limit_claim(name):
    """Read one integer limit claim off the validated token. 0 when absent
    or unparseable — i.e. fall back to the external default, never to
    'uncapped'. A malformed claim must not widen access."""
    claims = getattr(request, "jwt_claims", None) or {}
    try:
        return int(claims.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def client_limit_claims(client):
    """The limit claims to stamp into a token minted for `client`.

    Only non-zero values are stamped, so an unconfigured client's token
    carries no new claims at all.
    """
    if not client:
        return {}
    out = {}
    if client.max_page_limit:
        out[CLAIM_MAX_PAGE_LIMIT] = int(client.max_page_limit)
    if client.total_record_cap:
        out[CLAIM_TOTAL_RECORD_CAP] = int(client.total_record_cap)
    return out


def page_limit_ceiling():
    """The most records this caller may pull in ONE page."""
    if _request_is_frontend():
        return MAX_PAGE_LIMIT
    configured = _limit_claim(CLAIM_MAX_PAGE_LIMIT)
    if configured == LIMIT_UNCAPPED:
        return MAX_PAGE_LIMIT
    if configured > 0:
        # MAX_PAGE_LIMIT still applies: it bounds the cost of a single
        # SELECT and is not the commercial control.
        return min(configured, MAX_PAGE_LIMIT)
    return EXTERNAL_MAX_PAGE_LIMIT


def record_cap():
    """The most records of any one resource this caller may see across all
    cursor pages — the paywall safeguard — or None when uncapped."""
    if _request_is_frontend():
        return None
    configured = _limit_claim(CLAIM_TOTAL_RECORD_CAP)
    if configured == LIMIT_UNCAPPED:
        return None
    if configured > 0:
        return configured
    return EXTERNAL_TOTAL_CAP


def parse_limit(kwargs):
    """Read and clamp `limit` from kwargs. Default DEFAULT_PAGE_LIMIT;
    ceiling from `page_limit_ceiling()` — MAX_PAGE_LIMIT for the Cadra web
    frontend and for a client provisioned uncapped, the client's own
    `max_page_limit` when it has one, EXTERNAL_MAX_PAGE_LIMIT otherwise.

    A capped caller can still paginate via `cursor` up to `record_cap()`.

    CLAMPING and REFUSING are different answers to different inputs, and both
    are deliberate. `?limit=100000` is clamped, silently, and that is the
    published contract — the ceiling is per-credential, so a caller cannot
    know it in advance and being refused for asking would be unhelpful.
    `?limit=all` is refused: it is not a number at all, and quietly serving
    50 rows to a caller who believes they asked for everything is the same
    false statement the filters used to make.
    """
    raw = kwargs.get("limit", DEFAULT_PAGE_LIMIT)
    limit = parse_int("limit", raw, null_is_absent=False, minimum=1)
    if limit is None:
        limit = DEFAULT_PAGE_LIMIT
    return max(1, min(limit, page_limit_ceiling()))


TRUNCATION_REASON = (
    "This credential is limited to the first {cap} records of any query. "
    "Filter the query, or contact WestMetro to raise the limit."
)


def flag_truncation(cap, total):
    """Record that the record cap bit on this request.

    Stored on `request` rather than returned, because the response envelope
    is built by `ok()` and a list endpoint's `data` is an ARRAY — there is
    no `data._warnings` to hang it off, and a truncation an endpoint has to
    remember to forward is a truncation that will eventually go unreported.
    `ok()` picks it up for every route, including ones written later.
    """
    if total <= cap:
        return
    request.cadra_truncation = {
        "cap": cap,
        "total": total,
        "reason": TRUNCATION_REASON.format(cap=cap),
    }


def truncation_warning():
    """The truncation block for this request, or None."""
    return getattr(request, "cadra_truncation", None)


# Resources the total_record_cap does not apply to, and the reason.
#
# A chain of custody is not a page of a register. It is ONE ASSET'S COMPLETE
# RECORD — bounded by how often that asset changed hands, not by how much
# data a tenant holds — and the entire finding `nrs.asset.custody` was built
# to close is that **a truncated chain cannot be told from a complete one**.
# An auditor handed the first 100 links of a 140-link chain has no way to
# know, and no way to trust the part they can see. Capping it would put the
# defect back in the one place a handoff was just spent removing it.
#
# `include=custody` on the asset serializer has always been exempt because it
# does not paginate at all; this is what makes the dedicated route agree with
# it instead of quietly answering a shorter version of the same question.
#
# `total_estimate` is unaffected either way — it is always the true count.
# The per-page ceiling is unaffected too: it bounds the cost of one SELECT
# and is not the commercial control. A capped client walks the whole chain
# with the cursor.
CAP_EXEMPT_REASON_CUSTODY = "a chain of custody is complete or it is evidence of nothing"


def paginate(model, domain, *, limit, cursor=None, order="id", uncapped=False,
             descending=False, keyset_field=None):
    """Cursor-paginate `model.search(domain)`.

    Returns (records, next_cursor_or_None, total_estimate).

    `total_estimate` is ALWAYS a `search_count` of the caller's own,
    unclamped domain. It used to report the size of the capped window
    instead, so an external token asking `jaizbankplc` for its assets
    received 100 rows and was told there were 100, of 2,316 — a false
    statement about the register, made by a government system, that neither
    the caller nor we would ever find out about. Whatever the cap does to
    the rows, the count is a fact.

    There is deliberately no branch below in which that line does not run,
    and `tests/test_source_guards.py` asserts that by construction.

    Capped callers (`record_cap()`) are bounded to the first N records of
    the domain, sorted by `order`. Pagination still works inside that
    window; once the cumulative records served exceed the cap, next_cursor
    goes to null — and `flag_truncation` makes the response say so.

    `uncapped=True` exempts one resource from the record cap. It exists for
    exactly one caller today — see CAP_EXEMPT_REASON_CUSTODY above, which is
    where the reasoning lives, not here. It does NOT touch `total_estimate`,
    which is the true count on every path.

    `descending=True` walks the same keyset backwards — newest id first —
    for a caller that asked for it. Three things move together and none of
    them can move alone:

      * the ORDER becomes `id desc`;
      * the CURSOR COMPARATOR becomes `<` rather than `>`, because a keyset
        walk reads "everything after the last row I saw" and which side that
        is depends on the direction;
      * the cursor PAYLOAD gains `desc: True`, so a token says which walk
        issued it.

    That third one is why a direction is not simply a query parameter the
    route reads and forgets. A cursor from an ascending walk replayed
    against a descending one is a request nobody can answer honestly: the
    comparator would page AWAY from the rows the caller has not seen and the
    response would look like a short, complete list. So a mismatch is a
    `BadFilter` — a 400 — and never a best guess.

    An ascending token is byte-for-byte what it has always been: `desc` is
    added only on the descending path, so every cursor already in flight,
    and every cursor an existing integration holds, keeps working unchanged.

    Descending is defined for the DEFAULT `id` keyset only. Passing it with
    a custom `order` raises, rather than silently ordering one way and
    paging the other — no caller does this today and the assertion is here
    so none starts by accident.

    `keyset_field` (handoff 60 §2a) walks ascending by a stored, non-null
    column first and `id` second — `GET /candidates?sort=oldest`, by
    `register_state_since`, so the unit that has waited longest is on the
    first page. The cursor carries the field's name and the last row's
    value beside its id (`by`, `after`), and a cursor issued for another
    walk is a `BadFilter`, for the reason above. Ascending only.
    """
    if keyset_field and descending:
        raise ValueError(
            "paginate(keyset_field=...) walks ascending only; got "
            "descending=True.")
    if descending and order != "id":
        raise ValueError(
            "paginate(descending=True) is defined for the default `id` "
            "keyset only; got order=%r. Ordering one way and paging the "
            "other returns a page that is neither." % (order,))

    cursor_data = decode_cursor(cursor) if cursor else {}
    effective_domain = list(domain)

    # The direction the TOKEN was issued for, against the direction this
    # request asked for. Absent means ascending: that is what every cursor
    # issued before this parameter existed means, and it is why the
    # ascending payload stays unchanged.
    if cursor and cursor_data.get("by") != keyset_field:
        raise BadFilter(
            "`cursor` was issued for a walk ordered by %s and this request "
            "asks for one ordered by %s. Restart the walk without a cursor, "
            "or keep `sort` the same for every page of it."
            % (cursor_data.get("by") or "id", keyset_field or "id"),
            details={"cursor": cursor})
    if cursor and bool(cursor_data.get("desc")) != bool(descending):
        raise BadFilter(
            "`cursor` was issued for a %s walk and this request asks for a "
            "%s one. Restart the walk without a cursor, or keep `sort` the "
            "same for every page of it."
            % ("descending" if cursor_data.get("desc") else "ascending",
               "descending" if descending else "ascending"),
            details={"cursor": cursor,
                     "cursor_direction":
                         "descending" if cursor_data.get("desc") else "ascending",
                     "requested_direction":
                         "descending" if descending else "ascending"},
        )

    effective_order = "id desc" if descending else order
    if keyset_field:
        effective_order = "%s asc, id asc" % keyset_field

    total = model.search_count(domain)

    # Compute the visible window once, before any cursor filtering, so the
    # cap survives across pages.
    cap = None if uncapped else record_cap()
    if cap is not None:
        # Descending, this window is the NEWEST `cap` records rather than
        # the oldest. That is the same sentence as before — "the first N
        # records of the domain, sorted by `order`" — read in the direction
        # the caller asked for, and it is the right half to give them: a
        # capped client walking newest-first wants the recent end.
        allowed = model.search(domain, order=effective_order, limit=cap)
        if not allowed:
            return model.browse([]), None, total
        effective_domain.append(("id", "in", allowed.ids))
        flag_truncation(cap, total)

    if "last_id" in cursor_data and keyset_field:
        after = cursor_data.get("after")
        try:
            # A cursor is unsigned: a tampered `after` is caller input and a
            # 400, never a 500 from the ORM's datetime parse (handoff 22).
            valid = isinstance(after, str) and bool(
                fields.Datetime.to_datetime(after))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise BadFilter("`cursor` is not a cursor this API issued.",
                            details={"cursor": cursor})
        effective_domain += [
            "|", (keyset_field, ">", after),
            "&", (keyset_field, "=", after),
            ("id", ">", cursor_data["last_id"])]
    elif "last_id" in cursor_data:
        # Already an int: `decode_cursor` coerced it or refused the request.
        # The comparator follows the direction — see the docstring.
        effective_domain.append(
            ("id", "<" if descending else ">", cursor_data["last_id"]))

    # Fetch one extra to know if there's a next page
    records = model.search(effective_domain, order=effective_order,
                           limit=limit + 1)
    # capped-count-ok: `records` IS the page. This asks how many rows
    # came back from the fetch, not how many exist — `total` above is
    # the count of the register and is the number the caller is given.
    has_more = len(records) > limit
    page = records[:limit]

    next_cursor = None
    if has_more and page:
        payload = {"last_id": page[-1].id}
        if keyset_field:
            value = page[-1][keyset_field]
            payload["by"] = keyset_field
            payload["after"] = (fields.Datetime.to_string(value)
                                if isinstance(value, _dt.datetime)
                                else str(value))
        if descending:
            # Added ONLY here. An ascending token keeps the exact shape it
            # has always had, so nothing already holding one is affected.
            payload["desc"] = True
        next_cursor = encode_cursor(payload)

    return page, next_cursor, total


# ─── idempotency ─────────────────────────────────────────────────────

IDEMPOTENCY_HEADER = "X-Idempotency-Key"
IDEMPOTENCY_TTL_SECONDS = 24 * 3600
IDEMPOTENCY_KEY_MAX_LENGTH = 128


class IdempotencyKeyError(Exception):
    """The caller sent an X-Idempotency-Key we cannot honour.

    Raised rather than returning None so the endpoint decorator can answer
    400. Silently downgrading to a non-idempotent create would leave the
    caller believing it was protected against a retry storm when it was
    not, and there is no way for it to detect the difference.
    """

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def idempotency_key():
    """Return the inbound X-Idempotency-Key, or None if absent.

    Empty strings are absent. Keys are case-sensitive opaque tokens —
    typically UUIDs from the client. An over-long key raises
    IdempotencyKeyError; see that class for why it is not just dropped.
    """
    raw = (request.httprequest.headers.get(IDEMPOTENCY_HEADER) or "").strip()
    if not raw:
        return None
    if len(raw) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise IdempotencyKeyError(
            f"`{IDEMPOTENCY_HEADER}` must be at most "
            f"{IDEMPOTENCY_KEY_MAX_LENGTH} characters",
            details={
                "header": IDEMPOTENCY_HEADER,
                "max_length": IDEMPOTENCY_KEY_MAX_LENGTH,
                "received_length": len(raw),
            },
        )
    return raw


def idempotency_check(key, endpoint_path):
    """Return a cached response body for (key, endpoint), or None.

    The caller is responsible for short-circuiting with the returned body.
    """
    if not key:
        return None
    rec = request.env["myservice.api.idempotency"].sudo().search(
        [("key", "=", key), ("endpoint", "=", endpoint_path)], limit=1
    )
    if not rec:
        return None
    if rec.expires_at and rec.expires_at < fields.Datetime.now():
        rec.unlink()
        return None
    try:
        return json.loads(rec.response_body)
    except (ValueError, TypeError):
        # An unreadable row is worse than no row: it can never be replayed,
        # and it holds the (key, endpoint) slot for the full TTL, so every
        # retry under that key hits the unique constraint and gets a 409
        # telling it to retry. Drop it and let this request re-create it.
        _logger.warning("discarding unparseable idempotency row %s for %s",
                        rec.id, endpoint_path)
        rec.unlink()
        return None


def idempotency_store(key, endpoint_path, body):
    """Persist the response body under (key, endpoint) for IDEMPOTENCY_TTL_SECONDS.

    Raises psycopg2.errors.UniqueViolation if a concurrent request under the
    same key got there first — see `_idempotency_replay_after_race`.
    """
    if not key:
        return
    now = fields.Datetime.now()
    request.env["myservice.api.idempotency"].sudo().create({
        "key": key,
        "endpoint": endpoint_path,
        "response_body": json.dumps(body, default=str),
        "expires_at": fields.Datetime.add(now, seconds=IDEMPOTENCY_TTL_SECONDS),
    })


def _idempotency_replay_after_race(key, endpoint_path):
    """Resolve a lost race on (key, endpoint) into the winner's response.

    We roll back the whole request, not just the failed cache insert. The
    losing request has by this point performed its own write — a second
    asset, a second location — and keeping that while returning the winner's
    body would be the duplicate-create the key exists to prevent. Discarding
    it and replaying the winner is what the caller asked for when it sent the
    header: exactly one effect, one response, however many times it retries.
    """
    request.env.cr.rollback()
    cached = idempotency_check(key, endpoint_path)
    if cached is not None:
        # Logged because a race is otherwise invisible: the caller sees a
        # normal success and nothing records that a duplicate write was
        # discarded. An operator needs to know if this is happening often.
        _logger.info("idempotency race on %s — rolled back the duplicate and "
                     "replayed the stored response", endpoint_path)
        return cached
    _logger.warning("idempotency race on %s — key claimed but no readable "
                    "response to replay; answering 409", endpoint_path)
    # The winner's row is gone or unreadable (expired between the violation
    # and this read, or its transaction rolled back after ours saw the
    # conflict). We have nothing truthful to return and our own work is
    # already discarded, so say so rather than invent a response.
    return err(
        ERR_CONFLICT,
        "A concurrent request with this idempotency key is still in flight. "
        "Retry with the same key.",
        status=409,
        details={"header": IDEMPOTENCY_HEADER, "endpoint": endpoint_path},
    )


# ─── request param accessor ──────────────────────────────────────────

def get_params():
    """Return a dict of params for the current request body or query string.

    GET / DELETE / HEAD → query string (werkzeug MultiDict → plain dict;
                          values are strings, callers coerce types as needed)
    POST / PATCH / PUT  → parsed JSON body (flat, no `params` wrapper)

    Path parameters (e.g. <int:id>) are NOT in here — Odoo's router passes
    them as named method args. Use this helper for everything else.
    """
    method = request.httprequest.method.upper()
    if method in ("GET", "DELETE", "HEAD"):
        return dict(request.httprequest.args)
    # Try werkzeug's get_json first; fall back to manual JSON.loads on the
    # raw body. Odoo's HttpRequest sometimes consumes the body stream before
    # the controller runs, so we can't always rely on get_json() at the
    # werkzeug layer — use raw data as a safety net.
    #
    # `cache=True` is what makes that safety net exist. With cache=False,
    # get_json consumes the stream without keeping it, so the get_data() call
    # below returns b'' and the fallback can never fire — the request comes
    # back as {} and the endpoint reports its required fields missing. That is
    # an intermittent 400 on whichever call lost the body, `/auth/token`
    # included, which is the first endpoint any integration makes.
    try:
        body = request.httprequest.get_json(silent=True, force=True, cache=True)
    except Exception:
        # catch-all: unknown — `silent=True` already means werkzeug returns
        # None for a body it cannot parse, so nothing here is SUPPOSED to
        # raise. What does is a property of whichever werkzeug ships with
        # the image, and the raw-body fallback below recovers from it. It
        # goes to the log so that a version bump changing this shows up as
        # a line somebody can read rather than as intermittent 400s.
        _logger.warning("get_json raised despite silent=True; "
                        "falling back to the raw body", exc_info=True)
        body = None
    if not isinstance(body, dict):
        raw = request.httprequest.get_data(cache=True, as_text=False)
        if raw:
            try:
                body = json.loads(raw)
            except (ValueError, TypeError):
                # The caller sent a body that is not JSON. Expected, and
                # the endpoint's own required-field validation is what
                # tells them so.
                body = None
    return body if isinstance(body, dict) else {}


# ─── multipart bodies ────────────────────────────────────────────────
#
# Handoff 61 §5: the first route INSIDE the envelope whose body is a form
# with a file in it (`POST /assets/<id>/photos`). The only multipart route
# before it, the employee xlsx import, is a raw `@http.route` outside
# `cadra_route` and reads `request.httprequest.files` by hand — so every rule
# the envelope gives a JSON body (one refusal shape for a key the route does
# not read, nothing written on a refusal) had no multipart equivalent. This
# is that equivalent, written once, for every upload that comes after.
#
# What it does NOT need to do, because `cadra_endpoint` already has:
# authentication and scopes (before the route runs), the envelope, the
# rollback on an exception, and IDEMPOTENCY — `X-Idempotency-Key` is keyed
# on (key, path) and replayed by the decorator before the route is called,
# so a retried upload under the same key answers the stored 201 and stores
# nothing twice, exactly as a JSON create does. (As on every route, the key
# is not compared with the body: the same key with a different picture is
# the first picture's answer.)
#
# Odoo parses the form BEFORE any route runs (`HttpDispatcher.dispatch`
# builds `request.params` from it), so a body over Odoo's own ceiling
# (`DEFAULT_MAX_CONTENT_LENGTH`, 128 MiB) is refused by Odoo with its own
# page before this code is reached. A route's own cap (300 KB for a photo)
# is the route's to state, in words, from `Upload.size`.

MULTIPART_FORM_DATA = "multipart/form-data"


class Upload:
    """One file part of a multipart body, as `get_multipart` hands it over.

    `filename` and `declared_type` are what the CLIENT said — informational
    only, and never a basis for deciding what the bytes are; a route that
    cares sniffs the bytes. `size` is measured from the part itself, so a
    route can refuse an oversized file in words without reading it.
    """

    __slots__ = ("field", "filename", "declared_type", "size", "_storage",
                 "_data")

    def __init__(self, field, storage):
        self.field = field
        self.filename = storage.filename or ""
        self.declared_type = storage.mimetype or None
        self._storage = storage
        self._data = None
        stream = storage.stream
        try:
            here = stream.tell()
            stream.seek(0, 2)
            self.size = stream.tell()
            stream.seek(here)
        except (AttributeError, OSError, ValueError):
            # A stream that cannot seek is read once, here, and kept.
            self._data = storage.read()
            self.size = len(self._data)

    def read(self, limit=None):
        """The bytes — at most `limit` of them when one is given."""
        if self._data is not None:
            return self._data if limit is None else self._data[:limit]
        stream = self._storage.stream
        stream.seek(0)
        return stream.read() if limit is None else stream.read(limit)


def get_multipart(*, file_fields=(), text_fields=(), required=()):
    """Read a `multipart/form-data` body for a `cadra_route`, once.

    Returns `(values, uploads, None)` — `values` the text fields as stripped
    strings, `uploads` an `Upload` per file field — or `(None, None,
    envelope)`, which the route returns as it stands. Every refusal is made
    BEFORE the route has written anything, and says what it refused:

    * **not a form** — `400 invalid_request`, naming the content type that
      arrived (a JSON body sent to an upload route is told so);
    * **a part this route does not read** — `refuse_unwritable`'s `400
      invalid_request` with `rejected_fields` and `writable`, the refusal a
      JSON body gets for an unknown key (rule 3): an integration must never
      guess which parts were used;
    * **a part in the wrong shape** — a file field sent as text, or a text
      field sent as a file — `400 invalid_request`;
    * **a part sent twice** — `400 invalid_request`, naming the count:
      which of two pictures was meant is a guess;
    * **a required part missing** (a file part with no name and no bytes,
      which a browser sends for an empty file input, is missing) — `400
      validation_failed`, naming it.

    Query-string arguments are not read, exactly as `get_params` ignores
    them on a POST.
    """
    http_request = request.httprequest
    received = http_request.mimetype or None
    if received != MULTIPART_FORM_DATA:
        return None, None, err(
            ERR_INVALID_REQUEST,
            "This route takes a multipart/form-data body (a file and its "
            "fields), not %s. Nothing was written."
            % (received or "a body with no content type"),
            details={"expected_content_type": MULTIPART_FORM_DATA,
                     "received_content_type": received})
    form, files = http_request.form, http_request.files
    declared = set(file_fields) | set(text_fields)
    sent = list(dict.fromkeys(list(form.keys()) + list(files.keys())))
    rejected = [name for name in sent if name not in declared]
    if rejected:
        return None, None, refuse_unwritable(
            rejected, declared,
            hint="These are the names of the parts of the multipart body "
                 "this route reads.")
    for name in sent:
        is_file = name in file_fields
        if is_file and name in form:
            return None, None, err(
                ERR_INVALID_REQUEST,
                "`%s` must be sent as a file part (with a filename), not as "
                "text. Nothing was written." % name,
                details={"field": name, "expected": "file"})
        if not is_file and name in files:
            return None, None, err(
                ERR_INVALID_REQUEST,
                "`%s` is a text field, not a file. Nothing was written."
                % name,
                details={"field": name, "expected": "text"})
        count = len(files.getlist(name) if is_file else form.getlist(name))
        if count > 1:
            return None, None, err(
                ERR_INVALID_REQUEST,
                "Send one `%s` per request; this body carried %d. Nothing "
                "was written." % (name, count),
                details={"field": name, "count": count})
    uploads = {}
    for name in file_fields:
        storage = files.get(name)
        if storage is None:
            continue
        upload = Upload(name, storage)
        if not upload.filename and not upload.size:
            continue  # an empty file input: nothing was chosen
        uploads[name] = upload
    values = {name: (form.get(name) or "").strip() for name in text_fields
              if name in form}
    missing = [name for name in required
               if name not in uploads and not values.get(name)]
    if missing:
        return None, None, err(
            ERR_VALIDATION_FAILED,
            "Required: %s. Nothing was written."
            % ", ".join("`%s`" % name for name in missing),
            details={"missing": missing})
    return values, uploads, None


# ─── HTTP response helper ────────────────────────────────────────────

def _http_response(body, success_status=200):
    """Render the PRD envelope as a real HTTP response.

    Status code derivation:
      - if body has an `error` key, pull `error.details.http_status`
      - else, `success_status` (the @cadra_route default — usually 200,
        201 for resource-create POSTs without a path id)

    Note on Odoo 15 quirk: `request.make_response(data, headers, cookies)`
    does NOT accept a `status=` kwarg. We set the status on the returned
    werkzeug Response after construction.
    """
    status = success_status
    if isinstance(body, dict) and "error" in body:
        # A handler that returned a bare {"error": "some string"} is not an
        # envelope — it used to crash here on `.get`, and the caller got a
        # 500 HTML page from werkzeug with no request_id and no code. Treat a
        # non-conforming error as a server fault and SAY so, in the envelope.
        detail = body.get("error")
        if isinstance(detail, dict):
            status = (detail.get("details") or {}).get("http_status", 400)
        else:
            _logger.error("handler returned a non-envelope error: %r", detail)
            body = err(ERR_INTERNAL,
                       "The endpoint returned a malformed error",
                       details={"returned": detail}, status=500)
            status = 500
    response = request.make_response(
        json.dumps(body, default=str),
        headers=[("Content-Type", "application/json; charset=utf-8")],
    )
    response.status_code = status
    return response


# ─── client value errors ─────────────────────────────────────────────
#
# The ORM signals a value it cannot coerce by raising a bare ValueError, which
# used to reach the decorator's catch-all and answer 500. A 500 tells an
# integration the fault is ours and the request is worth retrying, so a
# malformed field became an infinite retry loop instead of a fixable error.
# Each pattern below is matched narrowly on the message the ORM (or CPython)
# actually produces: a ValueError we cannot place is our bug, not the
# caller's, and still returns 500.

# odoo/orm/fields_selection.py — "Wrong value for %s: %r", %s being model.field
_SELECTION_VALUE_RE = re.compile(
    r"^Wrong value for (?P<model>[\w.]+)\.(?P<field>\w+): (?P<value>.*)$"
)
# CPython's own coercion messages, raised out of Date/Datetime/Float/Integer
# conversion. These do NOT name the field — the ORM has lost that context by
# the time they surface — so the envelope echoes the offending value instead.
_COERCION_RES = (
    (re.compile(r"^time data (?P<value>.*) does not match format (?P<fmt>.*)$"),
     "date", "is not a valid date"),
    (re.compile(r"^Invalid (?:date|datetime|isoformat) string: (?P<value>.*)$"),
     "date", "is not a valid date"),
    (re.compile(r"^could not convert string to float: (?P<value>.*)$"),
     "number", "is not a valid number"),
    (re.compile(r"^invalid literal for int\(\) with base 10: (?P<value>.*)$"),
     "integer", "is not a valid integer"),
)


def selection_values(model_name, field_name, fallback):
    """The accepted values for a Selection field, on the READ path. Never empty.

    Reads the model's own Selection so a value the model gains is accepted by
    the filter that publishes it on the same day, and falls back to the
    published tuple if it cannot — never to "skip the check". A validator
    that disables itself on failure puts `?state=bogus` back to answering
    `200 []`, which is the silent degradation the validation exists to
    remove.

    Deliberately NOT `_selection_allowed_values` below, and the difference is
    the whole reason this exists: that one calls `cr.rollback()` when it
    cannot read a field, because it runs on the error path AFTER a failed
    write where the cursor is already dirty. This runs on the happy path of
    every list request, where rolling back a cursor nobody asked it to touch
    would turn a transient read failure into a corrupted response. The
    ruling is landed (docs/DECISIONS.md, 2026-09-06).

    Reads the registry, not the database: `_fields[...]` is Python and
    `get_values` resolves a Selection's own list. `ir.model.fields.selection`
    rows exist for studio-added values only; none of the fields this is used
    for has any.
    """
    try:
        field = request.env[model_name]._fields[field_name]
        if field.type == "selection":
            values = list(field.get_values(request.env))
            if values:
                return values
    except Exception:
        # catch-all: unknown — broad on purpose. The FALLBACK is the safe
        # answer here, not the exception: whatever goes wrong reading the
        # model, the published tuple still rejects a typo, which is the
        # control. Narrowing would mean guessing what `get_values` can raise
        # and letting the guess decide whether every list request 500s.
        _logger.warning(
            "could not read %s.%s selection; falling back to the published "
            "values", model_name, field_name, exc_info=True)
    return list(fallback)


def _selection_allowed_values(model_name, field_name):
    """The accepted values for a Selection field, or None if we cannot read them.

    Enrichment only: a 400 naming the offending field already beats the 500
    this replaced. Any failure rolls back first — this runs after the
    decorator has rolled back once, and leaving a second aborted transaction
    behind would surface as the bare non-enveloped 500 we are removing.
    """
    try:
        field = request.env[model_name]._fields[field_name]
        if field.type != "selection":
            return None
        return list(field.get_values(request.env))
    except Exception:
        # catch-all: unknown — this runs AFTER the route decorator has
        # already rolled back once, on a transaction that may be in any
        # state, purely to enrich an error message. Narrowing it would mean
        # predicting what a poisoned cursor raises; the rollback below is
        # the guarantee that matters and it must run whatever arrives.
        _logger.warning("could not resolve selection values for %s.%s",
                        model_name, field_name, exc_info=True)
        request.env.cr.rollback()
        return None


def _client_value_error(exc):
    """Turn an ORM value-coercion ValueError into a 400 envelope.

    Returns None if `exc` is not one of the known client-error shapes, so the
    caller falls through to 500.
    """
    message = str(exc) or ""

    match = _SELECTION_VALUE_RE.match(message)
    if match:
        model_name, field_name = match.group("model"), match.group("field")
        return err(
            ERR_VALIDATION_FAILED,
            f"`{field_name}` is not one of the accepted values",
            status=400,
            details={
                "field": field_name,
                "model": model_name,
                "received": match.group("value").strip("'\""),
                # So an integration that sent a value we reject never has to
                # read our source to find the set we accept.
                "allowed_values": _selection_allowed_values(model_name, field_name),
            },
        )

    for pattern, expected, phrasing in _COERCION_RES:
        match = pattern.match(message)
        if not match:
            continue
        value = match.group("value").strip("'\"")
        # Logged because this shape is also reachable from a genuine bug in
        # our own code passing a bad string to the ORM; a 400 would otherwise
        # bury it.
        _logger.warning("client value error (%s): %s", expected, message)
        return err(
            ERR_VALIDATION_FAILED,
            f"`{value}` {phrasing}",
            status=400,
            # The ORM does not name the field for these, and inferring it from
            # the traceback would be guesswork. The value is echoed so the
            # caller can find which of its fields carried it.
            details={"received": value, "expected_type": expected, "field": None},
        )

    return None


# ─── endpoint decorator ──────────────────────────────────────────────

def cadra_endpoint(scopes=(), idempotent=False, success_status=200):
    """Auth + scope-check + idempotency + envelope-wrap + JSON HTTP response.

    Apply BELOW Odoo's @http.route decorator (or use the `cadra_route`
    convenience wrapper in v1.py which does both). The wrapped function
    returns one of:
      - a plain dict  → wrapped via ok() as the `data` payload
      - a plain list  → wrapped via ok() as the `data` payload
      - a result of ok()/err() → passed through unchanged

    The wrapper turns that into a real HTTP response with Content-Type:
    application/json and the right status code.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _new_request_id()

            # Auth + scope
            _, envelope, _ = require_jwt(scopes)
            if envelope is not None:
                return _http_response(envelope)

            # Idempotency (only for write methods — read methods are naturally
            # idempotent and don't need caching)
            method = request.httprequest.method.upper()
            is_write = method in ("POST", "PUT", "PATCH", "DELETE")
            endpoint_path = request.httprequest.path
            # Validate the header's length on EVERY route, not only the ones
            # that honour it. A caller sending a 200-character key has a bug
            # worth knowing about wherever it sends it, and finding out only
            # on the subset of endpoints that cache is how you ship the bug.
            # The header itself is not rejected on routes that ignore it —
            # a caller harmlessly spraying it should not start failing.
            try:
                supplied_key = idempotency_key()
            except IdempotencyKeyError as e:
                return _http_response(err(
                    ERR_INVALID_REQUEST, str(e), status=400, details=e.details,
                ))
            ikey = supplied_key if (idempotent and is_write) else None

            if ikey:
                cached = idempotency_check(ikey, endpoint_path)
                if cached is not None:
                    return _http_response(cached, success_status=success_status)

            # Call the endpoint
            try:
                result = fn(*args, **kwargs)
            # ORDER IS LOAD-BEARING. In Odoo 19 `AccessError`, `MissingError`
            # and `ValidationError` are ALL subclasses of `UserError`:
            #
            #     AccessError.__mro__ -> AccessError, UserError, Exception
            #
            # so a `except (UserError, ValidationError)` clause placed first
            # swallows every one of them. It was, and the two clauses below it
            # were dead code: an access refusal answered `400 validation_failed`
            # and a missing record answered `400 validation_failed`, meaning two
            # published error codes — `forbidden` and `not_found` — were
            # unreachable through this path for the whole life of the envelope.
            #
            # Vendra branches on `error.code`. An authorisation failure that
            # reports itself as a validation failure tells an integrator to fix
            # their payload when the answer is to fix their credentials.
            # Specific first, `UserError` last.
            # RE-RAISED, NOT ENVELOPED. Odoo owns two retry layers ABOVE
            # this decorator, and both of them work by seeing an exception
            # come out of the dispatch:
            #
            #   * `http.py` catches `ReadOnlySqlTransaction` and re-dispatches
            #     the whole request on a read/write cursor — that is how a
            #     route that turns out to write on a read-only cursor still
            #     succeeds;
            #   * `service/model.retrying` catches `OperationalError` and
            #     `ConcurrencyError` and replays the request up to five times
            #     on a serialization failure, which is how two callers writing
            #     the same row at once both succeed.
            #
            # `except Exception` below is INSIDE both of them, so swallowing
            # these turned a condition Odoo recovers from transparently into a
            # `500 internal_error` the caller has to handle. Found by a new
            # HttpCase in this handoff: `POST /assets/<id>/transfer-custody`
            # answered 500 where `/auth/token` — which is not wrapped by this
            # decorator — retried and succeeded, in the same run, on the same
            # cursor. The unwrapped route was the one that worked.
            #
            # `IntegrityError` is deliberately NOT here: `retrying` re-raises
            # it immediately unless it is a serialization failure, and the
            # handlers below turn a unique or foreign-key violation into the
            # 409 and 400 the API publishes for them.
            except (psycopg2.errors.ReadOnlySqlTransaction,
                    psycopg2.OperationalError,
                    ConcurrencyError):
                raise
            except BadFilter as e:
                # A query parameter we could not read. Every list route also
                # catches this around its own domain builder, and this is the
                # floor UNDER those: a route that forgets the try/except, or
                # one written next year, still answers 400 rather than the
                # 500 a bare exception would produce — and a 500 tells an
                # integration to retry a request that can never succeed.
                #
                # **No rollback**, and that is the point rather than an
                # omission. Every raiser is on a READ path and none of them
                # writes: the parameter parsers are pure by construction
                # (`query_params` imports nothing, enforced by
                # `tests/test_query_param_guard.py`), and `decode_cursor`,
                # which joined them in handoff 22, runs before the first
                # query on every route that calls it. There is no
                # transaction to undo — and rolling back a clean cursor is
                # the exact behaviour that ruled `_selection_allowed_values`
                # out of the read path in the first place
                # (docs/DECISIONS.md, 2026-09-06).
                return _http_response(err(
                    ERR_INVALID_REQUEST, str(e), status=400, details=e.details,
                ))
            except AccessError as e:
                request.env.cr.rollback()
                return _http_response(err(ERR_FORBIDDEN, str(e), status=403))
            except GateRefused as e:
                # A receipt-gate refusal from the model — BEFORE the generic
                # `UserError` below, which it subclasses. One mapping for
                # every route that can meet one (handoff 58, D3): the gate
                # routes, the affix route, a move, a custody change, a
                # disposal, a receipt. An exception, so the rollback below
                # undoes anything the request had begun.
                request.env.cr.rollback()
                return _http_response(gate_refusal(e))
            except MissingError as e:
                request.env.cr.rollback()
                return _http_response(err(ERR_NOT_FOUND, str(e), status=404))
            except (UserError, ValidationError) as e:
                # Odoo-level validation: ondelete, @api.constrains,
                # explicit raise UserError in business code.
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED, str(e) or e.__class__.__name__,
                    status=400,
                ))
            except psycopg2.errors.UniqueViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_CONFLICT, "Unique constraint violation",
                    status=409,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except psycopg2.errors.ForeignKeyViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED,
                    "Referenced record does not exist",
                    status=400,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except psycopg2.errors.NotNullViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED,
                    f"Required field missing: {e.diag.column_name}",
                    status=400,
                    details={"column": e.diag.column_name,
                             "table": e.diag.table_name},
                ))
            except psycopg2.IntegrityError as e:
                # Catch-all for any other DB integrity issue (check
                # constraints, exclusion constraints, etc.).
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED, "Database constraint violation",
                    status=400,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except ValueError as e:
                # The ORM signals an uncoercible value with a bare ValueError —
                # a bad enum, an unparseable date, a non-numeric cost. Those
                # are client errors, but they were reaching the catch-all
                # below and answering 500, which tells an integrator to retry
                # a request that can never succeed. Only the recognised shapes
                # are reinterpreted; anything else is our bug and still 500s.
                request.env.cr.rollback()
                envelope = _client_value_error(e)
                if envelope is None:
                    _logger.exception("Unhandled error in %s", endpoint_path)
                    return _http_response(
                        err(ERR_INTERNAL, "Unhandled server error", status=500))
                return _http_response(envelope)
            except psycopg2.DataError as e:
                # Postgres rejecting a literal for a column's type — most often
                # a non-integer sent for a many2one id, which the ORM passes
                # straight through. DataError is not an IntegrityError, so it
                # was falling to the catch-all and answering 500 as well.
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED,
                    "A field value is not valid for its type",
                    status=400,
                    details={"db_detail": (str(e.diag.message_primary or e) or "").strip()
                                          or None,
                             "column": e.diag.column_name},
                ))
            except (psycopg2.errors.UndefinedColumn,
                    psycopg2.errors.UndefinedTable) as e:
                # The code is ahead of this tenant's database: a stored field
                # or a model landed and this database was not upgraded
                # (handoff 57 finding P8 — the register filter reads
                # `register_state` on EVERY asset search, so one missed
                # tenant fails every list). Said for what it is rather than
                # as "Unhandled server error"; 503 because it is the
                # deployment's to fix and a retry after the upgrade succeeds.
                request.env.cr.rollback()
                return _http_response(schema_behind(e))
            except Exception:
                # catch-all: reported — the last line of the envelope. It is
                # BROAD BY DESIGN: every route in this API ends here, and a
                # failure that escaped it would answer a raw Odoo HTML page
                # to an integration that branches on `error.code`. It logs
                # the traceback, rolls back, and returns the envelope's own
                # 500. Nothing is hidden; the caller is told the truth and
                # so is the log.
                _logger.exception("Unhandled error in %s", endpoint_path)
                request.env.cr.rollback()
                return _http_response(err(ERR_INTERNAL, "Unhandled server error", status=500))

            # If the function already returned an envelope (ok()/err()), keep it.
            # Otherwise, wrap plain dicts/lists into the `data` slot.
            if isinstance(result, dict) and ("data" in result or "error" in result):
                body = result
            else:
                body = ok(result)

            if ikey and "error" not in body:
                # Inside its own guard, not outside the handler's, because a
                # concurrent request carrying the same key loses the race on
                # the (key, endpoint) unique constraint here — after this one
                # has already done its write. Letting that escape produced a
                # bare, non-enveloped 500 for what is a normal retry.
                try:
                    idempotency_store(ikey, endpoint_path, body)
                except psycopg2.errors.UniqueViolation:
                    return _http_response(
                        _idempotency_replay_after_race(ikey, endpoint_path),
                        success_status=success_status,
                    )

            return _http_response(body, success_status=success_status)
        return wrapper
    return decorator
