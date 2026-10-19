"""
Cadra API v1 — Assets resource (REST shape per PRD §8.10).

Implements the subset of PRD §8 that maps onto `nrs.asset`. The in-house
model has a simpler 5-state lifecycle (active/in_repair/disposed/
transferred/missing) versus PRD §8.4's 10-state machine
(procured/received/tagged/deployed/in_maintenance/in_transit/idle/lost/
retired/disposed). The full state machine and the disposal-approval
workflow (PRD §8.9) are deferred to a future schema-extension pass.

The immutable custodianship chain (PRD §8.5) is `nrs.asset.custody`,
readable as `include=custody` on an asset and as
`GET /assets/<id>/custody`. It is written by `nrs.asset.write` rather
than by any one route, because `custodian_id` has several writers and a
chain with a gap in it cannot be told from a period of no movement.

The move endpoint persists its side-effect by creating an
`nrs.asset.transfer` row. Transfer-custody does not: that model requires
a location change and `_check_locations` forbids from == to, so a pure
custody move cannot be recorded in it at all.
"""
import datetime
import logging

from odoo import fields as odoo_fields, http
from odoo.http import request

from .utils import (
    ERR_CONFLICT,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_APPROVALS_WRITE,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    SCOPE_DASHBOARDS_READ,
    SCOPE_REQUESTS_READ,
    SCOPE_TAGGING_WRITE,
    SCOPE_CANDIDATES_READ,
    ERR_FORBIDDEN,
    _missing_scopes,
    caller_holds,
    decode_cursor,
    encode_cursor,
    err,
    flag_truncation,
    get_params,
    ok,
    paginate,
    parse_limit,
    record_cap,
    refuse_unwritable,
    selection_values,
)
# The door. Every query parameter this controller reads is parsed by one of
# these before it becomes a domain term, and none of them touches the
# database, the cursor or the request — see that module's docstring for why
# that purity is a rule rather than a preference.
from .query_params import (
    BadFilter,
    int_filter_terms,
    parse_bool,
    parse_enum,
    parse_int,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route

# Handoff 35. The approval gate lives on `nrs.asset` and applies to every
# writer; what these two helpers do is let the two ROUTES that are a person
# deciding to move something answer well — with a request and a reference
# number — instead of letting the model's `UserError` surface as a 400 on a
# button the user was told to press.
_CHANGE_REQUEST = "nrs.asset.change.request"


def _approval_required():
    """Whether this tenant needs a second person. Read per request.

    Not cached anywhere, for the reason `approval_policy` gives at length:
    the failure this control has is a worker serving `off` from an ormcache
    for a tenant whose row now says `on`, which is a control that has stopped
    applying with no symptom at all.
    """
    return request.env[_CHANGE_REQUEST].sudo().approval_is_required()


def _resolve_approver(body, asset):
    """(approver_user, error_envelope). WHO IS BEING ASKED, from the body.

    This IS read from the body, and it is the one thing on this path that is
    — because it is a nomination, not an authority. `approver_id` says whose
    queue the request lands in and who the notification is addressed to; it
    confers nothing. WHO DECIDED is `approved_by_id`, written from the token
    by `action_approve` and never readable from any payload. Two fields, on
    purpose and by instruction: a requester who can name the approver can
    forge one, and that is only true if naming them is what makes them the
    approver.
    """
    CR = request.env[_CHANGE_REQUEST].sudo()
    raw = body.get("approver_id")
    if raw in (None, "", 0, "0"):
        candidates = CR.eligible_approvers(
            exclude_user=request.env.user, limit=10)
        return None, err(
            ERR_INVALID_REQUEST,
            "This register requires a second person to approve a change of "
            "this kind, so `approver_id` is required: name who you are "
            "asking. GET /api/v1/approvals/approvers lists who may be asked.",
            details={
                "asset_id": asset.id,
                "approval_required": True,
                "approvers": [{"id": u.id, "name": u.display_name}
                              for u in candidates],
            })
    try:
        approver_id = int(raw)
    except (TypeError, ValueError):
        return None, err(ERR_INVALID_REQUEST,
                         "`approver_id` must be an integer")
    approver = request.env["res.users"].sudo().browse(approver_id).exists()
    if not approver:
        return None, err(ERR_NOT_FOUND, f"User {approver_id} not found",
                         status=404)
    if approver.id == request.env.uid:
        # Refused here AND by `_check_approver_is_not_the_requester` on the
        # model. Here so the message is about what the caller did; there
        # because a rule enforced only at the door is a rule with a back way
        # in, which is the lesson of every handoff since 28.
        return None, err(
            ERR_INVALID_REQUEST,
            "You cannot ask yourself to approve your own change. Name "
            "somebody else.",
            details={"asset_id": asset.id})
    if not approver.active:
        # Handoff 43 §2, measured: `eligible_approvers` hides an archived
        # user (the default `active` domain) but `browse().exists()` here
        # did not, so the picker and the gate disagreed — a deactivated
        # manager could be nominated by id and the request waited on
        # somebody who cannot sign in.
        return None, err(
            ERR_INVALID_REQUEST,
            "%s cannot be asked: their account is deactivated. Name "
            "somebody who can sign in." % approver.display_name,
            details={"asset_id": asset.id, "approver_id": approver.id})
    if not approver.has_group(CR.APPROVER_GROUP) \
            and not approver._is_admin():
        return None, err(
            ERR_INVALID_REQUEST,
            "%s cannot approve a change of this kind. An approver must be "
            "somebody who could have made the change themselves."
            % approver.display_name,
            details={"asset_id": asset.id, "approver_id": approver.id})
    return approver, None


def _pending_conflict(asset):
    """409 if something is already waiting on this asset, else None.

    A database partial-unique index enforces one pending request per asset,
    and it is the authority. This exists because the index answers with a
    `psycopg2.IntegrityError` that aborts the transaction, and a person who
    pressed Move deserves the reference number of the request in their way.
    Proved by the model probe in handoff 35: the raw violation takes the
    whole transaction with it.
    """
    existing = request.env[_CHANGE_REQUEST].sudo().pending_for_asset(asset)
    if not existing:
        return None
    return err(
        ERR_CONFLICT,
        "%s is already waiting for approval on this asset — %s asked %s on "
        "%s. Decide or withdraw that one first."
        % (existing.name,
           existing.requested_by_name or existing.requested_by_id.display_name,
           existing.approver_id.display_name,
           existing.requested_at and existing.requested_at.date() or "?"),
        status=409,
        details={
            "asset_id": asset.id,
            "pending_request": {
                "id": existing.id,
                "reference": existing.name,
                "change_type": existing.change_type,
                "requested_by": _ref(existing.requested_by_id),
                "approver": _ref(existing.approver_id),
            },
        })


def _raised_payload(req, asset, *, action):
    """What a route answers when it raised a request instead of acting.

    **Status stays 200 and the BODY carries the whole truth.** `pending_approval`
    is `true`, `request` is the record, and `asset` is the asset UNCHANGED —
    read back from the database in the same response, so a consumer that
    trusts the asset rather than the verb sees that nothing moved.

    200 rather than 202 is a judgement and worth stating: the per-call status
    override this API does not have would have to be carried through the
    idempotency cache as well, or a replay of the same key would answer 202
    once and 200 afterwards — and an idempotent replay that is not byte-exact
    is the property handoff 18 built and handoff 31 protected. Changing the
    cache for one route's status code was not worth it; the body says it
    three ways and `data._warnings` says it a fourth.
    """
    return {
        # FIRST KEY, and a boolean rather than a string, so the cheapest
        # possible read of this response is the correct one.
        "pending_approval": True,
        "action": action,
        "request": {
            "id": req.id,
            "reference": req.name,
            "state": req.state,
            "change_type": req.change_type,
            "approver": _ref(req.approver_id),
            "requested_by": _ref(req.requested_by_id),
            "requested_at": req.requested_at and req.requested_at.isoformat(),
            "to_location": _ref(req.to_location_id),
            "to_custodian": _ref(req.to_custodian_id),
            "reason": req.reason or None,
        },
        # UNCHANGED. The whole point.
        "asset": serialize_asset(asset),
        # The two keys the old contract published. Null, explicitly, because
        # a consumer reading `movement_id` must be able to tell "not yet"
        # from "absent" — and both are what this call did NOT produce.
        "movement_id": None,
        "transfer": None,
        "custody_change": None,
    }


# The instant a historical snapshot is taken at. A module function rather
# than a model method because it is arithmetic on a date and has no record to
# hang off; imported at module level, NOT inside the handler, so a rename in
# `myservice_asset_register` fails the whole controller at load with a
# traceback naming the symbol instead of turning into a per-request 500 that
# reads like a data problem. `myservice_api` already declares that module in
# its `depends`, so the import order is guaranteed.
from odoo.addons.myservice_asset_register.models.asset_snapshot import (
    snapshot_cutoff,
    snapshot_today,
)

# The affix route's `scanned_format` / `serial_format` enum is the event
# model's own Selection, imported at module level for the reason above: a
# rename fails the controller at load, not one request at a time.
from odoo.addons.myservice_asset_register.models.asset_event import (
    SCANNED_FORMATS,
)

_logger = logging.getLogger(__name__)

# ─── the published enum floors ───────────────────────────────────────
#
# Every enum filter below validates against the MODEL's own Selection, read
# by `utils.selection_values`, so a value the model gains is accepted by the
# filter that publishes it on the same day. These tuples are the floor under
# that reader and never a substitute for it: if the registry cannot be read,
# the published tuple still rejects a typo. A validator that disables itself
# on failure puts `?state=bogus` back to answering `200 []`, which is the
# silent degradation the validation exists to remove.
#
# `utils.selection_values` is deliberately NOT `utils._selection_allowed_values`,
# and the difference is the whole reason the former exists: that one calls
# `cr.rollback()` when it cannot read a field, because it was written for the
# error path AFTER a failed write, where the cursor is already dirty. These
# run on the happy path of every list request, where rolling back a cursor
# nobody asked it to touch would turn a transient read failure into a
# corrupted response. The ruling is landed (docs/DECISIONS.md, 2026-09-06).

# nrs.asset.state — the in-house 5-state lifecycle (module docstring above).
_ASSET_STATES = ("active", "in_repair", "disposed", "transferred", "missing")

# nrs.asset.condition.
_ASSET_CONDITIONS = ("new", "good", "fair", "poor", "decommissioned")

# nrs.asset.asset_level — position in the hierarchy, and the same four values
# INT-06 §8 publishes to SAP.
_ASSET_LEVELS = ("group", "asset", "sub_asset", "component")

# `?sort` on the listing. Deliberately NOT read off the model the way the
# field enums are (handoff 22): this is a property of the LISTING, there is
# no `nrs.asset` field behind it, and so there is nothing for it to drift
# from. `oldest` is the default and is spelled out so a caller can say it
# rather than rely on it.
_LIST_SORT_VALUES = ("newest", "oldest")

# nrs.asset.domain — the FM domain. The field is `related='category_id.domain'`,
# so the Selection is declared on `nrs.asset.category`; the related field
# carries it, which is why reading `nrs.asset.domain` off the registry gets the
# right list — the same shape as `tag_label_state` below, which is related to
# `nrs.asset.tag.label.label_state` and has been read off the registry that
# way since its filter was written. Mirrors `v1_settings._FM_DOMAINS`.
_FM_DOMAINS = ("building", "plant", "plumbing", "fleet", "security", "it",
               "furniture", "other")

# nrs.asset.import_source — which system wrote the record. `vendra` is INT-03.
_IMPORT_SOURCES = ("myservice", "sap", "redhubb", "vendra", "excel", "other")

# The published `tag_label_state` values, mirroring the model's Selection
# (`nrs.asset.tag.label.label_state`) and the OpenAPI enum below.
_TAG_LABEL_STATES = ("issued", "printed", "affixed", "scrapped")

# The published `sap_reconciliation_state` values, mirroring the model's
# Selection (`nrs.asset.sap_reconciliation_state`) and the OpenAPI enum below.
# More is at stake on this one than on any other filter here: its whole
# audience is an auditor asking which assets are incomplete, so
# `?sap_reconciliation_state=exceptions` — the plural, the natural typo —
# answering `200 []` tells them there are none.
_SAP_RECONCILIATION_STATES = ("not_tagged", "pending", "reconciled",
                              "exception")

# The optional embeds the two single-asset routes accept on `include=`.
# nrs.asset.warranty_status (handoff 34). Three and not two: `none` is the
# honest third and it is almost every asset.
_WARRANTY_STATUSES = ("under_warranty", "expired", "none")

# The widest `?warranty_expires_within_days=` window. Ten years is past any
# warranty a register holds; beyond it the question is not "soon".
_WARRANTY_WINDOW_MAX_DAYS = 3650

_INCLUDE_SECTIONS = ("transfers", "custody", "pm", "children")


# ─── published descriptions ──────────────────────────────────────────
#
# Said once, in the wording `sap_reconciliation_state` already publishes,
# because it is now true of every filter on this controller and a caller
# reading the OpenAPI document should not have to infer it from one
# parameter's description.
_ENUM_FILTER_400 = ("A value outside the enum is a 400 `invalid_request` "
                    "carrying `details.allowed_values`, not an empty list.")
_ID_FILTER_400 = ("Exact match on the record id. A value that is not an "
                  "integer is a 400 `invalid_request`, never the unfiltered "
                  "list.")


# ─── small helpers ───────────────────────────────────────────────────

def _ref(rec, name_field="name"):
    if not rec:
        return None
    return {"id": rec.id, "name": getattr(rec, name_field, None) or rec.display_name}


def _date(v):
    return v.isoformat() if v else None


def _serialize_depreciation(a):
    """The depreciation block of an asset's `financial` object (PRD §8.6).

    Method names match the published enum: straight_line | declining_balance |
    none | erp_managed. For erp_managed the figures are supplied by the
    tenant's ERP and Cadra does not compute them (NRS spec §6.2).
    """
    return {
        "method": a.depreciation_method,
        "useful_life_months": a.useful_life_months or None,
        "declining_rate": a.declining_rate or None,
        # The RATE beside the derived amount (handoff 50 §5, closing 33 §B1):
        # `salvage_rate` has been writable since the field existed and was
        # published only as the derived `salvage_value`, so a caller could
        # see the effect of what it sent but never the figure it sent —
        # 10,364 of 11,173 assets on test19 carry one (2026-10-03). The keys
        # are the writable names, so a block read can be sent back unchanged.
        "salvage_rate": a.salvage_rate or None,
        "salvage_value": a.salvage_value or None,
        "depreciable_cost": a.depreciable_cost or None,
        "start_date": _date(a.depreciation_start_date),
        "start_date_source": a.depreciation_start_source or None,
        "start_date_is_estimated": a.depreciation_start_is_estimated,
        "accumulated_depreciation": a.accumulated_depreciation or None,
        "current_book_value": a.current_book_value or None,
        "state": a.depreciation_state,
        "end_date": _date(a.depreciation_end_date),
        "uses_category_policy": a.use_category_policy,
    }


def _parse_datetime(raw):
    """Parse an inbound timestamp to the naive UTC Odoo stores, or None.

    Odoo's own `Datetime.to_datetime` accepts only "%Y-%m-%d %H:%M:%S" — it
    rejects the ISO 8601 `T` separator that this endpoint's schema advertises
    and that every integration actually sends. So parse ISO first and fall
    back to Odoo's format, rather than publishing `format: date-time` and
    refusing date-times.

    An offset is honoured and converted; a naive value is taken as UTC, which
    is what the rest of the API assumes.
    """
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError:
        try:
            return odoo_fields.Datetime.to_datetime(raw)
        except (ValueError, TypeError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _serialize_tagging(a):
    """The physical-tagging block (INT-04/05).

    Reads the label physically on the asset. An asset with no tag at all, and
    an asset whose tag was generated but never printed or affixed, both read
    as not tagged — which is the honest answer and the whole point: the old
    `tag` field said every asset was tagged from the moment it was created.

    Deliberately NOT `active_tag_id`, which drops a tag as soon as a
    replacement is requested: the label is still on the asset until someone
    peels it off, and reporting it as untagged would be the same bug pointed
    the other way.
    """
    label = a.physical_tag_id
    return {
        # `nrs.asset.tag.label` id — NOT an asset id, and the two collide
        # numerically. This is what GET /barcode/print-url wants as its
        # `tag_id`. Exposed here because an integration that has an asset
        # payload had no documented route to it: `recent-tags` was the only
        # endpoint that put the two ids together, and rebuilding a print URL
        # from the wrong one renders a real label for a different machine.
        "label_id": label.id if label else None,
        "tag_number": label.name if label else None,
        "label_state": label.label_state if label else None,
        # Handoff 61 (R3): which print of this number is on the asset — 0
        # for the first, one more for each approved replacement, which
        # reprints under the same number.
        "reprint_count": label.reprint_count if label else None,
        # The single boolean an integration should branch on.
        "is_tagged": bool(label) and label.label_state == "affixed",
        "printed_at": _date(label.printed_date) if label else None,
        "printed_by": _ref(label.printed_by) if label else None,
        "affixed_at": _date(label.affixed_date) if label else None,
        "affixed_by": _ref(label.affixed_by) if label else None,
        "affixed_by_name": (label.affixed_by_name or None) if label else None,
    }


def _sap_amount(value, synced):
    """A figure SAP reported, or None where SAP has reported none.

    Deliberately NOT `value or None`, which is what this serialiser does with
    Cadra's own money. A fully-depreciated asset has a net book value of
    exactly 0.00, and that is SAP's ANSWER, not the absence of one — reporting
    it as null would tell an integration that finance has never touched an
    asset finance has written all the way down. `_set_sap_master` draws the
    same line on the way in ("absent and zero are different answers and only
    one of them is a figure"); losing it on the way out would be a silent
    degradation of exactly the kind rule 3 forbids.

    `synced` is what separates the two cases: a zero on a record SAP has
    answered for is a figure, a zero on one it never has is a column default.
    A non-zero value is always a figure, whoever wrote it — the legacy
    extract loader populates these without going through INT-07.
    """
    if not value and not synced:
        return None
    return value


def _serialize_sap(a):
    """The SAP block — INT-06/07 and the dual-code control.

    Nested for exactly the reason `provenance` is nested: twelve SAP keys
    flattened onto the envelope is twelve new breaking-change surfaces on a
    contract another system builds against, and between them they answer one
    question — what does finance know about this asset. One new envelope key
    instead of twelve.

    Every figure here is what SAP REPORTED, never what Cadra computed.
    `financial.depreciation` is Cadra's arithmetic; this is SAP's, and the two
    are allowed to disagree. Anything reconciling them has to be able to see
    both, so they stay in separate blocks — merging them would hide the
    disagreement the reconciliation exists to find.

    Read-only over the API. None of these fields is in `_WRITABLE_FIELDS` and
    none of them belongs there: a client that could PATCH `sap_asset_number`
    could mark an asset reconciled without SAP ever having booked it, which
    is the precise audit control this block exists to publish.
    """
    synced = bool(a.sap_synced_at)
    return {
        # The SAP half of the dual-code pair; `asset_code` at the top level
        # is Cadra's half. An asset carrying only one of the two is the
        # finding `reconciliation_state` names.
        "asset_number": a.sap_asset_number or None,
        "asset_subnumber": a.sap_asset_subnumber or None,
        # The asset number is not unique on its own — the same number can
        # exist under two company codes — so anything matching on it needs
        # this alongside.
        "company_code": a.sap_company_code or None,
        # The class SAP actually posted under, which is not necessarily the
        # one Cadra derived from the category. Where the two differ the
        # mapping is wrong, and this is the field that shows it.
        "asset_class": a.sap_asset_class or None,
        "capitalisation_date": _date(a.sap_capitalisation_date),
        "capitalised_amount": _sap_amount(a.sap_capitalised_amount, synced),
        "net_book_value": _sap_amount(a.sap_net_book_value, synced),
        "accumulated_depreciation": _sap_amount(
            a.sap_accumulated_depreciation, synced),
        # How the SAP number got onto the record. A code returned by SAP is
        # evidence that finance booked the asset; a code typed in by a person
        # is a claim that they did. The dual-code control is an audit
        # control, so the two must not look alike over the API either — the
        # same instinct as `tagging.label_state` against `state`.
        "code_source": a.sap_code_source or None,
        # Emitted raw, like `state` and `condition` above: `posting_state`
        # carries a column default and `reconciliation_state` is a stored
        # compute, so there is always a value and `or None` could only invent
        # an absence that does not exist.
        "posting_state": a.sap_posting_state,
        "reconciliation_state": a.sap_reconciliation_state,
        # When SAP last answered for this asset. The discriminator above, and
        # on its own the answer to "are these figures stale?".
        "synced_at": _date(a.sap_synced_at),
        # Handoff 58, P4: when SAP's INT-06 answer carried an asset number
        # DIFFERENT from the one the Register Maker entered, the entered one
        # stays in `asset_number` and this names both numbers, the maker and
        # the checker; `reconciliation_state` is `exception`. Null otherwise.
        "discrepancy": a._sap_discrepancy(),
    }


def _naive_iso(v):
    """A naive datetime as ISO 8601 with no offset, or None.

    Deliberately not `format: date-time` in the OpenAPI schema: Cadra stores
    naive UTC and renders it with `.isoformat()`, e.g. "2026-03-31T23:59:59".
    That is not the RFC 3339 `date-time` promises, and claiming the format
    would make a strict parser reject a value that is otherwise perfectly
    readable. Same reasoning as `AssetTagging.printed_at`.
    """
    return v.isoformat() if v else None


def _parse_report_date(qs, param, *, required=False):
    """Read one YYYY-MM-DD query parameter. Returns (date_or_None, error).

    Copied in rigour from `get_asset_depreciation`'s `as_of` block, which is
    the only other date parameter in this API, and tightened in one place:
    an ABSENT required parameter is a 400 of its own rather than a silent
    default.

    That matters more here than it reads. CLAUDE.md's backlog records five
    boolean query parameters API-wide that silently drop their filter and
    return the UNFILTERED list — an empty list reads as "no matches", a full
    list reads as an answer, and the full list is the dangerous half. The
    equivalent failure on an audit report is a period nobody asked for and a
    snapshot silently dated today, both of which answer 200 with a figure an
    auditor would put in a file. Every path out of this function is either a
    date the caller supplied or a 400 naming the parameter.

    Deliberately NOT `utils._selection_allowed_values`: that helper calls
    `cr.rollback()` on failure and is written for the post-rollback error
    path, and these run on the happy path of a read.
    """
    raw = (qs.get(param) or "").strip()
    if not raw:
        if required:
            return None, err(
                ERR_INVALID_REQUEST,
                "`%s` is required and must be a date in YYYY-MM-DD format"
                % param,
                details={param: qs.get(param)})
        return None, None
    try:
        parsed = odoo_fields.Date.from_string(raw)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None:
        return None, err(
            ERR_INVALID_REQUEST,
            "`%s` must be a date in YYYY-MM-DD format" % param,
            details={param: raw})
    return parsed, None


# Query parameters this report reads for itself rather than passing to the
# asset filter builder. Everything else the caller sent is a filter, and is
# disclosed as one.
_SNAPSHOT_OWN_PARAMS = frozenset({"as_of", "limit", "cursor"})


def _snapshot_filter_disclosure(qs):
    """What the caller filtered on, and the fact that it was evaluated TODAY.

    This is the second half of the fidelity boundary and it is easy to miss.
    `_list_domain` builds an ordinary Odoo domain over the asset table, so
    every filter matches the asset's CURRENT value — including filters on
    fields the snapshot then rolls back. `?as_of=2026-03-31&state=active`
    therefore means "assets that are active TODAY, reported as they stood on
    31 March", which is a different population from "assets that were active
    on 31 March" and will reconcile to a different number.

    Rolling the filters back too would need the whole domain evaluated
    against history, which the tracking values cannot support. So the report
    says what it did instead of implying it did the other thing (rule 3).
    """
    supplied = sorted(k for k in qs if k not in _SNAPSHOT_OWN_PARAMS)
    return {
        "query_parameters_supplied": supplied,
        "evaluated_as_of": "today",
        # Composed for a reader (handoff 50 §5 words guard, class 1): no
        # backticks, no payload paths — "the requested date" instead of the
        # parameter's name, "listed as rolled back" instead of the key path.
        "note": (
            "Filters select on the asset's CURRENT value, not its value on "
            "the requested date — the rows are rolled back, the selection "
            "is not. A filter on any field this report lists as rolled "
            "back therefore chooses a different population from the one "
            "the snapshot reports for that field. Filter on the date alone "
            "for a figure that reconciles. Parameters this endpoint does "
            "not recognise are ignored by the filter builder exactly as "
            "they are on the asset list, and are still echoed here as "
            "sent."),
    }


def _serialize_disposal(a):
    """How the asset left the estate, and the paper that authorised it.

    Grouped rather than flattened for the same reason `provenance` and `sap`
    are: six new top-level keys would bury the one question this block
    answers, which is the auditor's three-part test — *was it authorised, by
    whom, and is the paper there?* (specification §13.4, INT-10 §2.9).

    `date` and `reason` are ALSO published at `dates.disposal_date` and at
    the top-level `disposal_reason`, where they have always been. They are
    repeated here rather than moved: removing a published field is a
    breaking change (rule 1) and Vendra is downstream, and a block that
    answers "was this disposal documented" while the date lives somewhere
    else is not an answer an auditor can read in one pass. Both spellings
    read the same column.

    `approved_by` and `approved_at` are READ-ONLY — deliberately absent from
    `_WRITABLE_FIELDS`, for the reasoning recorded there. They are written by
    `nrs.asset.action_approve_disposal` from the acting user, which is
    evidence; a field a client can PATCH is a claim.

    `date_reconstructed` says the date was recovered from the tracked state
    change rather than recorded when the disposal happened. It is published,
    not hidden behind the report, because an auditor reading one asset needs
    the same disclosure as one reading the schedule — the same argument as
    `nrs.asset.custody.source = 'tracking_backfill'`.
    """
    return {
        "date": _date(a.disposal_date),
        "date_reconstructed": a.disposal_date_reconstructed,
        "method": a.disposal_method or None,
        "reference": a.disposal_reference or None,
        "approved_by": _ref(a.disposal_approved_by, name_field="name"),
        "approved_at": _date(a.disposal_approved_date),
        "proceeds": a.disposal_proceeds or None,
        "currency": _ref(a.currency_id),
        "reason": a.disposal_reason or None,
    }


def _serialize_warranty(a):
    """The warranty — the answer AND the working (handoff 34).

    `warranty_expiry` alone is the answer; `warranty_start_date` and
    `warranty_months` are the working, and `basis` says them in words so a
    reader holding the certificate can check the one against the other. A
    bare date with no basis says so rather than inventing one.

    The keys are the WRITABLE names, deliberately, not shorter ones under a
    `warranty.` prefix: a client that reads this block, edits it and sends
    the keys back must not be refused for having used the name we published
    (handoff 33 §B2, found the week before this was written).

    `status` is judged against `status_as_of`, a LAGOS day, and moves with
    the calendar with no write to the record. A warranty is a fact about a
    contract: `status` is not the asset's condition, lifecycle or review
    state, and nothing on this API counts it as any of them.
    """
    start, months = a.warranty_start_date, a.warranty_months
    if start and months:
        basis = "%d months from %s" % (months, start.isoformat())
    elif a.warranty_expiry:
        basis = ("Entered as an expiry date; no start date or duration "
                 "was recorded")
    else:
        basis = None
    return {
        "status": a.warranty_status,
        "status_as_of": snapshot_today().isoformat(),
        "warranty_expiry": _date(a.warranty_expiry),
        "warranty_start_date": _date(start),
        "warranty_months": months or None,
        "warrantor": a.warrantor or None,
        "warranty_reference": a.warranty_reference or None,
        "basis": basis,
    }


def _serialize_custody(c):
    """One link in the chain of custody.

    `source` is published deliberately. A link reconstructed from the old
    chatter tracking values reads `tracking_backfill`, and an auditor has to
    be able to see that WITHOUT knowing to ask — a reconstruction presented
    as a contemporaneous record is worse than no record.

    The `*_name` fields are the names as they stood when the change was
    made. They are not derived from the linked records: an employee deleted
    since is null in `from`/`to` and still named here.
    """
    return {
        "id": c.id,
        "changed_at": _date(c.changed_at),
        "from_custodian": _ref(c.from_custodian_id),
        "to_custodian": _ref(c.to_custodian_id),
        "from_custodian_name": c.from_custodian_name or None,
        "to_custodian_name": c.to_custodian_name or None,
        # Who MOVED it, which is a different question from who held it.
        "changed_by": _ref(c.changed_by_id),
        "changed_by_name": c.changed_by_name or None,
        "reason": c.reason or None,
        "source": c.source,
    }


def _parse_include(raw):
    """The `include=` sections a caller asked for, or a `BadFilter`.

    Comma-separated, whitespace tolerated, absent and empty both meaning "no
    sections". An unrecognised section used to be dropped without a word, so
    `?include=custdy` answered 200 with an asset that simply had no `custody`
    key on it — and a caller reading `data.get("custody", [])` is told the
    asset has never changed hands. That is the same reassuring wrong answer
    the filters below used to give, one parameter along, and rule 3 forbids
    it: nothing degrades in silence.

    Each token is checked on its own so the 400 names the section that was
    not recognised rather than echoing the whole string back.
    """
    sections = []
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        sections.append(parse_enum("include", token, _INCLUDE_SECTIONS))
    return sections


# ─── serializer ──────────────────────────────────────────────────────

def _caller_scopes():
    """The bearer token's scopes, as `_missing_scopes` reads them."""
    claims = getattr(request, "jwt_claims", None) or {}
    granted, _missing = _missing_scopes(claims, [])
    return granted


def _serialize_gates(a):
    """The receipt-gate block (handoff 57). Cheap for a registered asset:
    nothing can fire from `registered`, so no event is read."""
    if a.register_state == "registered":
        # `registration` (handoff 60) is the maker's submission while the
        # unit waits on the checker; on the register it is history, read
        # from the asset's own fields and its events.
        return {"waiting_on": None, "state_since": None, "available": [],
                "registration": None}
    block = a._gates_block(scopes=_caller_scopes())
    if block.get("state_since"):
        block["state_since"] = block["state_since"].replace(" ", "T") + "Z"
    return block


#: `?register_state=` on `GET /assets` (handoff 57 §2d). Absent: the
#: register — registered assets only, by the model's own default
#: (`asset_gates._search`). `any`, or one state: needs `candidates:read`.
REGISTER_STATES = ("captured", "vfm_pending", "vfm_verified", "vfm_approved",
                   "vfm_query", "vfm_rejected", "tag_requested", "tag_issued",
                   "tagged", "reg_ready", "reg_submitted", "registered")


def _register_state_domain(qs):
    """`(terms, error)` for `?register_state=`. A term that NAMES the field
    is what lifts the model's implicit `registered` default — `any` is
    `register_state != False`, which every row satisfies (the field is
    required)."""
    raw = (qs.get("register_state") or "").strip()
    if not raw:
        return [], None
    # `caller_holds`, so `admin` and `*` are judged as the gate judges them.
    if raw != "registered" and not caller_holds(SCOPE_CANDIDATES_READ):
        return None, err(
            ERR_FORBIDDEN,
            "Seeing receipt candidates needs the `candidates:read` scope; "
            "without it the register shows registered assets only.",
            status=403, details={"required_scopes": [SCOPE_CANDIDATES_READ]})
    if raw == "any":
        return [("register_state", "!=", False)], None
    if raw not in REGISTER_STATES:
        return None, err(
            ERR_INVALID_REQUEST,
            "`register_state` must be `any` or one of: %s"
            % ", ".join(REGISTER_STATES),
            details={"allowed_values": ["any", *REGISTER_STATES]})
    return [("register_state", "=", raw)], None


def serialize_asset(a, *, include=()):
    """Map an nrs.asset record to a Cadra-shaped dict.

    `include` accepts:
      - "transfers"   : embed nrs.asset.transfer history (last 20)
      - "custody"     : embed the WHOLE chain of custody, oldest first
      - "pm"          : embed PM schedule summaries
      - "children"    : embed direct sub-assets (id+name)
    """
    include = set(include or ())
    data = {
        "id": a.id,
        "asset_code": a.asset_code,
        # DEPRECATED (annotation only — see components.schemas.Asset). It is
        # the tag NUMBER, allocated at creation, so it has never answered "is
        # there a label on this asset"; `tagging.is_tagged` does. Kept because
        # breaking a published field to fix a naming problem is not a trade
        # worth making with a live consumer.
        "tag": a.asset_tag or None,
        "legacy_asset_code": a.legacy_asset_code or None,
        "name": a.name,
        # Derived from the credential that created the record, never
        # declared (`myservice_api/models/test_fixture.py`). Additive and
        # always present; FALSE on every record created before handoff 26,
        # which is NOT the same statement as "this is a real record".
        "is_test_fixture": a.is_test_fixture,
        "serial_number": a.serial_number or None,
        "make": a.make or None,
        "model": a.model_name or None,
        "manufacturer": a.manufacturer or None,
        # Section 12 (handoff 58 §4): the attributes a unit with no
        # manufacturer serial is identified by, and the identification mode
        # the unit was RECEIVED under — fixed at receipt (AD-31), null for
        # anything received with the gates off.
        "colour": a.colour or None,
        "material": a.material or None,
        "dimensions": a.dimensions or None,
        # Handoff 59 §2: the title, plot number, licence key or contract that
        # identifies a `record_only` unit.
        "record_reference": a.record_reference or None,
        "identification_mode": a.identification_mode or None,
        "category": _ref(a.category_id),
        "subcategory": _ref(a.subcategory_id),
        "asset_type": _ref(a.asset_type_id),
        "asset_level": a.asset_level or None,
        "domain": a.domain or None,
        "parent_asset": _ref(a.parent_id),
        "child_count": len(a.child_ids),
        "current_location": _ref(a.location_id),
        "location_hierarchy": {
            "building": _ref(a.building_id),
            "floor": _ref(a.floor_id),
            "room": _ref(a.room_id),
        },
        "floor_room": a.floor_room or None,
        "address_display": a.address_display or None,
        "coordinates": {
            "latitude_display": a.latitude_display or None,
            "longitude_display": a.longitude_display or None,
        } if (a.latitude_display or a.longitude_display) else None,
        "current_custodian": _ref(a.custodian_id),
        "department": a.department or None,
        "condition": a.condition,
        "state": a.state,
        "financial": {
            "currency": _ref(a.currency_id),
            "purchase_value": a.purchase_value or None,
            "replacement_cost": a.replacement_cost or None,
            "acquisition_cost": a.acquisition_cost or None,
            # Legacy hand-entered figure. Superseded by
            # financial.depreciation.current_book_value, which is derived.
            "current_value": a.current_value or None,
            "depreciation": _serialize_depreciation(a),
        },
        "dates": {
            "purchase_date": _date(a.purchase_date),
            "warranty_expiry": _date(a.warranty_expiry),
            "acquisition_date": _date(a.acquisition_date),
            "disposal_date": _date(a.disposal_date),
            "last_verified_date": _date(a.last_verified_date),
            "next_service_date": _date(a.next_service_date),
        },
        # Whether the asset is PHYSICALLY tagged, which `tag` above cannot
        # answer: a tag record is auto-generated on every create, so `tag` is
        # populated from the moment the asset exists. `is_tagged` is true only
        # once an affix confirmation has been received (INT-04/05).
        "tagging": _serialize_tagging(a),
        "disposal_reason": a.disposal_reason or None,
        # How the asset left, and whether anybody authorised it (§13.4).
        # `disposal_reason` above and `dates.disposal_date` are the older
        # published spellings of two of these fields and stay exactly where
        # they were — this block adds the four that did not exist and the
        # flag on the date, so the whole disposal reads as one thing.
        "disposal": _serialize_disposal(a),
        # Handoff 34. `dates.warranty_expiry` above stays exactly where it
        # was; this block adds who honours it, the certificate, and the
        # basis the date was worked out from.
        "warranty": _serialize_warranty(a),
        # Where the asset came from. Grouped rather than flattened so the
        # commercial hand-off (INT-03) reads as one block: `grn_reference`
        # and `purchase_order_reference` are Vendra's and SAP's identifiers
        # for the receipt and the order, `purchase_vendor` is who supplied
        # it (NOT `maintenance_vendor`, which is who services it), and the
        # `import_*` trio is the stamp of whichever system wrote the record.
        "provenance": {
            "grn_reference": a.grn_reference or None,
            "purchase_order_reference": a.purchase_order_reference or None,
            "purchase_vendor": a.purchase_vendor or None,
            "import_source": a.import_source or None,
            "import_date": _date(a.import_date),
            "import_ref": a.import_ref or None,
        },
        # What finance knows (INT-06/07) and whether the two codes agree.
        # Grouped for the same reason `provenance` is, and kept out of
        # `financial` on purpose: that block is Cadra's own arithmetic and
        # this one is SAP's reported figures, and a reconciliation needs to
        # read them apart.
        "sap": _serialize_sap(a),
        "maintenance_vendor": _ref(a.maintenance_vendor_id),
        "is_verified": a.is_verified,
        # WHO verified it, which `dates.last_verified_date` cannot say.
        # READ-ONLY and absent from `_WRITABLE_FIELDS` on purpose: written
        # only by `POST /assets/<id>/verify`, from the acting user. Null on
        # an asset whose date arrived by PATCH — which, until handoff 28,
        # was every verification made from the Cadra app. Null means nobody
        # is recorded, not that nobody checked.
        "last_verified_by": _ref(a.last_verified_by),
        # What the last verification said (handoff 50 §5, closing 33 §B1).
        # Writable since the field existed, published until now only in the
        # response to `POST /assets/<id>/verify` (as `verification.notes`,
        # which stays) — so a caller could write it and never read it back
        # on a GET. 193 of 11,173 assets on test19 carry one (2026-10-03).
        "verification_notes": a.verification_notes or None,
        "pm_count": a.pm_count,
        "request_count": a.request_count,
        # Handoff 57, kept by 58. Anything but `registered` is a receipt
        # candidate, hidden from every list and count by default. `gates` says who it is
        # waiting on and which gate actions THIS CALLER may fire now — the
        # no-two-gates rule already applied, so the app draws no button the
        # server would refuse.
        "register_state": a.register_state,
        "gates": _serialize_gates(a),
        "notes": a.notes or None,
        "created_at": _date(a.create_date),
        "updated_at": _date(a.write_date),
        "created_by": _ref(a.create_uid),
        "updated_by": _ref(a.write_uid),
    }
    if "transfers" in include:
        data["transfers"] = [
            {
                "id": t.id,
                "reference": t.name,
                "from_location": _ref(t.from_location_id),
                "to_location": _ref(t.to_location_id),
                "from_custodian": _ref(t.from_custodian_id),
                "to_custodian": _ref(t.to_custodian_id),
                "transfer_date": _date(t.transfer_date),
                "state": t.state,
                "reason": t.reason or None,
            }
            for t in a.transfer_ids.sorted(lambda r: r.transfer_date or odoo_fields.Date.today(), reverse=True)[:20]
        ]
    if "custody" in include:
        # NOT capped. The embedded `transfers` list above takes the last 20,
        # and "the last twenty custodians" is precisely the answer an auditor
        # cannot use: a truncated chain is indistinguishable from a complete
        # one, so the question it exists to answer comes back wrong with no
        # sign that it did.
        #
        # Sorted by id, not by the model's `changed_at, id` default, so this
        # is byte-for-byte the order `GET /assets/<id>/custody` returns —
        # that route pages on an ascending id cursor and cannot sort any
        # other way. Both are oldest-first, which is the direction a chain
        # reads; the two agreeing is what stops a reader who switches from
        # the embed to the route seeing a different chain.
        data["custody"] = [_serialize_custody(c)
                           for c in a.custody_ids.sorted("id")]
    if "children" in include:
        data["children"] = [{"id": c.id, "name": c.name, "asset_code": c.asset_code} for c in a.child_ids]
    if "pm" in include:
        data["pm_schedules"] = [
            {"id": p.id, "name": p.name if hasattr(p, "name") else None,
             "next_due_date": _date(p.next_due_date), "active": p.active}
            for p in a.pm_schedule_ids
        ]
    return data


# ─── domain builder ──────────────────────────────────────────────────

def _parse_updated_since(raw):
    """`?updated_since=` (handoff 61 §6) → a naive UTC datetime, or None
    when absent. ISO-8601: a date (`2026-10-15`, midnight UTC), or a date
    and time with an optional fraction and an optional zone (`Z`, `+01:00`)
    — `T` or a space between them, so an `updated_at` this API published
    is accepted back verbatim. A time with no zone is UTC, as every
    datetime this API publishes is. Anything else is a `BadFilter` → 400;
    never "no filter", which would hand a sync the whole register and call
    it a change set (handoff 21).

    Parsed here rather than in `query_params.py`, whose purity rule forbids
    any import (`tests/test_query_param_guard.py`) and a date cannot be read
    without one; waived there by name, like `_parse_report_date`."""
    if raw is None:
        return None
    text = raw.strip() if isinstance(raw, str) else raw
    if text in ("", None):
        return None
    if not isinstance(text, str):
        raise BadFilter("`updated_since` must be an ISO-8601 date or "
                        "date-time", details={"updated_since": raw})
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        if len(candidate) == 10:
            value = datetime.datetime.combine(
                datetime.date.fromisoformat(candidate), datetime.time.min)
        else:
            value = datetime.datetime.fromisoformat(candidate)
    except ValueError:
        raise BadFilter(
            "`updated_since` must be an ISO-8601 date or date-time, for "
            "example 2026-10-15 or 2026-10-15T09:30:00Z; %r is neither"
            % text, details={"updated_since": raw,
                             "example": "2026-10-15T09:30:00Z"})
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


def _list_domain(qs):
    domain = []
    # Handoff 61 §6, the sync filter: every asset whose own record changed
    # at or after the instant (`updated_at`, which is `write_date`). `>=`
    # rather than `>`, so a client that sends back the last `updated_at` it
    # saw re-reads that row rather than missing a second row written in the
    # same second; a sync upserts by id, so a row read twice is harmless.
    updated_since = _parse_updated_since(qs.get("updated_since"))
    if updated_since is not None:
        domain.append(("write_date", ">=", updated_since))
    q = (qs.get("q") or "").strip()
    if q:
        # Match the asset's own identity fields plus the human-meaningful
        # relations users actually search by: custodian (name or IR number),
        # category/sub-category, and location.
        terms = [
            ("name", "ilike", q),
            ("asset_code", "ilike", q),
            ("asset_tag", "ilike", q),
            ("legacy_asset_code", "ilike", q),
            ("serial_number", "ilike", q),
            ("department", "ilike", q),
            ("custodian_id.name", "ilike", q),
            ("custodian_id.ir_number", "ilike", q),
            ("category_id.name", "ilike", q),
            ("subcategory_id.name", "ilike", q),
            ("location_id.name", "ilike", q),
            # An auditor holding a GRN or a PO pastes it into the search box
            # before they think to reach for a named filter.
            ("grn_reference", "ilike", q),
            ("purchase_order_reference", "ilike", q),
        ]
        domain += ["|"] * (len(terms) - 1) + terms
    # The foreign-key filters. Every one of these used to sit inside an
    # `except (TypeError, ValueError): pass`, so `?category_id=laptops`
    # appended no term at all and returned EVERY asset in the register — and
    # a caller who put a name where an id belongs reads that as "this
    # category holds the whole estate". `"null"` still counts as absent,
    # which is what these have always done and what a client sending it
    # means by it.
    domain += int_filter_terms(qs, ("category_id", "subcategory_id",
                                    "location_id", "building_id", "floor_id",
                                    "room_id", "custodian_id", "parent_id"))
    # The four enum filters, which used to be `if val: domain.append(...)` —
    # anything the caller typed became a domain term, so `?state=Active`, the
    # capital being the natural typo, matched no row and answered `200 []`.
    # That reads as "there are no active assets" and is indistinguishable
    # from a genuine empty result. Validated against the model's own
    # Selection, floored by the published tuple.
    for fld, fallback in (("state", _ASSET_STATES),
                          ("condition", _ASSET_CONDITIONS),
                          ("domain", _FM_DOMAINS),
                          ("asset_level", _ASSET_LEVELS)):
        value = parse_enum(fld, qs.get(fld),
                           selection_values("nrs.asset", fld, fallback))
        if value is not None:
            domain.append((fld, "=", value))
    # `?is_tagged=true` is the question Vendra actually asks; it maps onto the
    # one label state that means a physical label was confirmed on the asset.
    # `"null"` reads as absent here and almost nowhere else: that leniency is
    # what this parameter has published since handoff 01, so it keeps it. A
    # parameter that never published it does not get it.
    is_tagged = parse_bool("is_tagged", qs.get("is_tagged"),
                           null_is_absent=True)
    if is_tagged is True:
        domain.append(("tag_label_state", "=", "affixed"))
    elif is_tagged is False:
        domain.append(("tag_label_state", "!=", "affixed"))
    # Provenance lookups are exact, not fuzzy: `?grn_reference=GRN-2026-00001`
    # has to return that receipt's assets and nothing else, or it is not an
    # audit trail. `import_source` is the one closed set among them and is
    # validated as one — a mistyped source answering `200 []` reads as "no
    # Vendra receipt has ever landed here", which is a statement about INT-03
    # nobody should be able to make by typo.
    for fld in ("grn_reference", "purchase_order_reference", "purchase_vendor",
                "import_ref"):
        val = qs.get(fld)
        if val:
            domain.append((fld, "=", val))
    import_source = parse_enum(
        "import_source", qs.get("import_source"),
        selection_values("nrs.asset", "import_source", _IMPORT_SOURCES))
    if import_source is not None:
        domain.append(("import_source", "=", import_source))
    # `tag_label_state` is an enum, and an unrecognised value used to answer
    # `200 []` — so a typo in a poller read as "nothing is tagged yet" rather
    # than as an error, which is the silent degradation POST already refuses.
    # The accepted values come from the model's own Selection so this check
    # cannot drift from it; a value the model gains is accepted the same day.
    # Only absent and empty mean "no filter". `"null"` is NOT treated as
    # absent here, unlike the sentinels above: a JS caller that stringifies an
    # unset value sends the literal `"null"`, and letting that through as
    # "unfiltered" would hand back the ENTIRE register to a poller that meant
    # to narrow it. An empty list looks like "no matches"; a full list looks
    # like an answer. So it validates like any other unrecognised value: 400.
    label_state = parse_enum(
        "tag_label_state", qs.get("tag_label_state"),
        selection_values("nrs.asset", "tag_label_state", _TAG_LABEL_STATES))
    if label_state is not None:
        domain.append(("tag_label_state", "=", label_state))
    # ── SAP (INT-06/07) ───────────────────────────────────────────────
    #
    # Exact, like the provenance references above and for the same reason:
    # `?sap_asset_number=100000001234` has to return the asset finance booked
    # under that number and nothing else, or it is not a reconciliation.
    raw_sap_number = qs.get("sap_asset_number")
    if raw_sap_number:
        domain.append(("sap_asset_number", "=", raw_sap_number))
    # `?has_sap_code=false` is the auditor's question — which assets has
    # finance not booked — so it is the one filter that must never quietly
    # answer with the whole register. Anything unparseable is a 400: an empty
    # list reads as "no matches", but an unfiltered list reads as an ANSWER,
    # and a caller cannot tell it from one.
    #
    # Stricter than `is_tagged` above on a single point: `"null"` is rejected
    # here rather than read as "no filter". That leniency is `is_tagged`'s
    # published behaviour and stays, but it is the same hole the
    # `tag_label_state` check closes — a JS caller stringifying an unset value
    # sends the literal "null" — and a new parameter should not be born with
    # it.
    has_sap_code = parse_bool("has_sap_code", qs.get("has_sap_code"))
    if has_sap_code is True:
        # `= False` on a Char covers NULL and '' both, so its negation is
        # "there is a code", not merely "the column is not NULL".
        domain.append(("sap_asset_number", "!=", False))
    elif has_sap_code is False:
        domain.append(("sap_asset_number", "=", False))
    # The dual-code state. Same rule as `tag_label_state`, and it matters
    # more here rather than less: an auditor filtering for `exception` is
    # asking to be shown the findings, and a typo answering `200 []` reads as
    # "there are none" — the single most reassuring wrong answer this API can
    # give. `"null"` is not a "no filter" sentinel on an enum.
    recon_state = parse_enum(
        "sap_reconciliation_state", qs.get("sap_reconciliation_state"),
        selection_values("nrs.asset", "sap_reconciliation_state",
                         _SAP_RECONCILIATION_STATES))
    if recon_state is not None:
        domain.append(("sap_reconciliation_state", "=", recon_state))
    # `is_verified` was the worst of the five booleans, because BOTH of its
    # branches were membership tests and there was no third branch at all:
    # `?is_verified=1` fell out of the bottom having appended nothing, and
    # the caller received the ENTIRE register — every asset in it reading as
    # verified, including the ones nobody has laid eyes on. This is the
    # filter an auditor uses to ask what has NOT been physically checked, so
    # the unfiltered list is not merely wrong, it is the answer that ends the
    # enquiry. No published leniency: `"null"` is not absent here.
    is_verified = parse_bool("is_verified", qs.get("is_verified"))
    if is_verified is not None:
        domain.append(("is_verified", "=", is_verified))
    # Warranty (handoff 34). The status is a non-stored compute whose search
    # method applies the same three rules the compute does, on the same
    # Lagos day, so a row this filter returns publishes the status it was
    # filtered on. `"null"` is not absent: `none` is a value here, and a JS
    # caller stringifying an unset one must not be read as asking for it.
    warranty_status = parse_enum(
        "warranty_status", qs.get("warranty_status"),
        selection_values("nrs.asset", "warranty_status", _WARRANTY_STATUSES))
    if warranty_status is not None:
        domain.append(("warranty_status", "=", warranty_status))
    # Expiring soon: an expiry from today to today + N, both inclusive —
    # so it is never an EXPIRED warranty, and a window of 1 is today and
    # tomorrow. Stricter than the id filters: `"null"` is a 400, not "no
    # filter", for the `tag_label_state` reason.
    within = parse_int("warranty_expires_within_days",
                       qs.get("warranty_expires_within_days"),
                       null_is_absent=False, minimum=1,
                       maximum=_WARRANTY_WINDOW_MAX_DAYS)
    if within is not None:
        today = snapshot_today()
        domain += [
            ("warranty_expiry", ">=", today),
            ("warranty_expiry", "<=",
             today + datetime.timedelta(days=within)),
        ]
    return domain


# ─── writable-fields allow-list ──────────────────────────────────────

# `asset_tag` is deliberately ABSENT. It is the number printed on the physical
# label, and a client able to PATCH it can walk the record away from the sticker
# on the asset — which defeats the affix control that verifies a scanned tag
# against the one Cadra issued, and then returns a confusing 400 from that
# control. Tags are minted by Cadra (`_generate_tag`) and moved only through the
# tag-label lifecycle. Breaking change, announced: Vendra is the only live
# consumer and does not write it.
_WRITABLE_FIELDS = {
    "name", "legacy_asset_code", "serial_number",
    "make", "model_name", "manufacturer",
    # Section 12 (handoff 58 §4): what a `tag_id` unit is identified by.
    "colour", "material", "dimensions",
    # Handoff 59 §2: what a `record_only` unit is identified by — a title or
    # plot number, a licence key, a contract. `reference` until handoff 60
    # (ruling 7, BREAKING): renamed before any client read it.
    "record_reference",
    "category_id", "subcategory_id", "asset_type_id", "asset_level", "domain",
    "parent_id",
    # `building_id`, `floor_id` and `room_id` were here until handoff 30 and
    # are deliberately ABSENT. On the Odoo form they drive `location_id`
    # through an `@api.onchange`, and an onchange never runs for the API: so
    # `PATCH {"building_id": …}` was accepted with a 200, rewrote the
    # building — and with it the published address and coordinates, which
    # are computed from the building — and MOVED NOTHING. The asset then
    # contradicted itself, and the movement record correctly said no move
    # had happened (report 28 §1). Re-implementing the onchange inside
    # `write` would be a second copy of a rule, which is how two things that
    # should agree come not to. `location_id` is the one writable statement
    # of where an asset is, and `POST /assets/<id>/move` is the act. All
    # three stay published, read-only, under `data.location_hierarchy`, and
    # stay filters on the list.
    "location_id",
    "custodian_id", "department",
    "condition", "state",
    "currency_id", "purchase_date",
    # Warranty (handoff 34). All optional. A start date and a duration go
    # together and derive `warranty_expiry`; an expiry sent beside them that
    # contradicts them is a 400 `validation_failed` from the model, not an
    # overwrite (`nrs.asset._resolve_warranty`). Every change is an
    # append-only `warranty_changed` event.
    "warranty_expiry", "warranty_start_date", "warranty_months",
    "warrantor", "warranty_reference",
    "purchase_value", "replacement_cost",
    "acquisition_date", "acquisition_cost", "current_value",
    "disposal_date", "disposal_reason",
    # Disposal documentation (specification §13.4, INT-10 §2.9). Three of the
    # six new disposal fields are here and three are deliberately NOT — see
    # the block below the allow-list for why. `disposal_method` describes the
    # route out of the estate and `disposal_reference` cites the document
    # that authorised it; both are descriptions of an event, not assertions
    # of authority, and both are tracked on the asset's mail.thread so a
    # later change leaves a trail. `disposal_proceeds` is money that actually
    # changed hands — a fact finance holds independently and reconciles
    # against a bank statement, which is what makes an overstated figure fail
    # against outside evidence rather than stand as a record.
    "disposal_method", "disposal_reference", "disposal_proceeds",
    # Depreciation policy (PRD §8.6)
    "use_category_policy", "depreciation_method", "useful_life_months",
    "declining_rate", "salvage_rate", "depreciation_start_date",
    # Writable so an external ERP can feed figures for erp_managed assets.
    # Cadra overwrites these for any computed method.
    "accumulated_depreciation", "current_book_value",
    "maintenance_vendor_id",
    # Acquisition provenance (INT-03). Writable on PATCH as well as POST so a
    # mis-keyed GRN can be corrected, but they are write-once in practice:
    # they describe an event that already happened, and Vendra sends them on
    # create. Any later change is tracked on the asset's mail.thread.
    "grn_reference", "purchase_order_reference", "purchase_vendor",
    # Already written by the bulk importer; writable here so an integration
    # can stamp its own provenance rather than be indistinguishable from a
    # hand-keyed record.
    "import_source", "import_date", "import_ref",
    "last_verified_date", "verification_notes",
    "notes",
}

# `disposal_approved_by`, `disposal_approved_date` and
# `disposal_date_reconstructed` are deliberately ABSENT, and they are the
# highest-value omission in this file.
#
# The whole point of the disposal report is the auditor's three-part test —
# **was it authorised, by whom, and is the paper there?** `no_approver` is
# one of its findings. A client able to PATCH `disposal_approved_by` could
# create a disposal and name any user in the tenant as the person who
# authorised it, in the same request, turning that finding into a clean row
# without anybody having authorised anything. That is not a report of the
# estate any more; it is a report of what the integration chose to write.
# `action_approve_disposal` records WHO PRESSED THE BUTTON, which is
# evidence — the same distinction as `sap_code_source`: a code returned by
# SAP is evidence finance booked the asset, a code typed in is a claim that
# they did.
#
# `disposal_approved_date` is withheld for the same reason and one more: a
# writable date beside a non-writable approver would let a client backdate
# an approval it did not make, or move one across a financial year boundary,
# which is a disposal-report answer nobody could challenge from the record.
# It is stamped from the clock at the moment of approval.
#
# `disposal_date_reconstructed` marks a date the 19.0.1.14.0 migration
# RECOVERED from the tracked state change rather than one recorded when the
# disposal happened. A client able to clear it would erase the disclosure
# that the date is a reconstruction — precisely the defect
# `nrs.asset.custody.source = 'tracking_backfill'` exists to prevent. It is
# `readonly=True` on the model and written by the migration and nothing else.
#
# All three are published read-only under `data.disposal`, and they stay that
# way now that the gap report 16 named is closed. `POST /api/v1/assets/<id>/
# approve-disposal` (handoff 23) records a disposal approval over the API
# WITHOUT any of them becoming writable: the approver is the user behind the
# bearer token, never a value in the body, so the route records who called it
# rather than who the caller says approved. The scope decision that closing
# it needed is `approvals:write`, which gates nothing else asset-related — so
# granting it is a deliberate act rather than something a broad credential
# already carries.

#: Every spelling a caller might reach for when it thinks it can name the
#: approver. The route refuses the request rather than dropping the key:
#: dropping it returns `200` to a client that believes it appointed somebody,
#: and the recorded approver is then not the one in the caller's own logs.
_APPROVER_CLAIM_FIELDS = frozenset({
    "disposal_approved_by", "disposal_approved_date", "disposal_approved_at",
    "approved_by", "approved_date", "approved_at", "approver", "approver_id",
    "approved_by_id", "approver_name", "user_id", "uid",
})

# The `sap_*` fields are deliberately ABSENT for the same reason `asset_tag`
# is. They are written by the SAP integration (`_set_sap_master`, INT-07) and
# by the legacy extract loader, and `sap_code_source` records which — a code
# returned by SAP is evidence finance booked the asset, a code typed in is a
# claim that they did. A client able to PATCH `sap_asset_number` could move
# an asset to `reconciled` without SAP having booked anything, which is
# exactly the audit control the dual-code work exists to create; a client
# able to PATCH `sap_reconciliation_state` could do it without even the
# pretence of a code. They are published read-only under `data.sap`.


def _filter_writable(body):
    if not isinstance(body, dict):
        return {}, []
    vals = {k: v for k, v in body.items() if k in _WRITABLE_FIELDS}
    rejected = [k for k in body if k not in _WRITABLE_FIELDS]
    return vals, rejected


#: The one key a save takes that is not a field of the asset (handoff 64
#: §2): `{"id": <suggestion_id>, "ignored": [field, ...]}`, naming the
#: suggestion from a photo the person worked from. Taken off the body
#: BEFORE `_filter_writable`, so it is neither refused nor written to the
#: asset — it decides what the save RECORDS, never what it writes.
AI_SUGGESTION_KEY = "ai_suggestion"


def _ai_suggestion_of(body):
    """`(suggestion, ignored, error)` for a save's `ai_suggestion` block.

    Pops the key from `body`. `ignored` is the fields the person dismissed;
    a proposed field the save does not send is ignored too. Every refusal
    here happens before anything is written."""
    if not isinstance(body, dict) or AI_SUGGESTION_KEY not in body:
        return None, (), None
    from odoo.addons.myservice_asset_register.models.ai_suggestion import (
        SUGGESTED_FIELDS)
    raw = body.pop(AI_SUGGESTION_KEY)
    shape = ("`ai_suggestion` must be {\"id\": <suggestion_id>, "
             "\"ignored\": [field, ...]}. Nothing was written.")
    if not isinstance(raw, dict) or set(raw) - {"id", "ignored"} \
            or isinstance(raw.get("id"), bool) \
            or not isinstance(raw.get("id"), int):
        return None, (), err(ERR_VALIDATION_FAILED, shape,
                             details={"field": AI_SUGGESTION_KEY})
    ignored = raw.get("ignored") or []
    if not isinstance(ignored, list) or any(
            f not in SUGGESTED_FIELDS for f in ignored):
        return None, (), err(
            ERR_VALIDATION_FAILED,
            "`ai_suggestion.ignored` lists fields a suggestion proposes: "
            "%s. Nothing was written." % ", ".join(SUGGESTED_FIELDS),
            details={"field": "ai_suggestion.ignored",
                     "allowed_values": list(SUGGESTED_FIELDS)})
    rec = request.env["nrs.ai.suggestion"].sudo().browse(raw["id"]).exists()
    if not rec:
        return None, (), err(ERR_NOT_FOUND,
                             "No suggestion %d. Nothing was written."
                             % raw["id"], status=404)
    return rec, tuple(ignored), None


def _suggestion_refusal(e):
    return err(e.code, str(e.args[0]) if e.args else str(e),
               status=e.status, details=e.details)


def _applied(event, outcomes, counts, suggestion):
    return {"id": suggestion.id, "event_id": event.id, "counts": counts,
            "fields": outcomes}


def _last_event_id(rec):
    """The newest `nrs.asset.event` id on the asset NOW, or 0. Taken BEFORE
    an action, so `_event_written` can tell the row the action wrote from
    one that was already there."""
    return max(rec.event_ids.ids or [0])


def _event_written(rec, event_type, after):
    """The id of the event of this type written SINCE `after`, or None.

    Not "the newest of this type". That was the first draft, and it answers
    with a PREVIOUS call's row the day an action writes none — unreachable
    when it was written, and one refactor from publishing somebody else's
    verification as the record of yours.
    """
    rec.invalidate_recordset(["event_ids"])
    event = rec.event_ids.filtered(
        lambda e: e.event_type == event_type and e.id > after).sorted("id")[-1:]
    return event.id or None


def _required_reason(body):
    """`(reason, None)` or `(None, error)`. A blank reason is no reason."""
    reason = body.get("reason") if isinstance(body, dict) else None
    if reason is not None and not isinstance(reason, str):
        return None, err(ERR_INVALID_REQUEST, "`reason` must be a string")
    reason = (reason or "").strip()
    if not reason:
        return None, err(ERR_INVALID_REQUEST, "`reason` is required")
    return reason, None


def _browse_or_404(asset_id):
    rec = request.env["nrs.asset"].sudo().browse(int(asset_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Asset {asset_id} not found", status=404)
    return rec, None


def _on_the_register_or_409(rec, act):
    """A received unit not yet on the register cannot be verified, marked
    missing, marked found or condemned (handoff 61, ruling R10; disposal
    since 58). Asked FIRST, before the route's own state checks, so a
    candidate is told what it is rather than "not missing". The model says
    the same under every writer (`_assert_on_the_register`); this is the
    route saying it before anything else is read. Raises `GateRefused`,
    which the envelope makes `409 conflict`, `details.reason =
    "not_on_the_register"`."""
    rec._refuse_off_the_register(act)


# ─── controller ──────────────────────────────────────────────────────

class CadraAssetsV1(http.Controller):

    # ── List: GET /api/v1/assets ───────────────────────────────────

    @cadra_route("/api/v1/assets", method="GET",
                 summary="List assets with filters and cursor pagination",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"type": "array",
                                  "items": {"$ref": "#/components/schemas/Asset"}},
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search across name, asset_code, asset_tag, "
                                     "serial_number, grn_reference, purchase_order_reference"},
                     {"name": "category_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "subcategory_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "location_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "updated_since",
                      "schema": {"type": "string", "format": "date-time"},
                      "description": (
                          "Handoff 61 — the sync filter. Assets whose own "
                          "record changed at or after this instant "
                          "(`updated_at`). ISO-8601 date or date-time; no "
                          "zone means UTC. Composes with every other filter, "
                          "`location_id` and `register_state=any` included; "
                          "order and paging unchanged (by id). Unparseable "
                          "is a 400, never the whole register. A change to a "
                          "related record (a photo, a custody row) does not "
                          "move `updated_at`. To page a sync without missing "
                          "a row changed mid-sync, see "
                          "docs/integrations/mobile-ai-capture-endpoints.md.")},
                     {"name": "building_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "floor_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "room_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "custodian_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "parent_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "state", "schema": {"type": "string",
                      "enum": ["active", "in_repair", "disposed",
                               "transferred", "missing"]},
                      "description": _ENUM_FILTER_400},
                     {"name": "condition", "schema": {"type": "string",
                      "enum": ["new", "good", "fair", "poor",
                               "decommissioned"]},
                      "description": _ENUM_FILTER_400},
                     # `domain` and `asset_level` published no enum at all
                     # until this pass, while the model has always had one —
                     # so the documented surface was wider than the data and
                     # a caller had nothing to validate against. Additive:
                     # every value listed is one the model already accepts.
                     # Taken from the tuples the filter itself falls back to,
                     # so the published list and the floor cannot drift.
                     {"name": "domain", "schema": {"type": "string",
                      "enum": list(_FM_DOMAINS)},
                      "description": "The FM domain, inherited from the "
                                     "asset's category. " + _ENUM_FILTER_400},
                     {"name": "asset_level", "schema": {"type": "string",
                      "enum": list(_ASSET_LEVELS)},
                      "description": "Position in the asset hierarchy. "
                                     + _ENUM_FILTER_400},
                     {"name": "is_verified", "schema": {"type": "boolean"},
                      "description": "Whether the last physical verification is "
                                     "still inside its window. This EXPIRES: the "
                                     "window is the asset category's "
                                     "`verification_interval_days`, falling back to "
                                     "the tenant default (365 days), and a daily job "
                                     "re-evaluates it. An asset can therefore go from "
                                     "true to false with no write to the record. "
                                     "An unparseable value is a 400 "
                                     "`invalid_request`, never the unfiltered "
                                     "list — this filter asks what has not been "
                                     "physically checked, and the whole register "
                                     "is not an answer to that."},
                     {"name": "warranty_status", "schema": {"type": "string",
                      "enum": list(_WARRANTY_STATUSES)},
                      "description": (
                          "`under_warranty` — an expiry on or after today; "
                          "`expired` — an expiry before today; `none` — no "
                          "warranty recorded, which is the ordinary case and "
                          "is never folded into `expired`. Today is a LAGOS "
                          "day (UTC+1), and every row returned publishes the "
                          "same `warranty.status`. This EXPIRES with the "
                          "calendar, with no write to the record. A warranty "
                          "is a fact about a contract and says nothing about "
                          "whether the asset is in service. "
                          + _ENUM_FILTER_400)},
                     {"name": "warranty_expires_within_days",
                      "schema": {"type": "integer", "minimum": 1,
                                 "maximum": _WARRANTY_WINDOW_MAX_DAYS},
                      "description": (
                          "Expiring soon: a warranty expiry from today to "
                          "today + N days, both inclusive and both LAGOS "
                          "days — never one already expired. Combines with "
                          "every other filter. Outside 1–%d, or not an "
                          "integer (the literal `null` included), is a 400 "
                          "`invalid_request`." % _WARRANTY_WINDOW_MAX_DAYS)},
                     {"name": "grn_reference", "schema": {"type": "string"},
                      "description": "Exact match. Returns every asset created "
                                     "from that goods receipt (INT-03)."},
                     {"name": "purchase_order_reference", "schema": {"type": "string"},
                      "description": "Exact match on the purchase order reference."},
                     {"name": "purchase_vendor", "schema": {"type": "string"},
                      "description": "Exact match on the supplying vendor."},
                     {"name": "import_source", "schema": {"type": "string",
                      "enum": ["myservice", "sap", "redhubb", "vendra",
                               "excel", "other"]},
                      "description": "Which system wrote the record; `vendra` "
                                     "is an INT-03 goods receipt. "
                                     + _ENUM_FILTER_400},
                     {"name": "import_ref", "schema": {"type": "string"},
                      "description": "Exact match on the writing system's own batch reference."},
                     {"name": "is_tagged", "schema": {"type": "boolean"},
                      "description": "True returns only assets with a label "
                                     "confirmed affixed (INT-04/05). This is "
                                     "the physical-tagging question; the `tag` "
                                     "field is populated from creation and "
                                     "does not answer it. Anything other than "
                                     "`true`/`false` is a 400 `invalid_request`. "
                                     "The literal `null` is read as 'no filter' "
                                     "here, which is this parameter's published "
                                     "behaviour and is not shared by the other "
                                     "filters."},
                     {"name": "tag_label_state", "schema": {"type": "string",
                      "enum": ["issued", "printed", "affixed", "scrapped"]},
                      "description": (
                          "Filter on the label's physical lifecycle. A value "
                          "outside the enum is a 400 `invalid_request` "
                          "carrying `details.allowed_values`, not an empty "
                          "list.")},
                     {"name": "sap_asset_number", "schema": {"type": "string"},
                      "description": "Exact match on the SAP asset number "
                                     "(INT-07). The SAP half of the dual-code "
                                     "pair; `asset_code` is Cadra's half."},
                     {"name": "has_sap_code", "schema": {"type": "boolean"},
                      "description": (
                          "True returns only assets linked to a SAP asset "
                          "number; false returns only those with none — the "
                          "completeness question. An unparseable value is a "
                          "400 `invalid_request`, never the unfiltered list. "
                          "Unlike `is_tagged`, the literal `null` is "
                          "rejected rather than read as 'no filter'.")},
                     {"name": "sap_reconciliation_state",
                      "schema": {"type": "string",
                                 "enum": ["not_tagged", "pending",
                                          "reconciled", "exception"]},
                      "description": (
                          "The dual-code control (INT-06/07). `reconciled` "
                          "means both the Cadra asset code and the SAP asset "
                          "code are linked; `exception` means the asset is "
                          "tagged and SAP has not booked it, which is the "
                          "audit finding. `not_tagged` is not a finding — "
                          "the SAP posting is not yet due. A value outside "
                          "the enum is a 400 `invalid_request` carrying "
                          "`details.allowed_values`, not an empty list.")},
                     {"name": "sort",
                      "schema": {"type": "string",
                                 "enum": list(_LIST_SORT_VALUES),
                                 "default": "oldest"},
                      "description": (
                          "Row order. `oldest` (the default, and what this "
                          "endpoint has always returned) walks ascending "
                          "asset id — oldest first. `newest` walks the same "
                          "keyset backwards, so the most recently created "
                          "asset is the first row of page one. A value "
                          "outside the enum is a 400 `invalid_request` "
                          "carrying `details.allowed_values`.\n\n"
                          "**Keep it the same for every page of one walk.** "
                          "A `cursor` records the direction it was issued "
                          "for; replaying it against the other direction is "
                          "a 400 rather than a page that silently skips the "
                          "rows you have not seen.")},
                     {"name": "register_state",
                      "schema": {"type": "string",
                                 "enum": ["any", *REGISTER_STATES]},
                      "description": (
                          "Handoff 57. Absent: registered assets only — a "
                          "receipt candidate is not on the register. `any` "
                          "or one state shows candidates and needs the "
                          "`candidates:read` scope (403 without it).")},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_assets(self, **kwargs):
        qs = get_params()
        Asset = request.env["nrs.asset"].sudo()
        state_terms, state_err = _register_state_domain(qs)
        if state_err:
            return state_err
        try:
            domain = _list_domain(qs) + state_terms
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        limit = parse_limit(qs)
        # Inside the same `try` as the domain builder: `parse_enum` refuses
        # an unknown value with a `BadFilter` carrying `allowed_values`, and
        # this route answers that as a 400 beside its other bad filters
        # rather than leaning on the decorator's floor.
        try:
            sort = parse_enum("sort", qs.get("sort"), _LIST_SORT_VALUES)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        page, next_cursor, total = paginate(
            Asset, domain,
            limit=limit, cursor=qs.get("cursor"),
            descending=(sort == "newest"),
        )
        return ok(
            data=[serialize_asset(a) for a in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── Get single: GET /api/v1/assets/<id> ────────────────────────

    @cadra_route("/api/v1/assets/<int:id>", method="GET",
                 summary="Get a single asset by id",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: transfers, custody, pm, children. `custody` embeds the WHOLE chain of custody, oldest first and uncapped; `GET /assets/<id>/custody` is the paginated form for a chain long enough to want one. A section outside that set is a 400 `invalid_request` carrying `details.allowed_values` — never a silently omitted embed, which a caller cannot tell from a section that is genuinely empty."},
                 ])
    def get_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        try:
            include = _parse_include(kwargs.get("include"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        return serialize_asset(rec, include=include)

    # ── Get by tag: GET /api/v1/assets/by-tag/<tag> ────────────────

    @cadra_route("/api/v1/assets/by-tag/<string:tag>", method="GET",
                 summary="Get a single asset by asset_tag (or asset_code as fallback)",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: transfers, custody, pm, children. `custody` embeds the WHOLE chain of custody, oldest first and uncapped; `GET /assets/<id>/custody` is the paginated form for a chain long enough to want one. A section outside that set is a 400 `invalid_request` carrying `details.allowed_values` — never a silently omitted embed, which a caller cannot tell from a section that is genuinely empty."},
                 ])
    def get_asset_by_tag(self, tag, **kwargs):
        # A single-record lookup: it finds a receipt candidate too, like
        # `GET /assets/<id>` (handoff 57 hides candidates from LISTS).
        Asset = request.env["nrs.asset"].sudo().with_context(
            cadra_candidates=True)
        rec = Asset.search([("asset_tag", "=", tag)], limit=1) \
            or Asset.search([("asset_code", "=", tag)], limit=1)
        if not rec:
            return err(ERR_NOT_FOUND, f"No asset with tag or code '{tag}'", status=404)
        try:
            include = _parse_include(kwargs.get("include"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        return serialize_asset(rec, include=include)

    # ── Create: POST /api/v1/assets ────────────────────────────────

    @cadra_route("/api/v1/assets", method="POST",
                 summary="Create a new asset (asset_code auto-generated if omitted)",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 request_schema={
                     "type": "object",
                     "required": ["name"],
                     "properties": {
                         "name": {"type": "string"},
                         "legacy_asset_code": {"type": "string", "nullable": True},
                         "serial_number": {"type": "string", "nullable": True},
                         "make": {"type": "string", "nullable": True},
                         "model_name": {"type": "string", "nullable": True},
                         "manufacturer": {"type": "string", "nullable": True},
                         "colour": {"type": "string", "nullable": True,
                                    "description": "Section 12 attribute "
                                                   "(handoff 58). Mandatory "
                                                   "at a gated receipt when "
                                                   "the class's schema says "
                                                   "so."},
                         "material": {"type": "string", "nullable": True},
                         "dimensions": {"type": "string", "nullable": True},
                         "record_reference": {
                                       "type": "string", "nullable": True,
                                       "description": "Handoff 59 (named "
                                                      "`reference` until "
                                                      "handoff 60). Title or "
                                                      "plot number, licence "
                                                      "key or contract — "
                                                      "what identifies a "
                                                      "`record_only` unit. "
                                                      "Mandatory at a gated "
                                                      "receipt when the "
                                                      "class's schema says "
                                                      "so."},
                         "category_id": {"type": "integer", "nullable": True},
                         "subcategory_id": {"type": "integer", "nullable": True},
                         "asset_type_id": {"type": "integer", "nullable": True},
                         "asset_level": {"type": "string", "nullable": True},
                         "domain": {"type": "string", "nullable": True},
                         "parent_id": {"type": "integer", "nullable": True},
                         "location_id": {"type": "integer", "nullable": True},
                         "custodian_id": {"type": "integer", "nullable": True,
                                          "description": "hr.employee id"},
                         "department": {"type": "string", "nullable": True},
                         "condition": {"type": "string",
                                       "enum": ["new", "good", "fair", "poor",
                                                "decommissioned"]},
                         "state": {"type": "string",
                                   "enum": ["active", "in_repair", "disposed",
                                            "transferred", "missing"]},
                         "currency_id": {"type": "integer", "nullable": True},
                         "purchase_date": {"type": "string", "format": "date", "nullable": True},
                         "warranty_expiry": {
                             "type": "string", "format": "date", "nullable": True,
                             "description": (
                                 "The last day the warranty covers. DERIVED "
                                 "when `warranty_start_date` and "
                                 "`warranty_months` are both sent — leave it "
                                 "out then; a value that contradicts them is "
                                 "a 400 `validation_failed`. Send it alone "
                                 "only when a date is all that is known.")},
                         "warranty_start_date": {
                             "type": "string", "format": "date", "nullable": True,
                             "description": (
                                 "The day the warranty runs from — usually "
                                 "the day of receipt. Goes together with "
                                 "`warranty_months`: one without the other "
                                 "is a 400 `validation_failed`.")},
                         "warranty_months": {
                             "type": "integer", "minimum": 1, "maximum": 600,
                             "nullable": True,
                             "description": (
                                 "How long the warranty runs, in whole "
                                 "calendar months, as quoted (24 for two "
                                 "years).")},
                         "warrantor": {
                             "type": "string", "nullable": True,
                             "description": (
                                 "WHO HONOURS the warranty — manufacturer, "
                                 "supplier or service agent — as a name, "
                                 "recorded as sent. Not a link to any "
                                 "record.")},
                         "warranty_reference": {
                             "type": "string", "nullable": True,
                             "description": (
                                 "The warranty certificate or document "
                                 "number, free text, as given.")},
                         "purchase_value": {"type": "number", "nullable": True},
                         "replacement_cost": {"type": "number", "nullable": True},
                         "acquisition_date": {"type": "string", "format": "date", "nullable": True},
                         "acquisition_cost": {"type": "number", "nullable": True},
                         "current_value": {"type": "number", "nullable": True},
                         "maintenance_vendor_id": {"type": "integer", "nullable": True,
                                                   "description": "Who services the asset. "
                                                                  "NOT the supplier — use "
                                                                  "`purchase_vendor` for that."},
                         "grn_reference": {"type": "string", "nullable": True,
                                           "description": "Goods Receipt Note reference "
                                                          "from the receiving system (INT-03)."},
                         "purchase_order_reference": {"type": "string", "nullable": True,
                                                      "description": "Purchase Order reference."},
                         "purchase_vendor": {"type": "string", "nullable": True,
                                             "description": "Supplier the asset was bought from."},
                         "import_source": {"type": "string",
                                           "enum": ["myservice", "sap", "redhubb",
                                                    "vendra", "excel", "other"],
                                           "description": "Which system wrote this record. "
                                                          "Defaults to `myservice`."},
                         "import_date": {"type": "string", "format": "date", "nullable": True},
                         "import_ref": {"type": "string", "nullable": True,
                                        "description": "The writing system's own batch "
                                                       "or transaction reference."},
                         "notes": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "name": "Dell Latitude 7430",
                     "serial_number": "5XJZ8T3",
                     "make": "Dell",
                     "model_name": "Latitude 7430",
                     "manufacturer": "Dell Inc.",
                     "category_id": 7,
                     "location_id": 12,
                     "custodian_id": 105,
                     "condition": "new",
                     "state": "active",
                     "purchase_date": "2026-05-10",
                     "purchase_value": 1850.00,
                     "grn_reference": "GRN-2026-00001",
                     "purchase_order_reference": "PO-2026-00417",
                     "purchase_vendor": "Dell Nigeria Ltd",
                     "import_source": "other",
                     "import_date": "2026-05-12",
                     "import_ref": "VENDRA-RCPT-00114",
                     "warranty_start_date": "2026-05-12",
                     "warranty_months": 24,
                     "warrantor": "Dell Nigeria Ltd",
                     "warranty_reference": "DL-WC-55120",
                 })
    def create_asset(self, **kwargs):
        body = get_params()
        suggestion, ignored, error = _ai_suggestion_of(body)
        if error:
            return error
        vals, rejected = _filter_writable(body)
        if rejected:
            return refuse_unwritable(rejected, _WRITABLE_FIELDS)
        if not vals.get("name"):
            return err(ERR_INVALID_REQUEST, "`name` is required")
        if suggestion:
            from odoo.addons.myservice_asset_register.models.ai_suggestion \
                import SuggestionRefused
            try:
                suggestion._check_applicable(None)
            except SuggestionRefused as e:
                return _suggestion_refusal(e)
        # An asset created already assigned to somebody opens its chain of
        # custody. `nrs.asset.create` records the link; this says where it
        # came from, so the row does not read as an anonymous direct write.
        Asset = request.env["nrs.asset"].sudo()
        # Handoff 57 §2b, kept by 58: with the tenant's receipt gate on, a
        # receipt enters as a CANDIDATE — `captured`, and no label minted
        # (the mint moved to `request-tagging`). The model then refuses what
        # the class cannot accept (Section 12: a serial-mode unit with no
        # serial, a `tag_id` unit missing an attribute, a `pool` unit, a
        # serial already on the register) and a custodian (P5), each a
        # `GateRefused` the envelope maps (`utils.gate_refusal`). Switch off:
        # none of that is asked, and the route does what it always did.
        if Asset._receipt_gated():
            vals["register_state"] = "captured"
        rec = Asset.with_context(
            cadra_custody_source="api_write",
            cadra_movement_source="api_write",
            cadra_event_source="api_write").create(vals)
        if suggestion:
            data = serialize_asset(rec)
            data[AI_SUGGESTION_KEY] = _applied(
                *suggestion._apply(rec, vals, ignored,
                                   actor=request.env.user), suggestion)
            return data
        return serialize_asset(rec)

    # ── Patch: PATCH /api/v1/assets/<id> ───────────────────────────

    @cadra_route("/api/v1/assets/<int:id>", method="PATCH",
                 summary="Partial update of an asset",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/assets. A field this route does not "
                                     "accept is a 400 `invalid_request` naming it "
                                     "in `details.rejected_fields`, with "
                                     "`details.writable` listing what is "
                                     "accepted — and NOTHING is written."),
                     "properties": {
                         "name": {"type": "string"},
                         "condition": {"type": "string",
                                       "enum": ["new", "good", "fair", "poor",
                                                "decommissioned"]},
                         "state": {"type": "string",
                                   "enum": ["active", "in_repair", "disposed",
                                            "transferred", "missing"]},
                         "notes": {"type": "string"},
                         "custodian_id": {"type": "integer"},
                         "location_id": {"type": "integer"},
                         "grn_reference": {"type": "string",
                                           "description": "Correctable, but write-once in "
                                                          "practice — it records an event "
                                                          "that already happened."},
                         "purchase_order_reference": {"type": "string"},
                         "purchase_vendor": {"type": "string"},
                     },
                 },
                 request_example={
                     "condition": "fair",
                     "notes": "Hinge cracked — flagged for replacement.",
                 })
    def patch_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        suggestion, ignored, error = _ai_suggestion_of(body)
        if error:
            return error
        vals, rejected = _filter_writable(body)
        # BEFORE the write, and whatever else the body holds. Until handoff 31
        # a PATCH whose EVERY field was refused passed the check below, wrote
        # nothing, and answered 200 — typed, saved, unchanged, no message.
        if rejected:
            return refuse_unwritable(rejected, _WRITABLE_FIELDS)
        if not vals:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        if suggestion:
            from odoo.addons.myservice_asset_register.models.ai_suggestion \
                import SuggestionRefused
            try:
                suggestion._check_applicable(rec)
            except SuggestionRefused as e:
                return _suggestion_refusal(e)

        # ── Nobody moves an asset alone (handoff 35) ─────────────────
        #
        # PATCH is the ambiguous writer. It is how the Cadra app's edit form
        # saves, and report 28 found it moves an asset with no reason and no
        # transfer document — so it IS a person deciding, and it is gated.
        #
        # **Only when the value actually CHANGES.** The edit form re-sends
        # `location_id` and `custodian_id` on every save whether or not
        # anybody touched them, so refusing the mere presence of the key
        # would make saving a note on an asset impossible. That is the trap
        # `CLAUDE.md` names — *a screen that PATCHes back the object it
        # GET-ed now fails* — and it is avoided by comparing, here and in the
        # model, rather than by looking at the shape of the body.
        #
        # A 400 and not a raised request, deliberately. A PATCH carries a
        # whole object; turning part of it into a request and writing the
        # rest would leave the caller with a half-applied save and no way to
        # tell which half. Refusing the WHOLE body is the contract handoff 31
        # published for every write route, and the message names the route
        # that does the job.
        #
        # THE TERMINAL RULE SPEAKS FIRST. A disposed asset cannot move or
        # change hands at all, so telling somebody to go and raise an
        # approval request for it names a remedy that cannot work however
        # many people agree — the same fault as the clearing dead end, one
        # route along. `_assert_disposed_is_terminal` is a no-op on every
        # other asset and `_write_recorded` calls it again below; this is
        # only about WHICH rule gets to answer. Found by the pytest pass,
        # which pinned the old wording rather than letting it later read as
        # a regression. Both ACTION routes already got this right.
        rec._assert_disposed_is_terminal(vals)
        # A receipt candidate is not on the register: no custodian, no move,
        # no disposal (handoff 58, P5) — before the approval refusal below,
        # whose remedy (`/move`, `/transfer-custody`) would not work either.
        rec._assert_on_the_register(vals)
        if _approval_required():
            # `vals[f]` truthy: CLEARING is not a grant and is not gated —
            # see `nrs.asset._assert_change_is_approved`, where the rule
            # lives. Repeated here only so the route does not refuse
            # something the model would allow, which is how a refusal comes
            # to name a remedy that cannot work: the verification pass found
            # this exact pair, where un-assigning a custodian was refused
            # with a message naming a route that requires a custodian.
            needs_approval = sorted(
                f for f in ("location_id", "custodian_id")
                if f in vals and vals[f]
                and rec._change_is_real(f, vals[f]))
            if needs_approval:
                routes = {"location_id": "POST /api/v1/assets/%s/move" % rec.id,
                          "custodian_id":
                              "POST /api/v1/assets/%s/transfer-custody" % rec.id}
                return err(
                    ERR_INVALID_REQUEST,
                    "This register requires a second person to approve a "
                    "change of %s, so it cannot be PATCHed: use %s, which "
                    "raises a request. Nothing in this call was written."
                    % (" or ".join("`%s`" % f for f in needs_approval),
                       " and ".join(routes[f] for f in needs_approval)),
                    details={
                        "asset_id": rec.id,
                        "approval_required": True,
                        "rejected_fields": needs_approval,
                        # The same two keys every other refusal publishes, so
                        # a caller repairing itself from `details.writable`
                        # finds it here too.
                        "writable": sorted(_WRITABLE_FIELDS - set(needs_approval)),
                        "use_instead": {f: routes[f] for f in needs_approval},
                    })
        if vals:
            # `custodian_id` is in `_WRITABLE_FIELDS`, so this route moves
            # custody as surely as transfer-custody does — it just does not
            # announce it. The recorder in `nrs.asset.write` catches it
            # either way; the context is what stops it being labelled
            # `direct`.
            # The same for `nrs.asset.event` (handoff 30): `state`,
            # `last_verified_date` and two of the three recorded references
            # are writable here, so this route changes a status as surely
            # as `/condemn` does. A model refusal — a disposed asset may not
            # change status, move or change hands — is raised in that
            # `write`, rolls the transaction back and answers 400
            # `validation_failed` in the model's own words.
            rec.with_context(cadra_custody_source="api_write",
                             cadra_movement_source="api_write",
                             cadra_event_source="api_write").write(vals)
        if suggestion:
            data = serialize_asset(rec)
            data[AI_SUGGESTION_KEY] = _applied(
                *suggestion._apply(rec, vals, ignored,
                                   actor=request.env.user), suggestion)
            return data
        return serialize_asset(rec)

    # ── Move action: POST /api/v1/assets/<id>/move ─────────────────

    @cadra_route("/api/v1/assets/<int:id>/move", method="POST",
                 summary="Move an asset to a location — or place one that has none",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object",
                     "required": ["to_location_id"],
                     "description": (
                         "BREAKING since handoff 35 on any tenant where "
                         "approval is required (the default): this route "
                         "RAISES A REQUEST instead of moving the asset, and "
                         "`approver_id` becomes required. The response then "
                         "carries `pending_approval: true`, the `request`, "
                         "and `asset` UNCHANGED. Read `pending_approval` "
                         "before believing the asset moved. "
                         "`GET /api/v1/settings/approvals` says which "
                         "behaviour this tenant has."),
                     "properties": {
                         "to_location_id": {"type": "integer",
                                            "description": "Destination generic.location id"},
                         "approver_id": {
                             "type": "integer", "nullable": True,
                             "description": "WHO IS BEING ASKED to approve "
                                            "— a res.users id from "
                                            "GET /api/v1/approvals/approvers. "
                                            "Required when the tenant "
                                            "requires approval, ignored when "
                                            "it does not. A nomination only: "
                                            "who DECIDED is taken from the "
                                            "approving caller's own token "
                                            "and can never be supplied."},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_location_id": 47,
                     "approver_id": 12,
                     "reason": "Reassigned to new project room",
                 })
    def move_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        try:
            to_loc_id = int(body.get("to_location_id") or 0)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST, "`to_location_id` must be an integer")
        if not to_loc_id:
            return err(ERR_INVALID_REQUEST, "`to_location_id` is required")
        to_loc = request.env["generic.location"].sudo().browse(to_loc_id)
        if not to_loc.exists():
            return err(ERR_NOT_FOUND, f"Destination location {to_loc_id} not found", status=404)

        from_loc = rec.location_id
        if from_loc.id == to_loc.id:
            return err(ERR_INVALID_REQUEST, "Asset is already at the requested location",
                       details={"current_location_id": from_loc.id})

        # EVERY refusal happens above this line, because everything below it
        # writes. The first draft of handoff 28 validated `reason` AFTER the
        # transfer document had been created: a refused request returned 400
        # and left behind a transfer in state `done`, for a move that never
        # happened — a false record, written by the change meant to end them.
        # An error RESPONSE does not roll the transaction back; only an
        # exception does. Found by fact-checking the endpoint reference.
        reason = body.get("reason") or ""
        if reason and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")

        # ASKED EARLY, not re-stated. Whether a disposed asset may move is
        # the model's rule and is refused in `nrs.asset.write` for every
        # writer; this calls that same method before anything is drawn. The
        # transfer row below rolls back with the refusal — an `ir.sequence`
        # number does not, so a refused move used to leave a gap in the
        # transfer references, one per attempt, that no transfer explained.
        rec._assert_disposed_is_terminal({"location_id": to_loc.id})
        # Handoff 58, P5: a receipt candidate is moved by nobody.
        rec._refuse_off_the_register("move")

        # ── Nobody moves an asset alone (handoff 35) ─────────────────
        #
        # STILL ABOVE EVERY WRITE, for the reason the block above says: an
        # `err(...)` return does not roll the transaction back, so anything
        # that can refuse has to refuse before anything is drawn. The
        # transfer document below is exactly what handoff 28 left behind on a
        # refused move, and it took a doc fact-check to find.
        #
        # The model refuses this write anyway — the gate is on
        # `nrs.asset._write_recorded`, under all twelve writers of
        # `location_id`, not here. What is here is the good answer: a request
        # with a reference number and somebody's name on it, instead of the
        # model's `UserError` arriving as a 400 on a button the app told the
        # user to press.
        if _approval_required():
            conflict = _pending_conflict(rec)
            if conflict:
                return conflict
            approver, approver_err = _resolve_approver(body, rec)
            if approver_err:
                return approver_err
            change = request.env["nrs.asset.change.request"].sudo().create({
                "asset_id": rec.id,
                "change_type": "location",
                "to_location_id": to_loc.id,
                "approver_id": approver.id,
                "reason": reason or False,
            })
            return _raised_payload(change, rec, action="move")

        # AN ASSET THAT IS NOWHERE IS PLACED, NOT TRANSFERRED.
        # `nrs.asset.transfer` requires BOTH locations — it is a document about
        # going from one place to another, and "from nowhere" is not a place.
        # This route used to build one regardless, so moving an asset with no
        # current location died on the NOT NULL and answered 400
        # *"Required field missing: from_location_id"*: a message about a
        # column in a table the user has never heard of, for the most ordinary
        # act in the register. 358 of `nrs19`'s assets and 1,920 of
        # `jaizbankplc`'s — 46% of that register — had no location and could
        # not be given one with the Move button at all. Reported by the owner,
        # from the screen. Handoff 28 had already said what the answer is: the
        # MOVE is the fact, the transfer is paperwork, and a move is not always
        # a transfer. The movement record below captures who, when, where and
        # why either way; the document is made when there is something for it
        # to say.
        transfer = request.env["nrs.asset.transfer"]
        if from_loc:
            seq = request.env["ir.sequence"].next_by_code("nrs.asset.transfer") or "/"
            transfer = transfer.sudo().create({
                "name": seq,
                "asset_id": rec.id,
                "from_location_id": from_loc.id,
                "to_location_id": to_loc.id,
                "from_custodian_id": rec.custodian_id.id or False,
                "to_custodian_id": rec.custodian_id.id or False,
                "transfer_date": odoo_fields.Date.today(),
                "reason": reason,
                "state": "done",
            })
        # The move itself is recorded by `nrs.asset.write`, append-only, as
        # an `nrs.asset.movement` — underneath every writer of `location_id`,
        # not here. What only this route knows is that the move was asked for
        # as a move, why, and which transfer document it produced.
        rec.with_context(
            cadra_custody_source="api_write",
            cadra_movement_source="api_move",
            cadra_movement_reason=reason or False,
            cadra_movement_transfer_id=transfer.id or False,
        ).write({"location_id": to_loc.id})
        movement = rec.movement_ids.sorted("id")[-1:]
        movement_id = movement.id if movement else None

        return {
            "asset": serialize_asset(rec),
            # The append-only record this call produced — the FACT, and what
            # `GET /assets/<id>/history` reads. At the top level since the
            # asset-with-no-location case, because there it is the ONLY
            # record: there is no transfer to hang it on.
            "movement_id": movement_id,
            # NULL when the asset had no location to be transferred FROM. A
            # consumer reading `transfer.id` must allow for that; one reading
            # `asset` — which is all the Cadra app reads — is unaffected.
            "transfer": {
                "id": transfer.id,
                "reference": transfer.name,
                "from_location": _ref(from_loc),
                "to_location": _ref(to_loc),
                # Kept where handoff 28 put it. Same value as the top-level key.
                "movement_id": movement_id,
            } if transfer else None,
        }

    # ── Verify: POST /api/v1/assets/<id>/verify ────────────────────

    @cadra_route("/api/v1/assets/<int:id>/verify", method="POST",
                 summary="Record that this asset was physically verified, "
                         "and by whom",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "properties": {
                         "notes": {"type": "string", "nullable": True,
                                   "description": "What was checked, or "
                                                  "what was found."},
                     },
                 },
                 request_example={"notes": "Sighted at desk 4F-12, tag intact"})
    def verify_asset(self, id, **kwargs):
        """A verification is somebody saying they checked. This records who.

        `last_verified_date` is in `_WRITABLE_FIELDS`, so `PATCH
        {"last_verified_date": …}` has always been able to mark an asset
        verified — and it records a date and NO PERSON, because
        `last_verified_by` is deliberately not writable: a verifier a client
        can name is a claim, not evidence. Until handoff 28 that PATCH was
        what the Cadra app's own Verify button sent, so report 27 could say
        of a government asset register that *no record anywhere says a
        physical check was made*.

        This route is the other door. It takes no date and no verifier: the
        date is today and the verifier is the ACTING USER — the person logged
        in, or the API client's own user — for the reason `approve-disposal`
        gives. PATCH keeps accepting the date; it is an integration's way to
        carry a verification made elsewhere, and what it cannot do is say who.

        What this buys, plainly: the asset holds the LAST verifier — one
        overwritten pair of columns — and, since handoff 30, every call also
        appends an `nrs.asset.event` of type `verified` that nobody can edit
        or delete. *"Show me every time this asset was checked, and by
        whom"* is answered from those, by `GET /assets/<id>/history`.
        `data.event_id` is the one this call wrote. Verifications made
        before that record began exist only as a chatter line, and the
        history says from when.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        _on_the_register_or_409(rec, "verification")
        body = get_params()
        notes = body.get("notes") or ""
        if notes and not isinstance(notes, str):
            return err(ERR_INVALID_REQUEST, "`notes` must be a string")
        before = _last_event_id(rec)
        rec.with_context(cadra_event_source="api_verify").action_verify(
            notes=notes or None)
        return {
            "asset": serialize_asset(rec),
            "verification": {
                "verified_on": _date(rec.last_verified_date),
                "verified_by": _ref(rec.last_verified_by),
                "notes": rec.verification_notes or None,
            },
            # The append-only record this call produced. ADDITIVE.
            "event_id": _event_written(rec, "verified", before),
        }

    # ── Mark missing: POST /api/v1/assets/<id>/mark-missing ────────

    @cadra_route("/api/v1/assets/<int:id>/mark-missing", method="POST",
                 summary="Mark an asset missing, and record why",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object",
                     "required": ["reason"],
                     "properties": {
                         "reason": {"type": "string",
                                    "description": "The circumstances: where "
                                                   "it was looked for, when "
                                                   "it was last seen, who "
                                                   "reported it."},
                     },
                 },
                 request_example={"reason": "Not found at desk 4F-12 during "
                                            "the Q3 verification exercise; "
                                            "last sighted 2026-06-30."})
    def mark_asset_missing(self, id, **kwargs):
        """An asset that cannot be found may be a loss. This records WHY.

        `PATCH {"state": "missing"}` has always been able to mark an asset
        missing and still can — it is how the Cadra app did it until handoff
        30 — but a PATCH has nowhere to put a sentence, so the first question
        anybody asks about a missing asset had no answer anywhere. The reason
        given here is written to the append-only `status_changed` event:
        what was said when it was marked, by whom, which nobody can tidy up
        afterwards. It is NOT a field on the asset.

        `reason` is REQUIRED, and that is deliberate on a new route: loosening
        it later breaks nobody, tightening it later would.

        **409** — already missing, or disposed. A disposed asset's status
        cannot change (the model refuses it for every writer); asking again
        for one already missing would append nothing, and a 200 for nothing
        is the answer this API refuses to give.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        _on_the_register_or_409(rec, "missing")
        reason, error = _required_reason(get_params())
        if error:
            return error
        if rec.state in ("missing", "disposed"):
            return err(
                ERR_CONFLICT,
                "This asset is already %s." % (
                    "missing" if rec.state == "missing" else
                    "disposed of, and a disposed asset cannot be marked "
                    "missing"),
                status=409, details={"asset_id": rec.id, "state": rec.state})
        before = _last_event_id(rec)
        rec.with_context(
            cadra_event_source="api_mark_missing").action_mark_missing(
                reason=reason)
        return {
            "asset": serialize_asset(rec),
            "event_id": _event_written(rec, "status_changed", before),
        }

    # ── Mark found: POST /api/v1/assets/<id>/mark-found ────────────

    @cadra_route("/api/v1/assets/<int:id>/mark-found", method="POST",
                 summary="A missing asset turned up — record where",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object",
                     "required": ["reason"],
                     "properties": {
                         "reason": {"type": "string",
                                    "description": "Where it turned up, who "
                                                   "found it, what state it "
                                                   "was in."},
                     },
                 },
                 request_example={"reason": "Found in the 2nd-floor store "
                                            "room during the October count, "
                                            "tag intact. It had been moved "
                                            "there for a repaint."})
    def mark_asset_found(self, id, **kwargs):
        """*Where it turned up* is as much an audit fact as *why it went*.

        `PATCH {"state": "active"}` has always been able to bring a missing
        asset back and still can — but a PATCH has nowhere to put a sentence,
        so an asset reappeared having recorded nothing about the most
        interesting event in its life. The reason given here is written to
        the append-only `status_changed` event, beside the one that says why
        it went missing. It sets `state` back to `active`. It does not verify
        the asset: whoever found it may not be whoever checks it.

        `reason` is REQUIRED, for `mark-missing`'s reason.

        **409** — the asset is not missing. There is nothing to find.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        _on_the_register_or_409(rec, "found")
        reason, error = _required_reason(get_params())
        if error:
            return error
        if rec.state != "missing":
            return err(ERR_CONFLICT,
                       "This asset is not missing, so it cannot be marked found.",
                       status=409,
                       details={"asset_id": rec.id, "state": rec.state})
        before = _last_event_id(rec)
        rec.with_context(
            cadra_event_source="api_mark_found").action_mark_found(
                reason=reason)
        return {
            "asset": serialize_asset(rec),
            "event_id": _event_written(rec, "status_changed", before),
        }

    # ── Condemn: POST /api/v1/assets/<id>/condemn ──────────────────

    @cadra_route("/api/v1/assets/<int:id>/condemn", method="POST",
                 summary="Dispose of an asset — status, condition and the "
                         "disposal date, set in one place on the server",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object",
                     "required": ["reason"],
                     "properties": {
                         "reason": {"type": "string",
                                    "description": "Why it is being disposed "
                                                   "of. Recorded on "
                                                   "`disposal_reason` and on "
                                                   "the append-only event."},
                     },
                 },
                 request_example={"reason": "Beyond economic repair — "
                                            "motherboard failure, BER "
                                            "report ICT/2026/114."})
    def condemn_asset(self, id, **kwargs):
        """Dispose of an asset the way the Odoo button does. `action_condemn`.

        Until handoff 30 the Cadra app condemned with a PATCH of four fields,
        one of which was the disposal DATE taken from the browser's clock. A
        PATCH is `write()`, which stamps nothing, so the app had to send a
        date, and a date a client sends is whatever the client's clock says.
        This route sends none: `state`, `condition` and `disposal_date` are
        set together, on the server, and the date is a LAGOS day — the same
        definition of the day the register snapshot cuts on, NOT the acting
        user's timezone, which for an API credential is unset and therefore
        UTC, and would have dated every disposal made between 00:00 and
        01:00 in Lagos to the day before.

        It records WHO carried the disposal out — the actor of the
        append-only `status_changed` event — which the register did not hold
        anywhere before. It does NOT approve the disposal: that is
        `POST /assets/<id>/approve-disposal`, a different scope, and
        condemning an asset is not authorising it.

        **409** — already disposed. Disposal is terminal.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        _on_the_register_or_409(rec, "disposal")
        reason, error = _required_reason(get_params())
        if error:
            return error
        if rec.state == "disposed":
            return err(ERR_CONFLICT, "This asset has already been disposed of.",
                       status=409,
                       details={"asset_id": rec.id, "state": rec.state,
                                "disposal_date": _date(rec.disposal_date)})
        before = _last_event_id(rec)
        # Handoff 58, P5: a receipt candidate is not on the register, so it
        # cannot leave it either — before anything is written.
        rec._refuse_off_the_register("disposal")
        rec.with_context(cadra_event_source="api_condemn").action_condemn(
            reason=reason)
        return {
            "asset": serialize_asset(rec),
            "disposal": _serialize_disposal(rec),
            "event_id": _event_written(rec, "status_changed", before),
        }

    # ── Transfer custody: POST /api/v1/assets/<id>/transfer-custody ─

    @cadra_route("/api/v1/assets/<int:id>/transfer-custody", method="POST",
                 summary="Transfer custody to a different hr.employee",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object",
                     "required": ["to_custodian_id"],
                     "description": (
                         "BREAKING since handoff 35 on any tenant where "
                         "approval is required (the default): this route "
                         "RAISES A REQUEST instead of changing custody, and "
                         "`approver_id` becomes required. The response then "
                         "carries `pending_approval: true`, the `request`, "
                         "and `asset` UNCHANGED — and `custody_change` is "
                         "null, because none was made."),
                     "properties": {
                         "to_custodian_id": {"type": "integer",
                                             "description": "New custodian hr.employee id"},
                         "approver_id": {
                             "type": "integer", "nullable": True,
                             "description": "WHO IS BEING ASKED to approve. "
                                            "Required when the tenant "
                                            "requires approval. A nomination "
                                            "only — who DECIDED comes from "
                                            "the approving caller's token."},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_custodian_id": 218,
                     "approver_id": 12,
                     "reason": "Previous custodian left the company",
                 })
    def transfer_custody(self, id, **kwargs):
        """Reassign the asset's custodian.

        The audit trail is an append-only `nrs.asset.custody` row, written by
        `nrs.asset.write` and readable at `GET /assets/<id>/custody` or as
        `include=custody` on the asset. It is append-only on the model
        itself, so it cannot be edited or deleted afterwards, by anyone,
        including an administrator using sudo.

        The chatter entry below is kept — it is what an Odoo user reads on
        the record — but it is no longer where the trail lives. It used to
        be, and a `mail.message` is deletable by any user holding the groups
        that let them delete one.

        We deliberately do NOT use `nrs.asset.transfer` here: both of its
        location fields are required and a constraint forbids from == to, so
        a pure custody change cannot be recorded in it at all.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        try:
            to_cust_id = int(body.get("to_custodian_id") or 0)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST, "`to_custodian_id` must be an integer")
        if not to_cust_id:
            return err(ERR_INVALID_REQUEST, "`to_custodian_id` is required")
        to_cust = request.env["hr.employee"].sudo().browse(to_cust_id)
        if not to_cust.exists():
            return err(ERR_NOT_FOUND, f"Employee {to_cust_id} not found", status=404)

        from_cust = rec.custodian_id
        if from_cust.id == to_cust.id:
            return err(ERR_INVALID_REQUEST, "Asset is already assigned to that custodian",
                       details={"current_custodian_id": from_cust.id})

        reason = body.get("reason") or ""
        if reason and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")

        # ASKED EARLY, exactly as `/move` asks it, and ABOVE the approval
        # block below. Whether a disposed asset may change hands is the
        # model's rule (`nrs.asset._assert_disposed_is_terminal`), and until
        # handoff 35 this route met it at the write — the write was the only
        # thing this route did. Now the route can end in a REQUEST instead,
        # and a request never writes, so the model would never be asked:
        # this answered 200 with a pending request against a disposed asset
        # that could never be approved, and which occupied that asset's one
        # pending slot until somebody withdrew it. Introduced by this handoff
        # and found by its verification pass.
        rec._assert_disposed_is_terminal({"custodian_id": to_cust.id})
        # Handoff 58, P5: nobody holds a unit that is not on the register.
        rec._refuse_off_the_register("custodian")

        # ── Nobody hands an asset over alone (handoff 35) ────────────
        #
        # Above the write, like every other refusal on this route. The model
        # gate under all thirteen writers of `custodian_id` is the rule; this
        # is the good answer for the door a person actually presses.
        if _approval_required():
            conflict = _pending_conflict(rec)
            if conflict:
                return conflict
            approver, approver_err = _resolve_approver(body, rec)
            if approver_err:
                return approver_err
            change = request.env["nrs.asset.change.request"].sudo().create({
                "asset_id": rec.id,
                "change_type": "custody",
                "to_custodian_id": to_cust.id,
                "approver_id": approver.id,
                "reason": reason or False,
            })
            return _raised_payload(change, rec, action="transfer-custody")

        # The source and the reason travel in the context because the ORM
        # write that carries a custody change has nowhere to put either. The
        # recorder is in `nrs.asset.write`, not here, because `custodian_id`
        # has several other writers — PATCH, the transfer completion, the
        # Odoo form — and a chain missing those is a chain with gaps that
        # read as periods of no movement.
        rec.with_context(
            cadra_custody_source="api_transfer",
            cadra_custody_reason=reason or False,
        ).write({"custodian_id": to_cust.id})
        custody = rec.custody_ids.sorted("id")[-1:]
        msg_body = (f"Custody transferred via API: "
                    f"<b>{from_cust.name or 'unassigned'}</b> → <b>{to_cust.name}</b>")
        if reason:
            msg_body += f"<br/>Reason: {reason}"
        msg = rec.message_post(body=msg_body, message_type="comment",
                               subtype_xmlid="mail.mt_note")

        return {
            "asset": serialize_asset(rec),
            "custody_change": {
                "from_custodian": _ref(from_cust),
                "to_custodian": _ref(to_cust),
                "reason": reason or None,
                "message_id": msg.id if msg else None,
                # The append-only link this call produced. Additive: a
                # consumer that reads `custody_change` keeps working, and one
                # that wants the audit record can follow this id without
                # re-listing the chain.
                "custody_id": custody.id if custody else None,
            },
        }

    # ── Chain of custody: GET /api/v1/assets/<id>/custody ──────────

    @cadra_route("/api/v1/assets/<int:id>/custody", method="GET",
                 summary="The asset's append-only chain of custody",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "type": "array",
                     "items": {"$ref": "#/components/schemas/AssetCustody"},
                 },
                 query_params=[*PAGINATION_QUERY_PARAMS])
    def asset_custody(self, id, **kwargs):
        """Every recorded change of custodian for one asset, oldest first.

        Append-only: `nrs.asset.custody` refuses `write` and `unlink` on the
        model itself, so a link cannot be altered once written.

        Oldest first, because a chain reads forwards and because cursor
        pagination walks ascending ids — a descending list could not be paged
        honestly with the cursor this API publishes.

        `source` tells a live link from one reconstructed out of the chatter
        tracking values that preceded this model (`tracking_backfill`), and a
        link written by the test suite against a live-shaped tenant (`test`).
        The reconstruction is faithful, but it begins where `custodian_id`
        became a tracked field, not where the register does.

        The chain is EXEMPT from the per-credential record cap. It is one
        asset's complete record rather than a page of a register, and a
        client limited to 100 records still walks all of it.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        qs = get_params()
        Custody = request.env["nrs.asset.custody"].sudo()
        page, next_cursor, total = paginate(
            Custody, [("asset_id", "=", rec.id)],
            limit=parse_limit(qs), cursor=qs.get("cursor"),
            # Exempt from `total_record_cap`, deliberately, and the reasoning
            # is at `utils.CAP_EXEMPT_REASON_CUSTODY`: a truncated chain
            # cannot be told from a complete one, which is the defect this
            # model exists to close. The embed (`include=custody`) has always
            # returned the whole chain; this is what makes the two paths give
            # the same answer to the same question instead of one of them
            # being silently shorter. `total_estimate` is true on both.
            uncapped=True,
        )
        return ok(
            data=[_serialize_custody(c) for c in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── History: GET /api/v1/assets/<id>/history ───────────────────

    @cadra_route("/api/v1/assets/<int:id>/history", method="GET",
                 summary="What has happened to this asset — one ordered "
                         "history, and what it cannot say",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "$ref": "#/components/schemas/AssetHistory"},
                 query_params=[
                     {"name": "sort",
                      "schema": {"type": "string",
                                 "enum": list(_LIST_SORT_VALUES)},
                      "description": "`newest` (the default) or `oldest`. "
                                     + _ENUM_FILTER_400},
                 ])
    def asset_history(self, id, **kwargs):
        """*"What has happened to this asset?"* — the question NRS asked.

        **Read `data.summary.statement` and `evidence` on each event before
        relying on the list.** It merges every place an asset's life leaves
        a mark — registration, the tag's issue, print and affix, the chain of
        custody, location moves, tracked field changes, the disposal
        approval, events sent to SAP and the Tag-Issuing Unit, maintenance
        requests — onto one clock. Those records are not worth the same. A
        change of custodian is append-only, and so is a move made since
        handoff 28; a move made before it is a row an asset manager can
        delete, or a message-log line; a status change exists only in the
        message log.
        Each event says which, and `data.fidelity.evidence_grades` says what
        each grade means in terms of what somebody can do to the record.

        `reconstructed: true` marks an event recovered after the fact rather
        than recorded when it happened — today, a custody link with
        `source: tracking_backfill`. `actor` is the user the record names and
        is null where the record names nobody; it is never filled in from a
        field that means something else.

        `data.fidelity.not_recorded` names the events Cadra never writes
        down at all — a changed cost, a changed SAP field, and a GRN
        reference changed before tracking of it began. They are listed on
        every response because their absence
        from `events` cannot otherwise be told from their not having
        happened. `data.fidelity.custody` says when custody recording began
        on this system and whether this asset was already held by somebody
        when it did; `data.fidelity.location` says the same of moves, and is
        true of nearly every asset on a register loaded before handoff 28.

        An asset with nothing after its registration says so in
        `summary.statement`, in words.

        Newest first by default, because the reader's first question about
        an asset is where it is now and how it got there; `?sort=oldest`
        reads it forwards. NOT paged and NOT capped: a merged history has no
        single id for a cursor to walk, and it is exempt from the
        per-credential record cap for the reason the chain of custody is —
        `utils.CAP_EXEMPT_REASON_CUSTODY`.

        Tracked changes publish the field, the old value and the new one.
        Message bodies are never published: a note typed on an asset was not
        promised to every holder of `assets:read`.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        qs = get_params()
        try:
            sort = parse_enum("sort", qs.get("sort"), _LIST_SORT_VALUES)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        # Absent means newest — the opposite default from the listing, whose
        # `oldest` predates `?sort`. Here there is no older behaviour to keep.
        return rec.asset_history(
            newest_first=sort != "oldest",
            # A maintenance request belongs to `requests:read`. Its reference
            # is published to a caller who holds that too, and withheld —
            # and SAID to be withheld — from one who does not (handoff 30).
            request_references=caller_holds(SCOPE_REQUESTS_READ))

    # ── Confirm tagging: POST /api/v1/assets/<id>/tag-affixed ──────

    @cadra_route("/api/v1/assets/<int:id>/tag-affixed", method="POST",
                 summary="Confirm a printed label was physically affixed to the asset",
                 scopes=[SCOPE_TAGGING_WRITE],
                 idempotent=True,
                 response_schema={
                     "type": "object",
                     "properties": {
                         "asset": {"$ref": "#/components/schemas/Asset"},
                         "tagging": {"$ref": "#/components/schemas/AssetTagging"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "required": ["tag_number"],
                     "properties": {
                         "tag_number": {
                             "type": "string",
                             "description": "The tag number READ OFF the label "
                                            "on the asset. Checked against the "
                                            "tag Cadra issued; a mismatch is "
                                            "rejected."},
                         "serial_number": {
                             "type": "string", "nullable": True,
                             "description": "The manufacturer serial READ OFF "
                                            "the asset. Optional, but when "
                                            "supplied it is checked against "
                                            "the serial on the record and a "
                                            "mismatch is rejected: this is the "
                                            "serial-to-tag match the "
                                            "Integration Flow asks for. Send "
                                            "it — Vendra holds the serial, so "
                                            "checking both sides costs "
                                            "nothing and checking one is half "
                                            "a control."},
                         "scanned_format": {
                             "type": "string", "nullable": True,
                             "enum": list(SCANNED_FORMATS),
                             "description": "How `tag_number` was read, when "
                                            "the client knows — the app's "
                                            "camera passes the symbology up "
                                            "with every decode; a typed or "
                                            "keyboard-wedge entry does not "
                                            "know and omits the key. A value "
                                            "outside the enum is a 400 and "
                                            "nothing is written. Recorded "
                                            "ONLY when the confirmation is "
                                            "refused, beside the refused "
                                            "value, so an auditor can tell a "
                                            "number read off Cadra's own "
                                            "label (code_128 / qr_code) from "
                                            "a manufacturer's; a successful "
                                            "affix stores nothing new."},
                         "serial_format": {
                             "type": "string", "nullable": True,
                             "enum": list(SCANNED_FORMATS),
                             "description": "How `serial_number` was read, "
                                            "same semantics as "
                                            "`scanned_format`. Recorded only "
                                            "on a refused serial check."},
                         "attributes_confirmed": {
                             "type": "boolean", "nullable": True,
                             "description": "Handoff 58 (Section 12). For a "
                                            "unit received as `tag_id` — no "
                                            "manufacturer serial — the "
                                            "tagger confirms the item "
                                            "matches its description, make "
                                            "and colour; REQUIRED (`true`) "
                                            "for such a unit and refused "
                                            "400 without it. Ignored for "
                                            "every other asset."},
                         "affixed_by_name": {
                             "type": "string", "nullable": True,
                             "description": "Name of the Tag-Issuing Unit "
                                            "operative who affixed it."},
                         "affixed_at": {
                             "type": "string", "format": "date-time",
                             "nullable": True,
                             "description": "When it was affixed. Defaults to "
                                            "now; supply it when confirming a "
                                            "batch recorded offline."},
                     },
                 },
                 request_example={
                     "tag_number": "HQ-GF-MR-IT-042",
                     "scanned_format": "code_128",
                     "serial_number": "5XJZ8T3",
                     "affixed_by_name": "J. Okafor",
                     "affixed_at": "2026-09-14T11:32:07",
                 })
    def confirm_tag_affixed(self, id, **kwargs):
        """Record the serial-to-tag match at the point of physical tagging.

        This is the only way an asset becomes `is_tagged`, and it sits behind
        its own `tagging:write` scope because the Integration Flow makes the
        Tag-Issuing Unit independent of whoever created the asset record. The
        submitted tag number is verified against the tag Cadra issued rather
        than trusted: that check is what makes the record evidence the right
        label is on the right asset, instead of an assertion that someone
        tagged something.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error

        body = get_params()
        tag_number = (body.get("tag_number") or "").strip()
        if not tag_number:
            return err(ERR_INVALID_REQUEST, "`tag_number` is required")

        # How each value was READ, when the client knows (handoff 54): the
        # app's camera passes the symbology up with every decode; a typed
        # or keyboard-wedge entry has none to claim and omits the key.
        # Validated BEFORE anything is written — including the serial
        # refusal record below, which must not carry a format the enum
        # refuses — and recorded only on a refusal: a successful affix
        # stores nothing new, by ruling (§7).
        for key in ("scanned_format", "serial_format"):
            value = body.get(key)
            if value is not None and value not in SCANNED_FORMATS:
                return err(ERR_INVALID_REQUEST,
                           "`%s` must be one of: %s"
                           % (key, ", ".join(SCANNED_FORMATS)),
                           details={"field": key, "value": value,
                                    "allowed_values": list(SCANNED_FORMATS)})
        scanned_format = body.get("scanned_format") or None
        serial_format = body.get("serial_format") or None
        # A claim about how a value was read, with no value: contradictory
        # input is refused, not quietly ignored (handoff 34's rule).
        if serial_format and not (body.get("serial_number") or "").strip():
            return err(ERR_INVALID_REQUEST,
                       "`serial_format` describes how `serial_number` was "
                       "read and cannot be sent without it",
                       details={"field": "serial_format"})

        label = rec.active_tag_id
        if not label:
            return err(ERR_INVALID_REQUEST,
                       "This asset has no active tag to confirm",
                       details={"asset_id": rec.id})

        # Section 12 (handoff 58 §4): a unit received as `tag_id` has no
        # manufacturer serial to scan, so its second check is the tagger's
        # confirmation that the item matches its attributes. Required for
        # such a unit — and asked of nothing else, so every other affix is
        # what it was.
        confirmed = body.get("attributes_confirmed")
        if confirmed is not None and not isinstance(confirmed, bool):
            return err(ERR_INVALID_REQUEST,
                       "`attributes_confirmed` must be true or false",
                       details={"field": "attributes_confirmed"})
        tag_id_unit = rec.identification_mode == "tag_id"
        # Only for a FIRST confirmation: a repeat on a label already on the
        # unit is answered idempotently (handoff 39), tick or no tick.
        if tag_id_unit and confirmed is not True \
                and label.label_state != "affixed":
            return err(ERR_VALIDATION_FAILED,
                       "Confirm the item matches its description — "
                       "description, make and colour — before confirming "
                       "the label",
                       details={"asset_id": rec.id,
                                "field": "attributes_confirmed",
                                "identification_mode": "tag_id"})

        # The serial-to-tag match. Optional because a fixed asset with no
        # legible serial still has to be taggable, but verified whenever the
        # caller can supply it — the tag check alone proves the label is the
        # one Cadra issued, not that it went onto the right box.
        #
        # Compared case-insensitively on stripped values: serials are read off
        # an engraved plate or a barcode and case is not information here. A
        # record with no serial on file cannot be checked, and says so rather
        # than passing quietly.
        scanned_serial = (body.get("serial_number") or "").strip()
        if scanned_serial:
            expected_serial = (rec.serial_number or "").strip()
            if not expected_serial:
                return err(ERR_VALIDATION_FAILED,
                           "This asset has no serial number on file, so the "
                           "scanned serial cannot be verified",
                           details={"asset_id": rec.id,
                                    "scanned_serial": scanned_serial})
            if scanned_serial.casefold() != expected_serial.casefold():
                # This refusal leaves a record too — handoff 52 §4, and the
                # exact *label going onto the wrong box* event an auditor
                # wants: the cheaper tell, since unlike the number refusal
                # below it reveals nothing to the person refused. This is
                # the `err(...)` path, not a raise — no exception, no
                # decorator rollback, the request cursor survives — so the
                # placement question is DIFFERENT from the raise's and was
                # measured again rather than assumed (report 52 §4): a
                # same-cursor write here would in fact commit with the
                # request. The shared recorder is used anyway — one
                # mechanism, one test-mode branch, and a row that stays
                # final if this err is ever turned into a raise.
                label.with_context(
                    cadra_event_source="api_affix",
                )._record_affix_refusal(scanned_serial,
                                        reason='serial_mismatch',
                                        scanned_format=serial_format)
                return err(ERR_VALIDATION_FAILED,
                           "Scanned serial %s does not match the serial on "
                           "this asset (%s) — the label may be going onto the "
                           "wrong asset" % (scanned_serial, expected_serial),
                           details={"asset_id": rec.id,
                                    "scanned_serial": scanned_serial,
                                    "expected_serial": expected_serial})

        affixed_at = None
        raw_when = (body.get("affixed_at") or "").strip()
        if raw_when:
            affixed_at = _parse_datetime(raw_when)
            if affixed_at is None:
                return err(ERR_INVALID_REQUEST,
                           "`affixed_at` must be an ISO 8601 date-time",
                           details={"affixed_at": raw_when})
            # A label cannot have been affixed in the future. Without this a
            # clock-skewed or mis-typed client writes a date the register will
            # carry for the life of the asset.
            if affixed_at > odoo_fields.Datetime.now():
                return err(ERR_INVALID_REQUEST,
                           "`affixed_at` cannot be in the future",
                           details={"affixed_at": raw_when})

        # A mismatch raises ValidationError, which the endpoint decorator turns
        # into a 400 `validation_failed` carrying the model's message — which
        # names both the scanned and the expected tag. Since handoff 51 the
        # refusal also leaves an `affix_refused` event behind, written by the
        # model on its own cursor so the decorator's rollback cannot unwind
        # it; `api_affix` is this route declaring where that row came from,
        # the same way `/verify` declares `api_verify`.
        # Which check this was, for the gate's event (Section 12).
        check = ("label_and_attributes" if tag_id_unit
                 else "label_and_serial" if scanned_serial
                 else "label_only")
        label.with_context(
            cadra_event_source="api_affix",
            cadra_affix_check=check,
        )._mark_affixed(tag_number,
                        affixed_by_name=body.get("affixed_by_name"),
                        affixed_date=affixed_at,
                        scanned_format=scanned_format)

        return {
            "asset": serialize_asset(rec),
            "tagging": _serialize_tagging(rec),
        }

    # ── Approve a disposal: POST /api/v1/assets/<id>/approve-disposal ──

    @cadra_route("/api/v1/assets/<int:id>/approve-disposal", method="POST",
                 summary="Record that the authenticated caller authorised "
                         "this disposal",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(409,),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "asset": {"$ref": "#/components/schemas/Asset"},
                         "disposal": {
                             "$ref": "#/components/schemas/AssetDisposal"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "description": (
                         "No body is required, and none is read. The approver "
                         "is the user behind the bearer token. A body naming "
                         "an approver or an approval date is REFUSED 400 "
                         "rather than ignored."),
                     "properties": {},
                 },
                 request_example={})
    def approve_disposal(self, id, **kwargs):
        """Approve a disposal as whoever is holding the credential.

        The approver is **derived from the token and never read from the
        body.** That is the whole design and it is the reason this route did
        not exist until now: `disposal_approved_by` is deliberately absent
        from `_WRITABLE_FIELDS`, because a client able to name the approver
        could create a disposal and appoint any user in the tenant as the
        authority for it in the same request — turning the disposal report's
        `no_approver` finding into a clean row with nobody having authorised
        anything. The control stays; what changes is that an integration can
        now approve **as itself**.

        That works without any code here because of handoff 08: every API
        client has its own `res.users`, `require_jwt` puts the token's `uid`
        on the request env, and Odoo 19's `sudo()` does not change `env.uid`.
        So `action_approve_disposal`, which writes `self.env.uid`, records the
        integration rather than `Administrator`.

        `approvals:write` gates nothing else asset-related, so granting it is
        a deliberate act somebody has to perform rather than something a broad
        credential already carries.

        Three answers other than success, and none of them silent:

        * **400** — the body tries to name an approver or a date. Ignoring it
          would return `200` to a caller who believes it set the approver,
          which is the "answer that looks like an answer" this codebase
          refuses everywhere else.
        * **400** — the asset is not disposed of. An approval recorded
          against an asset still on the register authorises nothing.
        * **409** — already approved. An approval is a one-time act, so a
          second caller is told who holds it rather than quietly succeeding.
          Replaying with the same `X-Idempotency-Key` still returns the
          original response; a genuinely new request does not.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error

        body = get_params()
        if isinstance(body, dict):
            claimed = sorted(k for k in body if k in _APPROVER_CLAIM_FIELDS)
            if claimed:
                return err(
                    ERR_INVALID_REQUEST,
                    "The approver is taken from the credential that made this "
                    "call and cannot be supplied: remove %s and call again as "
                    "the approving user." % ", ".join("`%s`" % k
                                                      for k in claimed),
                    # The same two keys `refuse_unwritable` publishes, so a
                    # caller reading `details.writable` finds it on BOTH of
                    # this route's refusals, three lines apart. This route
                    # reads no body, so nothing is writable.
                    details={"asset_id": rec.id, "rejected_fields": claimed,
                             "writable": []})

        # This route reads NO body. A key it does not read is a caller
        # misunderstanding, and since handoff 31 it is REFUSED — the same
        # contract PATCH publishes — rather than reported beside a 200 for
        # an approval the caller may believe it shaped.
        ignored = sorted(body) if isinstance(body, dict) else []
        if ignored:
            return refuse_unwritable(ignored, ())

        if rec.disposal_approved_by:
            return err(
                ERR_CONFLICT,
                "This disposal was already approved by %s%s. An approval "
                "records who authorised the disposal and is not re-taken."
                % (rec.disposal_approved_by.name,
                   " on %s" % _date(rec.disposal_approved_date)
                   if rec.disposal_approved_date else ""),
                status=409,
                details={
                    "asset_id": rec.id,
                    "approved_by": _ref(rec.disposal_approved_by,
                                        name_field="name"),
                    "approved_at": _date(rec.disposal_approved_date),
                })

        # `state != 'disposed'` raises UserError inside the action, which the
        # endpoint decorator turns into a 400 carrying the model's own words.
        # Not re-checked here: one statement of the rule, on the model.
        rec.action_approve_disposal()

        payload = {
            "asset": serialize_asset(rec),
            "disposal": _serialize_disposal(rec),
        }
        return payload

    # ── Register report: GET /api/v1/reports/depreciation ──────────

    @cadra_route("/api/v1/reports/depreciation", method="GET",
                 summary="Register-wide depreciation totals and breakdowns",
                 scopes=[SCOPE_DASHBOARDS_READ],
                 query_params=[
                     {"name": "category_id", "schema": {"type": "integer"},
                      "description": "Restrict the report to one asset "
                                     "category. A value that is not an "
                                     "integer is a 400 `invalid_request`."},
                 ])
    def depreciation_report(self, **kwargs):
        """Totals, per-category breakdown, and the two data-quality counts that
        matter in practice: assets whose start date was inferred, and assets
        with a depreciation method but no cost to depreciate."""
        domain = []
        # Already refused a non-integer before this pass — it is the one hand
        # rolled int filter in the file that never swallowed its error. Moved
        # onto the shared parser anyway so there is one place the answer is
        # decided; the message and `details` it produces are byte-identical
        # to the ones this route has always published.
        try:
            category_id = parse_int("category_id", kwargs.get("category_id"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        if category_id is not None:
            domain.append(("category_id", "=", category_id))
        return request.env["nrs.asset"].sudo().get_depreciation_report(domain)

    # ── Depreciation schedule: GET /api/v1/assets/<id>/depreciation ─

    @cadra_route("/api/v1/assets/<int:id>/depreciation", method="GET",
                 summary="Depreciation schedule and summary for one asset",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "as_of", "schema": {"type": "string", "format": "date"},
                      "description": "Truncate the schedule at this date for a "
                                     "point-in-time view (YYYY-MM-DD)"},
                 ])
    def get_asset_depreciation(self, id, **kwargs):
        """The period-by-period board (PRD §8.6).

        Generated on demand rather than stored: the schedule is a pure function
        of cost, salvage, start date, life and method, so persisting ~12k x ~60
        rows would be derivation with a staleness risk attached. It also makes
        `as_of` a genuine point-in-time view (PRD §13.4) for free.

        Returns an empty `periods` list for methods Cadra does not compute
        (`none`, `erp_managed`) — that is a valid state, not an error.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error

        as_of = None
        raw = (kwargs.get("as_of") or "").strip()
        if raw:
            try:
                as_of = odoo_fields.Date.from_string(raw)
            except (ValueError, TypeError):
                return err(ERR_INVALID_REQUEST,
                           "`as_of` must be a date in YYYY-MM-DD format",
                           details={"as_of": raw})

        periods = rec.get_depreciation_schedule(as_of=as_of)
        return {
            "asset": {"id": rec.id, "asset_code": rec.asset_code, "name": rec.name},
            "summary": _serialize_depreciation(rec),
            "as_of": _date(as_of),
            "currency": _ref(rec.currency_id),
            "period_count": len(periods),
            "periods": [{
                "sequence": p["sequence"],
                "period_end": _date(p["period_end"]),
                "charge": p["charge"],
                "accumulated_depreciation": p["accumulated"],
                "book_value": p["book_value"],
            } for p in periods],
        }

    # ── Audit reports (specification §13.4, INT-10) ────────────────
    #
    # SCOPE, and why it is `assets:read` on both rather than the
    # `dashboards:read` the only other `/reports/*` route takes.
    #
    # `/reports/depreciation` above returns AGGREGATES — totals, a
    # per-category breakdown, two data-quality counts. Nothing in it
    # identifies an asset, which is what makes `dashboards:read` an honest
    # gate for it: it is a figure on a screen.
    #
    # The two reports below return ROWS OF THE REGISTER — one per asset,
    # carrying custodian, location, condition, state, value, and in the
    # disposal report the authorising reference and the approver. That is the
    # same data `GET /api/v1/assets` returns, asked a different way. Gating
    # it on `dashboards:read` would put a SECOND, WEAKER DOOR onto the asset
    # base: a Security Officer or an FM dashboard credential holding
    # `dashboards:read` and not `assets:read` could pull the whole register
    # through a report, which is precisely the "undeclared gate" defect
    # handoff 09 removed from the dashboard routes, running the other way.
    #
    # The rule this settles on: **the same data takes the same scope,
    # whatever the route is called.** An audit report is a view of the
    # register, so it takes the register's scope.
    #
    # Deliberately NOT a new `audit:read` scope. A scope no group grants and
    # no client holds makes the reports unreachable on every tenant on the
    # day they ship, and the thing an audit credential actually needs is not
    # a different scope — it is `total_record_cap = -1` on its
    # `myservice.api.client` row, which is the mechanism handoff 12 built and
    # INT-10 §7 recommends.

    @cadra_route("/api/v1/reports/asset-register", method="GET",
                 summary="The asset register as it stood at a past date",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"$ref": "#/components/schemas/AssetRegisterSnapshot"},
                 query_params=[
                     {"name": "as_of", "required": True,
                      "schema": {"type": "string", "format": "date"},
                      "description": (
                          "REQUIRED. The date the register is reported as at "
                          "(YYYY-MM-DD), inclusive. There is no default: a "
                          "snapshot that quietly means 'today' is "
                          "GET /api/v1/assets wearing a report's name, and "
                          "every fidelity claim in it would be vacuous. A "
                          "future date is a 400.")},
                     {"name": "q", "schema": {"type": "string"}},
                     {"name": "category_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "subcategory_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "location_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "building_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "floor_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "room_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "custodian_id", "schema": {"type": "integer"},
                      "description": _ID_FILTER_400},
                     {"name": "state", "schema": {"type": "string",
                      "enum": ["active", "in_repair", "disposed",
                               "transferred", "missing"]},
                      "description": _ENUM_FILTER_400},
                     {"name": "condition", "schema": {"type": "string",
                      "enum": ["new", "good", "fair", "poor",
                               "decommissioned"]},
                      "description": _ENUM_FILTER_400},
                     # `domain` and `asset_level` published no enum at all
                     # until this pass, while the model has always had one —
                     # so the documented surface was wider than the data and
                     # a caller had nothing to validate against. Additive:
                     # every value listed is one the model already accepts.
                     # Taken from the tuples the filter itself falls back to,
                     # so the published list and the floor cannot drift.
                     {"name": "domain", "schema": {"type": "string",
                      "enum": list(_FM_DOMAINS)},
                      "description": "The FM domain, inherited from the "
                                     "asset's category. " + _ENUM_FILTER_400},
                     {"name": "asset_level", "schema": {"type": "string",
                      "enum": list(_ASSET_LEVELS)},
                      "description": "Position in the asset hierarchy. "
                                     + _ENUM_FILTER_400},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def asset_register_snapshot(self, **kwargs):
        """*"What did the register say on 31 March?"* — specification §13.4.

        READ-ONLY. Nothing on this path writes: the rollback is computed from
        `mail.tracking_value` rows and the chain of custody, no field is
        stamped, no schedule is applied, and `_apply_depreciation()` is never
        called. Report 19 in the Vendra repository made the argument and it
        holds here — a report that quietly repairs what it finds can never
        honestly report zero.

        ── The response shape, and why `data` is an OBJECT ──

        Every other list route in this API returns `data` as an ARRAY. This
        one does not, and the reason is the acceptance criterion the handoff
        wrote in capitals: *a snapshot that silently mixes as-of-the-date
        values with as-of-today values is worse than no snapshot, because an
        auditor will reconcile it against a figure and the discrepancy will
        be ours.*

        There is nowhere honest to put that declaration on an array. The
        handler-level `data._warnings` convention needs `data` to be an
        object — which is exactly why handoff 12 moved the truncation warning
        up to the envelope — and the envelope's `_warnings` is built inside
        `ok()` for truncation, is a *warning* channel, and is the one part of
        the body a client reading `body["data"]` never sees. A boundary a
        consumer can miss by reading the obvious key is not a boundary.

        So the rows live INSIDE the declaration, at `data.assets`, and it is
        not possible to receive them without receiving `data.fidelity`
        alongside. `pagination` stays at envelope level, so the cursor walk
        is byte-identical to every other list endpoint.

        ── `cutoff` ──

        `data.cutoff` is the exact instant the rollback was taken at, because
        "as at 31 March" in UTC and in UTC+1 are different questions and an
        auditor reconciling to the hour is entitled to know which one was
        answered. Cadra stores naive UTC throughout; the cutoff is published
        in the same terms rather than converted to a session timezone, which
        would invent a precision the tracking rows do not have.

        ── The cap: this report IS capped, deliberately ──

        `include=custody` and `GET /assets/<id>/custody` are exempt from the
        per-client record cap (`utils.CAP_EXEMPT_REASON_CUSTODY`) because a
        chain of custody is ONE ASSET'S COMPLETE RECORD, bounded by how often
        that asset changed hands. That argument does not transfer here and
        applying it would be a mistake with a large blast radius.

        This report is a page of the REGISTER, bounded by tenant size —
        11,942 assets on `nrs19` — and it accepts the same filters as
        `GET /api/v1/assets`. Exempting it would not loosen a cap on an audit
        report; it would DELETE the record cap API-wide, because
        `?as_of=<today>` is the register, and any capped credential could
        route round its own limit by asking for it here.

        So the cap applies and `paginate()` makes it honest for free:
        `total_estimate` is always the true count of the unclamped domain,
        and `ok()` attaches `_warnings.truncated` the moment the cap bites.
        A caller who is capped is TOLD they are capped, on page one, with the
        real number beside it — which is the whole of what INT-10 §2.11 asked
        for. The remedy for an audit credential is `total_record_cap = -1` on
        its `myservice.api.client` row: a per-client setting, provisioned
        deliberately, which is handoff 12's mechanism and INT-10 §7's own
        recommendation.
        """
        qs = get_params()

        as_of, error = _parse_report_date(qs, "as_of", required=True)
        if error:
            return error
        # "Today" in LAGOS, which is the day the cutoff is defined in — not
        # the UTC date, which is yesterday for the first hour of every Lagos
        # day. See `snapshot_today`.
        if as_of > snapshot_today():
            # A snapshot of tomorrow is today's register with a wrong label
            # on it. Answering 200 would put a date in an audit file that the
            # data cannot support.
            return err(ERR_INVALID_REQUEST,
                       "`as_of` cannot be in the future — the register has no "
                       "value at a date that has not happened",
                       details={"as_of": qs.get("as_of"),
                                "today": snapshot_today().isoformat()})

        if qs.get("updated_since") not in (None, ""):
            # The sync filter (handoff 61) reads TODAY's `write_date`, which
            # says nothing about the register as it stood on `as_of`; a
            # snapshot narrowed by it would be a different question answered
            # under the snapshot's name. Refused, never ignored.
            return err(ERR_INVALID_REQUEST,
                       "`updated_since` is a sync filter on the live register "
                       "and does not apply to a snapshot as of a date.",
                       details={"updated_since": qs.get("updated_since")})
        try:
            filter_domain = _list_domain(qs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)

        Asset = request.env["nrs.asset"].sudo()
        domain = Asset.snapshot_existence_domain(as_of) + filter_domain

        page, next_cursor, total = paginate(
            Asset, domain,
            limit=parse_limit(qs), cursor=qs.get("cursor"),
        )

        rows_by_id = page.snapshot_at(as_of)
        rows = []
        omitted = []
        for asset in page:
            row = rows_by_id.get(asset.id)
            if row is None:
                # The snapshot builder returned no row for an asset that its
                # own existence domain selected. That is a hole, and a hole
                # in an audit report is only survivable if it is NAMED — a
                # row quietly dropped from a page reads to an auditor as an
                # asset that did not exist on the date. Never silently short
                # (rule 3).
                omitted.append(asset.id)
                continue
            rows.append(row)
        if omitted:
            _logger.warning(
                "asset-register snapshot as_of=%s: snapshot_at() returned no "
                "row for %d of %d assets its existence domain selected: %s",
                as_of, len(omitted), len(page), omitted[:20])

        return ok(
            data={
                "as_of": _date(as_of),
                # The instant the rollback was taken at, naive UTC, no
                # offset — the same terms Cadra stores every datetime in.
                "cutoff": _naive_iso(snapshot_cutoff(as_of)),
                "cutoff_timezone": "UTC",
                # WITH the date: which fields can be rolled back depends on
                # it (handoff 28 — a field tracked only from a known day).
                "fidelity": Asset.snapshot_fidelity(as_of),
                "filters": _snapshot_filter_disclosure(qs),
                # Named, never dropped. Empty on every healthy request.
                "omitted_asset_ids": omitted,
                "assets": rows,
            },
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    @cadra_route("/api/v1/reports/disposals", method="GET",
                 summary="Disposals in a period, with what is missing from each",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"$ref": "#/components/schemas/DisposalReport"},
                 query_params=[
                     {"name": "from", "required": True,
                      "schema": {"type": "string", "format": "date"},
                      "description": "REQUIRED. First day of the period, "
                                     "INCLUSIVE (YYYY-MM-DD)."},
                     {"name": "to", "required": True,
                      "schema": {"type": "string", "format": "date"},
                      "description": (
                          "REQUIRED. Last day of the period, INCLUSIVE. An "
                          "auditor asks for a quarter by naming its first "
                          "and last day; an exclusive upper bound would "
                          "silently lose everything disposed of on 31 "
                          "March.")},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def disposals_report(self, **kwargs):
        """*"Show me every disposal this quarter and the paper behind it."*

        Specification §13.4 asks for a *disposal report with documentation
        refs, per period*; INT-10 §2.9 recorded that Cadra had neither the
        references nor the report. This is the report half.

        READ-ONLY. `nrs.asset.disposal_report` performs one search and one
        SELECT over the tracking values and writes nothing — no repaired
        date, no stamped field, no chatter post.

        ── Findings are never filtered out ──

        A disposal with no authorising reference IS the finding. It appears
        in `rows` carrying `no_authorising_reference` in its own `findings`
        list, and it is counted in `summary.findings` — so *"41 of 63
        disposals carry no authorising reference"* is one read of page one
        and not a walk through pages. A report that showed only the
        well-documented disposals would be a report of the paperwork rather
        than of the estate.

        ── `summary` describes the PERIOD; `rows` is a page of it ──

        The summary is computed over every disposal in the period on every
        request, never over the page, and `pagination.total_estimate` is the
        same number as `summary.total` — they come from one call to the model
        so they cannot disagree. A caller whose credential is capped still
        gets the true headline counts; what shortens is the schedule, and
        `_warnings.truncated` says so.

        ── `unplaceable` ──

        A disposal with no recorded date and no tracked state change cannot
        be placed in ANY period. It is returned in full, in its own key, in
        every response, with its own count in the summary — never mixed into
        the period totals, because that would double-count it in the next
        period, and never dropped, because dropping it makes it invisible in
        every report ever run. It is deliberately NOT capped: unlike the
        register it is not a resource anybody could walk to extract the
        estate — every row in it is by definition a defective record — and a
        truncated list of "the disposals that appear in no period report"
        cannot be told from a complete one, which is
        `CAP_EXEMPT_REASON_CUSTODY`'s argument in its proper place.

        ── Row order is ASCENDING ASSET ID, not disposal date ──

        The model returns the schedule in `disposal_date, id` order. This
        route re-sorts by asset id because cursor pagination walks ascending
        ids and a date-ordered list cannot be paged honestly with the cursor
        this API publishes — the same trade `GET /assets/<id>/custody` makes
        and for the same reason. Every row carries `disposal_date`, so a
        caller who has walked the whole period can order it however it likes.
        """
        qs = get_params()

        date_from, error = _parse_report_date(qs, "from", required=True)
        if error:
            return error
        date_to, error = _parse_report_date(qs, "to", required=True)
        if error:
            return error
        if date_from > date_to:
            # The model raises UserError on this, which the decorator turns
            # into `validation_failed`. Caught here instead so the answer
            # names the parameters — an integration branching on
            # `error.code` should be told its REQUEST was wrong, not that a
            # record failed validation.
            return err(ERR_INVALID_REQUEST,
                       "The period ends before it starts: `from` must be on "
                       "or before `to`",
                       details={"from": qs.get("from"), "to": qs.get("to")})

        # At the door, BEFORE the report runs. A cursor we cannot read is a
        # 400 (handoff 22) and there is no reason to make the caller wait for
        # a full pass over the period to be told so.
        cursor_data = decode_cursor(qs.get("cursor"))

        Asset = request.env["nrs.asset"].sudo()
        # ONE call. `summary`, `rows` and `unplaceable` come out of a single
        # pass, so the headline counts and the schedule cannot describe two
        # different reads of the table — Odoo runs READ COMMITTED, and two
        # calls a few milliseconds apart genuinely can see different data.
        report = Asset.disposal_report(date_from, date_to)

        # `summary.total` is the model's own count over an unlimited search
        # of the period. It is the number published as `total_estimate`, so
        # there is exactly one count of the period in this response.
        total = report["summary"]["total"]
        rows = sorted(report["rows"], key=lambda r: r["asset_id"])

        # The record cap, applied by hand because the schedule is a list of
        # dicts from a model method rather than a recordset `paginate()`
        # could take. Same semantics as the CSV export: the window is the
        # first `cap` rows of the whole period, computed BEFORE the cursor so
        # it survives across pages, and `flag_truncation` makes `ok()` say so.
        cap = record_cap()
        if cap is not None:
            rows = rows[:cap]
            flag_truncation(cap, total)

        if "last_id" in cursor_data:
            # No coercion and no fallback: `decode_cursor` has already proved
            # `last_id` is an int, or refused the request with a 400. The
            # `except: last_id = None` that used to stand here restarted the
            # walk at page one for a cursor the caller believed was page
            # three — the defect handoff 22 removed.
            rows = [r for r in rows if r["asset_id"] > cursor_data["last_id"]]

        limit = parse_limit(qs)
        page = rows[:limit]
        next_cursor = None
        if page and len(rows) > limit:
            next_cursor = encode_cursor({"last_id": page[-1]["asset_id"]})

        return ok(
            data={
                "period": report["period"],
                # Over the WHOLE period, on every page. See the docstring.
                "summary": report["summary"],
                "unplaceable": report["unplaceable"],
                "rows": page,
            },
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )
