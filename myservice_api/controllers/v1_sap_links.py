"""The link — a register asset given its SAP number from the mirror, by two
people (handoff 65), over HTTP.

The model is `nrs.sap.link` (`myservice_asset_register/models/sap_link.py`),
which says why it is maker-checker and why nothing is sent to SAP. The
confident matches are `nrs.sap.asset._confident_targets` — the same answer
the coverage report's `reconcilable_today` counts, so the list and the
report cannot disagree.

THE ROUTES
----------
* `GET /api/v1/sap-links/candidates` — the Register Maker's list: every
  register asset with no SAP number whose old tag (or, failing that, serial)
  points at exactly ONE active, unlinked SAP record that no other Cadra asset
  also points at. `?office=`, `?class=` (SAP's), `?status=open|proposed|all`.
* `POST /api/v1/sap-links/propose` — a batch, handoff 60's rules: N single
  proposals, each in its own savepoint, a line per asset with the status,
  code and sentence it would have had alone, `dry_run` rolls everything back.
* `GET /api/v1/sap-links` — the proposals, `?state=` (default `proposed`,
  the Register Checker's queue) and `?kind=`.
* `POST /api/v1/sap-links/approve`, `POST /api/v1/sap-links/return` — the
  checker's acts on a list of proposals (one is a list of one); a return
  needs a reason.
* `POST /api/v1/assets/<id>/sap-link/undo` — propose undoing a link, with a
  reason; the checker decides it on the same two routes.
* `GET /api/v1/sap-links/contested` — §2: each SAP record two or more Cadra
  assets point at, the assets side by side, counts by office.
* `POST /api/v1/sap-links/contested/<sap id>/propose` — the maker chooses one
  asset of a group; the others are left unlinked.
* `POST /api/v1/sap-links/contested/<sap id>/flag` — the group flagged as a
  likely duplicate, with a note. Nothing merged, retired or deleted.

Reads are `sap_mirror:read`; proposing, undoing and flagging `register:make`;
deciding `register:check`. One person may not propose and decide one asset's
link — the no-two-gates rule, refused 409 `segregation_of_duties` naming the
earlier act. The gate switch changes nothing: a link is not a receipt.
"""
from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.myservice_asset_register.models.asset_gates import (
    CANDIDATES_CTX,
    GateRefused,
)
from odoo.addons.myservice_asset_register.models.sap_link import (
    LINK_KINDS,
    LINK_STATES,
)

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_REGISTER_CHECK,
    SCOPE_REGISTER_MAKE,
    SCOPE_SAP_MIRROR_READ,
    err,
    gate_refusal,
    gate_refusal_parts,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_gates import BATCH_MAX, _DryRun, _token_scopes

_ISO = "%Y-%m-%dT%H:%M:%SZ"
#: A page of the candidates or the contested list.
PAGE_MAX = 500
STATUSES = ("open", "proposed", "all")


def _iso(value):
    return value.strftime(_ISO) if value else None


def _user(u):
    return {"id": u.id, "name": u.name} if u else None


def _assets(ids):
    return request.env["nrs.asset"].sudo().with_context(
        **{CANDIDATES_CTX: True}).browse(ids)


def _asset_brief(a):
    return {"id": a.id, "asset_code": a.asset_code or None,
            "name": a.name or None,
            "location": ({"id": a.location_id.id,
                          "name": a.location_id.display_name}
                         if a.location_id else None)}


def _sap_brief(s):
    return {"id": s.id, "asset_number": s.asset_number,
            "sub_number": s.sub_number or None,
            "class": s.asset_class or None,
            "description": s.description or None,
            "description_2": s.description_2 or None,
            "old_tag": s.old_tag or None,
            "serial_number": s.serial_number or None,
            "office_code": s.office_code or None,
            "capitalized_on": s.capitalized_on.isoformat()
            if s.capitalized_on else None}


def serialize_link(link, held=None):
    """One proposal. `can_decide`: the caller holds `register:check` and the
    no-two-gates rule does not bar them; `refusal` says why not."""
    held = held if held is not None else set(_token_scopes())
    can, refusal = False, None
    if link.state == "proposed":
        asset = link.asset_id.sudo()
        scopes = asset._gate_scopes(list(held))
        if SCOPE_REGISTER_CHECK in scopes:
            found = asset._two_gates_refusal("link_check")
            can, refusal = not found, (found[0] if found else None)
    return {
        "id": link.id,
        "kind": link.kind,
        "state": link.state,
        "asset": _asset_brief(link.asset_id),
        "sap": _sap_brief(link.sap_record_id),
        "sap_asset_number": link.sap_asset_number or None,
        "reason_code": link.reason_code or None,
        "reason": link.reason or None,
        "note": link.note or None,
        "proposed_by": _user(link.proposed_by_id),
        "proposed_at": _iso(link.proposed_at),
        "decided_by": _user(link.decided_by_id),
        "decided_at": _iso(link.decided_at),
        "return_reason": link.return_reason or None,
        "can_decide": can,
        "refusal": refusal,
    }


_SAP_BRIEF_SCHEMA = {"type": "object", "properties": {
    "id": {"type": "integer"}, "asset_number": {"type": "string"},
    "sub_number": {"type": "string", "nullable": True},
    "class": {"type": "string", "nullable": True},
    "description": {"type": "string", "nullable": True},
    "description_2": {"type": "string", "nullable": True},
    "old_tag": {"type": "string", "nullable": True},
    "serial_number": {"type": "string", "nullable": True},
    "office_code": {"type": "string", "nullable": True},
    "capitalized_on": {"type": "string", "format": "date",
                       "nullable": True}}}
_ASSET_BRIEF_SCHEMA = {"type": "object", "properties": {
    "id": {"type": "integer"},
    "asset_code": {"type": "string", "nullable": True},
    "name": {"type": "string", "nullable": True},
    "location": {"type": "object", "nullable": True}}}
LINK_SCHEMA = {
    "type": "object",
    "description": "A proposal to link a register asset to its SAP record "
                   "(or to undo one), and its decision.",
    "properties": {
        "id": {"type": "integer"},
        "kind": {"type": "string", "enum": [k for k, _l in LINK_KINDS]},
        "state": {"type": "string", "enum": [k for k, _l in LINK_STATES]},
        "asset": _ASSET_BRIEF_SCHEMA,
        "sap": _SAP_BRIEF_SCHEMA,
        "sap_asset_number": {"type": "string", "nullable": True},
        "reason_code": {"type": "string", "nullable": True,
                        "description": "`old_tag_unique`, `serial_unique`; "
                                       "`undo` for an undo."},
        "reason": {"type": "string", "nullable": True},
        "note": {"type": "string", "nullable": True},
        "proposed_by": {"type": "object", "nullable": True},
        "proposed_at": {"type": "string", "format": "date-time"},
        "decided_by": {"type": "object", "nullable": True},
        "decided_at": {"type": "string", "format": "date-time",
                       "nullable": True},
        "return_reason": {"type": "string", "nullable": True},
        "can_decide": {"type": "boolean"},
        "refusal": {"type": "string", "nullable": True},
    }}
_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "dry_run": {"type": "boolean"},
        "total": {"type": "integer"},
        "done": {"type": "integer"},
        "refused": {"type": "integer"},
        "results": {"type": "array", "items": {"type": "object",
            "properties": {
                "asset_id": {"type": "integer", "nullable": True},
                "asset_code": {"type": "string", "nullable": True},
                "link_id": {"type": "integer", "nullable": True},
                "sap_asset_number": {"type": "string", "nullable": True},
                "outcome": {"type": "string",
                            "enum": ["done", "would_do", "refused"]},
                "status": {"type": "integer"},
                "code": {"type": "string", "nullable": True},
                "message": {"type": "string", "nullable": True},
                "details": {"type": "object", "nullable": True}}}}}}


def _text_param(qs, name):
    raw = qs.get(name)
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _offset(qs):
    raw = qs.get("offset", 0)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = -1
    return value


def _page_limit(qs, default=100):
    raw = qs.get("limit", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    return value


def _paging_error(offset, limit):
    if offset < 0:
        return err(ERR_INVALID_REQUEST, "`offset` must be a whole number, 0 "
                   "or more.", details={"field": "offset"})
    if not 1 <= limit <= PAGE_MAX:
        return err(ERR_INVALID_REQUEST, "`limit` must be between 1 and %d."
                   % PAGE_MAX, details={"field": "limit", "max": PAGE_MAX})
    return None


def _body(allowed):
    body = get_params()
    rejected = sorted(k for k in (body or {}) if k not in allowed)
    if rejected:
        return None, refuse_unwritable(rejected, sorted(allowed))
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        return None, err(ERR_INVALID_REQUEST, "`dry_run` must be true or "
                         "false.", details={"field": "dry_run"})
    for key in ("note", "reason"):
        if body.get(key) is not None and not isinstance(body[key], str):
            return None, err(ERR_INVALID_REQUEST, "`%s` must be a string."
                             % key, details={"field": key})
    return body, None


def _ids(body, key):
    ids = body.get(key)
    if not isinstance(ids, list) or not ids or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return None, err(ERR_INVALID_REQUEST, "`%s` must be a list of ids — "
                         "at least one." % key, details={"field": key})
    if len(ids) > BATCH_MAX:
        return None, err(ERR_INVALID_REQUEST, "A batch takes at most %d; "
                         "this one has %d. Send it in parts."
                         % (BATCH_MAX, len(ids)),
                         details={"field": key, "max": BATCH_MAX,
                                  "received": len(ids)})
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        return None, err(ERR_INVALID_REQUEST, "Each id may appear once; %s "
                         "appear more than once."
                         % ", ".join(map(str, dupes)),
                         details={"field": key, "duplicates": dupes})
    return ids, None


def _line(asset=None, link=None):
    asset = asset or (link.asset_id if link else None)
    return {"asset_id": asset.id if asset else None,
            "asset_code": (asset.asset_code or None) if asset else None,
            "link_id": link.id if link else None,
            "sap_asset_number": (link.sap_asset_number or None)
            if link else None}


def _act(line, fn):
    """Run one act in its own savepoint; the line it leaves."""
    try:
        with request.env.cr.savepoint():
            result = fn()
    except GateRefused as e:
        status, code, message, details = gate_refusal_parts(e)
        line.update(outcome="refused", status=status, code=code,
                    message=message, details=details)
        return line
    except (UserError, ValidationError) as e:
        line.update(outcome="refused", status=400, code=ERR_VALIDATION_FAILED,
                    message=str(e.args[0]), details={})
        return line
    if result is not None and result._name == "nrs.sap.link":
        line.update(link_id=result.id,
                    sap_asset_number=result.sap_asset_number or None)
    line.update(outcome="done", status=200, code=None, message=None,
                details=None)
    return line


def _run(items, fire, dry_run, action):
    out = []
    try:
        with request.env.cr.savepoint():
            for item in items:
                out.append(fire(item))
            if dry_run:
                raise _DryRun()
    except _DryRun:
        pass
    if dry_run:
        for line in out:
            if line["outcome"] == "done":
                line["outcome"] = "would_do"
                # The proposal a dry run made was rolled back with it.
                line["link_id"] = None
    done = sum(1 for l in out if l["outcome"] in ("done", "would_do"))
    return {"action": action, "dry_run": dry_run, "total": len(out),
            "done": done, "refused": len(out) - done, "results": out}


def _flag_brief(event):
    if not event:
        return None
    return {"sap_asset_number": event.to_value or None,
            "note": event.notes or None,
            "flagged_by": {"id": event.actor_id.id,
                           "name": event.actor_name}
            if event.actor_id else {"id": None, "name": event.actor_name},
            "flagged_at": _iso(event.occurred_at)}


class CadraSapLinksV1(http.Controller):

    # ── the maker's list ──────────────────────────────────────────────

    @cadra_route("/api/v1/sap-links/candidates", method="GET",
                 summary="Register assets that point at one SAP record with "
                         "confidence, ready to link",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 query_params=[
                     {"name": "office", "description": "SAP's office code "
                      "(from the old tag)."},
                     {"name": "class", "description": "SAP's asset class."},
                     {"name": "status", "description": "`open` (default): "
                      "not yet proposed; `proposed`: waiting on the "
                      "checker; `all`."},
                     {"name": "limit"}, {"name": "offset"}])
    def link_candidates(self, **kwargs):
        qs = get_params()
        status = _text_param(qs, "status") or "open"
        if status not in STATUSES:
            return err(ERR_INVALID_REQUEST, "`status` is one of %s."
                       % ", ".join(STATUSES),
                       details={"field": "status",
                                "allowed_values": list(STATUSES)})
        office, klass = _text_param(qs, "office"), _text_param(qs, "class")
        offset, limit = _offset(qs), _page_limit(qs)
        error = _paging_error(offset, limit)
        if error:
            return error
        Sap = request.env["nrs.sap.asset"].sudo()
        targets = Sap._confident_targets()
        pairs = [(aid, sid, basis)
                 for aid, (sid, basis) in targets["target"].items()
                 if len(targets["claims"][sid]) == 1]
        records = {s.id: s for s in Sap.browse({p[1] for p in pairs})}
        open_links = {l.asset_id.id: l for l in
                      request.env["nrs.sap.link"].sudo().search(
                          [("state", "=", "proposed"),
                           ("asset_id", "in", [p[0] for p in pairs])])}
        by_office, rows = {}, []
        for aid, sid, basis in pairs:
            rec = records[sid]
            pending = open_links.get(aid)
            if status == "open" and pending:
                continue
            if status == "proposed" and not pending:
                continue
            if klass and rec.asset_class != klass:
                continue
            key = rec.office_code or None
            by_office[key] = by_office.get(key, 0) + 1
            if office and rec.office_code != office.upper():
                continue
            rows.append((aid, rec, basis, pending))
        assets = {a.id: a for a in _assets([r[0] for r in rows])}
        rows.sort(key=lambda r: (r[1].office_code or "~", r[1].asset_class
                                 or "~", assets[r[0]].asset_code or ""))
        page = rows[offset:offset + limit]
        held = set(_token_scopes())
        items = []
        for aid, rec, basis, pending in page:
            code = "old_tag_unique" if basis == "old_tag" else "serial_unique"
            items.append({
                "asset": _asset_brief(assets[aid]),
                "sap": _sap_brief(rec),
                "reason_code": code,
                "reason": "old tag, unique" if basis == "old_tag"
                else "serial, unique",
                "link": serialize_link(pending, held) if pending else None,
            })
        return {
            "status": status,
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "by_office": [{"office": k, "assets": v} for k, v in sorted(
                by_office.items(), key=lambda kv: (-kv[1], kv[0] or "~"))],
            "items": items,
            "sentence": (
                "%d register asset%s point%s at exactly one SAP record that "
                "no other Cadra asset points at (%s)." % (
                    len(rows), "" if len(rows) == 1 else "s",
                    "s" if len(rows) == 1 else "",
                    {"open": "not yet proposed",
                     "proposed": "proposed, waiting on the Register Checker",
                     "all": "proposed or not"}[status])),
        }

    @cadra_route("/api/v1/sap-links/propose", method="POST",
                 summary="Propose links for a batch of register assets",
                 success_status=200,
                 scopes=[SCOPE_REGISTER_MAKE],
                 request_schema={"type": "object", "required": ["asset_ids"],
                                 "properties": {
                                     "asset_ids": {"type": "array",
                                                   "items": {"type": "integer"},
                                                   "maxItems": BATCH_MAX},
                                     "note": {"type": "string"},
                                     "dry_run": {"type": "boolean"}}},
                 response_schema=_LINE_SCHEMA)
    def propose(self, **kwargs):
        body, error = _body({"asset_ids", "note", "dry_run"})
        if error:
            return error
        ids, error = _ids(body, "asset_ids")
        if error:
            return error
        assets = {a.id: a for a in _assets(ids).exists()}
        targets = request.env["nrs.sap.asset"].sudo()._confident_targets()
        scopes = _token_scopes()

        def fire(i):
            if i not in assets:
                return dict(_line(), asset_id=i, outcome="refused",
                            status=404, code=ERR_NOT_FOUND,
                            message="There is no asset with id %s." % i,
                            details={"asset_id": i})
            a = assets[i]
            return _act(_line(a), lambda: a._sap_link_propose(
                targets=targets, note=body.get("note"), scopes=scopes))
        return _run(ids, fire, body.get("dry_run", False), "propose")

    # ── the checker's queue ───────────────────────────────────────────

    @cadra_route("/api/v1/sap-links", method="GET",
                 summary="SAP link proposals — by default those waiting on "
                         "the Register Checker",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 response_schema={"type": "array", "items": LINK_SCHEMA},
                 query_params=[
                     {"name": "state", "description": "`proposed` (default), "
                      "`approved`, `returned` or `all`."},
                     {"name": "kind", "description": "`link` or `unlink`."},
                     {"name": "asset_id"},
                     *PAGINATION_QUERY_PARAMS])
    def list_links(self, **kwargs):
        qs = get_params()
        state = _text_param(qs, "state") or "proposed"
        states = [k for k, _l in LINK_STATES]
        if state not in states + ["all"]:
            return err(ERR_INVALID_REQUEST, "`state` is one of %s or all."
                       % ", ".join(states),
                       details={"field": "state",
                                "allowed_values": states + ["all"]})
        domain = [] if state == "all" else [("state", "=", state)]
        kind = _text_param(qs, "kind")
        if kind:
            kinds = [k for k, _l in LINK_KINDS]
            if kind not in kinds:
                return err(ERR_INVALID_REQUEST, "`kind` is one of %s."
                           % ", ".join(kinds),
                           details={"field": "kind", "allowed_values": kinds})
            domain.append(("kind", "=", kind))
        if qs.get("asset_id") is not None:
            try:
                domain.append(("asset_id", "=", int(qs["asset_id"])))
            except (TypeError, ValueError):
                return err(ERR_INVALID_REQUEST, "`asset_id` must be an id.",
                           details={"field": "asset_id"})
        page, next_cursor, total = paginate(
            request.env["nrs.sap.link"].sudo(), domain,
            limit=parse_limit(qs), cursor=qs.get("cursor"),
            descending=state != "proposed")
        held = set(_token_scopes())
        return ok(data=[serialize_link(l, held) for l in page],
                  pagination={"next_cursor": next_cursor,
                              "previous_cursor": None,
                              "total_estimate": total})

    def _decide(self, approve):
        allowed = {"link_ids", "dry_run"} | (set() if approve else {"reason"})
        body, error = _body(allowed)
        if error:
            return error
        ids, error = _ids(body, "link_ids")
        if error:
            return error
        links = {l.id: l for l in
                 request.env["nrs.sap.link"].sudo().browse(ids).exists()}
        scopes = _token_scopes()

        def fire(i):
            if i not in links:
                return dict(_line(), link_id=i, outcome="refused", status=404,
                            code=ERR_NOT_FOUND,
                            message="There is no SAP link proposal %s." % i,
                            details={"link_id": i})
            link = links[i]
            return _act(_line(link=link), lambda: link._decide(
                approve, reason=body.get("reason"), scopes=scopes))
        return _run(ids, fire, body.get("dry_run", False),
                    "approve" if approve else "return")

    @cadra_route("/api/v1/sap-links/approve", method="POST",
                 summary="Approve SAP link proposals (or undos): the number "
                         "is written; nothing is sent to SAP",
                 success_status=200,
                 scopes=[SCOPE_REGISTER_CHECK],
                 request_schema={"type": "object", "required": ["link_ids"],
                                 "properties": {
                                     "link_ids": {"type": "array",
                                                  "items": {"type": "integer"},
                                                  "maxItems": BATCH_MAX},
                                     "dry_run": {"type": "boolean"}}},
                 response_schema=_LINE_SCHEMA)
    def approve(self, **kwargs):
        return self._decide(True)

    @cadra_route("/api/v1/sap-links/return", method="POST",
                 summary="Return SAP link proposals to the maker, with a "
                         "reason",
                 success_status=200,
                 scopes=[SCOPE_REGISTER_CHECK],
                 request_schema={"type": "object",
                                 "required": ["link_ids", "reason"],
                                 "properties": {
                                     "link_ids": {"type": "array",
                                                  "items": {"type": "integer"},
                                                  "maxItems": BATCH_MAX},
                                     "reason": {"type": "string"},
                                     "dry_run": {"type": "boolean"}}},
                 response_schema=_LINE_SCHEMA)
    def return_(self, **kwargs):
        return self._decide(False)

    @cadra_route("/api/v1/assets/<int:id>/sap-link/undo", method="POST",
                 summary="Propose undoing an asset's SAP link, with a reason",
                 scopes=[SCOPE_REGISTER_MAKE],
                 error_statuses=(404, 409),
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": {"reason": {"type": "string"}}},
                 response_schema=LINK_SCHEMA)
    def undo(self, id, **kwargs):
        body, error = _body({"reason"})
        if error:
            return error
        asset = _assets([id]).exists()
        if not asset:
            return err(ERR_NOT_FOUND, "Asset %d not found" % id, status=404)
        try:
            with request.env.cr.savepoint():
                link = asset._sap_unlink_propose(body.get("reason"),
                                                 scopes=_token_scopes())
        except GateRefused as e:
            return gate_refusal(e)
        return serialize_link(link)

    # ── §2: the contested list ────────────────────────────────────────

    @cadra_route("/api/v1/sap-links/contested", method="GET",
                 summary="SAP records two or more Cadra assets point at, "
                         "side by side",
                 scopes=[SCOPE_SAP_MIRROR_READ],
                 query_params=[{"name": "office"}, {"name": "flagged",
                               "description": "`true` / `false`."},
                               {"name": "limit"}, {"name": "offset"}])
    def contested(self, **kwargs):
        qs = get_params()
        office = _text_param(qs, "office")
        flagged_q = _text_param(qs, "flagged")
        if flagged_q not in (None, "true", "false"):
            return err(ERR_INVALID_REQUEST, "`flagged` is true or false.",
                       details={"field": "flagged"})
        offset, limit = _offset(qs), _page_limit(qs, 50)
        error = _paging_error(offset, limit)
        if error:
            return error
        Sap = request.env["nrs.sap.asset"].sudo()
        targets = Sap._confident_targets()
        groups = {sid: aids for sid, aids in targets["claims"].items()
                  if len(aids) > 1}
        records = {s.id: s for s in Sap.browse(list(groups))}
        all_ids = [a for aids in groups.values() for a in aids]
        assets = {a.id: a for a in _assets(all_ids)}
        flags = _assets(all_ids)._sap_duplicate_flags()
        open_links = {l.sap_record_id.id: l for l in
                      request.env["nrs.sap.link"].sudo().search(
                          [("state", "=", "proposed"),
                           ("sap_record_id", "in", list(groups))])}
        by_office, rows = {}, []
        for sid, aids in groups.items():
            rec = records[sid]
            number = rec.asset_number_norm
            flagged = all(flags.get(a) and flags[a].to_value == number
                          for a in aids)
            key = rec.office_code or None
            stats = by_office.setdefault(key, {"groups": 0, "assets": 0,
                                               "flagged": 0})
            stats["groups"] += 1
            stats["assets"] += len(aids)
            stats["flagged"] += int(flagged)
            if office and rec.office_code != office.upper():
                continue
            if flagged_q and (flagged_q == "true") != flagged:
                continue
            rows.append((rec, aids, flagged))
        rows.sort(key=lambda r: (r[0].office_code or "~", r[0].asset_number))
        page = rows[offset:offset + limit]
        Photo = request.env["nrs.asset.photo"].sudo()
        held = set(_token_scopes())
        items = []
        for rec, aids, flagged in page:
            members = []
            for aid in sorted(aids, key=lambda i: assets[i].asset_code or ""):
                a = assets[aid]
                photos = Photo.search([("asset_id", "=", aid)],
                                      order="id desc", limit=3)
                basis = targets["target"][aid][1]
                members.append(dict(
                    _asset_brief(a),
                    old_tag=a.legacy_asset_code or None,
                    serial_number=a.serial_number or None,
                    custodian=({"id": a.custodian_id.id,
                                "name": a.custodian_id.name}
                               if a.custodian_id else None),
                    created_at=_iso(a.create_date),
                    matched_by=basis,
                    photos={"count": Photo.search_count(
                        [("asset_id", "=", aid)]),
                        "latest": [{"id": p.id, "url":
                                    "/api/v1/assets/%d/photos/%d"
                                    % (aid, p.id)} for p in photos]},
                    duplicate_flag=_flag_brief(flags.get(aid))))
            pending = open_links.get(rec.id)
            items.append({"sap": _sap_brief(rec), "assets": members,
                          "flagged": flagged,
                          "link": serialize_link(pending, held)
                          if pending else None})
        return {
            "total_groups": len(rows),
            "total_assets": sum(len(r[1]) for r in rows),
            "offset": offset,
            "limit": limit,
            "by_office": [dict(office=k, **v) for k, v in sorted(
                by_office.items(),
                key=lambda kv: (-kv[1]["assets"], kv[0] or "~"))],
            "items": items,
            "sentence": (
                "%d SAP records are each pointed at by two or more Cadra "
                "assets (%d assets). One of each group may be proposed for "
                "the link, or the group flagged as a likely duplicate; "
                "nothing is merged, retired or deleted."
                % (len(groups), len(all_ids))),
        }

    @cadra_route("/api/v1/sap-links/contested/<int:sap_id>/propose",
                 method="POST",
                 summary="Propose linking ONE asset of a contested group",
                 scopes=[SCOPE_REGISTER_MAKE],
                 error_statuses=(404, 409),
                 request_schema={"type": "object", "required": ["asset_id"],
                                 "properties": {
                                     "asset_id": {"type": "integer"},
                                     "note": {"type": "string"}}},
                 response_schema=LINK_SCHEMA)
    def contested_propose(self, sap_id, **kwargs):
        body, error = _body({"asset_id", "note"})
        if error:
            return error
        rec = request.env["nrs.sap.asset"].sudo().browse(sap_id).exists()
        if not rec:
            return err(ERR_NOT_FOUND, "SAP record %d not found" % sap_id,
                       status=404)
        aid = body.get("asset_id")
        if not isinstance(aid, int) or isinstance(aid, bool):
            return err(ERR_INVALID_REQUEST, "`asset_id` must be an asset id.",
                       details={"field": "asset_id"})
        asset = _assets([aid]).exists()
        if not asset:
            return err(ERR_NOT_FOUND, "Asset %d not found" % aid, status=404)
        try:
            with request.env.cr.savepoint():
                link = asset._sap_link_propose(sap_record=rec,
                                               note=body.get("note"),
                                               scopes=_token_scopes())
        except GateRefused as e:
            return gate_refusal(e)
        return serialize_link(link)

    @cadra_route("/api/v1/sap-links/contested/<int:sap_id>/flag",
                 method="POST",
                 summary="Flag a contested group as a likely duplicate, with "
                         "a note — nothing is merged or deleted",
                 success_status=200,
                 scopes=[SCOPE_REGISTER_MAKE],
                 error_statuses=(404, 409),
                 request_schema={"type": "object", "required": ["note"],
                                 "properties": {"note": {"type": "string"}}})
    def contested_flag(self, sap_id, **kwargs):
        body, error = _body({"note"})
        if error:
            return error
        rec = request.env["nrs.sap.asset"].sudo().browse(sap_id).exists()
        if not rec:
            return err(ERR_NOT_FOUND, "SAP record %d not found" % sap_id,
                       status=404)
        try:
            with request.env.cr.savepoint():
                group = request.env["nrs.asset"]._sap_flag_duplicate(
                    rec, body.get("note"), scopes=_token_scopes())
        except GateRefused as e:
            return gate_refusal(e)
        flags = group._sap_duplicate_flags()
        return {"sap": _sap_brief(rec),
                "assets": [dict(_asset_brief(a),
                                duplicate_flag=_flag_brief(flags.get(a.id)))
                           for a in group],
                "sentence": "%d Cadra assets flagged as a likely duplicate of "
                            "SAP asset %s. Nothing was merged, retired or "
                            "deleted." % (len(group), rec.asset_number)}
