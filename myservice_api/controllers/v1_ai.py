"""*Identify from photo* over HTTP — handoff 64 §1–§2, ruling R11.

THE ROUTES
----------
* `POST /api/v1/ai/identify` — **multipart/form-data**, `assets:write`,
  behind the tenant's switch `cadra.ai.identify` (off by default on every
  tenant). One of two parts names the photo:

  - `photo_id` — a photo already on an asset (`POST /assets/<id>/photos`);
  - `file` (+ `source`: `web`/`mobile`) — a photo for an asset that does
    not exist yet, checked by the photo's own rules and HELD
    (`nrs.ai.pending.photo`) until a save claims it, or for 24 hours.

  201 with the suggestion: the class (with confidence and up to two
  alternatives), the attributes in SAP's style, the condition, the text
  read off the item, the SAP matcher's candidates — the records for a
  caller holding `sap_mirror:read`, the count for anybody else — and
  `suggestion_id`, which the save names. Idempotent under
  `X-Idempotency-Key`: a phone re-sending after a dropped connection gets
  the same answer and the provider is not asked twice.

* `GET /api/v1/settings/ai-identify` — `settings:read`. The switch, the
  provider and model, the timeout, the daily cap with TODAY's count, and
  whether a key is placed (`key_placed`) — never the key.
* `PATCH /api/v1/settings/ai-identify` — `settings:write`. Everything above
  except the key, which is the owner's (`scripts/set_ai_key.sh`).

THE REFUSALS, every one in words and before the provider is asked:

* `403 forbidden`, `reason: switched_off` — the tenant's switch is off;
* `429 rate_limited`, `reason: daily_cap` — *"today's 500 identifications
  are used; fill the details by hand"*;
* `503 server_misconfigured` — no key placed, or the test stand-in on a
  database not marked `test`;
* the photo's own: `413` over 300 KB, `415` not a JPEG or PNG, `400`
  empty or unreadable;
* `400 invalid_request` — neither or both of `photo_id` / `file`.

AND AFTER IT IS ASKED — each still a recorded call (`nrs.ai.suggestion`,
counted against the cap):

* `503 internal_error`, `reason: provider_timeout` / `provider_error` /
  `provider_declined` — *"the photo could not be identified just now; fill
  the details by hand"*;
* `502 internal_error`, `reason: answer_discarded` — the answer failed the
  schema. Discarded, counted, and never shown.

THE CAP is counted, not reserved: the count is read before the call and the
row written after it, so calls made at the same moment as the 500th can
each pass and the day can close a few over — at most the number in flight
at that instant. Holding a lock across a 20-second provider call would
queue every person on the tenant behind each other; the cap is a cost
guard, and a handful over is what it costs to avoid that.
"""
import logging

from odoo import fields, http
from odoo.http import request

from odoo.addons.myservice_asset_register.models.ai_suggestion import (
    PENDING_PHOTO_HOURS,
    SuggestionRefused,
    lagos_today,
)
from odoo.addons.myservice_asset_register.models.asset_photo import (
    MAX_PHOTO_BYTES,
    UPLOAD_SOURCES,
    PhotoRefused,
    check_photo_size,
    sniff_photo,
)
from odoo.addons.myservice_nrs_base.database_class import TEST, database_class

from . import ai_provider as ai
from .utils import (
    ERR_FORBIDDEN,
    ERR_INTERNAL,
    ERR_INVALID_REQUEST,
    ERR_MISCONFIGURED,
    ERR_NOT_FOUND,
    ERR_RATE_LIMITED,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_WRITE,
    SCOPE_SAP_MIRROR_READ,
    SCOPE_SETTINGS_READ,
    SCOPE_SETTINGS_WRITE,
    caller_holds,
    err,
    get_multipart,
    get_params,
    refuse_unwritable,
)
from .v1 import cadra_route

_logger = logging.getLogger(__name__)

IDENTIFY_FILE_FIELDS = ("file",)
IDENTIFY_TEXT_FIELDS = ("photo_id", "source")

#: What the settings PATCH accepts. NOT the key: it is the owner's, placed
#: from a shell, and no route reads it back.
SETTINGS_KEYS = ("enabled", "provider", "model", "timeout_seconds",
                 "daily_cap", "effort")

NOT_NOW = ("The photo could not be identified just now; fill the details "
           "by hand.")


def notice(provider):
    """The one sentence both screens say (handoff 64 §3)."""
    return ("Photograph the item, not people. The photo is sent to %s to "
            "read it." % ai.PROVIDER_LABELS.get(provider, provider))


# ── the tenant's settings ────────────────────────────────────────────

def _params(env, names):
    """`{name: value}` read with raw SQL — not through `get_param`'s
    ormcache, so a value an owner sets from a shell is the value the next
    request reads, on every worker, without a restart. Flushed first: a
    value this request has just written through `set_param` is still in the
    ORM's buffer, and the settings PATCH answers with what it wrote (found
    by the live-check dry run: it answered with the values from BEFORE its
    own write)."""
    env["ir.config_parameter"].flush_model()
    env.cr.execute("SELECT key, value FROM ir_config_parameter "
                   "WHERE key = ANY(%s)", (list(names),))
    return dict(env.cr.fetchall())


def _int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def ai_settings(env):
    """The tenant's AI settings, every default applied. `key` is the secret
    and is returned ONLY to the caller in this module that hands it to the
    provider; nothing serialises it."""
    raw = _params(env, (ai.PARAM_ENABLED, ai.PARAM_PROVIDER, ai.PARAM_MODEL,
                        ai.PARAM_TIMEOUT, ai.PARAM_DAILY_CAP,
                        ai.PARAM_EFFORT, ai.PARAM_KEY))
    provider = (raw.get(ai.PARAM_PROVIDER) or "").strip() or \
        ai.DEFAULT_PROVIDER
    effort = (raw.get(ai.PARAM_EFFORT) or "").strip() or ai.DEFAULT_EFFORT
    return {
        "enabled": (raw.get(ai.PARAM_ENABLED) or "").strip().lower()
        in ("1", "true", "on", "yes"),
        "provider": provider,
        "model": (raw.get(ai.PARAM_MODEL) or "").strip() or ai.DEFAULT_MODEL,
        "timeout_seconds": _int(raw.get(ai.PARAM_TIMEOUT),
                                ai.DEFAULT_TIMEOUT),
        "daily_cap": _int(raw.get(ai.PARAM_DAILY_CAP), ai.DEFAULT_DAILY_CAP),
        "effort": effort if effort in ai.EFFORTS else ai.DEFAULT_EFFORT,
        "key": (raw.get(ai.PARAM_KEY) or "").strip(),
    }


def ai_switch_block(env):
    """What every screen may know: on or off, and who the photo goes to.
    Published on `GET /api/v1/settings` (`assets:read`)."""
    s = ai_settings(env)
    return {"enabled": s["enabled"], "provider": s["provider"],
            "provider_label": ai.PROVIDER_LABELS.get(s["provider"],
                                                     s["provider"]),
            "notice": notice(s["provider"])}


def _settings_block(env):
    s = ai_settings(env)
    calls = env["nrs.ai.suggestion"].sudo()._calls_today()
    return {
        "enabled": s["enabled"],
        "provider": s["provider"],
        "provider_label": ai.PROVIDER_LABELS.get(s["provider"],
                                                 s["provider"]),
        "providers": list(ai.PROVIDERS),
        "model": s["model"],
        "timeout_seconds": s["timeout_seconds"],
        "daily_cap": s["daily_cap"],
        "effort": s["effort"],
        "efforts": list(ai.EFFORTS),
        "key_placed": bool(s["key"]),
        "key_command": "scripts/set_ai_key.sh %s" % env.cr.dbname,
        "database_class": database_class(env),
        "today": {"day": lagos_today().isoformat(), "calls": calls,
                  "remaining": max(0, s["daily_cap"] - calls)},
        "notice": notice(s["provider"]),
        "prompt_version": ai.PROMPT_VERSION,
    }


def _provider_misconfigured(env, s):
    """A sentence when the configured provider cannot be used here, else
    None. The fake is a TEST stand-in and answers only on a database marked
    `test`; the real provider needs the owner's key."""
    if s["provider"] not in ai.PROVIDERS:
        return ("This tenant's provider is set to `%s`, which Cadra does "
                "not have. Choose one of: %s." % (
                    s["provider"], ", ".join(ai.PROVIDERS)))
    if s["provider"] == ai.PROVIDER_FAKE and database_class(env) != TEST:
        return ("This tenant is set to the test stand-in provider, which "
                "answers only on a database marked `test`. Choose "
                "`anthropic` in Settings.")
    if s["provider"] == ai.PROVIDER_ANTHROPIC and not s["key"]:
        return ("No provider key is placed on this tenant. The owner "
                "places it with `scripts/set_ai_key.sh %s`."
                % env.cr.dbname)
    return None


# ── the suggestion as published ──────────────────────────────────────

def _sap_candidates(env, clean, categories):
    """The matcher (handoff 63), fed with what the photo read: the old tag
    if one was read, a serial, the class's SAP class and the description.
    Up to five; the records only for a holder of `sap_mirror:read`."""
    reads = clean["text_read"]
    tag = next((r["text"] for r in reads
                if r["looks_like"] == "firs_tag_like"), None)
    serial = next((r["text"] for r in reads
                   if r["looks_like"] == "serial_like"), None)
    cat = categories.get(clean["category"]["id"]) or {}
    description = clean["attributes"].get("name")
    if not (tag or serial or description or cat.get("sap_asset_class")):
        return {"count": 0, "items": [], "basis": None,
                "query": {}, "note": "Nothing was read to match on."}
    answer = env["nrs.sap.asset"].sudo()._match(
        old_tag=tag, description=description,
        asset_class=cat.get("sap_asset_class"), serial=serial, limit=5)
    results = answer.get("results") or []
    query = {"old_tag": tag, "serial": serial,
             "class": cat.get("sap_asset_class"), "description": description}
    if not caller_holds(SCOPE_SAP_MIRROR_READ):
        return {"count": len(results), "items": None,
                "basis": answer.get("basis"), "query": query,
                "note": "%d SAP record(s) may be this item. Reading them "
                        "needs `sap_mirror:read`." % len(results)}
    recs = {r.id: r for r in env["nrs.sap.asset"].sudo().browse(
        [x["id"] for x in results])}
    items = []
    for x in results:
        rec = recs.get(x["id"])
        if not rec:
            continue
        items.append({
            "id": rec.id, "rank": x.get("rank"),
            "reason_code": x.get("reason_code"), "reason": x.get("reason"),
            "asset_number": rec.asset_number,
            "sub_number": rec.sub_number or None,
            "class": rec.asset_class or None,
            "description": rec.description or None,
            "old_tag": rec.old_tag or None,
            "office_code": rec.office_code or None,
        })
    return {"count": len(items), "items": items,
            "basis": answer.get("basis"), "query": query,
            "note": None if items else "No SAP record matched."}


def _published(clean, notes, categories, sap):
    def named(item):
        c = categories.get(item["id"]) or {}
        return {"id": item["id"], "name": c.get("name"),
                "identification_mode": c.get("identification_mode"),
                "sap_asset_class": c.get("sap_asset_class"),
                "confidence": item["confidence"]}
    category = named(clean["category"])
    category["alternatives"] = [named(a) for a in clean["alternatives"]]
    condition = dict(clean["condition"])
    return {
        "category": category,
        "attributes": clean["attributes"],
        "condition": condition,
        "text_read": clean["text_read"],
        "sap_candidates": sap,
        "notes": notes,
    }


def serialize_suggestion(rec, data, settings):
    """A suggestion row and its published body, as the identify route
    answers it."""
    photo = rec.photo_id
    pending = rec.pending_photo_id
    if photo:
        photo_ref = {"kind": "asset_photo", "id": photo.id,
                     "asset_id": photo.asset_id.id}
    elif pending:
        photo_ref = {"kind": "pending", "id": pending.id,
                     "expires_at": fields.Datetime.to_string(
                         pending.expires_at)}
    else:
        photo_ref = {"kind": "expired", "id": None}
    out = {
        "suggestion_id": rec.id,
        "prompt_version": rec.prompt_version,
        "provider": rec.provider,
        "provider_label": ai.PROVIDER_LABELS.get(rec.provider, rec.provider),
        "model": rec.model or None,
        "latency_ms": rec.latency_ms,
        "photo": photo_ref,
        "usage": {"input_tokens": rec.input_tokens,
                  "output_tokens": rec.output_tokens,
                  "cache_read_tokens": rec.cache_read_tokens,
                  "cache_write_tokens": rec.cache_write_tokens,
                  "cost_usd": rec.cost_usd if rec.cost_usd else None},
        "notice": notice(rec.provider),
        "is_test_fixture": bool(rec.is_test_fixture),
    }
    out.update(data)
    return out


def _photo_refusal(e, upload=None):
    details = dict(e.details or {})
    if upload is not None:
        details.setdefault("filename", upload.filename or None)
        details.setdefault("declared_type", upload.declared_type)
    return err(e.code, str(e.args[0]) if e.args else str(e),
               status=e.status, details=details)


_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestion_id": {"type": "integer"},
        "prompt_version": {"type": "string"},
        "provider": {"type": "string", "enum": list(ai.PROVIDERS)},
        "provider_label": {"type": "string"},
        "model": {"type": "string", "nullable": True},
        "latency_ms": {"type": "integer"},
        "photo": {"type": "object", "properties": {
            "kind": {"type": "string",
                     "enum": ["asset_photo", "pending", "expired"]},
            "id": {"type": "integer", "nullable": True},
            "asset_id": {"type": "integer"},
            "expires_at": {"type": "string"}}},
        "category": {"type": "object", "description":
                     "The tenant's class, with `confidence` (0–1) and up "
                     "to two `alternatives` of the same shape."},
        "attributes": {"type": "object", "properties": {
            k: {"type": "string", "nullable": True} for k in ai.ATTRIBUTES},
            "description": "`make` and `model_name` only if legible; "
                           "`dimensions` only if a label states them — a "
                           "photo has no scale."},
        "condition": {"type": "object", "properties": {
            "value": {"type": "string", "enum": list(ai.CONDITIONS)},
            "note": {"type": "string", "nullable": True}}},
        "text_read": {"type": "array", "items": {"type": "object",
                      "properties": {
                          "text": {"type": "string"},
                          "looks_like": {"type": "string",
                                         "enum": list(ai.TEXT_KINDS)}}}},
        "sap_candidates": {"type": "object", "description":
                           "`count`, and `items` (up to five, each with its "
                           "ranking `reason`) for a caller holding "
                           "`sap_mirror:read` — `null` for anybody else."},
        "notes": {"type": "array", "items": {"type": "string"}},
        "usage": {"type": "object"},
        "notice": {"type": "string"},
        "is_test_fixture": {"type": "boolean"},
    },
}

_SETTINGS_SCHEMA = {"type": "object", "properties": {
    "enabled": {"type": "boolean"},
    "provider": {"type": "string", "enum": list(ai.PROVIDERS)},
    "model": {"type": "string"},
    "timeout_seconds": {"type": "integer"},
    "daily_cap": {"type": "integer"},
    "effort": {"type": "string", "enum": list(ai.EFFORTS)},
    "key_placed": {"type": "boolean",
                   "description": "Whether the owner has placed a key. "
                                  "The key itself is never returned."},
    "today": {"type": "object"},
}}


class CadraAiV1(http.Controller):

    @cadra_route("/api/v1/ai/identify", method="POST",
                 summary="Identify the item in a photo (multipart: "
                         "`photo_id`, or `file` + `source`)",
                 scopes=[SCOPE_ASSETS_WRITE], idempotent=True,
                 success_status=201,
                 error_statuses=(403, 413, 415, 429, 502, 503),
                 request_schema={
                     "type": "object",
                     "x-cadra-content-type": "multipart/form-data",
                     "description":
                         "**multipart/form-data**. Exactly one of "
                         "`photo_id` (a photo already on an asset) or "
                         "`file` (a photo for an asset not yet saved; held "
                         "%d hours for a save to claim it). JPEG or PNG, at "
                         "most %d bytes. A part not listed here is refused "
                         "400. The suggestion writes NOTHING on any asset: "
                         "the save that uses it names `ai_suggestion`."
                         % (PENDING_PHOTO_HOURS, MAX_PHOTO_BYTES),
                     "properties": {
                         "photo_id": {"type": "integer"},
                         "file": {"type": "string", "format": "binary"},
                         "source": {"type": "string",
                                    "enum": list(UPLOAD_SOURCES),
                                    "description": "Which app took it. "
                                                   "Required with `file`."},
                     }},
                 response_schema=_SUGGESTION_SCHEMA)
    def ai_identify(self, **kwargs):
        env = request.env
        s = ai_settings(env)
        if not s["enabled"]:
            return err(ERR_FORBIDDEN,
                       "Identifying from a photo is switched off on this "
                       "tenant. Fill the details by hand.",
                       status=403, details={"reason": "switched_off"})
        values, uploads, error = get_multipart(
            file_fields=IDENTIFY_FILE_FIELDS,
            text_fields=IDENTIFY_TEXT_FIELDS)
        if error:
            return error
        upload = uploads.get("file")
        raw_id = values.get("photo_id")
        if bool(upload) == bool(raw_id):
            return err(ERR_INVALID_REQUEST,
                       "Send exactly one of `photo_id` (a photo already on "
                       "an asset) or `file` (a new photo). Nothing was "
                       "written.",
                       details={"reason": "photo_part",
                                "received": sorted(
                                    ([] if not upload else ["file"])
                                    + ([] if not raw_id else ["photo_id"]))})
        photo = None
        data = None
        if raw_id:
            if values.get("source"):
                return refuse_unwritable(["source"], ["photo_id"],
                                         hint="`source` goes with `file`; a "
                                              "stored photo already says "
                                              "which app took it.")
            try:
                pid = int(raw_id)
            except ValueError:
                return err(ERR_VALIDATION_FAILED,
                           "`photo_id` must be a photo's id (an integer).",
                           details={"field": "photo_id"})
            photo = env["nrs.asset.photo"].sudo().browse(pid).exists()
            if not photo:
                return err(ERR_NOT_FOUND, "No photo %d." % pid, status=404)
            data, intact = photo._bytes()
            if not intact:
                return err(ERR_VALIDATION_FAILED,
                           "Photo %d's stored bytes no longer match what was "
                           "uploaded; it cannot be identified." % pid,
                           status=409, details={"reason":
                                                "integrity_mismatch"})
            mimetype, width, height = photo.mimetype, photo.width, photo.height
            hint = photo.filename or ""
        else:
            if not values.get("source"):
                return err(ERR_VALIDATION_FAILED,
                           "`source` is required with `file`: web or "
                           "mobile. Nothing was written.",
                           details={"missing": ["source"]})
            try:
                check_photo_size(upload.size)
                data = upload.read()
                mimetype, width, height = sniff_photo(data)
            except PhotoRefused as e:
                return _photo_refusal(e, upload)
            hint = upload.filename or ""

        why = _provider_misconfigured(env, s)
        if why:
            return err(ERR_MISCONFIGURED, why, status=503,
                       details={"reason": "provider_not_ready",
                                "provider": s["provider"]})
        Suggestion = env["nrs.ai.suggestion"].sudo()
        calls = Suggestion._calls_today()
        if calls >= s["daily_cap"]:
            return err(ERR_RATE_LIMITED,
                       "Today's %d identifications are used; fill the "
                       "details by hand." % s["daily_cap"],
                       status=429,
                       details={"reason": "daily_cap",
                                "daily_cap": s["daily_cap"], "calls": calls,
                                "day": lagos_today().isoformat()})

        # Every refusal BEFORE the photo is held: `err()` rolls nothing back.
        rows, examples = ai.catalogue(env)
        categories = {r["id"]: r for r in rows}
        if not categories:
            return err(ERR_MISCONFIGURED,
                       "This register has no asset classes to choose from.",
                       status=503, details={"reason": "no_classes"})

        pending = None
        if upload:
            try:
                pending = env["nrs.ai.pending.photo"]._hold(
                    data, source=values["source"], filename=upload.filename,
                    actor=env.user)
            except PhotoRefused as e:
                return _photo_refusal(e, upload)

        req = ai.IdentifyRequest(
            image=ai.strip_metadata(data, mimetype), mimetype=mimetype, width=width, height=height,
            system=ai.build_system(rows, examples),
            schema=ai.answer_schema(list(categories)),
            instruction=ai.INSTRUCTION, model=s["model"],
            timeout=s["timeout_seconds"], effort=s["effort"], hint=hint,
            category_ids=list(categories),
            category_names={k: v["name"] for k, v in categories.items()})
        provider = ai.provider_for(s["provider"], s["key"])

        def record(result, **kw):
            return Suggestion._record(
                photo=photo, pending=pending, provider=s["provider"],
                prompt_version=ai.PROMPT_VERSION, result=result,
                actor=env.user, **kw)

        try:
            answer = provider.identify(req)
        except ai.ProviderTimeout:
            rec = record("timeout", model=s["model"],
                         failure="No answer within %d s."
                         % s["timeout_seconds"],
                         latency_ms=s["timeout_seconds"] * 1000)
            return err(ERR_INTERNAL, NOT_NOW, status=503,
                       details={"reason": "provider_timeout",
                                "suggestion_id": rec.id,
                                "timeout_seconds": s["timeout_seconds"]})
        except ai.ProviderRefused:
            rec = record("refused", model=s["model"],
                         failure="The provider declined to describe this "
                                 "photo.")
            return err(ERR_INTERNAL, NOT_NOW, status=503,
                       details={"reason": "provider_declined",
                                "suggestion_id": rec.id})
        except ai.ProviderError as e:
            rec = record("error", model=s["model"], failure=str(e)[:250])
            _logger.warning("AI identify: provider error on %s (%s)",
                            env.cr.dbname, e)
            return err(ERR_INTERNAL, NOT_NOW, status=503,
                       details={"reason": "provider_error",
                                "suggestion_id": rec.id})

        usage = dict(answer.usage)
        usage["cost_usd"] = ai.cost_usd(answer.model, usage)
        try:
            clean, notes = ai.validate_answer(answer.data, list(categories))
        except ai.InvalidAnswer as e:
            rec = record("invalid", model=answer.model,
                         failure=("Discarded: %s." % e)[:250],
                         latency_ms=answer.latency_ms, usage=usage)
            return err(ERR_INTERNAL, NOT_NOW, status=502,
                       details={"reason": "answer_discarded",
                                "suggestion_id": rec.id})
        sap = _sap_candidates(env, clean, categories)
        body = _published(clean, notes, categories, sap)
        rec = record("ok", model=answer.model, suggestion=body,
                     latency_ms=answer.latency_ms, usage=usage)
        return serialize_suggestion(rec, body, s)

    # ── settings ──────────────────────────────────────────────────────

    @cadra_route("/api/v1/settings/ai-identify", method="GET",
                 summary="Identify from photo: the tenant's settings and "
                         "today's count",
                 scopes=[SCOPE_SETTINGS_READ],
                 response_schema=_SETTINGS_SCHEMA)
    def ai_settings_get(self, **kwargs):
        return _settings_block(request.env)

    @cadra_route("/api/v1/settings/ai-identify", method="PATCH",
                 summary="Identify from photo: switch, provider, model, "
                         "timeout, daily cap (never the key)",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={"type": "object", "properties": {
                     "enabled": {"type": "boolean"},
                     "provider": {"type": "string",
                                  "enum": list(ai.PROVIDERS)},
                     "model": {"type": "string"},
                     "timeout_seconds": {"type": "integer",
                                         "minimum": 5, "maximum": 60},
                     "daily_cap": {"type": "integer", "minimum": 1,
                                   "maximum": 100000},
                     "effort": {"type": "string", "enum": list(ai.EFFORTS)},
                 }},
                 response_schema=_SETTINGS_SCHEMA)
    def ai_settings_patch(self, **kwargs):
        env = request.env
        body = get_params()
        if not isinstance(body, dict) or not body:
            return err(ERR_INVALID_REQUEST,
                       "Send at least one of: %s." % ", ".join(SETTINGS_KEYS))
        rejected = [k for k in body if k not in SETTINGS_KEYS]
        if rejected:
            hint = ("The key is the owner's and is never set over the API: "
                    "`scripts/set_ai_key.sh %s`." % env.cr.dbname) \
                if any("key" in k for k in rejected) else None
            return refuse_unwritable(rejected, SETTINGS_KEYS, hint=hint)
        current = ai_settings(env)
        writes = {}
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                return err(ERR_VALIDATION_FAILED,
                           "`enabled` must be true or false.",
                           details={"field": "enabled"})
            writes[ai.PARAM_ENABLED] = "true" if body["enabled"] else "false"
        if "provider" in body:
            if body["provider"] not in ai.PROVIDERS:
                return err(ERR_VALIDATION_FAILED,
                           "`provider` must be one of: %s."
                           % ", ".join(ai.PROVIDERS),
                           details={"field": "provider",
                                    "allowed_values": list(ai.PROVIDERS)})
            if body["provider"] == ai.PROVIDER_FAKE \
                    and database_class(env) != TEST:
                return err(ERR_VALIDATION_FAILED,
                           "The test stand-in provider may be chosen only on "
                           "a database marked `test`; this one is %s."
                           % (database_class(env) or "not marked"),
                           details={"field": "provider",
                                    "reason": "not_a_test_database"})
            writes[ai.PARAM_PROVIDER] = body["provider"]
        if "model" in body:
            model = body["model"]
            if not isinstance(model, str) or not model.strip() \
                    or len(model) > 80 or any(c.isspace() for c in
                                              model.strip()):
                return err(ERR_VALIDATION_FAILED,
                           "`model` must be the provider's model id — one "
                           "word, at most 80 characters.",
                           details={"field": "model"})
            writes[ai.PARAM_MODEL] = model.strip()
        for key, param, lo, hi in (
                ("timeout_seconds", ai.PARAM_TIMEOUT, 5, 60),
                ("daily_cap", ai.PARAM_DAILY_CAP, 1, 100000)):
            if key in body:
                v = body[key]
                if isinstance(v, bool) or not isinstance(v, int) \
                        or not lo <= v <= hi:
                    return err(ERR_VALIDATION_FAILED,
                               "`%s` must be a whole number from %d to %d."
                               % (key, lo, hi),
                               details={"field": key, "minimum": lo,
                                        "maximum": hi})
                writes[param] = str(v)
        if "effort" in body:
            if body["effort"] not in ai.EFFORTS:
                return err(ERR_VALIDATION_FAILED,
                           "`effort` must be one of: %s."
                           % ", ".join(ai.EFFORTS),
                           details={"field": "effort",
                                    "allowed_values": list(ai.EFFORTS)})
            writes[ai.PARAM_EFFORT] = body["effort"]
        # Turning it on with nothing to answer would only move the refusal
        # to the first person who presses the button.
        after = dict(current)
        if ai.PARAM_PROVIDER in writes:
            after["provider"] = writes[ai.PARAM_PROVIDER]
        turning_on = writes.get(ai.PARAM_ENABLED) == "true" or (
            current["enabled"] and writes.get(ai.PARAM_ENABLED) != "false")
        if turning_on:
            why = _provider_misconfigured(env, after)
            if why:
                return err(ERR_VALIDATION_FAILED,
                           "It cannot be switched on yet. " + why,
                           details={"reason": "provider_not_ready"})
        icp = env["ir.config_parameter"].sudo()
        for param, value in writes.items():
            icp.set_param(param, value)
        return _settings_block(env)
