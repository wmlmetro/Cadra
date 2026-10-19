"""What SAP holds, in Cadra — the SAP mirror over HTTP (handoff 63).

The mirror is `nrs.sap.asset` (`myservice_asset_register/models/sap_mirror.py`):
SAP's fixed-asset master for NRS as a READ-ONLY reference table. It is not
the register — nothing here is an asset, and no asset route reads it.

THE ROUTES
----------
* `POST /api/v1/sap-assets/imports` — **multipart/form-data**, one part
  `file`: the `.XLSX` as SAP produced it. `settings:write` **held by a
  System Administrator** (the token also carries `admin`): an Asset Manager
  holds `settings:write` and is refused, in words. The header row is read
  here and a missing column refuses the file there and then, naming it;
  everything else is read by a background job (`202`, the run). One run at
  a time (`409` while one is queued or running). The file is NOT kept once
  the run ends.
* `GET /api/v1/sap-assets/imports`, `GET /api/v1/sap-assets/imports/<id>` —
  each run: who, when, the file's name, rows read, created, updated,
  unchanged, refused (with the reasons counted, never the rows), how many
  were marked not in the latest export, duration, CPU and peak memory.
* `GET /api/v1/sap-assets` — a page of the mirror, by `office`, `class`,
  `updated_since`, `active` and `in_latest_export`. The offline phone's
  slice: paged and synced like `GET /assets` (handoff 61 §6).
* `GET /api/v1/sap-assets/match` — up to five ACTIVE, UNLINKED records for
  an item somebody found, each saying why it ranked (`SapMatcher`).
* `GET /api/v1/sap-assets/<id>` — one record, with the Cadra asset linked to
  it; `GET /api/v1/assets/<id>/sap-record` — the other way round.
* `GET /api/v1/reports/sap-coverage` — how much of SAP's register Cadra
  holds, by class and by office. Every count says what it counts.

Every read is `sap_mirror:read`: the Asset Controller, the Register Maker and
Checker, the Auditor, the System Administrator — not Asset Users, not
Vendra's credential.
"""
import base64
import io
import json
import zipfile
import zlib

from lxml import etree

from odoo import fields, http
from odoo.http import request

from odoo.addons.myservice_asset_register.models import sap_export_reader
from odoo.addons.myservice_asset_register.models.sap_mirror import (
    ABSENT_GUARD_SHARE,
    MAX_SHEET_BYTES,
    OFFICE_SOURCES,
    SERIAL_KINDS,
)

from .query_params import BadFilter, parse_bool
from .utils import (
    ERR_CONFLICT,
    ERR_FORBIDDEN,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_ADMIN,
    SCOPE_SAP_MIRROR_READ,
    SCOPE_SETTINGS_WRITE,
    caller_holds,
    err,
    get_multipart,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_assets import _browse_or_404, _parse_updated_since

#: The export as SAP produced it is ~75 MB; this is the ceiling an upload
#: is refused above, in words, before anything is stored. BELOW the
#: proxies' 200 MB (nginx locally, the cluster ingress), which refuse above
#: it with their own HTML 413 before Odoo sees the request — so a file
#: between this and 200 MB is told why in the envelope.
MAX_UPLOAD_BYTES = 150 * 1024 * 1024
#: The parts of the upload body.
UPLOAD_FILE_FIELDS = ("file",)

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _iso(value):
    return value.strftime(_ISO) if value else None


def _date(value):
    return value.isoformat() if value else None


_USER_REF = {"type": "object", "nullable": True,
             "properties": {"id": {"type": "integer"},
                            "name": {"type": "string"}}}

SAP_RECORD_SCHEMA = {
    "type": "object",
    "description": "One record of SAP's asset master, as the latest import "
                   "of SAP's export left it. Read-only: SAP's register, not "
                   "Cadra's.",
    "properties": {
        "id": {"type": "integer"},
        "company_code": {"type": "string", "nullable": True},
        "asset_number": {"type": "string",
                         "description": "SAP's asset number, as SAP wrote it."},
        "sub_number": {"type": "string", "nullable": True},
        "class": {"type": "string", "nullable": True,
                  "description": "SAP's asset class (`2000`, `3000`, …)."},
        "description": {"type": "string", "nullable": True},
        "description_2": {"type": "string", "nullable": True},
        "old_tag": {"type": "string", "nullable": True,
                    "description": "The old FIRS tag (SAP's Inventory "
                                   "number). NOT unique."},
        "office_code": {"type": "string", "nullable": True},
        "office_source": {"type": "string",
                          "enum": [k for k, _l in OFFICE_SOURCES],
                          "description": "`tag`: parsed from a "
                                         "`FIRS/<office>/…` old tag. "
                                         "`location_extract`: SAP's location "
                                         "extract (a later import). `none`: "
                                         "no office known."},
        "serial_number": {"type": "string", "nullable": True,
                          "description": "A real-looking serial only."},
        "serial_kind": {"type": "string",
                        "enum": [k for k, _l in SERIAL_KINDS]},
        "serial_placeholder": {"type": "string", "nullable": True,
                               "description": "What was typed where a serial "
                                              "should be, kept aside."},
        "capitalized_on": {"type": "string", "format": "date",
                           "nullable": True},
        "first_acquired_on": {"type": "string", "format": "date",
                              "nullable": True},
        "created_in_sap_on": {"type": "string", "format": "date",
                              "nullable": True},
        "deactivated_on": {"type": "string", "format": "date",
                           "nullable": True},
        "active": {"type": "boolean",
                   "description": "No deactivation date."},
        "vendor": {"type": "string", "nullable": True},
        "in_latest_export": {"type": "boolean",
                             "description": "False once an import ran "
                                            "without this record. Kept, "
                                            "never deleted."},
        "linked_asset": {
            "type": "object", "nullable": True,
            "description": "The Cadra asset whose SAP asset number is this "
                           "record's — computed at read time, never stored.",
            "properties": {"id": {"type": "integer"},
                           "asset_code": {"type": "string"},
                           "register_state": {"type": "string"}}},
        "updated_at": {"type": "string", "format": "date-time",
                       "description": "When an import last CHANGED this "
                                      "record. An unchanged re-import does "
                                      "not move it."},
    },
}

RUN_SCHEMA = {
    "type": "object",
    "description": "One import of SAP's asset-master export.",
    "properties": {
        "id": {"type": "integer"},
        "state": {"type": "string",
                  "enum": ["queued", "running", "done", "failed", "held"],
                  "description": "`held` (handoff 65): stopped before "
                                 "writing anything, because the file would "
                                 "have marked more than 5% of the mirror "
                                 "not in the latest export; `message` says "
                                 "how many."},
        "file_name": {"type": "string"},
        "file_size": {"type": "integer", "description": "Bytes uploaded."},
        "file_kept": {"type": "boolean",
                      "description": "True only while the run reads it."},
        "uploaded_by": _USER_REF,
        "uploaded_at": {"type": "string", "format": "date-time"},
        "started_at": {"type": "string", "format": "date-time",
                       "nullable": True},
        "finished_at": {"type": "string", "format": "date-time",
                        "nullable": True},
        "duration_seconds": {"type": "number", "nullable": True},
        "cpu_seconds": {"type": "number"},
        "ticks": {"type": "integer",
                  "description": "Background passes the run took."},
        "peak_memory_mb": {"type": "number"},
        "progress": {"type": "object", "properties": {
            "sheet_bytes": {"type": "integer"},
            "read_bytes": {"type": "integer"},
            "percent": {"type": "number"}}},
        "rows_read": {"type": "integer"},
        "created": {"type": "integer"},
        "updated": {"type": "integer"},
        "unchanged": {"type": "integer"},
        "refused": {"type": "integer"},
        "refused_reasons": {"type": "array", "items": {
            "type": "object", "properties": {
                "reason": {"type": "string"}, "rows": {"type": "integer"}}}},
        "marked_not_in_latest_export": {"type": "integer"},
        "message": {"type": "string", "nullable": True},
        "absent_guard": {"type": "object", "description": (
            "Handoff 65 §3. `phase`: `count` while the run counts what it "
            "would mark absent (writing nothing), then `write`. "
            "`would_mark_absent` of `mirror_records_before` is what the "
            "count found; over `threshold_share` the run is `held`. "
            "`confirmed`: uploaded with `mark_absent=true` — \"Yes, mark "
            "them absent\" — by `confirmed_by`, and not counted."),
            "properties": {
                "phase": {"type": "string", "enum": ["count", "write"]},
                "would_mark_absent": {"type": "integer", "nullable": True},
                "mirror_records_before": {"type": "integer",
                                          "nullable": True},
                "threshold_share": {"type": "number"},
                "confirmed": {"type": "boolean"},
                "confirmed_by": _USER_REF}},
    },
}


def serialize_sap(rec, linked=None):
    link = (linked or {}).get(rec.id)
    asset = None
    if link:
        a = request.env["nrs.asset"].sudo().browse(link["asset_id"])
        asset = {"id": a.id, "asset_code": a.asset_code or None,
                 "register_state": link["register_state"]}
    return {
        "id": rec.id,
        "company_code": rec.company_code or None,
        "asset_number": rec.asset_number,
        "sub_number": rec.sub_number or None,
        "class": rec.asset_class or None,
        "description": rec.description or None,
        "description_2": rec.description_2 or None,
        "old_tag": rec.old_tag or None,
        "office_code": rec.office_code or None,
        "office_source": rec.office_source or "none",
        "serial_number": rec.serial_number or None,
        "serial_kind": rec.serial_kind or "none",
        "serial_placeholder": rec.serial_placeholder or None,
        "capitalized_on": _date(rec.capitalized_on),
        "first_acquired_on": _date(rec.first_acquired_on),
        "created_in_sap_on": _date(rec.sap_created_on),
        "deactivated_on": _date(rec.deactivated_on),
        "active": bool(rec.sap_active),
        "vendor": rec.vendor or None,
        "in_latest_export": bool(rec.in_latest_export),
        "linked_asset": asset,
        "updated_at": _iso(rec.write_date),
    }


def serialize_run(run):
    sheet = run.sheet_size or 0
    read = run.resume_offset or 0
    reasons = run._reasons()
    return {
        "id": run.id,
        "state": run.state,
        "file_name": run.file_name,
        "file_size": run.file_size,
        "file_kept": bool(run._attachment()),
        "uploaded_by": ({"id": run.uploaded_by.id,
                         "name": run.uploaded_by.name}
                        if run.uploaded_by else None),
        "uploaded_at": _iso(run.create_date),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "duration_seconds": (round(run.duration_seconds, 1)
                             if run.state in ("done", "failed") else None),
        "cpu_seconds": round(run.cpu_seconds or 0, 1),
        "ticks": run.ticks,
        "peak_memory_mb": round(run.peak_rss_mb or 0),
        "progress": {
            "sheet_bytes": sheet, "read_bytes": read,
            "percent": (100.0 if run.state == "done" else
                        round(100.0 * read / sheet, 1) if sheet else 0.0)},
        "rows_read": run.rows_read,
        "created": run.created_count,
        "updated": run.updated_count,
        "unchanged": run.unchanged_count,
        "refused": run.refused_count,
        "refused_reasons": [{"reason": k, "rows": v}
                            for k, v in sorted(reasons.items(),
                                               key=lambda kv: -kv[1])],
        "marked_not_in_latest_export": run.marked_absent_count,
        "message": run.message or None,
        "absent_guard": {
            "phase": run.phase or "write",
            "would_mark_absent": run.would_mark_absent
            if run.phase == "write" and not run.absent_confirmed
            and run.mirror_records_before or run.state == "held" else None,
            "mirror_records_before": run.mirror_records_before or None,
            "threshold_share": ABSENT_GUARD_SHARE,
            "confirmed": bool(run.absent_confirmed),
            "confirmed_by": ({"id": run.absent_confirmed_by.id,
                              "name": run.absent_confirmed_by.name}
                             if run.absent_confirmed_by else None)},
    }


def _text(qs, name):
    raw = qs.get(name)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise BadFilter("`%s` must be text" % name, details={name: raw})
    return raw.strip() or None


def _share(n, of):
    return "%d of %d (%.1f%%)" % (n, of, 100.0 * n / of) if of else \
        "%d of 0" % n


def _class_evidence(Sap):
    """§4: one row per Cadra category with linked assets, its SAP classes
    most-carried first, and the sentence the handoff asks for."""
    cats = {}
    for cat_id, configured, cls, n, via in Sap._class_evidence():
        row = cats.setdefault(cat_id, {"configured": configured,
                                       "classes": [], "linked": 0,
                                       "via_link": 0})
        row["classes"].append({"class": cls, "assets": n})
        row["linked"] += n
        row["via_link"] += via
    names = {c.id: c.name for c in request.env[
        "nrs.asset.category"].sudo().browse([c for c in cats if c])}
    out = []
    for cat_id, row in cats.items():
        classes = sorted(row["classes"],
                         key=lambda c: (-c["assets"], c["class"] or "~"))
        name = names.get(cat_id) or "No category"
        configured = row["configured"]
        top = classes[0]["class"] if classes else None
        out.append({
            "category": {"id": cat_id or None, "name": name},
            "configured_class": configured,
            "linked": row["linked"],
            "via_link": row["via_link"],
            "sap_classes": classes,
            "agrees": (None if not configured else
                       all(c["class"] == configured for c in classes)),
            "sentence": "%s: %d linked; %s." % (
                name, row["linked"], ", ".join(
                    "SAP class %s for %d" % (c["class"] or "(none)",
                                             c["assets"])
                    for c in classes))
            + (" Configured: %s." % configured if configured
               else " No SAP class configured.")
            + (" The most-carried class differs from the configured one."
               if configured and top and top != configured else ""),
        })
    out.sort(key=lambda r: (-r["linked"], r["category"]["name"]))
    return out


class CadraSapMirrorV1(http.Controller):

    # ── the import ───────────────────────────────────────────────────

    @cadra_route("/api/v1/sap-assets/imports", method="POST",
                 summary="Import SAP's asset-master export into the SAP mirror",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 success_status=202,
                 error_statuses=(409, 413),
                 # Odoo's default ceiling is 128 MiB; this route's is 150 MB,
                 # refused in words below. A margin above it for the form's
                 # own bytes, so the words are what a 151 MB file gets.
                 max_content_length=MAX_UPLOAD_BYTES + (8 << 20),
                 request_schema={
                     "type": "object",
                     "description": "multipart/form-data: `file`, the .XLSX "
                                    "as SAP produced it, and optionally "
                                    "`mark_absent` = `true` (handoff 65: "
                                    "\"Yes, mark them absent\" — skip the "
                                    "5% guard, recorded on the run). "
                                    "The token must also hold `admin` — a "
                                    "System Administrator's act.",
                     "required": ["file"],
                     "properties": {"file": {"type": "string",
                                             "format": "binary"},
                                    "mark_absent": {"type": "string",
                                                    "enum": ["true",
                                                             "false"]}}},
                 response_schema=RUN_SCHEMA)
    def import_sap_export(self, **kwargs):
        # A System Administrator's act (handoff 63 §1): `settings:write` is
        # the route's scope, and the Asset Manager holds it — so the token
        # must ALSO carry `admin`. Asked before the body is read.
        if not caller_holds(SCOPE_ADMIN):
            return err(
                ERR_FORBIDDEN,
                "Importing SAP's asset master is the System Administrator's "
                "act. This account holds `settings:write` but is not a system "
                "administrator (the token carries no `admin`). Nothing was "
                "imported.", status=403,
                details={"required_scopes": [SCOPE_SETTINGS_WRITE,
                                             SCOPE_ADMIN]})
        values, uploads, error = get_multipart(
            file_fields=UPLOAD_FILE_FIELDS, text_fields=("mark_absent",),
            required=("file",))
        if error:
            return error
        # Handoff 65 §3: "Yes, mark them absent" — the guard is not applied
        # to this file, and the run records who said so.
        flag = (values.get("mark_absent") or "").lower()
        if flag not in ("", "true", "false"):
            return err(ERR_INVALID_REQUEST,
                       "`mark_absent` is true or false. Nothing was imported.",
                       details={"field": "mark_absent"})
        mark_absent = flag == "true"
        upload = uploads["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            return err(
                ERR_VALIDATION_FAILED,
                "The file is %d bytes; an export import takes up to %d. "
                "Nothing was imported." % (upload.size, MAX_UPLOAD_BYTES),
                status=413, details={"size": upload.size,
                                     "max_bytes": MAX_UPLOAD_BYTES})
        Run = request.env["nrs.sap.import.run"].sudo()
        busy = Run.search([("state", "in", ("queued", "running"))], limit=1)
        if busy:
            return err(
                ERR_CONFLICT,
                "Import %d (%s, uploaded by %s) is still %s. One import runs "
                "at a time; upload this file when it has finished. Nothing "
                "was imported." % (busy.id, busy.file_name,
                                   busy.uploaded_by.name or "?", busy.state),
                status=409, details={"run_id": busy.id, "state": busy.state})
        raw = upload.read()
        if not raw:
            return err(ERR_VALIDATION_FAILED,
                       "The file is empty. Nothing was imported.")
        try:
            export = sap_export_reader.Export(io.BytesIO(raw))
            sheet = export.zip.getinfo(export.sheet_path).file_size
            if sheet > MAX_SHEET_BYTES:
                raise sap_export_reader.ExportRefused(
                    "The sheet is %d bytes uncompressed; an import reads up "
                    "to %d." % (sheet, MAX_SHEET_BYTES), sheet_bytes=sheet)
            header, prefix, start = export.header()
            colmap = sap_export_reader.header_map(header)
        except sap_export_reader.ExportRefused as e:
            return err(ERR_VALIDATION_FAILED, str(e),
                       details=dict(e.details, file_name=upload.filename))
        except sap_export_reader.RowRefused as e:
            return err(ERR_VALIDATION_FAILED,
                       "The header row cannot be read: %s. Nothing was "
                       "imported." % e.reason)
        except (etree.XMLSyntaxError, zlib.error, zipfile.BadZipFile,
                StopIteration, KeyError, EOFError) as e:
            # A zip that is a workbook in name only: a member that is not
            # XML, a corrupt deflate stream, a sheet whose rows are not in
            # the spreadsheetml namespace (strict OOXML). Said, not a 500.
            return err(
                ERR_VALIDATION_FAILED,
                "This file cannot be read as SAP's .XLSX export (%s). "
                "Upload the export as SAP produced it. Nothing was "
                "imported." % type(e).__name__,
                details={"file_name": upload.filename,
                         "reason": type(e).__name__})
        run = Run.create({
            "file_name": upload.filename or "export.xlsx",
            "file_size": upload.size,
            "sheet_size": sheet,
            "file_data": base64.b64encode(raw),
            "uploaded_by": request.env.user.id,
            "header_map": json.dumps(colmap),
            "sheet_prefix": prefix.decode("utf-8"),
            "resume_offset": start,
            "absent_confirmed": mark_absent,
            "absent_confirmed_by": request.env.user.id if mark_absent
            else False,
        })
        request.env.ref(
            "myservice_asset_register.cron_sap_mirror_import").sudo()._trigger()
        return serialize_run(run)

    @cadra_route("/api/v1/sap-assets/imports", method="GET",
                 summary="The imports of SAP's asset-master export, newest first",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema={"type": "array", "items": RUN_SCHEMA},
                 query_params=[*PAGINATION_QUERY_PARAMS])
    def list_imports(self, **kwargs):
        qs = get_params()
        page, next_cursor, total = paginate(
            request.env["nrs.sap.import.run"].sudo(), [],
            limit=parse_limit(qs), cursor=qs.get("cursor"), descending=True)
        return ok(data=[serialize_run(r) for r in page],
                  pagination={"next_cursor": next_cursor,
                              "previous_cursor": None,
                              "total_estimate": total})

    @cadra_route("/api/v1/sap-assets/imports/<int:id>", method="GET",
                 summary="One import of SAP's asset-master export",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema=RUN_SCHEMA)
    def get_import(self, id, **kwargs):
        run = request.env["nrs.sap.import.run"].sudo().browse(id)
        if not run.exists():
            return err(ERR_NOT_FOUND, "Import %d not found" % id, status=404)
        return serialize_run(run)

    # ── the slice ────────────────────────────────────────────────────

    @cadra_route("/api/v1/sap-assets", method="GET",
                 summary="A page of the SAP mirror — the offline phone's slice",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema={"type": "array", "items": SAP_RECORD_SCHEMA},
                 query_params=[
                     {"name": "office", "schema": {"type": "string"},
                      "description": "An office code (`FIRS/<office>/…`), or "
                                     "`none` for the records with no office "
                                     "— every untagged one until SAP's "
                                     "location extract is imported."},
                     {"name": "class", "schema": {"type": "string"},
                      "description": "SAP asset class, exact (`2000`)."},
                     {"name": "updated_since",
                      "schema": {"type": "string", "format": "date-time"},
                      "description": "Records an import CHANGED at or after "
                                     "this instant — a re-import that "
                                     "changes nothing does not move them. "
                                     "The same rules as `GET /assets` "
                                     "(handoff 61 §6): start the next sync "
                                     "from the FIRST page's "
                                     "`meta.timestamp`. A record that "
                                     "left SAP's export comes back with "
                                     "`in_latest_export: false`."},
                     {"name": "active", "schema": {"type": "boolean"},
                      "description": "Active in SAP (no deactivation "
                                     "date). Unparseable is a 400."},
                     {"name": "in_latest_export",
                      "schema": {"type": "boolean"},
                      "description": "In the latest export. Unparseable is "
                                     "a 400."},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_sap_assets(self, **kwargs):
        qs = get_params()
        try:
            domain = []
            office = _text(qs, "office")
            if office:
                domain.append(("office_code", "=", False)
                              if office.lower() == "none"
                              else ("office_code", "=", office.upper()))
            cls = _text(qs, "class")
            if cls:
                domain.append(("asset_class", "=", cls))
            since = _parse_updated_since(qs.get("updated_since"))
            if since is not None:
                domain.append(("write_date", ">=", since))
            for name, field in (("active", "sap_active"),
                                ("in_latest_export", "in_latest_export")):
                value = parse_bool(name, qs.get(name))
                if value is not None:
                    domain.append((field, "=", value))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        Sap = request.env["nrs.sap.asset"].sudo()
        page, next_cursor, total = paginate(
            Sap, domain, limit=parse_limit(qs), cursor=qs.get("cursor"))
        linked = page._linked_assets()
        return ok(data=[serialize_sap(r, linked) for r in page],
                  pagination={"next_cursor": next_cursor,
                              "previous_cursor": None,
                              "total_estimate": total})

    # ── the matcher ──────────────────────────────────────────────────

    @cadra_route("/api/v1/sap-assets/match", method="GET",
                 summary="Up to five SAP records an item somebody found could "
                         "be, each saying why it ranked",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema={"type": "object", "properties": {
                     "basis": {"type": "string", "nullable": True,
                               "enum": ["old_tag", "serial", "description",
                                        None]},
                     "pool": {"type": "integer",
                              "description": "Active, unlinked records at "
                                             "the deciding step."},
                     "tied_at_top": {"type": "integer"},
                     "already_linked": {"type": "integer"},
                     "already_linked_note": {"type": "string",
                                             "nullable": True},
                     "office_used": {"type": "string", "nullable": True},
                     "office_from": {"type": "string", "nullable": True,
                                     "enum": ["param", "tag", None]},
                     "notes": {"type": "array", "items": {"type": "string"}},
                     "results": {"type": "array", "items": {
                         "type": "object", "properties": {
                             "rank": {"type": "integer"},
                             "reason_code": {"type": "string", "enum": [
                                 "old_tag_unique",
                                 "old_tag_shared_description",
                                 "old_tag_shared", "serial_unique",
                                 "serial_shared_description", "serial_shared",
                                 "description_office",
                                 "description_nationwide"]},
                             "reason": {"type": "string"},
                             "sap_asset": SAP_RECORD_SCHEMA}}}}},
                 query_params=[
                     {"name": "old_tag", "schema": {"type": "string"},
                      "description": "The old FIRS tag on the item. Compared "
                                     "trimmed, upper-case, `\\` as `/`."},
                     {"name": "description", "schema": {"type": "string"},
                      "description": "What the item is. Whole words, any "
                                     "case, against both SAP descriptions."},
                     {"name": "class", "schema": {"type": "string"},
                      "description": "SAP asset class."},
                     {"name": "office", "schema": {"type": "string"},
                      "description": "The office the item was found in. "
                                     "Without it, the office inside the old "
                                     "tag; without either, nationwide."},
                     {"name": "serial", "schema": {"type": "string"},
                      "description": "A serial on the item. Tried when no "
                                     "record carries the old tag. A "
                                     "placeholder (`XXXX`, `0`) is never "
                                     "matched."},
                 ])
    def match(self, **kwargs):
        qs = get_params()
        try:
            given = {k: _text(qs, k) for k in
                     ("old_tag", "description", "class", "office", "serial")}
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        if not any(given[k] for k in ("old_tag", "description", "class",
                                      "serial")):
            return err(
                ERR_INVALID_REQUEST,
                "Say something about the item: an `old_tag`, a "
                "`description`, a `class` or a `serial` (an `office` alone "
                "matches every record in it).",
                details={"accepted": ["old_tag", "description", "class",
                                      "office", "serial"]})
        Sap = request.env["nrs.sap.asset"].sudo()
        answer = Sap._match(old_tag=given["old_tag"],
                            description=given["description"],
                            asset_class=given["class"],
                            office=given["office"], serial=given["serial"])
        recs = Sap.browse([r["id"] for r in answer["results"]])
        by_id = {r.id: r for r in recs}
        for item in answer["results"]:
            item["sap_asset"] = serialize_sap(by_id[item.pop("id")])
        return answer

    # ── one record, both ways ────────────────────────────────────────

    @cadra_route("/api/v1/sap-assets/<int:id>", method="GET",
                 summary="One record of the SAP mirror, with the Cadra asset "
                         "linked to it",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema=SAP_RECORD_SCHEMA)
    def get_sap_asset(self, id, **kwargs):
        rec = request.env["nrs.sap.asset"].sudo().browse(id)
        if not rec.exists():
            return err(ERR_NOT_FOUND, "SAP mirror record %d not found" % id,
                       status=404)
        return serialize_sap(rec, rec._linked_assets())

    @cadra_route("/api/v1/assets/<int:id>/sap-record", method="GET",
                 summary="The SAP mirror record a Cadra asset is linked to",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema={"type": "object", "properties": {
                     "asset_id": {"type": "integer"},
                     "sap_asset_number": {"type": "string", "nullable": True},
                     "linked": {"type": "boolean"},
                     "sentence": {"type": "string"},
                     "sap_asset": dict(SAP_RECORD_SCHEMA, nullable=True)}})
    def asset_sap_record(self, id, **kwargs):
        asset, error = _browse_or_404(id)
        if error:
            return error
        Sap = request.env["nrs.sap.asset"].sudo()
        rec = Sap._for_asset(asset)
        number = (asset.sap_asset_number or "").strip() or None
        if rec:
            sentence = ("Linked: SAP asset %s is in the SAP mirror%s." % (
                rec.asset_number,
                "" if rec.in_latest_export
                else ", but not in SAP's latest export"))
        elif number:
            sentence = ("Not linked: this asset carries SAP asset number %s "
                        "and the SAP mirror holds no record of it." % number)
        else:
            sentence = ("Not linked: this asset carries no SAP asset number. "
                        "GET /sap-assets/match proposes candidates.")
        return {"asset_id": asset.id, "sap_asset_number": number,
                "linked": bool(rec), "sentence": sentence,
                "sap_asset": (serialize_sap(rec, rec._linked_assets())
                              if rec else None)}

    # ── the first reconciliation ─────────────────────────────────────

    @cadra_route("/api/v1/reports/sap-coverage", method="GET",
                 summary="How much of SAP's register Cadra holds, by class "
                         "and by office",
                 scopes=[SCOPE_SAP_MIRROR_READ])
    def sap_coverage(self, **kwargs):
        Sap = request.env["nrs.sap.asset"].sudo()
        cov = Sap._coverage()
        last = request.env["nrs.sap.import.run"].sudo().search(
            [("state", "=", "done")], order="id desc", limit=1)
        classes = sorted(set(cov["sap_by_class"]) | set(cov["cadra_by_class"]),
                         key=lambda c: (c is None, c or ""))
        by_class, totals = [], dict.fromkeys(
            ("sap_active", "linked", "linked_to_a_receipt_candidate",
             "not_linked", "sap_retired", "cadra_assets",
             "cadra_with_sap_number", "cadra_sap_number_not_in_mirror",
             "cadra_without_sap_number"), 0)
        for cls in classes:
            active, linked, cand, retired = cov["sap_by_class"].get(
                cls, (0, 0, 0, 0))
            c_all, c_num, c_gap, c_none = cov["cadra_by_class"].get(
                cls, (0, 0, 0, 0))
            row = {"class": cls, "sap_active": active, "linked": linked,
                   "linked_to_a_receipt_candidate": cand,
                   "not_linked": active - linked, "sap_retired": retired,
                   "cadra_assets": c_all, "cadra_with_sap_number": c_num,
                   "cadra_sap_number_not_in_mirror": c_gap,
                   "cadra_without_sap_number": c_none}
            for k in totals:
                totals[k] += row[k]
            row["held"] = _share(linked, active)
            by_class.append(row)
        by_office = [{"office": office, "sap_active": active,
                      "linked": linked, "not_linked": active - linked,
                      "held": _share(linked, active),
                      "cadra_assets": None, "cadra_with_sap_number": None,
                      "cadra_sap_number_not_in_mirror": None,
                      "cadra_without_sap_number": None}
                     for office, active, linked in cov["sap_by_office"]]
        conf = cov["confident"]
        sap = cov["sap"]
        evidence = _class_evidence(Sap)
        totals["held"] = _share(totals["linked"], totals["sap_active"])
        return {
            "as_of": _iso(fields.Datetime.now()),
            "latest_import": serialize_run(last) if last else None,
            "sentence": (
                "No export of SAP's asset master has been imported on this "
                "tenant; every SAP count is zero because the mirror is "
                "empty, not because Cadra holds nothing."
                if not sap["records"] else
                "Cadra holds %d of SAP's %d active assets (%s). Of the %d Cadra "
                "assets on the register with no SAP asset number, the "
                "matcher ranks %d first by a unique old tag or serial (%d by "
                "tag, %d by serial); %d of those point at a SAP record "
                "another Cadra asset also points at, which leaves %d that "
                "could be linked with confidence today." % (
                    totals["linked"], totals["sap_active"],
                    ("%.1f%%" % (100.0 * totals["linked"] / totals["sap_active"])
                     if totals["sap_active"] else "none active"),
                    conf["assets_without_sap_number"], conf["total"],
                    conf["by_unique_old_tag"], conf["by_unique_serial"],
                    conf["contested_assets"], conf["uncontested"])),
            "definitions": {
                "sap_active": "SAP records in the latest import that are "
                              "active in SAP (no deactivation date).",
                "linked": "Of those, the records whose SAP asset number a "
                          "Cadra asset carries (stripped and upper-cased; "
                          "receipt candidates included).",
                "linked_to_a_receipt_candidate": "Of the linked, those whose "
                                                 "Cadra asset is still a "
                                                 "receipt candidate, not yet "
                                                 "on the register.",
                "not_linked": "sap_active minus linked: SAP's assets Cadra "
                              "does not hold.",
                "sap_retired": "Records in the latest import that SAP has "
                               "deactivated. Not counted in sap_active.",
                "cadra_assets": "Cadra assets on the register (not "
                                "receipt candidates), by the SAP class of "
                                "their category; `class: null` means the "
                                "category has no SAP class.",
                "cadra_with_sap_number": "Of cadra_assets, those carrying an "
                                         "SAP asset number.",
                "cadra_sap_number_not_in_mirror": "Of those, the ones whose "
                                                  "SAP number the mirror "
                                                  "holds no record of — the "
                                                  "reverse gap.",
                "cadra_without_sap_number": "Of cadra_assets, those with no "
                                            "SAP asset number.",
                "held": "linked of sap_active, as a share.",
                "by_office": "SAP's side only: Cadra's locations carry no "
                             "SAP office code, so the Cadra columns are "
                             "null. `office: null` is every SAP record with "
                             "no office — no `FIRS/<office>/…` old tag, "
                             "until SAP's location extract is imported.",
                "class_evidence": "Per Cadra category (handoff 65 §4): its "
                                  "register assets whose SAP number names a "
                                  "mirror record, and the SAP classes those "
                                  "records carry in SAP's export — the "
                                  "evidence for the proposed class mapping. "
                                  "`configured_class` is the category's SAP "
                                  "class as set today (null: none); this "
                                  "report never writes it — NRS confirms "
                                  "the mapping. `via_link` counts the "
                                  "assets linked by two people on Link to "
                                  "SAP.",
                "reconcilable_today": "Cadra assets with no SAP number that "
                                      "the matcher would rank FIRST by a "
                                      "unique old tag (the asset's legacy "
                                      "asset code) or a unique real serial: "
                                      "exactly one active, unlinked SAP "
                                      "record carries it. `contested_*`: "
                                      "those whose SAP record another Cadra "
                                      "asset would also be linked to; "
                                      "`uncontested` is what is left.",
            },
            "sap": {"records_held": sap["records"],
                    "in_latest_export": sap["in_latest_export"],
                    "not_in_latest_export": sap["not_in_latest_export"],
                    "active_in_latest_export": sap["active"]},
            "totals": totals,
            "by_class": by_class,
            "by_office": by_office,
            "reconcilable_today": conf,
            "class_evidence": evidence,
        }
