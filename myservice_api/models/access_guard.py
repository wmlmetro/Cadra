"""What the API may never do to group membership — refused on the model.

Handoff 42 §2 and §3. Report 41 §G measured what refuses a privilege
escalation in Cadra today, and the answer was NOTHING: every v1 route runs
`sudo()`, which never consults the Access Rights ACL, and Odoo's own guards
on `group_ids` are only *portal and internal are exclusive* and *one
administrator must remain*. So a route that wrote `group_ids` would let any
`admin`-scoped caller grant `base.group_system` to anybody — and the sharp
case is an API CREDENTIAL holding `admin`, whose user is deliberately not a
system administrator, making itself one. The access record would write it
down and refuse nothing.

Two rulings, quoted from the handoff, and this file is where they hold:

  **Ruling 1 · `base.group_system` is not grantable through the API. At
  all.** *Not by an administrator, not by a credential, not with a
  confirmation flag. Making someone a system administrator stays a thing you
  do in the Odoo back office, signed in as a person with a password.* And it
  generalises: *no `base.*` group is grantable over the API. Only our own
  four — Asset User, Asset Manager, Tag-Issuing Unit, Auditor. If a fifth
  must be grantable later, that is a decision with a name on it.*

  **Ruling 2 · Nobody grants themselves a role.** *A caller may REMOVE their
  own roles — that is a downgrade and a person locking themselves out is
  their own problem, within Odoo's last-administrator guard. A caller may
  NOT add a role to their own account. Somebody else does it.*


WHERE THE REFUSAL LIVES
-----------------------

On the model, under every writer — not on the route. `access_change.py`'s
module docstring enumerates SIX structurally different directions the
membership relation is written from, and records that the list was wrong
twice before somebody enumerated it. A guard on `POST /users/<id>/roles` is a
guard on one of the six doors; this one sits beside the recorder's hooks, on
`res.users` and `res.groups`, so a future route, the user side, the group
side, an implication edge and a delete all meet it. It is the same argument
as `nrs.asset._assert_change_is_approved` and `_assert_disposed_is_terminal`:
a rule in a route is a rule with the other doors round it.


HOW IT TELLS OUR API FROM THE SYSTEM
------------------------------------

**An authenticated API request, and nothing else.** `require_jwt`
(`controllers/utils.py`) validates the bearer token, binds the token's user
onto the request's environment and leaves the claims on
`request.jwt_claims`. So the test is:

    bool(request) and getattr(request, 'jwt_claims', None)

`odoo.http.request` is a werkzeug `LocalStack` proxy: outside an HTTP
request `bool(request)` is False — and `getattr(request, 'x', None)` RAISES
`RuntimeError: object is not bound`, which is why the truth test comes
first. Inside an HTTP request that did not pass `require_jwt` (the back
office, a web-client RPC, an upgrade started from the Apps screen) the
attribute is simply absent.

**Deliberately NOT a context key.** A key is a way round that any RPC
caller could set on its own call, and the whole point of this file is that
the way round does not exist — cf. `_assert_disposed_is_terminal`, which
has no flag for the same reason. The two cases are told apart by a fact
about the request that the caller did not put there.

What is therefore deliberately NOT guarded — anything that runs without a
JWT, which is every legitimate system writer of `base.*` groups:
`scripts/bootstrap.py` (`odoo shell`, uid 1), `api_client.
_provision_client_user` (sudo, from a shell, a migration or the back
office), the 19.0.3.2.0 migration, the eight security XML files that
re-apply on every module upgrade, `auth_signup`'s template `copy()`, the
mail module's notification-type self-write, core multi-company, and an
administrator signed in to the back office as a person. *A guard that has
to be switched off to install the product is a guard that will be found
switched off* — this one never has to be, because an install is not an API
request.


THE TRADE IT MAKES
------------------

Diff-then-raise AFTER `super()`, exactly as the recorder does, because
`vals` cannot be parsed honestly: `(6, 0, ids)` does not say what it
replaced, `_default_groups()` puts a new user in groups the create never
mentioned, and a `Command.link` on a row already there is a no-op. So the
real membership is snapshotted before and after (the recorder's own
snapshot helpers, reused rather than copied), and the diff is judged. A
refusal is an `AccessError`, which `cadra_endpoint` maps to `403 forbidden`
with the sentence as the message — and an exception rolls the transaction
back, the recorder's rows included, so a refused change leaves no trace in
the access record either. `tests/test_access_guard.py` counts the record
before and after every refusal.

The guard class is registered AFTER the recorder in `models/__init__.py`, so
it wraps the recorder: snapshot, recorder snapshot, core write, recorder
rows, judgement. Reorder the imports and the recorder wraps the guard
instead, which still works but reads the wrong way round.
"""

from odoo import models, api, _
from odoo.exceptions import AccessError
from odoo.http import request

from .access_recorder import _field_name, _USER_GROUPS_FIELDS, _GROUP_USERS_FIELDS
from .role_names import role_alias

#: The ONLY groups an authenticated API caller may grant or remove — ruling
#: 1, generalised. `GET /roles` reads this to publish `grantable`, so there is
#: one constant and two readers. A fifth entry is a decision with a name on
#: it (handoff 42 §2), not a convenience.
API_GRANTABLE_XMLIDS = (
    'myservice_asset_register.group_asset_user',
    # The fifth entry, with the name on it: handoff 47 ruling 3 created the
    # Asset Officer — the role between reading the register and running it —
    # and a role administrators cannot grant from the Users screen is a role
    # that does not exist.
    'myservice_asset_register.group_asset_officer',
    'myservice_asset_register.group_asset_manager',
    'myservice_asset_register.group_tag_issuing_unit',
    'myservice_api.group_auditor',
    # Handoff 57 (kept by 58): the five receipt-gate roles,
    # named by the handoff (§2e) — an administrator grants them on the Users
    # screen, or the people in the room have no way to hold them.
    'myservice_asset_register.group_iad_vfm_officer',
    'myservice_asset_register.group_iad_vfm_approver',
    'myservice_asset_register.group_asset_controller',
    'myservice_asset_register.group_register_maker',
    'myservice_asset_register.group_register_checker',
    # Handoff 66: the audit team, granted on the Users screen like the gate
    # roles, for the same reason.
    'myservice_asset_register.group_audit_capturer',
    'myservice_asset_register.group_audit_reviewer',
)


def forget_group_memberships(env):
    """Drop the registry's cached group memberships, in THIS process.

    Odoo 19 caches a user's group ids per user (`res.users._get_group_ids`,
    an ormcache) the first time membership is asked. A grant that is
    REFUSED (`_assert_grants_allowed`, the role exclusions) or PREVIEWED
    (`POST /users/<id>/roles` with `dry_run`) writes the groups inside a
    savepoint, reads membership — which fills the cache with the groups it
    is about to undo — and rolls the savepoint back. A savepoint rollback
    does not reset the registry's caches, so the person went on HOLDING the
    refused role: every later `/auth/login` minted its scopes, until some
    other group write cleared the cache (handoff 66: the capturer persona's
    token carried `audit:review` after a refused capturer + reviewer grant;
    reproduced, four logins of four). Called before every such refusal is
    raised and after every preview is rolled back. Nothing is cached again
    between this call and the rollback: the caller raises at once."""
    env.registry.clear_cache()
    env.registry.clear_cache('groups')


def api_caller():
    """`(uid, claims)` when this write is happening inside an authenticated
    API request; `None` otherwise.

    The truth test on the proxy comes FIRST: an unbound `request` raises on
    attribute access rather than answering None.
    """
    if not request:
        return None
    claims = getattr(request, 'jwt_claims', None)
    if not claims:
        return None
    return claims.get('uid'), claims


def _grantable_groups(env):
    """The installed `res.groups` behind `API_GRANTABLE_XMLIDS`, sudo'd.

    A missing xmlid is skipped rather than raised on, for the reason
    `scopes_for_user` gives: a role's module may not be installed on this
    tenant, and a guard that failed on that would refuse every write.
    """
    Groups = env['res.groups'].sudo()
    groups = Groups.browse()
    for xmlid in API_GRANTABLE_XMLIDS:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            groups |= group.sudo()
    return groups


# Translated at the call, not at import, and the strings are LITERALS inside
# the functions because Odoo's PO extractor scans literal arguments — the
# same convention as `access_change.py`.

def _role_name(group, full=False):
    """The name a refusal says: the published alias where there is one
    (`role_names.py`), else what this sentence always said — `full_name` for
    the offending group, `name` elsewhere. Report 42 §F.5: the offending group
    was *Role / Administrator* where `/users` said *System Administrator*.
    Only the alias changes; every other group reads as it did (verification
    pass, report 44 §G)."""
    group = group.sudo()
    return role_alias(group) or (full and group.full_name) or group.name


def _not_grantable_message(env, group):
    names = ", ".join(_role_name(g) for g in _grantable_groups(env))
    return _(
        "Over the API only these roles can be granted or removed: %(roles)s. "
        "'%(group)s' is not one of them. Making somebody a system "
        "administrator, or changing any other Odoo group, is done in the "
        "Odoo back office, signed in as a person.",
        roles=names,
        group=_role_name(group, full=True),
    )


def _self_grant_message(user, group):
    return _(
        "Nobody grants themselves a role. %(login)s asked to add %(role)s "
        "to their own account; another administrator has to do that. "
        "Removing your own roles is allowed.",
        login=user.sudo().login,
        role=_role_name(group),
    )


def _no_user_unlink_message():
    return _("An account cannot be deleted over the API. Deactivate it "
             "instead.")


def _no_group_create_or_unlink_message():
    return _("Groups cannot be created or deleted over the API.")


def _no_implication_change_message(groups):
    return _(
        "What a group means cannot be changed over the API (%(group)s).",
        group=", ".join(_role_name(g) for g in groups) or "?",
    )


def _assert_api_change_is_allowed(env, user, added, removed, *,
                                  also_allowed=frozenset()):
    """The two rulings, applied to one user's diff.

    `added` and `removed` are sets of `res.groups` ids. `also_allowed` is
    extra ids that are not a grant at all — `_default_groups()` on a create,
    which Odoo puts every new internal user in whether the caller named them
    or not.

    Ruling 1 first: a group outside the grantable set refuses whichever way
    it moved, so the credential asking for `base.group_system` on its own
    account gets THIS sentence and not the self-grant one. Ruling 2 second:
    an addition to the caller's own account refuses; a removal does not.
    `env.uid` is the token's user — `require_jwt` binds it with
    `update_env(user=uid)` and the routes' `sudo()` keeps it — and it is the
    same uid the recorder names as the actor, so the refusal and the record
    agree about who "you" is.
    """
    allowed = set(_grantable_groups(env).ids) | set(also_allowed)
    offending = sorted((set(added) | set(removed)) - allowed)
    Groups = env['res.groups'].sudo()
    if offending:
        forget_group_memberships(env)
        raise AccessError(_not_grantable_message(env, Groups.browse(offending[0])))
    if added and user.id == env.uid:
        forget_group_memberships(env)
        raise AccessError(_self_grant_message(user, Groups.browse(min(added))))


class ResUsersAccessGuard(models.Model):
    """Rulings 1 and 2 on the user side; no deletes over the API."""

    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """A new account may land only in the grantable set and in what
        `_default_groups()` puts every internal user in anyway.

        Judged on the created records, not on `vals`, for the reasons in the
        module docstring. Ruling 2 cannot apply: a new user is never the
        caller.
        """
        users = super().create(vals_list)
        if api_caller():
            defaults = frozenset(self._default_groups().ids)
            after = users._access_membership_snapshot()
            for user in users:
                _assert_api_change_is_allowed(
                    self.env, user, after.get(user.id, frozenset()),
                    frozenset(), also_allowed=defaults)
        return users

    def write(self, vals):
        """Snapshot, write, snapshot, judge — only when the groups field is in
        `vals` AND the writer is an API caller, so a login's `login_date`
        write pays for nothing."""
        field = _field_name(self, _USER_GROUPS_FIELDS)
        judge = bool(field and field in vals and api_caller())
        before = self._access_membership_snapshot() if judge else None
        result = super().write(vals)
        if judge:
            after = self._access_membership_snapshot()
            for user in self:
                was = before.get(user.id, frozenset())
                now = after.get(user.id, frozenset())
                _assert_api_change_is_allowed(self.env, user, now - was, was - now)
        return result

    def unlink(self):
        """Handoff 43 deactivates; nothing over the API deletes an account,
        and the cascade on the membership table is the reason."""
        if api_caller():
            raise AccessError(_no_user_unlink_message())
        return super().unlink()


class ResGroupsAccessGuard(models.Model):
    """The same two rulings on the group side, and no structural change to
    groups at all over the API — a group's existence and what it IMPLIES
    are what `admin` scope was never meant to reach."""

    _inherit = 'res.groups'

    @api.model_create_multi
    def create(self, vals_list):
        if api_caller():
            raise AccessError(_no_group_create_or_unlink_message())
        return super().create(vals_list)

    def unlink(self):
        if api_caller():
            raise AccessError(_no_group_create_or_unlink_message())
        return super().unlink()

    def write(self, vals):
        """`implied_ids` / `implied_by_ids` refuse outright BEFORE the write:
        on Odoo 19 an implication edge grants every member of a group the
        rights of another while writing zero membership rows
        (`access_change.py`, case 4), so there is no diff to judge and
        nothing an API caller could legitimately mean by it.

        `user_ids` is membership from the other side — the SAME change as
        `res.users.write`, judged by the same two rules on the per-user diff
        the recorder's group snapshot gives."""
        caller = api_caller()
        if caller and ('implied_ids' in vals or 'implied_by_ids' in vals):
            raise AccessError(_no_implication_change_message(self))
        users_field = _field_name(self, _GROUP_USERS_FIELDS)
        judge = bool(caller and users_field and users_field in vals)
        before = self._access_group_snapshot() if judge else None
        result = super().write(vals)
        if judge:
            after = self._access_group_snapshot()
            Users = self.env['res.users'].sudo()
            for group in self:
                was = before.get(group.id, (frozenset(), frozenset()))[0]
                now = after.get(group.id, (frozenset(), frozenset()))[0]
                for user in Users.browse(sorted(now - was)):
                    _assert_api_change_is_allowed(
                        self.env, user, {group.id}, set())
                for user in Users.browse(sorted(was - now)):
                    _assert_api_change_is_allowed(
                        self.env, user, set(), {group.id})
        return result
