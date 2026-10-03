"""The back office is for system administrators. Everybody else is sent to
the app.

Handoff 45 §2.2: *"the back office should not be a place any NRS officer can
arrive at, by any route, ever."* This shuts the INTERFACE and leaves the
PLUMBING — Odoo's back office and its infrastructure share the `/web` prefix,
and only the first is closed here.

WHAT IS SHUT, AND HOW
---------------------
* **The web client** — `/web`, `/odoo`, every `/odoo/<path>` (Odoo 19 has no
  separate `/web#action=` route; actions, records and menus are all under
  `/odoo/`) and `/scoped_app/<path>`: one core handler, `Home.web_client`.
  A signed-in non-administrator is signed out of Odoo and sent to `/app/`;
  an ANONYMOUS visitor is sent to `/app/` too, because the app is where a
  person signs in. System administrators reach it through `/web/login`,
  which stays exactly as it was.
* **Signing in on Odoo's own page as a non-administrator** — `/web/login`
  succeeds, then the Odoo session is ended and the person is sent to the
  app, so nobody who is not an administrator walks away holding an Odoo
  session (which would otherwise let them use Odoo's JSON-RPC with their
  own access rules).
* **The two letter pages** — `/web/signup?token=…` and
  `/web/reset_password?token=…` are sent to `/app/accept-invite` and
  `/app/reset-password` with the same token, on GET and on POST. Every letter sent before
  handoff 45 carries that old link, so nobody invited yesterday is stranded.
  The token-less `/web/reset_password` form is sent to the app's
  *Forgot password?* page.

* **Every other way to HOLD an Odoo session** — JSON-RPC sign-in, the
  two-factor step, the portal — is shut one level down, in
  `models/backoffice_session.py`: no `auth='user'` route serves a
  non-administrator's session.

WHAT IS LEFT, ON PURPOSE — enumerated by driving the app as a
non-administrator (report 45 §B), not by reasoning about prefixes
-----------------------------------------------------------------------
The app authenticates with a bearer token on `/api/v1/*` and holds no Odoo
session at all. The one non-API Odoo URL it requests is `/report/barcode`
(the QR image on a printed label, `auth='public'`); labels are composed in
the browser (`src/lib/labels.ts`), not rendered by `/report/pdf`. None of
`/web/content`, `/web/image`, `/web/assets`, `/web/static`, `/report/*`,
`/websocket`, `/web/health`, `/web/login` (also the k8s probes' target) is
touched here.
"""

import logging

from odoo import http
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome

_logger = logging.getLogger(__name__)

APP_HOME = "/app/"
APP_ACCEPT_INVITE = "/app/accept-invite"
APP_RESET_PASSWORD = "/app/reset-password"
APP_FORGOT_PASSWORD = "/app/forgot-password"


def _is_system(uid):
    """Whether `uid` is a system administrator. Read fresh, sudo, so a
    session whose user lost the group is judged on what it holds now."""
    if not uid:
        return False
    user = request.env["res.users"].sudo().browse(uid)
    return bool(user.exists()) and user._is_system()


def _to_app(path=APP_HOME, token=None):
    target = path
    if token:
        from werkzeug.urls import url_encode
        target = "%s?%s" % (path, url_encode({"token": token}))
    return request.redirect(target, code=303, local=True)


def _end_odoo_session():
    """Sign the person out of ODOO. The app's bearer token is untouched —
    it lives in the browser's storage, not in this cookie."""
    request.session.logout(keep_db=True)


class CadraBackOfficeDoor(AuthSignupHome):

    @http.route()
    def web_client(self, s_action=None, **kw):
        uid = request.session.uid
        if uid and _is_system(uid):
            return super().web_client(s_action=s_action, **kw)
        if uid:
            _logger.info("back office: uid %s is not a system administrator; "
                         "signed out of Odoo and sent to the app", uid)
            _end_odoo_session()
        return _to_app()

    @http.route()
    def web_login(self, *args, **kw):
        response = super().web_login(*args, **kw)
        uid = request.session.uid
        if request.httprequest.method == "POST" and uid and not _is_system(uid):
            _logger.info("back office: uid %s signed in on /web/login and is "
                         "not a system administrator; sent to the app", uid)
            _end_odoo_session()
            return _to_app()
        return response

    # GET AND POST. The verification pass posted to `/web/reset_password`
    # with a made-up login and got Odoo's own page saying "No account found
    # for this login" — the door the app's same-answer route exists to shut.
    # Neither form is reachable any more, so neither method reaches core.
    @http.route()
    def web_auth_signup(self, *args, **kw):
        return _to_app(APP_ACCEPT_INVITE, kw.get("token"))

    @http.route()
    def web_auth_reset_password(self, *args, **kw):
        token = kw.get("token")
        return _to_app(APP_RESET_PASSWORD if token else APP_FORGOT_PASSWORD,
                       token)
