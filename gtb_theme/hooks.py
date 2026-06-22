import base64
import logging
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Displayed company name for the GTB instance. Drives the login-screen footer,
# document headers, etc. Adjust to taste (e.g. "Guaranty Trust Bank").
GTB_COMPANY_NAME = "GTB"

_LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "static", "src", "img", "logo.png"
)


def _gtb_post_init(cr, registry):
    """Apply GTB company branding (name + logo + favicon).

    The backend sidebar and the login screen both render
    ``/web/image/res.company/<id>/logo``, so setting the company logo here is
    what makes the whole UI read as GTB. Runs once on install; safe to re-run
    on upgrade (idempotent).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    logo_b64 = None
    if os.path.exists(_LOGO_PATH):
        with open(_LOGO_PATH, "rb") as fh:
            logo_b64 = base64.b64encode(fh.read())
    else:
        _logger.warning("gtb_theme: logo file missing at %s", _LOGO_PATH)

    companies = env["res.company"].search([])
    for company in companies:
        vals = {"name": GTB_COMPANY_NAME}
        if logo_b64:
            vals["logo"] = logo_b64
            # res.company has no standalone favicon write here in 15.0 via logo;
            # set it explicitly so the browser tab icon is GTB too.
            if "favicon" in company._fields:
                vals["favicon"] = logo_b64
        company.write(vals)

    _logger.info(
        "gtb_theme: applied GTB branding to %s company record(s)", len(companies)
    )
