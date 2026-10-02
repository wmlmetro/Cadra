from . import http_patch  # noqa: F401  — applied at import time, before controllers register
from . import models
from . import controllers


def post_init_hook(env):
    """A FRESH install (a client's single-tenant database) gets what the
    19.0.3.17.0 migration gave the existing ones: both sign-up rows saying
    `b2b` so the Settings screen tells the truth about a door the code
    shuts, and Odoo's "unregistered users" reminder cron off — it would
    mail the inviter Odoo's own letter five days after an unredeemed
    invitation (verification pass, report 43 §F)."""
    from .models.invitation import align_signup_rows
    align_signup_rows(env.cr)
