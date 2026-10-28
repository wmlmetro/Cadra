"""The administrator override (handoff 70).

An administrator — a PERSON signed in through `/auth/login` whose account is
in `base.group_system` — may, when the tenant has switched it on, act at
every receipt gate, at both ends of a SAP link, and capture and review in
any open audit campaign, their own capture included. It lifts the four
segregation-of-duties rules (handoff 70 §1, S1–S4) and nothing else: a unit
must still be in the right state, a scanned tag must still match, a capture
still needs its device, its code and its room.

**Off by default, on every tenant, absent included.** NRS's Addendum A §4
and the PRD require two people at each control; the switch stays off on
NRS's tenant until NRS accepts in writing that administrators may act alone
(`docs/GO-LIVE.md`). Read with raw SQL, as `cadra.receipt.gated` is, so no
cache can answer for the row.

**Never a machine credential.** A token from `/auth/token` (Vendra's, the
SAP sync's) carries no `aud: frontend`; it never overrides, even if its user
were in the group. Outside an API request — the back office, a shell, a
cron — there is no person token, and nothing is overridden either.

Every act the override made possible is flagged where it is recorded
(`nrs.asset.event.admin_override` / `override_of`; the capture's
`captured_as_admin` / `reviewed_as_admin`) and listed on
`GET /api/v1/reports/admin-overrides`. An act that broke no rule is not an
override and is not flagged.
"""

ADMIN_OVERRIDE_PARAM = 'cadra.admin_override'

#: The audience `/auth/login` stamps (`myservice_api.controllers.utils
#: .FRONTEND_AUDIENCE`), spelled here because that module depends on this
#: one. `/auth/refresh` carries it over; `/auth/token` never sets it.
PERSON_AUDIENCE = 'frontend'

#: The audit rules an override lifts, as recorded on the capture
#: (`capture_override_of`, `review_override_of`) and published.
OVERRIDE_NOT_A_CAPTURER = 'not_a_capturer'
OVERRIDE_OWN_CAPTURE = 'own_capture'
OVERRIDE_NOT_A_REVIEWER = 'not_a_reviewer'

_ON_VALUES = ('1', 'true', 'yes', 'on')

_FROM_REQUEST = object()


def override_switched_on(env):
    """Whether the tenant has switched the override on. Absent means off."""
    env.cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s",
        (ADMIN_OVERRIDE_PARAM,))
    row = env.cr.fetchone()
    return bool(row) and (row[0] or '').strip().lower() in _ON_VALUES


def _request_claims():
    try:
        from odoo.http import request
    except ImportError:  # pragma: no cover - always importable under Odoo
        return None
    return (getattr(request, 'jwt_claims', None) or None) if request else None


def current_token_kind(user=None):
    """`'person'` for a `/auth/login` token, `'machine'` for any other
    verified token, None outside an API request. A token that names another
    account than `user` is no token of theirs."""
    claims = _request_claims()
    if not claims:
        return None
    if user is not None and claims.get('uid') != user.id:
        return None
    return 'person' if claims.get('aud') == PERSON_AUDIENCE else 'machine'


def admin_overrides(env, user=None, token_kind=_FROM_REQUEST):
    """THE test, used by every site that lifts a segregation rule.

    True only when all three hold: the token is a person's, the person is a
    system administrator, the tenant has switched the override on."""
    user = user if user is not None else env.user
    if not user:
        return False
    if token_kind is _FROM_REQUEST:
        token_kind = current_token_kind(user)
    if token_kind != 'person':
        return False
    if not user.sudo().has_group('base.group_system'):
        return False
    return override_switched_on(env)
