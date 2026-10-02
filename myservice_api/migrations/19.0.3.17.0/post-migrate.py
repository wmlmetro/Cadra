"""Say `b2b` where the rows said `b2c` — handoff 43 §0.

`res.users._get_signup_invitation_scope` now answers `b2b` as a constant
(`models/invitation.py`), so after this upgrade no row decides whether a
stranger can create an account. The rows still exist, though, and two of
them are READ BY THE SETTINGS SCREEN: `auth_signup.invitation_scope` (the
parameter, `b2c` on 8 of 8 local tenants, put there by auth_signup's own
install data) and `website.auth_signup_uninvited` (the per-site field the
`website` module reads instead, `b2b` by default). A screen that says "Free
sign up" about a door that is shut is a confidently wrong runbook, which is
the kind this programme deletes. So both are set to what is true.

Measured before writing, on this machine: `/web/signup` already answered
404 on every tenant, because the website field was `b2b` everywhere — the
parameter's `b2c` had never been read. This migration changes no behaviour
on any tenant here; it makes the rows agree with the code.
"""
from odoo.addons.myservice_api.models.invitation import align_signup_rows


def migrate(cr, version):
    if not version:
        return
    align_signup_rows(cr)
