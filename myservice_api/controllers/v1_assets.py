"""
Cadra API v1 — Assets resource (REST shape per PRD §8.10).

Implements the subset of PRD §8 that maps onto `nrs.asset`. The in-house
model has a simpler 5-state lifecycle (active/in_repair/disposed/
transferred/missing) versus PRD §8.4's 10-state machine
(procured/received/tagged/deployed/in_maintenance/in_transit/idle/lost/
retired/disposed). The full state machine, the immutable custodianship
chain (PRD §8.5), and the disposal-approval workflow (PRD §8.9) are
deferred to a future schema-extension pass.

The move endpoint persists its side-effect by creating an
`nrs.asset.transfer` row. Transfer-custody uses `mail.thread` instead
because `nrs.asset.transfer._check_locations` forbids same-location
transfers.
"""
import datetime
import logging

from odoo import fields as odoo_fields, http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    SCOPE_DASHBOARDS_READ,
    SCOPE_TAGGING_WRITE,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route

_logger = logging.getLogger(__name__)

# The published `tag_label_state` values, mirroring the model's Selection
# (`nrs.asset.tag.label.label_state`) and the OpenAPI enum below. Used only
# as the floor under `_tag_label_states()` — the model is still the source of
# truth when it can be read.
_TAG_LABEL_STATES = ("issued", "printed", "affixed", "scrapped")


def _tag_label_states():
    """Accepted values for the `tag_label_state` filter. Never empty.

    Reads the model's own Selection so a value the model gains is accepted
    the same day, and falls back to the published tuple if it cannot — never
    to "skip the check". A validator that disables itself on failure puts
    `?tag_label_state=bogus` back to answering `200 []`, which is the silent
    degradation the validation exists to remove.

    Deliberately NOT `utils._selection_allowed_values`, which calls
    `cr.rollback()` on failure: that helper is written for the post-rollback
    error path, and this runs on the happy path of every list request.
    """
    try:
        field = request.env["nrs.asset"]._fields["tag_label_state"]
        if field.type == "selection":
            values = list(field.get_values(request.env))
            if values:
                return values
    except Exception:
        _logger.warning(
            "could not read nrs.asset.tag_label_state selection; "
            "falling back to the published values", exc_info=True)
    return list(_TAG_LABEL_STATES)


# The published `sap_reconciliation_state` values, mirroring the model's
# Selection (`nrs.asset.sap_reconciliation_state`) and the OpenAPI enum below.
# Same role as `_TAG_LABEL_STATES`: the floor under the reader, never a
# substitute for it.
_SAP_RECONCILIATION_STATES = ("not_tagged", "pending", "reconciled",
                              "exception")


def _sap_reconciliation_states():
    """Accepted values for the `sap_reconciliation_state` filter. Never empty.

    Same reader as `_tag_label_states()`, for the same reason and with more
    at stake: this filter's entire audience is an auditor asking which assets
    are incomplete, so `?sap_reconciliation_state=exceptions` — the plural,
    the natural typo — answering `200 []` tells them there are none. Read the
    model's own Selection so a state the model gains is accepted the same
    day, fall back to the published tuple when it cannot be read, and never
    fall back to skipping the check.

    Deliberately NOT `utils._selection_allowed_values`, which rolls the
    cursor back on failure; this runs on the happy path of every list
    request.
    """
    try:
        field = request.env["nrs.asset"]._fields["sap_reconciliation_state"]
        if field.type == "selection":
            values = list(field.get_values(request.env))
            if values:
                return values
    except Exception:
        _logger.warning(
            "could not read nrs.asset.sap_reconciliation_state selection; "
            "falling back to the published values", exc_info=True)
    return list(_SAP_RECONCILIATION_STATES)


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


class _BadFilter(Exception):
    """A query parameter we cannot interpret.

    Raised out of the domain builder and turned into a 400 by the listing
    endpoint. A bare ValueError would reach the decorator's catch-all and
    answer 500, which tells an integration to retry a request that can never
    succeed.
    """

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


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
    }


# ─── serializer ──────────────────────────────────────────────────────

def serialize_asset(a, *, include=()):
    """Map an nrs.asset record to a Cadra-shaped dict.

    `include` accepts:
      - "transfers"   : embed nrs.asset.transfer history (last 20)
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
        "serial_number": a.serial_number or None,
        "make": a.make or None,
        "model": a.model_name or None,
        "manufacturer": a.manufacturer or None,
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
        "pm_count": a.pm_count,
        "request_count": a.request_count,
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

def _list_domain(qs):
    domain = []
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
    for fld in ("category_id", "subcategory_id", "location_id", "building_id",
                "floor_id", "room_id", "custodian_id", "parent_id"):
        val = qs.get(fld)
        if val not in (None, "", "null"):
            try:
                domain.append((fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    for fld in ("state", "condition", "domain", "asset_level"):
        val = qs.get(fld)
        if val:
            domain.append((fld, "=", val))
    # Provenance lookups are exact, not fuzzy: `?grn_reference=GRN-2026-00001`
    # has to return that receipt's assets and nothing else, or it is not an
    # audit trail.
    # `?is_tagged=true` is the question Vendra actually asks; it maps onto the
    # one label state that means a physical label was confirmed on the asset.
    raw_tagged = qs.get("is_tagged")
    if raw_tagged not in (None, "", "null"):
        if raw_tagged in ("true", "True", True):
            domain.append(("tag_label_state", "=", "affixed"))
        elif raw_tagged in ("false", "False", False):
            domain.append(("tag_label_state", "!=", "affixed"))
        else:
            # Anything else used to fall through both branches and append no
            # domain at all, so `?is_tagged=1` quietly returned EVERY asset
            # and a caller branching on the result treated them all as tagged.
            raise _BadFilter("`is_tagged` must be `true` or `false`",
                             details={"is_tagged": raw_tagged})
    for fld in ("grn_reference", "purchase_order_reference", "purchase_vendor",
                "import_source", "import_ref"):
        val = qs.get(fld)
        if val:
            domain.append((fld, "=", val))
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
    raw_label_state = qs.get("tag_label_state")
    if raw_label_state not in (None, ""):
        allowed = _tag_label_states()
        if raw_label_state not in allowed:
            raise _BadFilter(
                "`tag_label_state` must be one of: %s" % ", ".join(allowed),
                details={"tag_label_state": raw_label_state,
                         "allowed_values": list(allowed)})
        domain.append(("tag_label_state", "=", raw_label_state))
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
    raw_has_sap_code = qs.get("has_sap_code")
    if raw_has_sap_code not in (None, ""):
        if raw_has_sap_code in ("true", "True", True):
            # `= False` on a Char covers NULL and '' both, so its negation is
            # "there is a code", not merely "the column is not NULL".
            domain.append(("sap_asset_number", "!=", False))
        elif raw_has_sap_code in ("false", "False", False):
            domain.append(("sap_asset_number", "=", False))
        else:
            raise _BadFilter("`has_sap_code` must be `true` or `false`",
                             details={"has_sap_code": raw_has_sap_code})
    # The dual-code state. Same rule as `tag_label_state`, and it matters
    # more here rather than less: an auditor filtering for `exception` is
    # asking to be shown the findings, and a typo answering `200 []` reads as
    # "there are none" — the single most reassuring wrong answer this API can
    # give. `"null"` is not a "no filter" sentinel on an enum.
    raw_recon_state = qs.get("sap_reconciliation_state")
    if raw_recon_state not in (None, ""):
        allowed = _sap_reconciliation_states()
        if raw_recon_state not in allowed:
            raise _BadFilter(
                "`sap_reconciliation_state` must be one of: %s"
                % ", ".join(allowed),
                details={"sap_reconciliation_state": raw_recon_state,
                         "allowed_values": list(allowed)})
        domain.append(("sap_reconciliation_state", "=", raw_recon_state))
    if qs.get("is_verified") in ("true", "True", True):
        domain.append(("is_verified", "=", True))
    elif qs.get("is_verified") in ("false", "False", False):
        domain.append(("is_verified", "=", False))
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
    "category_id", "subcategory_id", "asset_type_id", "asset_level", "domain",
    "parent_id",
    "building_id", "floor_id", "room_id", "location_id",
    "custodian_id", "department",
    "condition", "state",
    "currency_id", "purchase_date", "warranty_expiry",
    "purchase_value", "replacement_cost",
    "acquisition_date", "acquisition_cost", "current_value",
    "disposal_date", "disposal_reason",
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


def _browse_or_404(asset_id):
    rec = request.env["nrs.asset"].sudo().browse(int(asset_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Asset {asset_id} not found", status=404)
    return rec, None


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
                     {"name": "category_id", "schema": {"type": "integer"}},
                     {"name": "subcategory_id", "schema": {"type": "integer"}},
                     {"name": "location_id", "schema": {"type": "integer"}},
                     {"name": "building_id", "schema": {"type": "integer"}},
                     {"name": "floor_id", "schema": {"type": "integer"}},
                     {"name": "room_id", "schema": {"type": "integer"}},
                     {"name": "custodian_id", "schema": {"type": "integer"}},
                     {"name": "parent_id", "schema": {"type": "integer"}},
                     {"name": "state", "schema": {"type": "string",
                      "enum": ["active", "in_repair", "disposed", "transferred", "missing"]}},
                     {"name": "condition", "schema": {"type": "string",
                      "enum": ["new", "good", "fair", "poor", "decommissioned"]}},
                     {"name": "domain", "schema": {"type": "string"}},
                     {"name": "asset_level", "schema": {"type": "string"}},
                     {"name": "is_verified", "schema": {"type": "boolean"},
                      "description": "Whether the last physical verification is "
                                     "still inside its window. This EXPIRES: the "
                                     "window is the asset category's "
                                     "`verification_interval_days`, falling back to "
                                     "the tenant default (365 days), and a daily job "
                                     "re-evaluates it. An asset can therefore go from "
                                     "true to false with no write to the record."},
                     {"name": "grn_reference", "schema": {"type": "string"},
                      "description": "Exact match. Returns every asset created "
                                     "from that goods receipt (INT-03)."},
                     {"name": "purchase_order_reference", "schema": {"type": "string"},
                      "description": "Exact match on the purchase order reference."},
                     {"name": "purchase_vendor", "schema": {"type": "string"},
                      "description": "Exact match on the supplying vendor."},
                     {"name": "import_source", "schema": {"type": "string",
                      "enum": ["myservice", "sap", "redhubb", "vendra",
                               "excel", "other"]}},
                     {"name": "import_ref", "schema": {"type": "string"},
                      "description": "Exact match on the writing system's own batch reference."},
                     {"name": "is_tagged", "schema": {"type": "boolean"},
                      "description": "True returns only assets with a label "
                                     "confirmed affixed (INT-04/05). This is "
                                     "the physical-tagging question; the `tag` "
                                     "field is populated from creation and "
                                     "does not answer it."},
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
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_assets(self, **kwargs):
        qs = get_params()
        Asset = request.env["nrs.asset"].sudo()
        try:
            domain = _list_domain(qs)
        except _BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Asset, domain,
            limit=limit, cursor=qs.get("cursor"),
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
                      "description": "Comma-separated optional sections: transfers, pm, children"},
                 ])
    def get_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_asset(rec, include=include)

    # ── Get by tag: GET /api/v1/assets/by-tag/<tag> ────────────────

    @cadra_route("/api/v1/assets/by-tag/<string:tag>", method="GET",
                 summary="Get a single asset by asset_tag (or asset_code as fallback)",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: transfers, pm, children"},
                 ])
    def get_asset_by_tag(self, tag, **kwargs):
        Asset = request.env["nrs.asset"].sudo()
        rec = Asset.search([("asset_tag", "=", tag)], limit=1) \
            or Asset.search([("asset_code", "=", tag)], limit=1)
        if not rec:
            return err(ERR_NOT_FOUND, f"No asset with tag or code '{tag}'", status=404)
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
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
                         "category_id": {"type": "integer", "nullable": True},
                         "subcategory_id": {"type": "integer", "nullable": True},
                         "asset_type_id": {"type": "integer", "nullable": True},
                         "asset_level": {"type": "string", "nullable": True},
                         "domain": {"type": "string", "nullable": True},
                         "parent_id": {"type": "integer", "nullable": True},
                         "building_id": {"type": "integer", "nullable": True},
                         "floor_id": {"type": "integer", "nullable": True},
                         "room_id": {"type": "integer", "nullable": True},
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
                         "warranty_expiry": {"type": "string", "format": "date", "nullable": True},
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
                 })
    def create_asset(self, **kwargs):
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals.get("name"):
            return err(ERR_INVALID_REQUEST, "`name` is required",
                       details={"rejected_fields": rejected} if rejected else None)
        rec = request.env["nrs.asset"].sudo().create(vals)
        out = serialize_asset(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Patch: PATCH /api/v1/assets/<id> ───────────────────────────

    @cadra_route("/api/v1/assets/<int:id>", method="PATCH",
                 summary="Partial update of an asset",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 response_schema={"$ref": "#/components/schemas/Asset"},
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/assets. Unknown fields are rejected "
                                     "and reported under `_warnings`."),
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
        vals, rejected = _filter_writable(body)
        if not vals and not rejected:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        if vals:
            rec.write(vals)
        out = serialize_asset(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Move action: POST /api/v1/assets/<id>/move ─────────────────

    @cadra_route("/api/v1/assets/<int:id>/move", method="POST",
                 summary="Move asset to a new location (creates an nrs.asset.transfer row)",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["to_location_id"],
                     "properties": {
                         "to_location_id": {"type": "integer",
                                            "description": "Destination generic.location id"},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_location_id": 47,
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

        Transfer = request.env["nrs.asset.transfer"].sudo()
        seq = request.env["ir.sequence"].next_by_code("nrs.asset.transfer") or "/"
        transfer = Transfer.create({
            "name": seq,
            "asset_id": rec.id,
            "from_location_id": from_loc.id or False,
            "to_location_id": to_loc.id,
            "from_custodian_id": rec.custodian_id.id or False,
            "to_custodian_id": rec.custodian_id.id or False,
            "transfer_date": odoo_fields.Date.today(),
            "reason": body.get("reason") or "",
            "state": "done",
        })
        rec.write({"location_id": to_loc.id})

        return {
            "asset": serialize_asset(rec),
            "transfer": {
                "id": transfer.id,
                "reference": transfer.name,
                "from_location": _ref(from_loc),
                "to_location": _ref(to_loc),
            },
        }

    # ── Transfer custody: POST /api/v1/assets/<id>/transfer-custody ─

    @cadra_route("/api/v1/assets/<int:id>/transfer-custody", method="POST",
                 summary="Transfer custody to a different hr.employee",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["to_custodian_id"],
                     "properties": {
                         "to_custodian_id": {"type": "integer",
                                             "description": "New custodian hr.employee id"},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_custodian_id": 218,
                     "reason": "Previous custodian left the company",
                 })
    def transfer_custody(self, id, **kwargs):
        """Reassign the asset's custodian. The audit trail comes via Odoo's
        mail.thread auto-logging (custodian_id has tracking=True) plus an
        explicit message_post carrying the optional reason. We deliberately
        do NOT use nrs.asset.transfer here — that model has a NOT-NULL
        location-change constraint and is location-move-centric."""
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

        rec.write({"custodian_id": to_cust.id})
        reason = body.get("reason") or ""
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
            },
        }

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

        label = rec.active_tag_id
        if not label:
            return err(ERR_INVALID_REQUEST,
                       "This asset has no active tag to confirm",
                       details={"asset_id": rec.id})

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
        # names both the scanned and the expected tag.
        label._mark_affixed(tag_number,
                            affixed_by_name=body.get("affixed_by_name"),
                            affixed_date=affixed_at)

        return {
            "asset": serialize_asset(rec),
            "tagging": _serialize_tagging(rec),
        }

    # ── Register report: GET /api/v1/reports/depreciation ──────────

    @cadra_route("/api/v1/reports/depreciation", method="GET",
                 summary="Register-wide depreciation totals and breakdowns",
                 scopes=[SCOPE_DASHBOARDS_READ],
                 query_params=[
                     {"name": "category_id", "schema": {"type": "integer"},
                      "description": "Restrict the report to one asset category"},
                 ])
    def depreciation_report(self, **kwargs):
        """Totals, per-category breakdown, and the two data-quality counts that
        matter in practice: assets whose start date was inferred, and assets
        with a depreciation method but no cost to depreciate."""
        domain = []
        raw_cat = kwargs.get("category_id")
        if raw_cat:
            try:
                domain.append(("category_id", "=", int(raw_cat)))
            except (TypeError, ValueError):
                return err(ERR_INVALID_REQUEST, "`category_id` must be an integer",
                           details={"category_id": raw_cat})
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
