"""
Cadra API v1 — Identity resource (read-only).

First-class queryable surface for the NRS/SAP-sourced `hr.employee`
data. Today identity arrives in the system through two side channels
(POST /integrations/sap/employee-sync and POST /integrations/employees/import)
but isn't queryable through the public API — consumers can't resolve
custodian/assignee references without going through the Odoo UI.

This module is read-only on purpose. Creates and SCIM provisioning live
in a later slice once the IdP federation story (PRD §10.8) is settled.

Sensitive HR fields (private_email, private_phone, bank_account_id,
identification_id, passport_id, marital, birthday) are never exposed.
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_NOT_FOUND,
    SCOPE_ASSETS_READ,
    SCOPE_IDENTITY_READ,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_assets import serialize_asset


# ─── helpers ─────────────────────────────────────────────────────────

def _ref(rec, name_field="name"):
    if not rec:
        return None
    return {"id": rec.id, "name": getattr(rec, name_field, None) or rec.display_name}


def _date(v):
    return v.isoformat() if v else None


def _resolve_manager(emp):
    """Look up the manager record by IR number from `sap_manager_ir`.

    Returns {id, ir_number, name} or None. Manager linkage is stored as
    a Char on the employee (SAP feeds the IR number, not the FK) so we
    resolve at read time. Returns None when the IR doesn't match any
    employee — common during partial imports.
    """
    if not emp.sap_manager_ir:
        return None
    mgr = emp.sudo().search([("ir_number", "=", emp.sap_manager_ir)], limit=1)
    if not mgr:
        return {"id": None, "ir_number": emp.sap_manager_ir, "name": None}
    return {"id": mgr.id, "ir_number": mgr.ir_number, "name": mgr.name}


# ─── serializer ──────────────────────────────────────────────────────

def serialize_employee(emp, *, include_manager=False):
    """Map an hr.employee record to a Cadra-shaped identity dict.

    `include_manager=True` resolves the manager IR to a {id, ir_number,
    name} block. Off by default in list responses to avoid N+1 lookups.
    """
    data = {
        "id": emp.id,
        "ir_number": emp.ir_number or None,
        "name": emp.name,
        "work_email": emp.work_email or None,
        "work_phone": emp.work_phone or None,
        "job_title": emp.job_title or None,
        "department": _ref(emp.department_id),
        "grade_level": emp.grade_level or None,
        "cost_centre": emp.cost_centre or None,
        "sap": {
            "user_id": emp.sap_user_id or None,
            "status": emp.sap_status or None,
            "department": emp.sap_department or None,
            "manager_ir_number": emp.sap_manager_ir or None,
            "last_sync": emp.sap_last_sync.isoformat() if emp.sap_last_sync else None,
            "sync_status": emp.sap_sync_status or None,
        },
        "location": _ref(emp.sap_location_id),
        "employment": {
            "start_date": _date(emp.employment_start_date),
            "end_date": _date(emp.employment_end_date),
        },
        "assets": {
            "count": emp.asset_count,
            "has_pending_retrieval": emp.has_pending_retrieval,
        },
        "active": emp.active,
        "created_at": emp.create_date.isoformat() if emp.create_date else None,
        "updated_at": emp.write_date.isoformat() if emp.write_date else None,
    }
    if include_manager:
        data["manager"] = _resolve_manager(emp)
    return data


# ─── domain builder ──────────────────────────────────────────────────

def _list_domain(qs):
    """Translate query-string filters into an Odoo domain.

    Filters (all optional):
      - q              : substring match on name OR ir_number (case-insensitive)
      - ir_number      : exact match
      - sap_status     : exact (active/suspended/on_leave/transferred/exited)
      - sap_sync_status: exact (synced/pending/error/never)
      - location_id    : exact sap_location_id FK
      - department_id  : exact department_id FK
      - grade_level    : exact match
      - active         : 'true' | 'false' (default true)
    """
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        domain += ["|", ("name", "ilike", q), ("ir_number", "ilike", q)]
    if qs.get("ir_number"):
        domain.append(("ir_number", "=", qs["ir_number"].strip()))
    if qs.get("sap_status"):
        domain.append(("sap_status", "=", qs["sap_status"]))
    if qs.get("sap_sync_status"):
        domain.append(("sap_sync_status", "=", qs["sap_sync_status"]))
    if qs.get("grade_level"):
        domain.append(("grade_level", "=", qs["grade_level"]))
    for client_fld, model_fld in (
        ("location_id", "sap_location_id"),
        ("department_id", "department_id"),
    ):
        val = qs.get(client_fld)
        if val not in (None, "", "null"):
            try:
                domain.append((model_fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    active_filter = qs.get("active")
    if active_filter in ("false", "False", False):
        domain.append(("active", "=", False))
    elif active_filter in ("true", "True", True):
        domain.append(("active", "=", True))
    else:
        domain.append(("active", "=", True))
    return domain


def _browse_or_404(emp_id):
    rec = request.env["hr.employee"].sudo().browse(int(emp_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Employee {emp_id} not found", status=404)
    return rec, None


# ─── controller ──────────────────────────────────────────────────────

class CadraIdentityV1(http.Controller):

    # ── List: GET /api/v1/identity/employees ───────────────────────

    @cadra_route("/api/v1/identity/employees", method="GET",
                 summary="List employees with filters and cursor pagination",
                 scopes=[SCOPE_IDENTITY_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search across name and IR number"},
                     {"name": "ir_number", "schema": {"type": "string"},
                      "description": "Exact IR number match"},
                     {"name": "sap_status", "schema": {"type": "string",
                       "enum": ["active", "suspended", "on_leave", "transferred", "exited"]}},
                     {"name": "sap_sync_status", "schema": {"type": "string",
                       "enum": ["synced", "pending", "error", "never"]}},
                     {"name": "location_id", "schema": {"type": "integer"},
                      "description": "Office location FK (sap_location_id)"},
                     {"name": "department_id", "schema": {"type": "integer"}},
                     {"name": "grade_level", "schema": {"type": "string"},
                      "description": "Exact grade level (e.g. 'GL 14')"},
                     {"name": "active", "schema": {"type": "boolean"}},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_employees(self, **kwargs):
        qs = get_params()
        Employee = request.env["hr.employee"].sudo()
        domain = _list_domain(qs)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Employee, domain,
            limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_employee(e) for e in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── Get single: GET /api/v1/identity/employees/<id> ────────────

    @cadra_route("/api/v1/identity/employees/<int:id>", method="GET",
                 summary="Get a single employee by id (resolves manager IR)",
                 scopes=[SCOPE_IDENTITY_READ])
    def get_employee(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        return serialize_employee(rec, include_manager=True)

    # ── Lookup by IR: GET /api/v1/identity/employees/by-ir/<ir> ────

    @cadra_route("/api/v1/identity/employees/by-ir/<string:ir_number>",
                 method="GET",
                 summary="Lookup employee by IR number (natural key from SAP)",
                 scopes=[SCOPE_IDENTITY_READ])
    def get_employee_by_ir(self, ir_number, **kwargs):
        rec = request.env["hr.employee"].sudo().search(
            [("ir_number", "=", ir_number.strip())], limit=1,
        )
        if not rec:
            return err(ERR_NOT_FOUND,
                       f"No employee with IR number {ir_number!r}", status=404)
        return serialize_employee(rec, include_manager=True)

    # ── Assets: GET /api/v1/identity/employees/<id>/assets ─────────

    @cadra_route("/api/v1/identity/employees/<int:id>/assets",
                 method="GET",
                 summary="Assets where this employee is the current custodian",
                 scopes=[SCOPE_IDENTITY_READ, SCOPE_ASSETS_READ],
                 query_params=[*PAGINATION_QUERY_PARAMS])
    def list_employee_assets(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        qs = get_params()
        Asset = request.env["nrs.asset"].sudo()
        domain = [("custodian_id", "=", rec.id)]
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
