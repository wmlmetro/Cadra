"""The first five minutes — an invitation or a reset, redeemed in OUR app.

Handoff 45 §2.1. Until then the letter's link landed on Odoo's
`/web/signup` (or `/web/reset_password`): the app owned the letter and the
landing, and Odoo owned the middle — the page where a new officer decides
whether this is a real system. These routes are the middle, for the SPA's
`/app/accept-invite` and `/app/reset-password` pages:

    POST /api/v1/auth/password-token/inspect   {token}
    POST /api/v1/auth/password-token/redeem    {token, password, confirm_password}
    POST /api/v1/auth/password-reset           {login, turnstile_token?}

All three are anonymous, like `/auth/login` — the token IS the credential,
and the third is the *Forgot password?* link. They use bare `http.route`
because `cadra_route` always requires a bearer token.

THE TOKEN IS CORE'S, UNCHANGED
------------------------------
The letter still carries `auth_signup`'s signed token
(`res.partner._generate_signup_token`: `[partner_id, user_ids, login_date,
signup_type]`, HMAC-signed with `database.secret`, expiry baked in). Only the
page that receives it moved, so a letter sent before this change carries a
token these routes accept — `controllers/backoffice.py` sends the old
`/web/signup?token=…` link to the new page with the same token.

ITS FIVE STATES — 43's vocabulary, plus the one 43 never needed
---------------------------------------------------------------
`outstanding` · `expired` · `redeemed` · `cancelled` are the words
`res.users._cadra_invitation()` already publishes on every user row;
`invalid` is a token that was never one of ours (or is mangled). Core's
`verify_hash_signed` answers `None` for expired and forged alike, so
`_read_token` checks the signature and the expiry SEPARATELY — the token
carries its expiry in clear — which is what lets the page say *"this link
expired"* instead of *"this link is not valid"* to somebody who simply
waited a week.

  * signature bad, or not a token at all ............ invalid
  * signature good, past its expiry .................. expired
  * the account is deactivated ....................... cancelled
  * core still accepts it (`_get_partner_from_token`) . outstanding
  * the person has signed in since it was minted ..... redeemed
  * otherwise (a newer letter superseded it) ......... cancelled

PASSWORD RULES — the ones Odoo enforces, discovered
---------------------------------------------------
On Odoo 19 core enforces NOTHING on a password set through `signup()`: it
hashes whatever it is given, the empty string included (`_set_password`);
only `_change_password` refuses an empty one, and only the sign-up FORM
refuses a mismatched confirmation. `auth_password_policy`, which adds a
minimum length, is installed on 0 of 9 local databases (handoff 45 §2.1,
measured). So these routes refuse exactly: an empty (or all-space)
password, a confirmation that does not match, and — if the policy module is
ever installed — anything shorter than its `auth_password_policy.minlength`.
`/inspect` publishes those rules so the page can show them BEFORE the
person types, and every refusal is a sentence. Whether Cadra should impose a
minimum of its own is a decision, not a discovery: `docs/GO-LIVE.md` §22.
"""

import base64
import datetime
import hashlib
import json
import logging
import time

from odoo import fields, http
from odoo.exceptions import AccessDenied, UserError
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import hmac as odoo_hmac

from ..models.invitation import PASSWORD_FROM_LETTER
from .utils import (
    ok, err, get_params, _http_response, turnstile_error, jwt_secret,
    JwtSecretMissing, scopes_for_user,
    ERR_INVALID_REQUEST, ERR_CONFLICT, ERR_MISCONFIGURED,
)

_logger = logging.getLogger(__name__)

STATE_OUTSTANDING = "outstanding"
STATE_EXPIRED = "expired"
STATE_REDEEMED = "redeemed"
STATE_CANCELLED = "cancelled"
STATE_INVALID = "invalid"
TOKEN_STATES = (STATE_OUTSTANDING, STATE_EXPIRED, STATE_REDEEMED,
                STATE_CANCELLED, STATE_INVALID)

KIND_INVITATION = "invitation"
KIND_RESET = "reset"

#: What the page says for each state that is not `outstanding`, and the way
#: forward. ONE place, so `/inspect` and `/redeem` cannot word a state two
#: ways. `%(kind)s` is "invitation" or "reset link".
_STATE_SENTENCES = {
    STATE_EXPIRED: (
        "This %(kind)s has expired.",
        "Ask an administrator to send a new invitation, or use “Forgot "
        "password?” on the sign-in page if you already have an account."),
    STATE_REDEEMED: (
        "This %(kind)s has already been used — or you have signed in since "
        "it was sent.",
        "Sign in with the password you chose. If you have forgotten it, use "
        "“Forgot password?” on the sign-in page."),
    STATE_CANCELLED: (
        "This %(kind)s is no longer valid — a newer letter was sent, or the "
        "account was switched off.",
        "Use the most recent letter you received, or ask an administrator."),
    STATE_INVALID: (
        "This link is not valid.",
        "Check that the whole link was copied from the letter, or ask an "
        "administrator to send a new one."),
}

#: The keys each route reads. Anything else is refused (architecture rule 3).
_INSPECT_KEYS = frozenset({"token"})
_REDEEM_KEYS = frozenset({"token", "password", "confirm_password"})
_RESET_KEYS = frozenset({"login", "turnstile_token"})


# ─── the token ────────────────────────────────────────────────────────

def _read_token(env, token):
    """`(payload, signature_ok, expiry)` for a signup token — `expiry` an
    epoch second, 0 for none, exactly as core compares it — or
    `(None, False, None)` when it is not one at all.

    The same decoding as `odoo.tools.misc.verify_hash_signed`, with the two
    checks it folds together kept apart. Never raises: a mangled token is a
    state the page renders, not a 500.
    """
    if not isinstance(token, str) or not token.strip():
        return None, False, None
    try:
        raw = base64.urlsafe_b64decode(token.strip().encode() + b"===")
        if raw[:1] != b"\x01" or len(raw) < 42:
            return None, False, None
        expiry = int.from_bytes(raw[1:9], byteorder="little")
        signature, message = raw[9:41].hex(), raw[41:].decode()
        expected = odoo_hmac(env(su=True), "signup",
                             "1:%s:%s" % (message, expiry),
                             hash_function=hashlib.sha256)
        payload = json.loads(message)
    except (ValueError, TypeError, UnicodeDecodeError):
        # binascii.Error is a ValueError; json.JSONDecodeError too.
        return None, False, None
    if not (isinstance(payload, list) and len(payload) == 4):
        return None, False, None
    return payload, consteq(signature, expected), expiry


def token_status(env, token):
    """Everything the page needs to know about `token`. Reads only.

    Returns a dict: `state`, `kind`, `expires_at`, and — only for a token
    whose signature is good — `partner` and `user` (records, never
    published as such).
    """
    out = {"state": STATE_INVALID, "kind": None, "expires_at": None,
           "partner": None, "user": None}
    payload, signature_ok, expiry = _read_token(env, token)
    if not signature_ok:
        return out
    partner_id, user_ids, login_date, signup_type = payload
    out["kind"] = KIND_RESET if signup_type == "reset" else KIND_INVITATION
    # Naive UTC, like every datetime Odoo stores and publishes.
    out["expires_at"] = (datetime.datetime.fromtimestamp(
        expiry, datetime.timezone.utc).replace(tzinfo=None) if expiry else None)
    Partner = env["res.partner"].sudo()
    partner = Partner.browse(partner_id).exists() if isinstance(partner_id, int) else Partner
    if not partner:
        return out
    user = env["res.users"].sudo().with_context(active_test=False).search(
        [("partner_id", "=", partner.id)], order="active desc, id", limit=1)
    out.update(partner=partner, user=user)
    if not user or user.share:
        # A token for a partner with no internal account — core's portal
        # "grant access" link. This page sets an OFFICER's password; it is
        # not a link to it (`app_password_path` leaves those on core's path).
        return out
    if expiry and time.time() >= expiry:
        out["state"] = STATE_EXPIRED
    elif user and not user.active:
        out["state"] = STATE_CANCELLED
    elif Partner._get_partner_from_token(token.strip()):
        out["state"] = STATE_OUTSTANDING
    elif user and partner._get_login_date() and (
            login_date in (None, "None")
            or partner._get_login_date() > int(login_date)):
        out["state"] = STATE_REDEEMED
    else:
        out["state"] = STATE_CANCELLED
    return out


def password_rules(env):
    """The rules `/redeem` enforces, published so the page can show them."""
    Module = env["ir.module.module"].sudo()
    policy = bool(Module.search_count([("name", "=", "auth_password_policy"),
                                       ("state", "=", "installed")]))
    min_length = 0
    if policy:
        try:
            min_length = int(env["ir.config_parameter"].sudo().get_param(
                "auth_password_policy.minlength") or 0)
        except ValueError:
            min_length = 0
    return {
        "required": True,
        "must_match_confirmation": True,
        "min_length": max(min_length, 1),
        "source": ("auth_password_policy" if policy
                   else "odoo_core_refuses_only_empty"),
    }


def _password_refusal(rules, password, confirmation):
    """The sentence for a password the server will not take, or None."""
    if not isinstance(password, str) or not password.strip():
        return "Choose a password — it cannot be empty."
    if len(password) < rules["min_length"]:
        return ("Choose a password of at least %d characters (this one has "
                "%d)." % (rules["min_length"], len(password)))
    if password != confirmation:
        return "The two passwords do not match. Type the same password twice."
    return None


def _state_payload(env, status):
    """The published view of a token's status. Never echoes the token."""
    kind_word = ("reset link" if status["kind"] == KIND_RESET else "invitation")
    data = {
        "state": status["state"],
        "kind": status["kind"],
        "expires_at": (fields.Datetime.to_string(status["expires_at"])
                       if status["expires_at"] else None),
        # `env.company` is EMPTY under `auth='none'` — no user, no company —
        # which published `false` here (verification pass). The tenant's
        # company, as `letter_context` reads it.
        "organisation": env["res.company"].sudo().search([], order="id", limit=1).name,
        "password_rules": password_rules(env),
    }
    user = status.get("user")
    if status["state"] == STATE_OUTSTANDING and user:
        # Only for a live token: who the page is setting a password for. A
        # dead link says nothing about whose it was.
        data["name"] = user.name
        data["login"] = user.login
    sentence = _STATE_SENTENCES.get(status["state"])
    if sentence:
        data["message"] = sentence[0] % {"kind": kind_word}
        data["next"] = sentence[1]
    return data


def _refuse_unknown(body, allowed):
    extra = sorted(set(body) - allowed) if isinstance(body, dict) else []
    if extra:
        return err(ERR_INVALID_REQUEST,
                   "This request does not take: %s." % ", ".join(extra),
                   details={"rejected_fields": extra,
                            "writable": sorted(allowed)})
    return None


class CadraPasswordTokenV1(http.Controller):

    @http.route("/api/v1/auth/password-token/inspect", type="http",
                auth="none", methods=["POST"], csrf=False)
    def inspect(self, **kwargs):
        """What a letter's token is, before anybody types a password.

        Always 200 when the body is well-formed: an expired or used link is
        a state the page renders, not an error. Reads only."""
        body = get_params()
        refused = _refuse_unknown(body, _INSPECT_KEYS)
        if refused:
            return _http_response(refused)
        status = token_status(request.env, body.get("token"))
        return _http_response(ok(_state_payload(request.env, status)))

    @http.route("/api/v1/auth/password-token/redeem", type="http",
                auth="none", methods=["POST"], csrf=False)
    def redeem(self, **kwargs):
        """Set the password a letter invited, and sign the person in.

        Answers the same `data` block as `/auth/login`, so the app stores it
        the same way. Every refusal happens before anything is written.
        """
        env = request.env
        body = get_params()
        refused = _refuse_unknown(body, _REDEEM_KEYS)
        if refused:
            return _http_response(refused)
        token = body.get("token")
        status = token_status(env, token)
        if status["state"] != STATE_OUTSTANDING:
            data = _state_payload(env, status)
            return _http_response(err(
                ERR_CONFLICT, data.get("message") or "This link cannot be used.",
                status=409, details={"state": status["state"],
                                     "kind": status["kind"],
                                     "next": data.get("next")}))
        rules = password_rules(env)
        password = body.get("password")
        sentence = _password_refusal(rules, password, body.get("confirm_password"))
        if sentence:
            return _http_response(err(ERR_INVALID_REQUEST, sentence,
                                      details={"password_rules": rules}))
        user = status["user"]
        try:
            # Core's own redemption: it re-checks the token, clears
            # `signup_type` (so the link is spent) and writes the password.
            with env.cr.savepoint():
                env["res.users"].sudo().with_context(
                    **{PASSWORD_FROM_LETTER: True}).signup(
                        {"password": password}, token.strip())
        except UserError as e:
            # The policy module's length refusal, or core's own token
            # refusal racing a second click. Its sentence, not ours.
            msg = e.args[0] if e.args else str(e)
            if "token" in msg.lower():
                msg = _STATE_SENTENCES[STATE_CANCELLED][0] % {"kind": "invitation"}
            return _http_response(err(ERR_INVALID_REQUEST, msg))
        # Signing in through `authenticate` is what stamps `login_date`, so
        # the invitation reads `redeemed` on the Users page from now on.
        try:
            auth_info = env["res.users"].authenticate(
                {"type": "password", "login": user.login, "password": password},
                {"interactive": False})
            uid = auth_info.get("uid") if isinstance(auth_info, dict) else auth_info
        except AccessDenied:
            uid = False
        if not uid:
            # The password IS set; only the automatic sign-in failed. Say so
            # rather than pretend nothing happened.
            return _http_response(ok({"signed_in": False, "login": user.login}))
        try:
            secret = jwt_secret(env)
        except JwtSecretMissing as e:
            return _http_response(err(ERR_MISCONFIGURED, str(e), status=500))
        from .v1 import MyserviceApiV1
        user = env["res.users"].sudo().browse(uid)
        payload = MyserviceApiV1()._session_payload(
            secret, sub=user.login, user=user, scopes=scopes_for_user(user),
            aud="frontend", access_ttl=3600)
        payload.update(signed_in=True, login=user.login)
        return _http_response(ok(payload))

    @http.route("/api/v1/auth/password-reset", type="http", auth="none",
                methods=["POST"], csrf=False)
    def request_reset(self, **kwargs):
        """*Forgot password?* — send the reset letter.

        Answers the SAME sentence whether or not an account matched, so this
        cannot be used to learn who has an account. A deactivated account
        gets no letter (core refuses an archived user, and a switched-off
        person must not be able to switch themselves back on). A letter that
        could not be sent is logged for the operator and not told to an
        anonymous caller, for the same reason.
        """
        env = request.env
        body = get_params()
        refused = _refuse_unknown(body, _RESET_KEYS)
        if refused:
            return _http_response(refused)
        login = body.get("login")
        captcha = body.get("turnstile_token") or ""
        if not isinstance(login, str) or not login.strip() \
                or not isinstance(captcha, str):
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "Type the username or email address you sign in with."))
        challenge = turnstile_error(env, captcha)
        if challenge:
            return _http_response(challenge)
        login = login.strip()
        # Core's own order (`reset_password`): the login, then the email.
        # Counted, not windowed: an address held by two accounts sends
        # nobody a letter, since it cannot say whose password to reset.
        Users = env["res.users"].sudo()
        domain = [("login", "=", login)]
        matches = Users.search_count(domain)
        if not matches:
            # Core's own email match, `%`/`_` escaped (verification pass:
            # a bare `=ilike` made `a%` a pattern).
            domain = Users._get_email_domain(login)
            matches = Users.search_count(domain)
        user = Users.search(domain, limit=1) if matches == 1 else Users
        if user and user.active and not user.share:
            try:
                with env.cr.savepoint():
                    user.action_reset_password()
            except (MailDeliveryException, UserError):
                # NARROW, on purpose: the two ways a letter legitimately
                # fails (the server refused it; the account has no address).
                # Logged with the account for the operator; the anonymous
                # caller gets the same sentence as for an unknown login. A
                # broad catch here swallowed Odoo's read-only-cursor error
                # and so defeated its read/write retry — no letter, in the
                # in-registry run (`docs/ENVIRONMENT-FACTS.md`).
                _logger.exception("password reset letter for %s could not "
                                  "be sent", user.login)
        elif matches > 1:
            _logger.warning("password reset for %r matched %d accounts; no "
                            "letter sent", login, matches)
        return _http_response(ok({
            "message": ("If an account matches what you typed, a letter "
                        "with a link to choose a new password is on its way. "
                        "The link is valid for a few hours."),
        }))
