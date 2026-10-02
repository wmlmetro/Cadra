"""Who has what — the accounts on this tenant and the access each one holds.

Handoff 41 §4B. Three routes, every one of them a READ:

    GET /api/v1/roles                 the role vocabulary          admin
    GET /api/v1/users                 the accounts, paged          admin
    GET /api/v1/users/<int:user_id>   one account                  admin

**This module adds no writer.** Nothing here touches `group_ids`,
`user_ids` or `implied_ids`; nothing here creates, writes or unlinks a
`res.users` or a `res.groups`. The forward record of membership changes
(`models/access_change.py`) is on the models, not on any route, so the day a
later handoff adds a writer it is recorded without this file changing — and
`myservice_api/tests/test_users_endpoint.py` asserts that calling all three
routes leaves that record, and the membership relation itself, exactly as
long as it found them.


DIRECT AND EFFECTIVE ARE TWO QUESTIONS, AND ON ODOO 19 THEY HAVE TWO ANSWERS
---------------------------------------------------------------------------

"Which groups is this account IN" and "which groups does this account
HOLD" used to be the same table. On Odoo 15 the transitive closure of
`implied_ids` was materialised into `res_groups_users_rel`, so an Asset
Manager had a membership row for Asset User too. **On Odoo 19 it is not.**
`res.groups.all_implied_ids` is an unstored compute, `res.users.all_group_ids`
is computed at read time from it (`compute='_compute_all_group_ids'`, no
`store=True`), and an implication edge writes ZERO membership rows —
`models/access_change.py`'s docstring, case 4, which is the case the record
was first designed without.

So on this tenant an Asset Manager is a MEMBER of one role and HOLDS two,
because `group_asset_manager` implies `group_asset_user`
(`myservice_asset_register/security/asset_security.xml`). A screen that
shows the membership table shows one group and is wrong about what the
person can do; a screen that shows the closure shows two and is wrong about
what somebody granted. Both are published, named so they cannot be read as
each other:

    roles_direct      rows in `res_groups_users_rel`      — what was GRANTED
    roles_effective   `user.all_group_ids`                — what is HELD

restricted in both cases to the role vocabulary below, so a `base.group_user`
or a `mail.group_mail_template_editor` is not reported as a Cadra role. Both
lists are in catalogue order, so two accounts holding the same roles print
the same list.

`scopes` is what a token minted for the account carries, and
`scopes_source` says where that comes from, because it is not the same place
for the two kinds of account:

  * a PERSON's session token is minted by `POST /auth/login` from
    `utils.scopes_for_user`, the union over `GROUP_SCOPES` of the groups the
    person HOLDS (`has_group` follows implication) — `scopes_source: roles`;
  * an API CREDENTIAL's token is minted by `POST /auth/token` from the
    client record's own `scopes` field, and its `res.users` exists so that
    the record of who affixed a tag names the credential rather than
    Administrator (`models/api_client.py`). The groups that user is put in
    are derived FROM the scopes (`utils.SCOPE_GROUPS`) for legibility on the
    user form; they are not where its token comes from. So its row carries
    `scopes_source: credential`, and `roles_direct` may well be non-empty
    without being the source of anything.


THE ROLE TABLE IS DERIVED, NOT RESTATED
---------------------------------------

`GET /roles` and the two role lists on every user row are both read off
`utils.GROUP_SCOPES` — the one table `POST /auth/login` mints from. The key
is the xmlid's tail with `group_` removed, the name is the group record's,
the scopes are the tuple from the table, and `implies` is the closure
intersected with the vocabulary. Nobody maintains a second copy of which
role produces which scope; `tests/test_users.py` asserts that every person's
`scopes` is exactly the union over `/roles` of their `roles_effective`,
which is the drift check for this file and for the login route together.

The one name this module chooses rather than reads is `base.group_system`,
published as "System Administrator": Odoo calls the group "Settings" (and
its `full_name` "Administration / Settings"), which means nothing to NRS
and reads as a permission over a settings page rather than as the
omnipotent role it is.


WHAT IS DELIBERATELY LEFT OUT
-----------------------------

The three structural logins (`__system__`, `public`, `portaltemplate` —
`models/audit_access._STRUCTURAL_LOGINS`, imported rather than copied) and
every share user (portal and public, `share = True`) are outside the list
AND outside the detail route, through ONE domain, so a `/users/<id>` can
never answer for an account `/users` would not list. No credential field
of any kind is published: `myservice.api.client` is reduced to its id, its
name, its public `client_id`, `active` and `is_test_credential`, and the
HTTP suite walks every key of every response against the same
credential-name pattern the audit reports are held to.
"""

from odoo import http
from odoo.http import request

from .v1 import cadra_route, PAGINATION_QUERY_PARAMS
from .utils import (
    ok, err, get_params, parse_limit, paginate,
    ERR_INVALID_REQUEST, ERR_NOT_FOUND, SCOPE_ADMIN,
    GROUP_SCOPES, scopes_for_user,
)
from .query_params import BadFilter, parse_bool, parse_enum
from ..models.audit_access import _STRUCTURAL_LOGINS


# ─── the vocabulary ──────────────────────────────────────────────────

KIND_PERSON = "person"
KIND_API_CREDENTIAL = "api_credential"

SCOPES_SOURCE_ROLES = "roles"
SCOPES_SOURCE_CREDENTIAL = "credential"

#: The one place a role's published name is chosen rather than read off the
#: group record. Odoo's own name for `base.group_system` is "Settings",
#: which to NRS reads as a permission over a settings page and not as the
#: omnipotent role `admin` is.
_PUBLISHED_NAMES = {
    "base.group_system": "System Administrator",
}


def role_key(xmlid):
    """`myservice_asset_register.group_asset_manager` → `asset_manager`;
    `base.group_system` → `system`. The published, stable key of a role."""
    tail = xmlid.rsplit(".", 1)[-1]
    if tail.startswith("group_"):
        tail = tail[len("group_"):]
    return tail


#: Every role key, in `GROUP_SCOPES` order. This is the closed set the
#: `role` and `role_direct` filters are validated against, and the order
#: every role list on every row is sorted into.
ROLE_KEYS = tuple(role_key(xmlid) for xmlid, _scopes in GROUP_SCOPES)


def _humanise(key):
    return key.replace("_", " ").title()


def _resolved_roles(env):
    """`[(key, xmlid, scopes, group)]` in `GROUP_SCOPES` order.

    `group` is the `res.groups` record, sudo'd, or an EMPTY recordset when
    the xmlid is not installed on this tenant — `myservice_identity`,
    `myservice_security` and `myservice_staff_bus` are optional per
    deployment, and a vocabulary that failed on a missing addon would take
    the whole user list down with it. Same reasoning as `scopes_for_user`.
    """
    Groups = env["res.groups"].sudo()
    out = []
    for xmlid, scopes in GROUP_SCOPES:
        group = env.ref(xmlid, raise_if_not_found=False)
        group = group.sudo() if group else Groups.browse()
        out.append((role_key(xmlid), xmlid, tuple(scopes), group))
    return out


def role_catalogue(env):
    """The role vocabulary, as `GET /roles` publishes it: an ordered list of
    dicts, one per entry in `GROUP_SCOPES`, derived and never restated.

    `implies` is the keys of the OTHER roles in this vocabulary reachable
    through `all_implied_ids` — which on Odoo 19 is reflexive, so the role
    itself is removed before publication. A role whose group is not
    installed here is still listed, with `installed: false`, so a consumer
    can tell "this tenant does not have the role" from "the role does not
    exist".
    """
    resolved = _resolved_roles(env)
    catalogue = []
    for key, xmlid, scopes, group in resolved:
        if group:
            closure = set(group.all_implied_ids.ids) - {group.id}
            implies = [other_key for other_key, _x, _s, other in resolved
                       if other and other.id in closure]
            entry = {
                "key": key,
                "name": _PUBLISHED_NAMES.get(xmlid, group.name),
                "xmlid": xmlid,
                "scopes": sorted(scopes),
                "description": group.comment or None,
                "installed": True,
                "implies": implies,
            }
        else:
            entry = {
                "key": key,
                "name": _PUBLISHED_NAMES.get(xmlid, _humanise(key)),
                "xmlid": xmlid,
                "scopes": sorted(scopes),
                "description": None,
                "installed": False,
                "implies": [],
            }
        catalogue.append(entry)
    return catalogue


# ─── the accounts ────────────────────────────────────────────────────

def _users_model():
    """Sudo, and `active_test=False`: an archived account is still an
    account, and `?active=` is the filter — absent means both."""
    return request.env["res.users"].sudo().with_context(active_test=False)


def _users_base_domain():
    """The ONE domain both routes share, so the detail route can never
    answer for an account the list would not show."""
    return [
        ("login", "not in", list(_STRUCTURAL_LOGINS)),
        ("share", "=", False),
    ]


def _clients_by_user(user_ids=None):
    """`{user_id: myservice.api.client}` — ONE search, never one per row.

    `active_test=False` on purpose: an archived credential's user is still
    an API credential and must not be re-reported as a mysterious person.
    """
    domain = [("user_id", "!=", False)]
    if user_ids is not None:
        domain.append(("user_id", "in", list(user_ids)))
    clients = request.env["myservice.api.client"].sudo().with_context(
        active_test=False).search(domain)
    return {c.user_id.id: c for c in clients if c.user_id}


def _role_term(field, key, resolved):
    """The domain term for `?role=` (`all_group_ids`, effective) or
    `?role_direct=` (`group_ids`, membership).

    `all_group_ids` IS searchable on Odoo 19:
    `res.users.all_group_ids` declares `search='_search_all_group_ids'`,
    which rewrites to `('group_ids.all_implied_ids', op, value)`, and
    `res.groups.all_implied_ids` declares `search='_search_all_implied_ids'`,
    which for `in` resolves the value to every group whose closure contains
    it. So the effective filter is applied on the ORM side and paginates
    honestly — `total_estimate` counts the whole answer, not a page.

    A role whose group is not installed on this tenant matches nothing,
    said as an empty answer rather than a 400: the key is in the published
    vocabulary, this tenant simply has nobody in it.
    """
    for role_key_, _xmlid, _scopes, group in resolved:
        if role_key_ == key:
            if not group:
                return ("id", "in", [])
            return (field, "in", [group.id])
    return ("id", "in", [])


def _users_domain(qs, resolved):
    """Query string → domain. Every value this cannot read is a `BadFilter`,
    turned into a 400 by the route — never dropped (`query_params.py`)."""
    domain = _users_base_domain()

    q = (qs.get("q") or "").strip()
    if q:
        domain += ["|", "|",
                   ("name", "ilike", q),
                   ("login", "ilike", q),
                   ("email", "ilike", q)]

    active = parse_bool("active", qs.get("active"))
    if active is not None:
        domain.append(("active", "=", active))

    is_api_client = parse_bool("is_api_client", qs.get("is_api_client"))
    if is_api_client is not None:
        client_user_ids = list(_clients_by_user().keys())
        domain.append(("id", "in" if is_api_client else "not in",
                       client_user_ids))

    role = parse_enum("role", qs.get("role"), ROLE_KEYS)
    if role is not None:
        domain.append(_role_term("all_group_ids", role, resolved))

    role_direct = parse_enum("role_direct", qs.get("role_direct"), ROLE_KEYS)
    if role_direct is not None:
        domain.append(_role_term("group_ids", role_direct, resolved))

    return domain


def _role_ref(key, xmlid, group):
    return {"key": key, "name": _PUBLISHED_NAMES.get(xmlid, group.name)}


def _iso(value):
    return value.isoformat() if value else None


def _user_row(user, resolved, client):
    """One published account. Every key is always present."""
    direct_ids = set(user.group_ids.ids)
    effective_ids = set(user.all_group_ids.ids)

    roles_direct = [_role_ref(key, xmlid, group)
                    for key, xmlid, _scopes, group in resolved
                    if group and group.id in direct_ids]
    # `via`: for a role held by implication, WHICH of the account's direct
    # groups implies it — any group, not only the eight in the vocabulary.
    # On `test19` the administrator holds Security Officer through Security
    # Manager, a group `/roles` does not list; without this the row would
    # show a role that nothing on the row explains. Empty for a direct role.
    roles_effective = []
    for key, xmlid, _scopes, group in resolved:
        if not group or group.id not in effective_ids:
            continue
        ref = _role_ref(key, xmlid, group)
        if group.id in direct_ids:
            ref["via"] = []
        else:
            ref["via"] = sorted(
                g.name for g in user.group_ids
                if g.id != group.id and group.id in g.all_implied_ids.ids)
        roles_effective.append(ref)

    if client:
        # The credential's token is minted by `/auth/token` from the client
        # record's own `scopes`, NOT from the groups its user is in — those
        # groups are derived from the scopes for legibility on the user
        # form (`utils.SCOPE_GROUPS`) and grant the token nothing.
        scopes = sorted(set((client.scopes or "").split()))
        scopes_source = SCOPES_SOURCE_CREDENTIAL
        api_client = {
            "id": client.id,
            "name": client.name,
            "client_id": client.client_id,
            "active": bool(client.active),
            "is_test_credential": bool(client.is_test_credential),
        }
        kind = KIND_API_CREDENTIAL
    else:
        # `user` is sudo'd, so `has_group` accepts a record that is not the
        # caller (`res.users.has_group` refuses otherwise).
        scopes = scopes_for_user(user)
        scopes_source = SCOPES_SOURCE_ROLES
        api_client = None
        kind = KIND_PERSON

    return {
        "id": user.id,
        "name": user.name,
        "login": user.login,
        "email": user.email or None,
        "active": bool(user.active),
        "kind": kind,
        "api_client": api_client,
        "roles_direct": roles_direct,
        "roles_effective": roles_effective,
        "scopes": scopes,
        "scopes_source": scopes_source,
        "last_login_at": _iso(user.login_date),
        "created_at": _iso(user.create_date),
    }


# ─── OpenAPI query parameters ────────────────────────────────────────

_USER_QUERY_PARAMS = [
    {"name": "q", "schema": {"type": "string"},
     "description": "Free-text search across name, login and email"},
    {"name": "role", "schema": {"type": "string", "enum": list(ROLE_KEYS)},
     "description": (
         "Accounts that HOLD this role once implication is applied — "
         "'who can do X'. `?role=asset_user` includes every Asset Manager, "
         "because Asset Manager implies Asset User.")},
    {"name": "role_direct",
     "schema": {"type": "string", "enum": list(ROLE_KEYS)},
     "description": (
         "Accounts that are MEMBERS of this role — a row in the membership "
         "table, what somebody granted. `?role_direct=asset_user` excludes "
         "an Asset Manager who was never granted Asset User directly.")},
    {"name": "active", "schema": {"type": "boolean"},
     "description": "`true` or `false`. Absent returns both."},
    {"name": "is_api_client", "schema": {"type": "boolean"},
     "description": ("`true` for API credentials only, `false` for people "
                     "only. Absent returns both.")},
    *PAGINATION_QUERY_PARAMS,
]


# ─── controller ──────────────────────────────────────────────────────

class CadraUsersV1(http.Controller):

    # ── GET /api/v1/roles ────────────────────────────────────────────

    @cadra_route("/api/v1/roles", method="GET",
                 summary="The role vocabulary and the scopes each role produces",
                 scopes=[SCOPE_ADMIN],
                 response_schema={"type": "array",
                                  "items": {"$ref": "#/components/schemas/Role"}})
    def list_roles(self, **kwargs):
        """One entry per `GROUP_SCOPES` row, derived rather than restated."""
        return ok(data=role_catalogue(request.env))

    # ── GET /api/v1/users ────────────────────────────────────────────

    @cadra_route("/api/v1/users", method="GET",
                 summary="The accounts on this tenant and what each one holds",
                 scopes=[SCOPE_ADMIN],
                 query_params=_USER_QUERY_PARAMS,
                 response_schema={"type": "array",
                                  "items": {"$ref": "#/components/schemas/User"}})
    def list_users(self, **kwargs):
        qs = get_params()
        resolved = _resolved_roles(request.env)
        try:
            domain = _users_domain(qs, resolved)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        page, next_cursor, total = paginate(
            _users_model(), domain,
            limit=parse_limit(qs), cursor=qs.get("cursor"),
        )
        clients = _clients_by_user(page.ids)
        return ok(
            data=[_user_row(u, resolved, clients.get(u.id)) for u in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── GET /api/v1/users/<id> ───────────────────────────────────────

    @cadra_route("/api/v1/users/<int:user_id>", method="GET",
                 summary="One account and what it holds",
                 scopes=[SCOPE_ADMIN],
                 response_schema={"$ref": "#/components/schemas/User"},
                 error_statuses=(404,))
    def get_user(self, user_id, **kwargs):
        """Same row as the list. 404 for a missing id, a structural login or
        a share user — through the same domain, so the two routes cannot
        disagree about who is an account."""
        user = _users_model().search(
            [("id", "=", int(user_id))] + _users_base_domain(), limit=1)
        if not user:
            return err(ERR_NOT_FOUND, f"User {user_id} not found", status=404)
        resolved = _resolved_roles(request.env)
        clients = _clients_by_user([user.id])
        return ok(data=_user_row(user, resolved, clients.get(user.id)))
