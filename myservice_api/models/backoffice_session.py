# -*- coding: utf-8 -*-
"""No Odoo SESSION for anybody who is not a system administrator.

Handoff 45 §2.2, the half `controllers/backoffice.py` cannot do alone. That
file shuts the doors a person walks through — the web client, Odoo's login
page, the two letter pages. The verification pass found the doors a person
does not walk through but a session still opens: `/web/session/authenticate`
(JSON-RPC, `auth='none'`, issues a cookie), the two-factor step of
`/web/login`, and then everything `auth='user'` that cookie reaches —
`/web/dataset/call_kw` (the ORM, with the person's own access rules),
`/web/tests`, the portal's `/my`, `/report/pdf`. Closing them one by one is
the shape that missed them in the first place.

So the rule is put where every one of them passes: `ir.http._authenticate`,
for a route declared `auth='user'`. A session whose user is not a system
administrator is ended there, before the route runs, and the request is then
judged as anonymous — an `http` route answers a redirect to the app, a
JSON-RPC route answers core's *"Session expired"*. An anonymous visitor to an
`http` `auth='user'` page (`/my`, a record link) is sent to the app as well,
not to Odoo's login page.

What this does NOT touch, on purpose: `auth='none'` routes (every `/api/v1/*`
route — the app authenticates with a bearer token and holds no Odoo session
at all), `auth='public'` routes (`/report/barcode`, the QR on a printed label;
`/web/content`, `/web/image`, assets; `/web/login` itself, which the k8s
probes GET), and a system administrator's session, which reaches everything
as before.
"""

import logging

from werkzeug.exceptions import HTTPException

from odoo import api, http, models
from odoo.http import request

_logger = logging.getLogger(__name__)

APP_HOME = "/app/"


def is_system_uid(env, uid):
    """Whether `uid` is a system administrator, read sudo and fresh."""
    if not uid:
        return False
    user = env["res.users"].sudo().browse(uid)
    return bool(user.exists()) and user._is_system()


class IrHttpBackOffice(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _authenticate(cls, endpoint):
        routing = getattr(endpoint, "routing", {}) or {}
        uid = request.session.uid if request.session else None
        preflight = http.is_cors_preflight(request, endpoint)
        if (routing.get("auth") == "user" and not uid and not preflight
                and routing.get("type") == "http"):
            # ANONYMOUS on a page that needs a session: core would send them
            # to Odoo's `/web/login?redirect=…`. A person who is not signed
            # in is sent where a person signs in — the app. System
            # administrators sign in at `/web/login` directly; the deep
            # `redirect=` back into the back office is what this costs them.
            raise HTTPException(response=request.redirect(
                APP_HOME, code=303, local=True))
        if (routing.get("auth") == "user" and uid and not preflight
                and not is_system_uid(request.env, uid)):
            _logger.info("back office: ended the Odoo session of uid %s (not a "
                         "system administrator) on an auth='user' route", uid)
            request.session.logout(keep_db=True)
            request.env = api.Environment(request.env.cr, None,
                                          request.session.context)
            if routing.get("type") == "http":
                raise HTTPException(response=request.redirect(
                    APP_HOME, code=303, local=True))
        return super()._authenticate(endpoint)
