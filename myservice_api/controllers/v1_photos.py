"""Photos on an asset over HTTP — handoff 61 §5.

THE ROUTES
----------
* `POST /api/v1/assets/<id>/photos` — **multipart/form-data**, the first
  body of that shape inside `cadra_route`'s envelope. Parts: `file` (one
  photo, required), `source` (required: `web` or `mobile`), `caption`
  (optional). `assets:write`. 201 with the photo. Idempotent under
  `X-Idempotency-Key`, which a phone syncing over a bad connection needs.
* `GET /api/v1/assets/<id>/photos` — `assets:read`. ONE answer to "what
  pictures does this asset have": every photo (superseded ones included,
  and marked) and IAD's verification evidence, each item labelled `kind`
  `photo` or `iad_evidence`. **Evidence obeys `evidence_readable()`** (ruling
  1 on report 60): a caller without `evidence:read` gets no evidence item
  and `iad_evidence` says how many there are, in words, and nothing else.
* `GET /api/v1/assets/<id>/photos/<photo_id>` — the bytes, with the sniffed
  content type. A raw route (the body is not the envelope), behind the same
  token as everything else; a photo of ANOTHER asset is a 404, so the route
  cannot be walked.
* `POST /api/v1/assets/<id>/photos/<photo_id>/supersede` — `{"reason"}`,
  required. `assets:write`. Writes one append-only `photo_superseded` event;
  the photo is kept. A second supersede is a 409 naming who and when.

A candidate (a received unit not yet on the register) takes photos too: a
received unit's photo is evidence before it is registered. `_browse_or_404`
browses, and `browse` is not filtered by the register's candidate filter.

WHAT IS IN THE LIST, AND WHY ALL THE EVIDENCE
---------------------------------------------
Every evidence file a `verify` gate event names is listed — not only the
images. IAD's evidence is delivery notes and invoices as often as it is
photographs, and "what pictures does this asset have" answered without the
delivery note IAD photographed as a PDF would be a partial answer that
looks whole. Each carries its `mimetype`, so a screen draws an image where
it is one and a file where it is not. `width`/`height` are read from an
image's header and are null for anything else.

THE REFUSALS — every one before anything is written, and in words:

* `400 invalid_request` — not multipart; a part this route does not read
  (`rejected_fields` / `writable`, as for a JSON key); `file` sent as text;
  two `file` parts (`utils.get_multipart`).
* `400 validation_failed` — `file` or `source` missing; `source` not `web` /
  `mobile`; an empty file; bytes that begin as a JPEG or PNG and cannot be
  read as one; more than 50 megapixels.
* `413 validation_failed` — over 300 KB (AI-NFR-07), naming the cap and the
  size received.
* `415 validation_failed` — not a JPEG or a PNG, judged from the bytes, with
  `details.detected` (`application/pdf` for a PDF renamed `.jpg`).
* `409 conflict` — the asset already holds 12 photos that are not
  superseded; a photo already superseded (`details.superseded` says by whom,
  when and why).
"""
import io

from PIL import Image

from odoo import fields, http
from odoo.http import request

from odoo.addons.myservice_asset_register.models.asset_photo import (
    ALLOWED_MIMETYPES,
    MAX_PHOTO_BYTES,
    MAX_PHOTO_PIXELS,
    MAX_PHOTOS_PER_ASSET,
    UPLOAD_SOURCES,
    PhotoRefused,
    check_photo_size,
)

from .utils import (
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    _http_response,
    err,
    evidence_count_only,
    evidence_readable,
    get_multipart,
    get_params,
    refuse_unwritable,
    require_jwt,
)
from .v1 import cadra_route
from .v1_assets import _browse_or_404

#: The parts of the upload body. Anything else is refused (rule 3).
UPLOAD_FILE_FIELDS = ("file",)
UPLOAD_TEXT_FIELDS = ("source", "caption")
#: The supersede body.
SUPERSEDE_KEYS = ("reason",)

_ERRORS = (409, 413, 415)

#: Pillow's own words for what it cannot read from an evidence file's
#: header. A file that is not an image, or a damaged one, has no
#: dimensions; that is not an error in a list.
_NO_SIZE = (OSError, SyntaxError, ValueError, EOFError, IndexError,
            TypeError, Image.DecompressionBombError)

_USER_REF = {"type": "object", "nullable": True,
             "properties": {"id": {"type": "integer"},
                            "name": {"type": "string"}}}

_ITEM_SCHEMA = {
    "type": "object",
    "description": "One picture of the asset. `(kind, id)` identifies it: a "
                   "photo's id and an evidence file's id are different "
                   "sequences.",
    "properties": {
        "kind": {"type": "string", "enum": ["photo", "iad_evidence"]},
        "id": {"type": "integer",
               "description": "The photo's id, or the evidence file's "
                              "attachment id."},
        "asset_id": {"type": "integer"},
        "source": {"type": "string",
                   "enum": list(UPLOAD_SOURCES) + ["gate_evidence"],
                   "description": "`web` / `mobile`: which app a photo "
                                  "came through, as its sender declared. "
                                  "`gate_evidence`: attached by Internal "
                                  "Audit when it verified the receipt."},
        "caption": {"type": "string", "nullable": True},
        "filename": {"type": "string", "nullable": True,
                     "description": "As sent. Never used to decide what "
                                    "the file is."},
        "mimetype": {"type": "string", "nullable": True,
                     "description": "A photo's is sniffed from its bytes "
                                    "(`image/jpeg`, `image/png`). An "
                                    "evidence file's is as stored, and may "
                                    "be any type."},
        "size": {"type": "integer", "description": "Bytes."},
        "width": {"type": "integer", "nullable": True},
        "height": {"type": "integer", "nullable": True},
        "sha256": {"type": "string", "nullable": True,
                   "description": "Photos only: the SHA-256 of the bytes "
                                  "as received. The bytes route refuses to "
                                  "serve bytes that no longer match it."},
        "uploaded_by": _USER_REF,
        "uploaded_by_name": {"type": "string", "nullable": True,
                             "description": "As recorded. For evidence, "
                                            "the IAD officer who verified."},
        "uploaded_at": {"type": "string", "nullable": True,
                        "description": "UTC, `YYYY-MM-DD HH:MM:SS`. For "
                                       "evidence, when the verification "
                                       "was recorded."},
        "superseded": {
            "type": "object", "nullable": True,
            "description": "Null while the photo stands; always null for "
                           "evidence.",
            "properties": {"at": {"type": "string"},
                           "by": _USER_REF,
                           "by_name": {"type": "string", "nullable": True},
                           "reason": {"type": "string"},
                           "event_id": {"type": "integer"}}},
        "verification_event_id": {"type": "integer", "nullable": True,
                                  "description": "Evidence only: the "
                                                 "`verify` event that "
                                                 "names the file."},
        "is_test_fixture": {"type": "boolean", "nullable": True,
                            "description": "Photos only: sent by a test "
                                           "credential or a demo persona. "
                                           "Derived, never settable."},
        "url": {"type": "string",
                "description": "The bytes, with the bearer token. A photo: "
                               "`/api/v1/assets/<id>/photos/<photo_id>`. "
                               "Evidence: the evidence file route, which "
                               "needs `evidence:read`."},
    },
}

def _ref(user):
    """`{id, name}` for a user that still exists, else None."""
    if not user:
        return None
    return {"id": user.id, "name": user.name}


def _when(dt):
    return fields.Datetime.to_string(dt) if dt else None


def serialize_photo(p, superseded=None):
    """One photo, as the list and the upload publish it. `superseded` is its
    `photo_superseded` event, when it has one — read by the caller in one
    query for the whole list rather than one per photo."""
    return {
        "kind": "photo",
        "id": p.id,
        "asset_id": p.asset_id.id,
        "source": p.source,
        "caption": p.caption or None,
        "filename": p.filename or None,
        "mimetype": p.mimetype,
        "size": p.size,
        "width": p.width,
        "height": p.height,
        "sha256": p.sha256,
        "uploaded_by": _ref(p.uploaded_by_id),
        "uploaded_by_name": p.uploaded_by_name or None,
        "uploaded_at": _when(p.uploaded_at),
        "superseded": {
            "at": _when(superseded.occurred_at),
            "by": _ref(superseded.actor_id),
            "by_name": superseded.actor_name or None,
            "reason": superseded.reason or None,
            "event_id": superseded.id,
        } if superseded else None,
        "verification_event_id": None,
        "is_test_fixture": bool(p.is_test_fixture),
        "url": "/api/v1/assets/%d/photos/%d" % (p.asset_id.id, p.id),
    }


def _image_size(attachment):
    """`(width, height)` from an image's header, or `(None, None)`."""
    if not (attachment.mimetype or "").startswith("image/"):
        return None, None
    try:
        with Image.open(io.BytesIO(attachment.raw or b"")) as image:
            return image.size
    except _NO_SIZE:
        return None, None


def _evidence_item(asset, verification, f):
    """One IAD evidence file, labelled, for a caller who may read it."""
    event = verification["event"]
    width, height = _image_size(f)
    return {
        "kind": "iad_evidence",
        "id": f.id,
        "asset_id": asset.id,
        "source": "gate_evidence",
        "caption": None,
        "filename": f.name or None,
        "mimetype": f.mimetype or None,
        "size": f.file_size or 0,
        "width": width,
        "height": height,
        "sha256": None,
        "uploaded_by": _ref(event.actor_id),
        "uploaded_by_name": event.actor_name or None,
        "uploaded_at": _when(event.occurred_at),
        "superseded": None,
        "verification_event_id": event.id,
        "is_test_fixture": None,
        "url": "/api/v1/assets/%d/evidence/%d" % (asset.id, f.id),
    }


def _photo_or_404(asset, photo_id):
    """The photo IF it is this asset's. Any other id — another asset's
    photo included — is the same 404, so ids cannot be walked."""
    photo = request.env["nrs.asset.photo"].sudo().browse(int(photo_id))
    if not photo.exists() or photo.asset_id.id != asset.id:
        return None, err(
            ERR_NOT_FOUND, "Asset %s has no photo %s." % (asset.id, photo_id),
            status=404,
            details={"asset_id": asset.id, "photo_id": int(photo_id)})
    return photo, None


def _refusal(e):
    return err(e.code, str(e.args[0]) if e.args else str(e),
               status=e.status, details=e.details)


class CadraAssetPhotosV1(http.Controller):

    # ── add ───────────────────────────────────────────────────────────

    @cadra_route("/api/v1/assets/<int:id>/photos", method="POST",
                 summary="Add a photo to an asset (multipart: `file`, "
                         "`source`, `caption`)",
                 scopes=[SCOPE_ASSETS_WRITE], idempotent=True,
                 success_status=201, error_statuses=_ERRORS,
                 request_schema={
                     "type": "object",
                     "x-cadra-content-type": "multipart/form-data",
                     "description":
                         "**multipart/form-data**, not JSON. One photo per "
                         "request. A part not listed here is refused 400 "
                         "and nothing is written. JPEG or PNG only, judged "
                         "from the bytes; at most %d bytes (300 KB, "
                         "AI-NFR-07); at most %d photos per asset that are "
                         "not superseded; at most %d megapixels."
                         % (MAX_PHOTO_BYTES, MAX_PHOTOS_PER_ASSET,
                            MAX_PHOTO_PIXELS // 1_000_000),
                     "required": ["file", "source"],
                     "properties": {
                         "file": {"type": "string", "format": "binary",
                                  "description": "The photo. Its filename "
                                                 "and part content type are "
                                                 "recorded and never "
                                                 "trusted."},
                         "source": {"type": "string",
                                    "enum": list(UPLOAD_SOURCES),
                                    "description": "Which app took it."},
                         "caption": {"type": "string",
                                     "description": "Optional."},
                     }},
                 response_schema=_ITEM_SCHEMA)
    def asset_photo_upload(self, id, **kwargs):
        asset, error = _browse_or_404(id)
        if error:
            return error
        values, uploads, error = get_multipart(
            file_fields=UPLOAD_FILE_FIELDS, text_fields=UPLOAD_TEXT_FIELDS,
            required=("file", "source"))
        if error:
            return error
        upload = uploads["file"]
        try:
            # Measured, not read: an oversized file is refused in words
            # without its bytes ever being loaded.
            check_photo_size(upload.size)
            photo = request.env["nrs.asset.photo"]._upload(
                asset, upload.read(), source=values.get("source"),
                caption=values.get("caption"), filename=upload.filename,
                actor=request.env.user)
        except PhotoRefused as e:
            details = dict(e.details)
            details.setdefault("filename", upload.filename or None)
            details.setdefault("declared_type", upload.declared_type)
            e.details = details
            return _refusal(e)
        return serialize_photo(photo)

    # ── list ──────────────────────────────────────────────────────────

    @cadra_route("/api/v1/assets/<int:id>/photos", method="GET",
                 summary="What pictures this asset has: its photos and "
                         "IAD's evidence, each labelled",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "type": "object",
                     "properties": {
                         "asset_id": {"type": "integer"},
                         "items": {"type": "array", "items": _ITEM_SCHEMA,
                                   "description": "Newest first. Evidence "
                                                  "items appear only for a "
                                                  "caller holding "
                                                  "`evidence:read`."},
                         "photos": {
                             "type": "object",
                             "properties": {
                                 "count": {"type": "integer"},
                                 "standing": {"type": "integer",
                                              "description": "Not "
                                                             "superseded — "
                                                             "what the cap "
                                                             "counts."},
                                 "superseded": {"type": "integer"},
                                 "max_standing": {"type": "integer"},
                                 "max_bytes": {"type": "integer"},
                                 "allowed_types": {
                                     "type": "array",
                                     "items": {"type": "string"}}}},
                         "iad_evidence": {
                             "type": "object",
                             "description": "`{readable: true, count}` for "
                                            "a reader; for anybody else "
                                            "`{readable: false, count, "
                                            "summary: \"IAD evidence: N "
                                            "items\", requires_scope}` and "
                                            "no evidence item in `items`.",
                             "properties": {
                                 "readable": {"type": "boolean"},
                                 "count": {"type": "integer"},
                                 "summary": {"type": "string"},
                                 "requires_scope": {"type": "string"}}},
                     }})
    def asset_photo_list(self, id, **kwargs):
        asset, error = _browse_or_404(id)
        if error:
            return error
        photos = request.env["nrs.asset.photo"].sudo().search(
            [("asset_id", "=", asset.id)])
        superseded = photos._supersede_events()
        items = [serialize_photo(p, superseded.get(p.id)) for p in photos]

        verifications = asset._gate_evidence()
        count = sum(len(v["files"]) for v in verifications)
        if evidence_readable():
            items += [_evidence_item(asset, v, f)
                      for v in verifications for f in v["files"]]
            iad_evidence = {"readable": True, "count": count}
        else:
            iad_evidence = evidence_count_only(count)
        # One clock for both kinds, newest first; a photo before evidence
        # recorded in the same second, then the higher id.
        items.sort(key=lambda i: (i["uploaded_at"] or "",
                                  i["kind"] == "photo", i["id"]),
                   reverse=True)
        return {
            "asset_id": asset.id,
            "items": items,
            "photos": {
                "count": len(photos),
                "standing": len(photos) - len(superseded),
                "superseded": len(superseded),
                "max_standing": MAX_PHOTOS_PER_ASSET,
                "max_bytes": MAX_PHOTO_BYTES,
                "allowed_types": list(ALLOWED_MIMETYPES),
            },
            "iad_evidence": iad_evidence,
        }

    # ── supersede ─────────────────────────────────────────────────────

    @cadra_route("/api/v1/assets/<int:id>/photos/<int:photo_id>/supersede",
                 method="POST",
                 summary="Say a photo no longer stands, and why — it is "
                         "kept, marked, and stops counting",
                 scopes=[SCOPE_ASSETS_WRITE], idempotent=True,
                 error_statuses=(409,),
                 request_schema={
                     "type": "object", "required": ["reason"],
                     "properties": {"reason": {
                         "type": "string",
                         "description": "Required, in words — recorded on "
                                        "the append-only event."}}},
                 request_example={"reason": "Blurred; retaken with the tag "
                                            "in frame."},
                 response_schema=_ITEM_SCHEMA)
    def asset_photo_supersede(self, id, photo_id, **kwargs):
        asset, error = _browse_or_404(id)
        if error:
            return error
        photo, error = _photo_or_404(asset, photo_id)
        if error:
            return error
        body = get_params() or {}
        stray = [k for k in body if k not in SUPERSEDE_KEYS]
        if stray:
            return refuse_unwritable(stray, SUPERSEDE_KEYS)
        reason = body.get("reason")
        if reason is not None and not isinstance(reason, str):
            return err(ERR_VALIDATION_FAILED, "`reason` must be text.",
                       status=400, details={"field": "reason"})
        try:
            event = photo.action_supersede(reason, actor=request.env.user)
        except PhotoRefused as e:
            return _refusal(e)
        return serialize_photo(photo, event)

    # ── the bytes ─────────────────────────────────────────────────────

    @http.route("/api/v1/assets/<int:id>/photos/<int:photo_id>",
                type="http", auth="none", methods=["GET"], csrf=False)
    def asset_photo_file(self, id, photo_id, **kwargs):
        """The photo's bytes — the file, not the envelope. Only a photo OF
        THIS ASSET; any other id is a 404."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_ASSETS_READ])
        if envelope is not None:
            return _http_response(envelope)
        asset = request.env["nrs.asset"].sudo().browse(id).exists()
        if not asset:
            return _http_response(err(
                ERR_NOT_FOUND, "Asset %s not found" % id, status=404))
        photo, error = _photo_or_404(asset, photo_id)
        if error:
            return _http_response(error)
        data, intact = photo._bytes()
        if not intact:
            # Altered underneath the row — only an administrator can write
            # an attachment. Not served as the photo: it is not the photo.
            return _http_response(err(
                ERR_CONFLICT,
                "The stored bytes of photo %d no longer match the SHA-256 "
                "recorded when it was uploaded, so they are not served as "
                "the photo. Tell an administrator." % photo.id,
                status=409,
                details={"reason": "integrity_mismatch",
                         "photo_id": photo.id,
                         "recorded_sha256": photo.sha256}))
        return request.make_response(data, headers=[
            ("Content-Type", photo.mimetype),
            ("Content-Length", str(len(data))),
            ("Content-Disposition", http.content_disposition(
                photo.filename or "photo-%d" % photo.id,
                disposition_type="inline")),
            ("X-Content-Type-Options", "nosniff"),
            # The bytes of a photo never change — it can be superseded,
            # never replaced — so a viewer may keep them.
            ("Cache-Control", "private, max-age=31536000, immutable"),
            ("ETag", '"%s"' % photo.sha256),
        ])
