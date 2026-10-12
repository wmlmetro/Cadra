"""
Cadra API v1 — Configuration (asset categories + depreciation settings).

Reads are on `assets:read` so any client can see how a tenant is configured.
WRITES ARE ON `admin`, deliberately: changing a category's useful life restates
book value on every asset in that class, and the calculation conventions restate
the entire register. That is not the same risk as editing one asset, so it does
not share the `assets:write` scope.
"""
import re

from odoo import http
from odoo.http import request
from odoo.tools.mail import single_email_re

from .utils import (
    ERR_CONFLICT,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_FORBIDDEN,
    SCOPE_ASSETS_READ,
    SCOPE_SETTINGS_CLASSES,
    SCOPE_SETTINGS_READ,
    SCOPE_SETTINGS_WRITE,
    caller_holds,
    err,
    get_params,
    ok,
    refuse_unwritable,
)
from .v1 import cadra_route

#: Depreciation policy — what the Depreciation settings screen edits.
_CATEGORY_POLICY_FIELDS = {
    "depreciation_method", "useful_life_months", "declining_rate", "salvage_rate",
}

#: Identity and classification — what the Asset Categories screen edits.
#
# `name` and `code` were deliberately excluded when this controller only served
# the depreciation screen: renaming a category is a taxonomy change, not a
# depreciation setting. Now that there is a categories admin screen that is
# precisely its job, so they are writable here. The split above keeps the two
# screens from editing the same field in two places.
_CATEGORY_IDENTITY_FIELDS = {
    "name", "code", "domain", "description", "sequence", "pm_interval_days",
    # How long a physical verification of an asset in this category stays
    # current. Sits beside pm_interval_days because it is the same kind of
    # setting — a cadence this category is inspected on — and belongs on the
    # same screen. 0 means "use the tenant-wide default"; see
    # nrs.asset._verification_interval_days.
    "verification_interval_days",
}

#: How a received unit of the class is identified — Section 12, handoff 58
#: §4 — and which SAP asset class it maps to (handoff 59 §1). The ONLY keys
#: a caller holding `settings:classes` without `settings:write` may send
#: (the Asset Controller's).
_CATEGORY_CLASS_FIELDS = {"identification_mode", "class_attributes_schema",
                          "sap_asset_class"}

_CATEGORY_WRITABLE = (_CATEGORY_POLICY_FIELDS | _CATEGORY_IDENTITY_FIELDS
                      | _CATEGORY_CLASS_FIELDS)

_IDENTIFICATION_MODES = ["serial", "tag_id", "pool", "record_only"]

#: Mirrors the Selection on nrs.asset.category.
_FM_DOMAINS = [
    "building", "plant", "plumbing", "fleet",
    "security", "it", "furniture", "other",
]

_SETTINGS_WRITABLE = {"mode", "proration", "declining_switches_to_straight_line"}


def _serialize_category(c):
    return {
        "id": c.id,
        "name": c.name,
        "code": c.code or None,
        "domain": c.domain or None,
        "description": c.description or None,
        "sequence": c.sequence,
        "asset_count": c.asset_count,
        "depreciating_count": c.asset_depreciating_count,
        "pm_interval_days": c.pm_interval_days or None,
        "verification_interval_days": c.verification_interval_days or None,
        "depreciation": {
            "method": c.depreciation_method,
            "useful_life_months": c.useful_life_months or None,
            "declining_rate": c.declining_rate or None,
            "salvage_rate": c.salvage_rate or None,
        },
        # Section 12 (handoff 58 §4), read by Vendra's receipt: how a unit
        # of this class is identified, and what a receipt of it must carry
        # — the EFFECTIVE schema, never null, in the shape PATCH accepts.
        "identification_mode": c.identification_mode or "serial",
        "class_attributes_schema": c._effective_schema(),
        # Handoff 59 §1: SAP's four-digit asset class for this category, or
        # null — and a registration of a class with none is refused, because
        # INT-06 would send SAP a null class and SAP rejects the master.
        "sap_asset_class": c.sap_asset_class or None,
    }


def _class_field_error(vals):
    """The 400 for a bad mode or schema, or None."""
    from odoo.addons.myservice_asset_register.models.asset_identification \
        import parse_schema
    mode = vals.get("identification_mode")
    if "identification_mode" in vals and mode not in _IDENTIFICATION_MODES:
        return err(ERR_INVALID_REQUEST,
                   "`identification_mode` must be one of: %s"
                   % ", ".join(_IDENTIFICATION_MODES),
                   details={"field": "identification_mode",
                            "allowed_values": _IDENTIFICATION_MODES})
    if "class_attributes_schema" in vals and vals[
            "class_attributes_schema"] is None:
        # `null` resets the class to its mode's default schema (stored
        # empty); what GET publishes is then that default.
        vals["class_attributes_schema"] = False
    elif "class_attributes_schema" in vals:
        try:
            names = parse_schema(vals["class_attributes_schema"])
        except ValueError as e:
            return err(ERR_INVALID_REQUEST, str(e),
                       details={"field": "class_attributes_schema"})
        vals["class_attributes_schema"] = {"mandatory": list(names)}
    if "sap_asset_class" in vals:
        from odoo.addons.myservice_asset_register.models.asset_identification \
            import SAP_CLASS_RE, SAP_CLASS_SENTENCE
        value = vals["sap_asset_class"]
        value = value.strip() if isinstance(value, str) else value
        if value in (None, ""):
            vals["sap_asset_class"] = False
        elif not isinstance(value, str) or not SAP_CLASS_RE.match(value):
            return err(ERR_INVALID_REQUEST, SAP_CLASS_SENTENCE,
                       details={"field": "sap_asset_class",
                                "example": "3000"})
        else:
            vals["sap_asset_class"] = value
    return None


# ── Receipt gates (handoff 57, kept by handoff 58) ───────────────────

#: The parameter `nrs.asset._receipt_gated()` reads (raw SQL, absent = off).
#: Written here as `true`/`false`, never deleted, so the row keeps its writer.
RECEIPT_GATE_PARAM = "cadra.receipt.gated"

#: Said on the Settings screen, from here, so the screen and the API cannot
#: describe the switch differently.
RECEIPT_GATE_STATEMENT_ON = (
    "On: a unit received from a goods receipt is a candidate, not an asset. "
    "It joins the register only after Internal Audit has verified and "
    "approved it, a tag has been affixed, and a Register Maker and a "
    "different Register Checker have registered it. Nobody may pass a "
    "candidate through two of those gates. SAP receives the asset master at "
    "registration, not at tagging.")
RECEIPT_GATE_STATEMENT_OFF = (
    "Off: a unit received from a goods receipt is an asset in the register "
    "at once, its tag is issued on receipt, and SAP receives the asset "
    "master when the tag is affixed.")

_RECEIPT_GATE_SCHEMA = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean"},
        "configured": {"type": "boolean"},
        "default_when_unset": {"type": "boolean"},
        "parameter": {"type": "string"},
        "statement": {"type": "string"},
        "candidates_in_flight": {"type": "integer", "nullable": True},
        "changed_by": {"type": "object", "nullable": True,
                       "properties": {"id": {"type": "integer"},
                                      "name": {"type": "string"}}},
        "changed_at": {"type": "string", "format": "date-time",
                       "nullable": True},
    },
}


def _receipt_gate_block(env):
    """What the switch says, who set it, and what is waiting on the gates.

    `configured` tells *nobody has ever set this* from *somebody turned it
    off*, as `/settings/approvals` does. `candidates_in_flight` is there
    because turning the switch off does not register anything: a candidate
    already in the machine stays a candidate, hidden from the register, until
    its gates are passed — a screen about to switch it off should say so.
    """
    enabled = env["nrs.asset"].sudo()._receipt_gated()
    env.cr.execute(
        "SELECT value, write_uid, write_date FROM ir_config_parameter "
        "WHERE key = %s", (RECEIPT_GATE_PARAM,))
    row = env.cr.fetchone()
    writer = env["res.users"].sudo().browse(row[1]).exists() if row and row[1] \
        else None
    Asset = env["nrs.asset"].sudo().with_context(active_test=False)
    in_flight = (Asset.search_count([("register_state", "!=", "registered")])
                 if "register_state" in Asset._fields else None)
    return {
        "enabled": enabled,
        "configured": row is not None,
        "default_when_unset": False,
        "parameter": RECEIPT_GATE_PARAM,
        "statement": (RECEIPT_GATE_STATEMENT_ON if enabled
                      else RECEIPT_GATE_STATEMENT_OFF),
        "candidates_in_flight": in_flight,
        "changed_by": ({"id": writer.id, "name": writer.name}
                       if writer else None),
        "changed_at": (row[2].isoformat() if row and row[2] else None),
    }


#: Said on the Asset Categories screen, from here (handoff 59 §3).
PLACEHOLDER_STATEMENT = (
    "A value on this list is not a serial number. With the receipt gates on, "
    "a unit received with one is refused — \"'XXXX' is a placeholder, not a "
    "serial number. Capture the serial printed on the item.\" — and a "
    "placeholder already on a legacy asset is never the reason a real serial "
    "is refused. Nothing already on the register is changed; with the gates "
    "off, nothing is checked.")

_PLACEHOLDER_SCHEMA = {
    "type": "object",
    "properties": {
        "exact": {"type": "array", "items": {"type": "string"}},
        "patterns": {"type": "array", "items": {"type": "string"}},
        "configured": {"type": "boolean"},
        "parameter": {"type": "string"},
        "statement": {"type": "string"},
        "changed_by": {"type": "object", "nullable": True,
                       "properties": {"id": {"type": "integer"},
                                      "name": {"type": "string"}}},
        "changed_at": {"type": "string", "format": "date-time",
                       "nullable": True},
        "legacy": {
            "type": "object",
            "description": "Every asset record on this tenant, measured now: "
                           "how many carry a serial, how many of those a "
                           "placeholder, and the commonest.",
            "properties": {
                "assets": {"type": "integer"},
                "with_serial": {"type": "integer"},
                "placeholders": {"type": "integer"},
                "top": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"value": {"type": "string"},
                                   "count": {"type": "integer"}}}},
            },
        },
    },
}


def _placeholder_block(env):
    from odoo.addons.myservice_asset_register.models import (
        serial_placeholders)
    lists = serial_placeholders.load(env)
    env.cr.execute(
        "SELECT write_uid, write_date FROM ir_config_parameter "
        "WHERE key = %s", (serial_placeholders.PARAM,))
    row = env.cr.fetchone()
    writer = env["res.users"].sudo().browse(row[0]).exists() \
        if row and row[0] else None
    return {
        "exact": lists["exact"],
        "patterns": lists["patterns"],
        "configured": lists["configured"],
        "parameter": serial_placeholders.PARAM,
        "statement": PLACEHOLDER_STATEMENT,
        "changed_by": ({"id": writer.id, "name": writer.name}
                       if writer else None),
        "changed_at": (row[1].isoformat() if row and row[1] else None),
        "legacy": serial_placeholders.measure(env),
    }


class CadraConfigV1(http.Controller):

    # ── Categories ─────────────────────────────────────────────────

    @cadra_route("/api/v1/asset-categories", method="GET",
                 summary="List asset categories with their depreciation policy",
                 scopes=[SCOPE_ASSETS_READ])
    def list_categories(self, **kwargs):
        """Every category, with the policy its assets inherit.

        Not paginated: the taxonomy is ~20 rows and the settings screen wants
        all of it at once to render a single editable table.
        """
        cats = request.env["nrs.asset.category"].sudo().search([], order="name")
        return [_serialize_category(c) for c in cats]

    @cadra_route("/api/v1/asset-categories/<int:id>", method="PATCH",
                 summary="Update a category's policy, identity or "
                         "identification mode",
                 # `settings:write` for every key, OR `settings:classes` for
                 # the two Section 12 keys alone (handoff 58 §4) — checked in
                 # the route, because the decorator's list is all-of.
                 scopes=[],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "depreciation_method": {
                             "type": "string",
                             "enum": ["none", "straight_line",
                                      "declining_balance", "erp_managed"]},
                         "useful_life_months": {"type": "integer"},
                         "declining_rate": {"type": "number"},
                         "salvage_rate": {"type": "number"},
                         "pm_interval_days": {"type": "integer"},
                         "verification_interval_days": {"type": "integer"},
                         "identification_mode": {
                             "type": "string", "enum": _IDENTIFICATION_MODES,
                             "description": "Handoff 58 (Section 12). New "
                                            "receipts only (AD-31). Needs "
                                            "`settings:write` or "
                                            "`settings:classes`."},
                         "class_attributes_schema": {
                             "type": "object",
                             "description": "{\"mandatory\": [field, ...]} — "
                                            "what a receipt of this class "
                                            "must carry, from: name, make, "
                                            "model_name, manufacturer, "
                                            "colour, material, dimensions, "
                                            "reference."},
                         "sap_asset_class": {
                             "type": "string", "nullable": True,
                             "pattern": "^[0-9]{4}$",
                             "description": "Handoff 59. SAP's four-digit "
                                            "asset class code; null or an "
                                            "empty string clears it. Needs "
                                            "`settings:write` or "
                                            "`settings:classes`."},
                     },
                 },
                 request_example={
                     "depreciation_method": "straight_line",
                     "useful_life_months": 60,
                     "salvage_rate": 10.0,
                 })
    def patch_category(self, id, **kwargs):
        """Change a category's policy and push it down to the assets that
        follow it. Assets with a per-asset override are left alone."""
        # The scope FIRST — before existence and before the body — so a
        # caller holding neither scope is refused 403 and learns nothing
        # about which categories exist (the decorator cannot say either-or;
        # found by the verification pass: it answered 404/400 instead).
        if not (caller_holds(SCOPE_SETTINGS_WRITE)
                or caller_holds(SCOPE_SETTINGS_CLASSES)):
            return err(ERR_FORBIDDEN,
                       "Changing a category needs the `settings:write` "
                       "scope (or `settings:classes`, for its "
                       "identification mode and SAP asset class alone)",
                       status=403,
                       details={"required_scopes": [
                           SCOPE_SETTINGS_WRITE, SCOPE_SETTINGS_CLASSES]})
        cat = request.env["nrs.asset.category"].sudo().browse(int(id))
        if not cat.exists():
            return err(ERR_NOT_FOUND, f"Category {id} not found", status=404)

        body = get_params()
        vals = {k: v for k, v in body.items() if k in _CATEGORY_WRITABLE}
        rejected = [k for k in body if k not in _CATEGORY_WRITABLE]
        if rejected:
            return refuse_unwritable(rejected, _CATEGORY_WRITABLE)
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable fields supplied",
                       details={"writable": sorted(_CATEGORY_WRITABLE)})
        if not caller_holds(SCOPE_SETTINGS_WRITE):
            beyond = sorted(set(vals) - _CATEGORY_CLASS_FIELDS)
            if beyond:
                return err(ERR_FORBIDDEN,
                           "`settings:classes` changes a class's "
                           "identification mode, mandatory attributes and "
                           "SAP asset class only; %s needs `settings:write`"
                           % ", ".join("`%s`" % k for k in beyond),
                           status=403,
                           details={"fields": beyond,
                                    "required_scopes": [SCOPE_SETTINGS_WRITE]})
        error = _class_field_error(vals)
        if error:
            return error

        if vals.get("domain") and vals["domain"] not in _FM_DOMAINS:
            # Handoff 25 C2. Every other refusal in this API publishes the
            # accepted set as `allowed_values`; this one alone said `allowed`,
            # so a client keying on the standard name got nothing here and
            # had no way to know it was the odd one out.
            #
            # BOTH keys, same list. Renaming outright would break any client
            # reading `allowed` today, and a published details key is API
            # surface like any other — so `allowed` is DEPRECATED rather than
            # removed, and goes at the next major version. See
            # docs/api/CHANGELOG.md for the date.
            return err(ERR_INVALID_REQUEST,
                       f"Unknown FM domain '{vals['domain']}'",
                       details={"allowed_values": _FM_DOMAINS,
                                "allowed": _FM_DOMAINS})

        cat.write(vals)

        # Policy is inherited, so the assets need re-deriving — otherwise the
        # register would keep reporting the old useful life until the next cron.
        # Only when the POLICY changed: an identification-mode change (handoff
        # 58) re-deriving every asset of the class would be 12,715 rewrites on
        # `test19`'s category 1 for nothing (verification pass).
        assets = request.env["nrs.asset"].browse()
        if _CATEGORY_POLICY_FIELDS & set(vals):
            assets = request.env["nrs.asset"].sudo().search([
                ("category_id", "=", cat.id),
                ("use_category_policy", "=", True),
            ])
            assets._sync_policy_from_category()
            assets._apply_depreciation()

        data = _serialize_category(cat)
        data["assets_recomputed"] = len(assets)
        return data

    @cadra_route("/api/v1/asset-categories", method="POST",
                 summary="Create an asset category",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["name"],
                     "properties": {
                         "name": {"type": "string"},
                         "code": {"type": "string", "nullable": True},
                         "domain": {"type": "string", "enum": _FM_DOMAINS,
                                    "nullable": True},
                         "description": {"type": "string", "nullable": True},
                         "sequence": {"type": "integer"},
                         "pm_interval_days": {"type": "integer"},
                         "verification_interval_days": {"type": "integer"},
                     },
                 },
                 request_example={"name": "Medical Equipment", "code": "MED",
                                  "domain": "other", "pm_interval_days": 180})
    def create_category(self, **kwargs):
        body = get_params()
        # THE ELEVENTH ROUTE. Handoff 31 counted ten routes that dropped a
        # field they did not accept, by searching for the ones that REPORTED
        # it in `_warnings`. This one dropped fields and reported nothing, so
        # that search could not see it: `{"name": "X", "method":
        # "straight_line"}` answered 201 and set no policy — the depreciation
        # bug that justified the ruling, at the one door the ruling missed.
        # Found by the test author, reading the file.
        rejected = [k for k in body if k not in _CATEGORY_WRITABLE]
        if rejected:
            return refuse_unwritable(rejected, _CATEGORY_WRITABLE)
        name = (body.get("name") or "").strip()
        if not name:
            return err(ERR_INVALID_REQUEST, "`name` is required")

        vals = {k: v for k, v in body.items() if k in _CATEGORY_WRITABLE}
        vals["name"] = name
        error = _class_field_error(vals)
        if error:
            return error
        if vals.get("domain") and vals["domain"] not in _FM_DOMAINS:
            # Handoff 25 C2, second of three sites. `allowed` is deprecated;
            # both keys carry the same list until the next major version.
            return err(ERR_INVALID_REQUEST,
                       f"Unknown FM domain '{vals['domain']}'",
                       details={"allowed_values": _FM_DOMAINS,
                                "allowed": _FM_DOMAINS})

        cat = request.env["nrs.asset.category"].sudo().create(vals)
        return _serialize_category(cat)

    @cadra_route("/api/v1/asset-categories/<int:id>", method="DELETE",
                 summary="Delete an asset category (only when it holds no assets)",
                 scopes=[SCOPE_SETTINGS_WRITE])
    def delete_category(self, id, **kwargs):
        """Refuses while assets still reference the category.

        category_id is required on nrs.asset, so deleting one that is in use
        would either orphan those rows or fail at the database. Better to say
        so plainly, with the count, than surface a foreign-key error.
        """
        cat = request.env["nrs.asset.category"].sudo().browse(int(id))
        if not cat.exists():
            return err(ERR_NOT_FOUND, f"Category {id} not found", status=404)

        count = request.env["nrs.asset"].sudo().search_count(
            [("category_id", "=", cat.id)])
        if count:
            return err(ERR_CONFLICT,
                       f"'{cat.name}' still holds {count} asset(s)",
                       status=409,
                       details={"asset_count": count,
                                "hint": "Reassign those assets first."})

        name = cat.name
        cat.unlink()
        return {"deleted": True, "id": int(id), "name": name}

    # ── Branding ───────────────────────────────────────────────────

    #: ir.config_parameter keys the brand endpoint reads. The per-tenant
    #: cadra_brand_* modules seed these with noupdate="1", so writing them here
    #: via set_param is the supported way to change a live tenant — editing the
    #: data file would not touch an existing database.
    _BRAND_PARAMS = {
        "short_name": "cadra.brand_short_name",
        "primary": "cadra.brand_primary",
        "primary_dark": "cadra.brand_primary_dark",
        "logo": "cadra.brand_logo",
    }

    #: A logo rides in every page load as a data URI, so keep it small. Jaiz's
    #: official SVG is ~10KB; this leaves generous headroom without allowing
    #: someone to paste a multi-megabyte PNG into every request.
    _LOGO_MAX_CHARS = 262_144

    _ALLOWED_LOGO_PREFIXES = ("data:image/svg+xml", "data:image/png",
                              "data:image/jpeg", "data:image/webp")

    #: RFC 5321's limit on a forward path; anything longer is not an address
    #: a mail server will accept, whatever the pattern says.
    _SENDER_EMAIL_MAX_CHARS = 254

    def _sender_company(self):
        """The company whose `email` is the letters' From (handoff 45 H.6).

        `res.users._action_reset_password` (`models/invitation.py`) sends
        from `user.company_id.email_formatted` — the RECIPIENT's company —
        and a person created over the API is put in the main company. So the
        main company is the one written; the first company by order is the
        fallback for a database that has lost the xmlid. Every local tenant
        has exactly one company (8 of 8, measured 2026-10-02), so this and
        the `search([], limit=1)` that `name` renames are the same record
        there; on a multi-company database they need not be.
        """
        env = request.env
        company = env.ref("base.main_company", raise_if_not_found=False)
        if company and company._name == "res.company" and company.exists():
            return company.sudo()
        return env["res.company"].sudo().search([], limit=1)

    def _branding_payload(self):
        """Plain dict — NOT the route handler.

        `get_branding` is wrapped by cadra_route/cadra_endpoint, so calling it
        from another handler returns the wrapped response rather than the data.
        Both handlers go through this instead.
        """
        env = request.env
        icp = env["ir.config_parameter"].sudo()
        company = env["res.company"].sudo().search([], limit=1)
        sender = self._sender_company()
        return {
            "name": company.name if company else "Cadra",
            "short_name": icp.get_param(self._BRAND_PARAMS["short_name"], ""),
            "primary": icp.get_param(self._BRAND_PARAMS["primary"], ""),
            "primary_dark": icp.get_param(self._BRAND_PARAMS["primary_dark"], ""),
            "logo": icp.get_param(self._BRAND_PARAMS["logo"], ""),
            # The address invitations and password resets are sent FROM; ""
            # when the company has none. Stored on the company record, not
            # as a parameter, because that is where the letter reads it.
            "sender_email": (sender.email or "") if sender else "",
        }

    @cadra_route("/api/v1/settings/branding", method="GET",
                 summary="Tenant branding (name, colours, logo, sender address)",
                 scopes=[SCOPE_ASSETS_READ])
    def get_branding(self, **kwargs):
        return self._branding_payload()

    @cadra_route("/api/v1/settings/branding", method="PATCH",
                 summary="Update tenant branding",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "name": {"type": "string"},
                         "short_name": {"type": "string"},
                         "primary": {"type": "string",
                                     "description": "Hex colour, e.g. #004080"},
                         "primary_dark": {"type": "string"},
                         "logo": {"type": "string",
                                  "description": "data: URI, or empty to clear"},
                         "sender_email": {
                             "type": "string", "format": "email",
                             "nullable": True,
                             "description":
                                 "The address invitations and password "
                                 "resets are sent from — the company "
                                 "record's email. One bare address "
                                 "(no display name); null or \"\" clears "
                                 "it. An address that is not one is "
                                 "refused with 400 and nothing is written.",
                         },
                     },
                 },
                 request_example={"short_name": "Jaiz", "primary": "#004080",
                                  "primary_dark": "#00305F"})
    def patch_branding(self, **kwargs):
        """Writes the brand a tenant is served at runtime.

        One static SPA bundle serves every tenant and fetches GET /api/v1/brand
        at startup, so this takes effect without a rebuild or a deploy — which
        is the whole point of not shipping a module per customer.
        """
        body = get_params()
        allowed = {"name", "sender_email"} | set(self._BRAND_PARAMS)
        vals = {k: v for k, v in body.items() if k in allowed}
        rejected = [k for k in body if k not in allowed]
        if rejected:
            return refuse_unwritable(rejected, allowed)
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable branding fields supplied",
                       details={"writable": sorted(allowed)})

        for key in ("primary", "primary_dark"):
            colour = (vals.get(key) or "").strip()
            if colour and not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
                return err(ERR_INVALID_REQUEST,
                           f"`{key}` must be a 6-digit hex colour like #004080",
                           details={key: colour})
            if colour:
                vals[key] = colour.upper()

        logo = vals.get("logo")
        if logo:
            if len(logo) > self._LOGO_MAX_CHARS:
                return err(ERR_INVALID_REQUEST,
                           "Logo is too large — it is sent with every page load",
                           details={"chars": len(logo),
                                    "max_chars": self._LOGO_MAX_CHARS})
            if not logo.startswith(self._ALLOWED_LOGO_PREFIXES):
                # Handoff 25 C2, third of three sites — the handoff named
                # one. `allowed` is deprecated; both keys, same list.
                return err(ERR_INVALID_REQUEST,
                           "Logo must be an image data: URI",
                           details={"allowed_values": list(self._ALLOWED_LOGO_PREFIXES),
                                    "allowed": list(self._ALLOWED_LOGO_PREFIXES)})

        # EVERY refusal before ANY write. The blank-name check used to sit
        # below the `set_param` loop, so `{"primary": "#123456", "name": " "}`
        # wrote the colour and THEN answered 400 — and `err()` returns a
        # response, it does not roll back. The rule handoff 31's 400 states
        # ("nothing was written") was already broken here by a different
        # refusal; found by the verification pass, which was asked to look
        # for a route that validates after it writes.
        if "name" in vals and not (vals["name"] or "").strip():
            return err(ERR_INVALID_REQUEST, "`name` cannot be blank")

        # The sender address (handoff 45 H.6). Validated here, with the rest,
        # because a refusal must come before ANY write. The value the record
        # already holds is accepted as it is: the Branding screen sends every
        # key on every save, so an address stored before this check existed
        # must not make saving a colour impossible.
        sender_email = None
        if "sender_email" in vals:
            raw = vals["sender_email"]
            if raw is not None and not isinstance(raw, str):
                return err(ERR_INVALID_REQUEST,
                           "`sender_email` must be an email address, or "
                           "empty to clear it",
                           details={"sender_email": raw})
            sender_email = (raw or "").strip()
            current = (self._sender_company().email or "").strip()
            if sender_email and sender_email != current and (
                    len(sender_email) > self._SENDER_EMAIL_MAX_CHARS
                    or not single_email_re.match(sender_email)):
                return err(ERR_INVALID_REQUEST,
                           f"`sender_email` must be one email address, like "
                           f"assets@example.org, with no name or spaces — "
                           f"'{sender_email[:80]}' is not one. Send it empty "
                           f"to clear it.",
                           details={"sender_email": sender_email})

        env = request.env
        icp = env["ir.config_parameter"].sudo()
        for field, key in self._BRAND_PARAMS.items():
            if field in vals:
                icp.set_param(key, vals[field] or "")

        if "name" in vals:
            name = (vals["name"] or "").strip()
            # This renames the company record, which is what /api/v1/brand
            # reports as the tenant name.
            company = env["res.company"].sudo().search([], limit=1)
            if company:
                company.name = name

        if sender_email is not None:
            company = self._sender_company()
            if company and (company.email or "").strip() != sender_email:
                # `res.company.email` is a related field onto the company's
                # partner, so this writes `res_partner.email` — the column
                # `company_id.email_formatted` reads.
                company.email = sender_email or False

        return self._branding_payload()

    # ── Depreciation settings ──────────────────────────────────────

    @cadra_route("/api/v1/settings/depreciation", method="GET",
                 summary="Tenant depreciation settings and data-quality counts",
                 scopes=[SCOPE_ASSETS_READ])
    def get_depreciation_settings(self, **kwargs):
        return request.env["cadra.depreciation.settings"].sudo().get_settings()

    @cadra_route("/api/v1/settings/depreciation", method="PATCH",
                 summary="Update tenant depreciation settings",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "mode": {"type": "string",
                                  "enum": ["computed", "erp_managed"]},
                         "proration": {"type": "string",
                                       "enum": ["whole_month", "daily"]},
                         "declining_switches_to_straight_line": {"type": "boolean"},
                     },
                 },
                 request_example={"declining_switches_to_straight_line": True})
    def patch_depreciation_settings(self, **kwargs):
        """Every one of these restates book values across the register, so the
        model recomputes before returning."""
        body = get_params()
        vals = {k: v for k, v in body.items() if k in _SETTINGS_WRITABLE}
        rejected = [k for k in body if k not in _SETTINGS_WRITABLE]
        if rejected:
            return refuse_unwritable(rejected, _SETTINGS_WRITABLE)
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable settings supplied",
                       details={"writable": sorted(_SETTINGS_WRITABLE)})

        return request.env["cadra.depreciation.settings"].sudo().set_settings(vals)

    # ── Approvals: GET /api/v1/settings/approvals ────────────────────

    @cadra_route("/api/v1/settings/approvals", method="GET",
                 summary="Does this register require a second person to "
                         "approve a move or a custody change?",
                 # `assets:read`, NOT `settings:read`. Every other block on
                 # this controller reads with `settings:read`, and this one
                 # deliberately does not: the app has to ask this question
                 # wherever it draws a Move button, and `settings:read` is
                 # granted by `group_asset_manager` and `group_auditor` only.
                 # Gating it that way would make the answer unreadable to
                 # some signed-in users while the button was still on their
                 # screen — and the front end fails CLOSED on an unreadable
                 # answer, so the symptom would be a correct-looking dialog
                 # asking for an approver on a tenant that does not want one.
                 # The value is not sensitive: it says whether this register
                 # asks for a second person, which anyone who can see an
                 # asset may as well know.
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "type": "object",
                     "properties": {
                         "required": {"type": "boolean"},
                         "setting": {"type": "string", "nullable": True,
                                     "enum": ["on", "off", None]},
                         "configured": {"type": "boolean"},
                         "default_when_unset": {"type": "boolean"},
                         "parameter": {"type": "string"},
                     },
                 })
    def get_approval_settings(self, **kwargs):
        """What the approval switch says, and whether anybody ever set it.

        **READ-ONLY, and there is deliberately no PATCH twin.** Every other
        settings block on this controller has one; this one does not, and the
        reason is the point of the control. `assets:write`, `approvals:write`
        and `settings:write` are all granted by a single group,
        `group_asset_manager` — so a PATCH here would let exactly the people
        the rule constrains switch it off, move the asset and switch it back
        on. That is not a control; it is a speed bump with an audit trail
        nobody reads.

        An administrator sets it once, in the database, the way
        `cadra.database_class` is set. The command is printed inside the
        refusal a gated write raises, so nobody has to come looking for it.

        `configured` is what a screen needs and `required` alone cannot say:
        *nobody has ever set this and it is getting the default* and *somebody
        deliberately turned it on* are the same behaviour and very different
        facts.
        """
        from odoo.addons.myservice_asset_register.approval_policy import (
            PARAM, REQUIRED_WHEN_UNSET, approval_setting)
        env = request.env
        setting = approval_setting(env)
        return {
            "required": env["nrs.asset.change.request"].sudo(
            ).approval_is_required(),
            "setting": setting,
            "configured": setting is not None,
            "default_when_unset": REQUIRED_WHEN_UNSET,
            "parameter": PARAM,
        }

    # ── Receipt gates: GET /api/v1/settings, PATCH …/receipt-gate ────
    #
    # Handoff 57, kept by 58: the one place a tenant says "a received unit
    # is not an asset yet". The gate machine it turns on is
    # `nrs.asset.register_state` (`asset_gates.py`).

    @cadra_route("/api/v1/settings", method="GET",
                 summary="Tenant-wide switches every screen may need to know",
                 # `assets:read`, as `/settings/approvals` is and for its
                 # reason: the Candidates page, the asset page's banner and
                 # the register all behave differently when receipts are
                 # gated, and an answer some signed-in people cannot read is
                 # one the app has to guess at.
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "type": "object",
                     "properties": {
                         "receipt_gated": {"type": "boolean"},
                         "receipt_gate": _RECEIPT_GATE_SCHEMA,
                     },
                 })
    def get_settings(self, **kwargs):
        return {
            "receipt_gated": request.env["nrs.asset"].sudo()._receipt_gated(),
            "receipt_gate": _receipt_gate_block(request.env),
        }

    @cadra_route("/api/v1/settings/receipt-gate", method="PATCH",
                 summary="Turn the receipt gates on or off for this tenant",
                 # `settings:write`, as every write on this controller is
                 # (`test_settings_routes_use_settings_write_and_not_admin`:
                 # `admin` is a wildcard). KNOWN WEAKNESS, said rather than
                 # hidden: the Asset Manager holds `settings:write`, so the
                 # person the gates constrain can switch them off — and the
                 # switch is recorded in the configuration-change report, which
                 # is the only thing between that and nobody knowing. Report
                 # 57 suggested making this what `/settings/approvals` is
                 # (read-only over the API, set by an administrator's
                 # command); handoff 58 did not ask for it, so it is on report
                 # 58 §9's go-live list instead of changed here.
                 scopes=[SCOPE_SETTINGS_WRITE],
                 success_status=200,
                 request_schema={
                     "type": "object",
                     "required": ["enabled"],
                     "properties": {"enabled": {"type": "boolean"}},
                 },
                 request_example={"enabled": True},
                 response_schema=_RECEIPT_GATE_SCHEMA)
    def patch_receipt_gate(self, **kwargs):
        """One key, a boolean, stored as `true`/`false` so the row — and its
        writer and write time — survives either way. That row is what the
        configuration-change report reads (`/reports/configuration-changes`),
        so switching this IS a configuration-record event: who, when, what it
        says now."""
        body = get_params()
        rejected = [k for k in body if k != "enabled"]
        if rejected:
            return refuse_unwritable(rejected, {"enabled"})
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return err(ERR_INVALID_REQUEST,
                       "Say whether receipts are gated with `enabled`: true "
                       "or false.",
                       details={"field": "enabled", "received": enabled})
        # `sudo()` keeps the acting uid, so `write_uid` on the row is the
        # person who clicked — the configuration report's "last writer".
        request.env["ir.config_parameter"].sudo().set_param(
            RECEIPT_GATE_PARAM, "true" if enabled else "false")
        request.env.flush_all()
        return _receipt_gate_block(request.env)

    # ── Placeholder serials: GET/PUT /api/v1/settings/serial-placeholders ─
    #
    # Handoff 59 §3. The list a gated receipt refuses as "not a serial"
    # (`myservice_asset_register/models/serial_placeholders.py`). Beside the
    # receipt switch because it is consulted at a gated receipt and nowhere
    # else; with the switch off it changes nothing.

    @cadra_route("/api/v1/settings/serial-placeholders", method="GET",
                 summary="The placeholder serials a gated receipt refuses, "
                         "and how many legacy assets carry one",
                 scopes=[SCOPE_SETTINGS_READ],
                 response_schema=_PLACEHOLDER_SCHEMA)
    def get_serial_placeholders(self, **kwargs):
        return _placeholder_block(request.env)

    @cadra_route("/api/v1/settings/serial-placeholders", method="PUT",
                 summary="Replace the placeholder-serial list",
                 # `settings:write`, as every write on this controller is.
                 scopes=[SCOPE_SETTINGS_WRITE],
                 success_status=200,
                 request_schema={
                     "type": "object",
                     "required": ["exact", "patterns"],
                     "properties": {
                         "exact": {"type": "array",
                                   "items": {"type": "string"},
                                   "description": "Values compared stripped, "
                                                  "upper-cased, internal "
                                                  "spaces collapsed."},
                         "patterns": {"type": "array",
                                      "items": {"type": "string"},
                                      "description": "Regular expressions, "
                                                     "matched "
                                                     "case-insensitively "
                                                     "against the same "
                                                     "normalised value."},
                     },
                 },
                 request_example={"exact": ["4A12345FD", "N/A", "NONE"],
                                  "patterns": ["^X+$", "^0+$"]},
                 response_schema=_PLACEHOLDER_SCHEMA)
    def put_serial_placeholders(self, **kwargs):
        """The whole list, both keys — a PUT, so the screen sends what it
        shows and nothing is merged behind it. One parameter row, so the
        change is on the configuration record with who and when."""
        from odoo.addons.myservice_asset_register.models import (
            serial_placeholders)
        body = get_params()
        allowed = {"exact", "patterns"}
        rejected = [k for k in body if k not in allowed]
        if rejected:
            return refuse_unwritable(rejected, allowed)
        missing = sorted(allowed - set(body))
        if missing:
            return err(ERR_INVALID_REQUEST,
                       "Send the whole list: %s %s required."
                       % (" and ".join("`%s`" % k for k in missing),
                          "is" if len(missing) == 1 else "are"),
                       details={"missing_fields": missing})
        try:
            serial_placeholders.store(request.env, body["exact"],
                                      body["patterns"])
        except ValueError as e:
            return err(ERR_INVALID_REQUEST, str(e),
                       details={"fields": ["exact", "patterns"]})
        request.env.flush_all()
        return _placeholder_block(request.env)

    @cadra_route("/api/v1/settings/depreciation/recompute", method="POST",
                 summary="Recompute book values across the register",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 # An action, not a creation — the house default of 201 for
                 # POST-on-a-collection would be wrong here.
                 success_status=200,
                 request_schema={"type": "object", "properties": {}},
                 request_example={})
    def recompute_depreciation(self, **kwargs):
        """On-demand equivalent of the monthly cron — for after a bulk cost
        import, or when someone wants today's figures without waiting."""
        return request.env["cadra.depreciation.settings"].sudo().action_recompute()
