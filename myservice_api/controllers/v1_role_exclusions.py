"""Role exclusions over HTTP — handoff 58 §5 (Addendum A §4, rule 2).

The table is `nrs.role.exclusion` (`models/role_exclusion.py`), and so is the
rule: a grant that would give one person both roles of an active exclusion
is refused on the model, under every writer — `POST /users/<id>/roles`
included, which answers it `403 forbidden` with the model's sentence. These
routes only read and edit the table, and list who ALREADY holds a forbidden
pair: nothing is revoked (§5); deciding is the owner's.

* `GET  /api/v1/settings/role-exclusions` — `settings:read`.
* `POST /api/v1/settings/role-exclusions` — `settings:write`.
* `PATCH /api/v1/settings/role-exclusions/<id>` — `settings:write`; `active`
  and `reason` only. The two roles of an exclusion are its identity: a
  different pair is a new row, so the record of who turned which one off
  keeps meaning what it said.
* `GET  /api/v1/settings/conflicting-grants` — `settings:write`.

There is no DELETE: switch an exclusion off. Every create and change writes
the configuration record (`cadra.role_exclusion.<id>`).
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_SETTINGS_READ,
    SCOPE_SETTINGS_WRITE,
    err,
    get_params,
    ok,
    refuse_unwritable,
)
from .v1 import cadra_route
from .v1_users import _resolved_roles

_ROLE = {"type": "object", "properties": {
    "key": {"type": "string"}, "name": {"type": "string"}}}
_EXCLUSION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "role_a": _ROLE,
        "role_b": _ROLE,
        "active": {"type": "boolean"},
        "reason": {"type": "string"},
        "holders": {"type": "integer",
                    "description": "People (not API credentials) who hold "
                                   "both roles now, implication included."},
    },
}
_POST_KEYS = ("role_a", "role_b", "reason")
_PATCH_KEYS = ("active", "reason")


def _roles(env):
    """`{key: group}` and `{group_id: key}` over the role vocabulary, less
    `system` — an exclusion is between the roles people are given here."""
    by_key, by_id = {}, {}
    for key, _xmlid, _scopes, group in _resolved_roles(env):
        if group and key != "system":
            by_key[key] = group
            by_id[group.id] = key
    return by_key, by_id


def _role(group, by_id):
    from ..models.access_guard import _role_name
    return {"key": by_id.get(group.id), "name": _role_name(group)}


def _row(rec, by_id, holders):
    return {
        "id": rec.id,
        "role_a": _role(rec.group_a, by_id),
        "role_b": _role(rec.group_b, by_id),
        "active": bool(rec.active),
        "reason": rec.reason or "",
        "holders": len(holders.get(rec.id, ())),
    }


def _exclusions():
    return request.env["nrs.role.exclusion"].sudo().with_context(
        active_test=False)


class CadraRoleExclusionsV1(http.Controller):

    @cadra_route("/api/v1/settings/role-exclusions", method="GET",
                 summary="The role combinations nobody may be granted",
                 scopes=[SCOPE_SETTINGS_READ],
                 response_schema={"type": "array", "items": _EXCLUSION_SCHEMA})
    def list_exclusions(self, **kwargs):
        _by_key, by_id = _roles(request.env)
        recs = _exclusions().search([], order="id")
        holders = recs._holders()
        return [_row(r, by_id, holders) for r in recs]

    @cadra_route("/api/v1/settings/role-exclusions", method="POST",
                 summary="Forbid one person holding two roles",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": list(_POST_KEYS),
                     "properties": {
                         "role_a": {"type": "string"},
                         "role_b": {"type": "string"},
                         "reason": {"type": "string"},
                     },
                 },
                 request_example={"role_a": "register_maker",
                                  "role_b": "register_checker",
                                  "reason": "A registration is made by one "
                                            "person and checked by another"},
                 response_schema=_EXCLUSION_SCHEMA)
    def create_exclusion(self, **kwargs):
        body = get_params()
        rejected = [k for k in body if k not in _POST_KEYS]
        if rejected:
            return refuse_unwritable(rejected, _POST_KEYS)
        by_key, by_id = _roles(request.env)
        for field in ("role_a", "role_b"):
            if not isinstance(body.get(field), str) \
                    or body.get(field) not in by_key:
                return err(ERR_INVALID_REQUEST,
                           "`%s` must be one of: %s"
                           % (field, ", ".join(sorted(by_key))),
                           details={"field": field,
                                    "allowed_values": sorted(by_key)})
        reason = body.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return err(ERR_INVALID_REQUEST,
                       "An exclusion needs a `reason`, in words",
                       details={"field": "reason"})
        rec = _exclusions().create({
            "group_a": by_key[body["role_a"]].id,
            "group_b": by_key[body["role_b"]].id,
            "reason": reason.strip(),
        })
        return _row(rec, by_id, rec._holders())

    @cadra_route("/api/v1/settings/role-exclusions/<int:id>", method="PATCH",
                 summary="Switch an exclusion on or off, or reword its reason",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "properties": {"active": {"type": "boolean"},
                                    "reason": {"type": "string"}},
                 },
                 request_example={"active": False},
                 response_schema=_EXCLUSION_SCHEMA)
    def patch_exclusion(self, id, **kwargs):
        rec = _exclusions().browse(int(id)).exists()
        if not rec:
            return err(ERR_NOT_FOUND, f"Role exclusion {id} not found",
                       status=404)
        body = get_params()
        rejected = [k for k in body if k not in _PATCH_KEYS]
        if rejected:
            return refuse_unwritable(rejected, _PATCH_KEYS)
        vals = {}
        if "active" in body:
            if not isinstance(body["active"], bool):
                return err(ERR_INVALID_REQUEST, "`active` must be true or false",
                           details={"field": "active"})
            vals["active"] = body["active"]
        if "reason" in body:
            if not isinstance(body["reason"], str) or not body["reason"].strip():
                return err(ERR_INVALID_REQUEST,
                           "An exclusion needs a `reason`, in words",
                           details={"field": "reason"})
            vals["reason"] = body["reason"].strip()
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable fields supplied",
                       details={"writable": list(_PATCH_KEYS)})
        rec.write(vals)
        _by_key, by_id = _roles(request.env)
        return _row(rec, by_id, rec._holders())

    @cadra_route("/api/v1/settings/conflicting-grants", method="GET",
                 summary="People who already hold a combination the "
                         "exclusion table forbids",
                 scopes=[SCOPE_SETTINGS_WRITE])
    def conflicting_grants(self, **kwargs):
        """Measured now, over the ACTIVE exclusions, effective membership.
        People only — an API credential's groups are derived from its scopes
        and it is outside rule 2 (`models/role_exclusion.py`). Nothing here
        revokes anything."""
        _by_key, by_id = _roles(request.env)
        # `active` named, not left to the request's `active_test` (see
        # `models/role_exclusion._forbidden_pairs`).
        recs = _exclusions().search([("active", "=", True)], order="id")
        people = {}
        for rec in recs:
            for user in rec._holders()[rec.id]:
                entry = people.setdefault(user.id, {
                    "user": {"id": user.id, "name": user.name,
                             "login": user.login, "active": bool(user.active)},
                    "pairs": []})
                entry["pairs"].append({
                    "exclusion_id": rec.id,
                    "role_a": _role(rec.group_a, by_id),
                    "role_b": _role(rec.group_b, by_id),
                    "reason": rec.reason or "",
                })
        rows = [people[k] for k in sorted(people)]
        total = len(rows)
        if total:
            statement = (
                "%d %s a combination the exclusion table forbids. Nothing "
                "has been revoked; deciding is the owner's."
                % (total, "person holds" if total == 1 else "people hold"))
        else:
            statement = ("Nobody holds a combination the exclusion table "
                         "forbids.")
        body = ok(data=rows)
        # The denominator and the sentence ride in `meta`, beside the
        # request id, so `data` stays the list every list route returns.
        body["meta"] = dict(body["meta"], total=total, statement=statement)
        return body
