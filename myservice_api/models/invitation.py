"""The person, and the door — handoff 43.

Three overrides on two core models, and two stored stamps. Each exists
because a core behaviour was measured and found to be the wrong one for a
government asset register with named officers.

1. **The front door is shut, in Python.** `res.users._get_signup_invitation_scope`
   answers `b2b` — invitation only — whatever `auth_signup.invitation_scope`
   says and whatever the `website` row says. Report 41 found the parameter
   at `b2c` (free sign-up) on 8 of 8 tenants; report 42 found the door shut
   anyway (anonymous `/web/signup` → 404 on every host); this handoff found
   WHY: the `website` module overrides the same method with its own
   per-site field, whose default is `b2b`
   (`website/models/res_users.py:66-68`, `website/models/website.py:213`).
   So the door was shut by an accident of module order, and a tenant
   administrator opening *Settings › Customer Account* could open it with
   one click. The owner's ruling is that nobody signs themselves up to this
   product, so the answer is a constant here, not a row anywhere. The
   migration beside this file also sets both rows to `b2b` so that the
   Settings screen stops saying "Free sign up" about a door that is shut.

2. **The letters are the tenant's, not Odoo's.** `_action_reset_password`
   is what EVERY path to an invitation or a reset ends in — the user form's
   button, `res.users.create` (which invites by itself unless told not to),
   `/web/reset_password`, and `POST /api/v1/users` — and core's version
   picks `auth_signup.set_password_email` for the one and a hand-built mail
   around the `auth_signup.reset_password_email` QWeb view for the other:
   Odoo's wording, Odoo's footer, "Never heard of Odoo?", a link to an Odoo
   tour. Ours renders `data/mail_templates.xml` with the brand the per-client
   `cadra_brand_*` module put in `cadra.brand_*` (the same parameters
   `/api/v1/brand` serves the app from), the organisation's name from
   `res.company`, and a link that points at the host the request came in
   on. **A method you override is a name the framework owns**:
   `tests/test_user_lifecycle.py` reads core's source and fails the day
   `create` or `action_reset_password` stop calling this name.

3. **The link points at the tenant's own host — when somebody we know asks.** Core builds the sign-up
   URL on `partner.get_base_url()` — the website domain if one is set, else
   `web.base.url`, which core REWRITES on every system-administrator login
   from whatever host they used (`base/models/res_users.py:784-811`). On
   this machine every tenant's `web.base.url` was `http://<db>.localhost`
   with no port, because the dev proxy passed `$host`; on the cluster it is
   whatever the last administrator typed. `res.partner._get_signup_url_for_action`
   prefers the bound request's own `url_root` when the caller is
   authenticated (an API token or a back-office session), which under
   `proxy_mode` is the host and scheme the person actually reached us on;
   for an anonymous request (`/web/reset_password`) and with no request
   bound (a cron, a shell) it does exactly what core did, because an
   anonymous caller must not choose the host a victim's link points at.

The stamps — `cadra_invitation_sent_at`, `_sent_by_id`, `_sends` — are
written here, under every path, so the user row can say *an invitation is
outstanding, sent on <date> by <who>* without a second mechanism. They are
stored columns on `res.users`: a multi-tenant migration, per CLAUDE.md.
"""
import logging
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

#: The ruling, as a constant. Not a parameter: a parameter is a thing a
#: Settings screen can flip.
SIGNUP_SCOPE = 'b2b'

INVITATION_TEMPLATE = 'myservice_api.mail_template_invitation'
RESET_TEMPLATE = 'myservice_api.mail_template_password_reset'

#: Company names Odoo ships with. A tenant still carrying one has not been
#: named, and a letter headed "My Company" is not a letter from anybody.
GENERIC_COMPANY_NAMES = frozenset({'My Company', 'YourCompany', 'Your Company'})

#: Where the letter sends the person after they have set a password: the
#: app, not Odoo's back office.
LANDING_PATH = '/app/'

#: Context key set ONLY by `POST /api/v1/auth/password-token/redeem` around
#: core's `signup()`. Handoff 45: setting the password a letter asked for
#: made core send its own *"Security Update: Password Changed"* mail — an
#: Odoo-branded letter with an Odoo link, in the middle of the first five
#: minutes, telling the person what they did a second ago from a link sent
#: to that same mailbox. Every other password change keeps core's notice.
PASSWORD_FROM_LETTER = 'cadra_password_from_letter'


def _request_is_authenticated():
    """Somebody we know is asking: an API token (`jwt_claims`, set only by
    `require_jwt`) or a signed-in back-office session. An ANONYMOUS request —
    `/web/reset_password` typed by a stranger — is not, and must not choose
    the host a victim's link points at: under `proxy_mode` the request host
    is `X-Forwarded-Host`, which a proxy that does not overwrite it passes
    through from the client (verification pass, report 43 §F)."""
    if getattr(request, 'jwt_claims', None):
        return True
    session = getattr(request, 'session', None)
    return bool(getattr(session, 'uid', None))


def request_base_url():
    """`scheme://host[:port]` of the request being served, when the caller
    is authenticated; '' otherwise and when nothing is bound.

    `odoo.http.request` is a proxy that is falsy when nothing is bound;
    `_FakeApiRequest` in the in-registry suites has no `httprequest` at all,
    hence the `getattr`. Under `proxy_mode = True` (both compose profiles and
    the cluster ConfigMap) `url_root` already reflects `X-Forwarded-Host` and
    `X-Forwarded-Proto`, so this is the host the person typed, not the
    container's.
    """
    if not request or not _request_is_authenticated():
        return ''
    httpreq = getattr(request, 'httprequest', None)
    url_root = getattr(httpreq, 'url_root', None) if httpreq is not None else None
    return (url_root or '').rstrip('/')


#: Handoff 45 §2.1: the page that takes a letter's token is the APP's. Core's
#: route for each signup type → ours. The token itself is core's, unchanged.
APP_PASSWORD_PAGES = {
    '/web/signup': '/app/accept-invite',
    '/web/reset_password': '/app/reset-password',
}


def app_password_path(relative):
    """Core's `/web/signup?db=…&token=…&redirect=…` (or `/web/reset_password…`)
    → `/app/accept-invite?token=…` (or `/app/reset-password?token=…`).

    Only the TOKEN travels: `db` is the host's business under the dbfilter,
    `redirect` was always the app, and `signup_email` would put the address
    in a URL for nothing. Any other core path (`/web/login?…`, a record
    link) is returned untouched. `controllers/backoffice.py` sends a link in
    the old shape — every letter sent before this change — to the same page.
    """
    parsed = urlsplit(relative)
    page = APP_PASSWORD_PAGES.get(parsed.path)
    if not page:
        return relative
    token = dict(parse_qsl(parsed.query)).get('token')
    if not token:
        return relative
    return '%s?%s' % (page, urlencode({'token': token}))


def signup_base_url(partner):
    """ONE answer for every absolute URL in a letter: the authenticated
    request's host, else exactly what core would have used
    (`partner.get_base_url()` — the website domain, else `web.base.url`)."""
    return (request_base_url() or partner.get_base_url() or '').rstrip('/')


def letter_context(env, base_url):
    """Everything the two templates print, resolved at SEND time from the
    tenant the request is bound to.

    The brand is the same four parameters `/api/v1/brand` serves the app from
    — `cadra_brand_<client>/data/brand_params.xml` owns them — so the letter
    a person receives from `jaizbankplc` carries Jaiz's name, colour and
    logo and never the word NRS. The logo is served as an image URL
    (`/api/v1/brand/logo`, this handoff) rather than embedded as a `data:`
    URI, because Gmail and Outlook strip inline-data images; a tenant whose
    brand module supplies none gets a wordmark in the brand colour, not a
    broken image.
    """
    icp = env['ir.config_parameter'].sudo()
    company = env['res.company'].sudo().search([], limit=1)
    short_name = (icp.get_param('cadra.brand_short_name', '') or '').strip()
    organisation = (company.name or '').strip() if company else ''
    if not organisation or organisation in GENERIC_COMPANY_NAMES:
        organisation = short_name or 'Cadra'
    logo = icp.get_param('cadra.brand_logo', '') or ''
    return {
        'organisation': organisation,
        'short_name': short_name or organisation,
        'primary': icp.get_param('cadra.brand_primary', '') or '#1F2937',
        'primary_dark': icp.get_param('cadra.brand_primary_dark', '') or '#111827',
        'logo_url': (base_url + '/api/v1/brand/logo') if logo.startswith('data:image/') else '',
        'base_url': base_url,
        'login_url': base_url + LANDING_PATH,
    }


class ResUsersInvitation(models.Model):
    _inherit = 'res.users'

    cadra_invitation_sent_at = fields.Datetime(
        string='Invitation last sent', readonly=True, copy=False,
        help="When this person was last sent a link to set their password. "
             "Stamped by every path that sends one: the API, the user form, "
             "and a create with an email address.")
    cadra_invitation_sent_by_id = fields.Many2one(
        'res.users', string='Invitation last sent by', readonly=True,
        copy=False, ondelete='set null',
        help="The administrator who sent it; empty when the system did.")
    cadra_invitation_sends = fields.Integer(
        string='Invitations sent', default=0, readonly=True, copy=False)

    # ── 1. the door ──────────────────────────────────────────────────

    @api.model
    def _get_signup_invitation_scope(self):
        """Invitation only, on every tenant, whatever any row says."""
        return SIGNUP_SCOPE

    # ── 2. the letters ───────────────────────────────────────────────

    def _action_reset_password(self, signup_type="reset"):
        """Cadra's version of core's: same contract — token prepared on the
        partner, one mail per user, the archived and the address-less
        refused in the same sentences, the same client action returned —
        with the tenant's letter instead of Odoo's, and the stamps."""
        if self.env.context.get('install_mode') or self.env.context.get('import_file'):
            return
        if self.filtered(lambda user: not user.active):
            raise UserError(_("You cannot perform this action on an archived user."))
        create_mode = bool(self.env.context.get('create_user'))

        self.mapped('partner_id').signup_prepare(signup_type=signup_type)

        template = self.env.ref(
            INVITATION_TEMPLATE if signup_type == 'signup' else RESET_TEMPLATE)
        icp = self.env['ir.config_parameter'].sudo()
        validity_hours = int(icp.get_param(
            'auth_signup.signup.validity.hours' if signup_type == 'signup'
            else 'auth_signup.reset_password.validity.hours',
            144 if signup_type == 'signup' else 4))

        email_values = {
            'email_cc': False,
            'auto_delete': True,
            'message_type': 'user_notification',
            'recipient_ids': [],
            'partner_ids': [],
            'scheduled_date': False,
        }
        acting = self.env.user
        # `acting` is EMPTY under an `auth='none'` request with no user bound
        # — handoff 45's anonymous *Forgot password?* route — and
        # `_is_public()` on an empty recordset raises. No user, no sender.
        sender = acting if (acting and self.env.uid != SUPERUSER_ID
                            and not acting._is_public()) else self.env['res.users']
        now = fields.Datetime.now()

        for user in self:
            if not user.email:
                raise UserError(_("Cannot send email: user %s has no email address.", user.name))
            partner = user.partner_id
            base_url = signup_base_url(partner)
            letter = letter_context(self.env, base_url)
            link = partner.with_context(create_user=create_mode) \
                ._get_signup_url_for_action(url=LANDING_PATH)[partner.id]
            email_values['email_to'] = user.email
            # A From, with core's own fallbacks and in core's order for the
            # reset path (`company_id.email_formatted or user.email_formatted`
            # — the RECIPIENT's address last). The first drive of this
            # handoff had the template fall back to the acting user, which
            # for an API credential on a tenant whose company has no address
            # is nobody, and the send died inside `_build_email__` with a
            # sentence about ICPs.
            email_values['email_from'] = (
                user.company_id.email_formatted
                or (sender.email_formatted if sender and sender.email else False)
                or user.email_formatted)
            ctx = dict(
                letter,
                link=link,
                validity_hours=validity_hours,
                validity_days=max(1, validity_hours // 24),
                recipient_name=user.name,
                sender_name=sender.name if sender else '',
            )
            # Core wraps this in `contextlib.closing(cr.savepoint())`. On 19
            # `Savepoint.close()` ROLLS BACK by default (`sql_db.py:118`), so
            # core's pattern discards the `mail.mail` row after the SMTP
            # send — harmless to it, the row is auto-deleted anyway, but it
            # hides the letter from `MockEmail` in the suites. A plain
            # context manager releases on success and rolls back on failure,
            # which is what was meant.
            with self.env.cr.savepoint():
                template.with_context(cadra_letter=ctx).send_mail(
                    user.id, force_send=True, raise_exception=True,
                    email_values=email_values)
            if signup_type == 'signup':
                user.sudo().write({
                    'cadra_invitation_sent_at': now,
                    'cadra_invitation_sent_by_id': sender.id if sender else False,
                    'cadra_invitation_sends': (user.cadra_invitation_sends or 0) + 1,
                })
                _logger.info("Invitation sent for user <%s> to <%s> (link host %s)",
                             user.login, user.email, base_url)
                message = _('A signup link was sent by email')
            else:
                _logger.info("Password reset email sent for user <%s> to <%s>",
                             user.login, user.email)
                message = _('A reset password link was sent by email')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Notification', 'message': message, 'sticky': False}}

    # ── what the API publishes ───────────────────────────────────────

    def _cadra_invitation(self):
        """The `invitation` block of a user row. One of five states, each a
        sentence somebody can act on:

          never        no invitation has ever been sent
          outstanding  sent, the link still valid, not yet used
          expired      sent, the link past its validity, not used
          redeemed     sent, and the person has since set a password and
                       signed in
          cancelled    sent, then voided without being used — deactivation
                       cancels the token (`auth_signup`'s `write`), and a
                       password reset asked for from the login page replaces
                       it with a reset token

        `expires_at` is derived from the send time and the validity the
        token was minted with (`hash_sign` bakes the expiry into the token
        itself; there is no row to read it from).
        """
        self.ensure_one()
        sent_at = self.cadra_invitation_sent_at
        if not sent_at:
            state, expires_at = 'never', None
        else:
            hours = int(self.env['ir.config_parameter'].sudo().get_param(
                'auth_signup.signup.validity.hours', 144))
            expires_at = fields.Datetime.add(sent_at, hours=hours)
            # A sign-in since the send comes FIRST: the token carries
            # `login_date` in its payload, so one sign-in kills it whatever
            # `signup_type` still says (verification pass, report 43 §F).
            if self.login_date and self.login_date >= sent_at:
                state = 'redeemed'
            elif self.partner_id.sudo().signup_type == 'signup':
                state = 'outstanding' if fields.Datetime.now() < expires_at else 'expired'
            else:
                state = 'cancelled'
        sender = self.cadra_invitation_sent_by_id
        return {
            'state': state,
            'sent_at': sent_at.isoformat() if sent_at else None,
            'sent_by': {'id': sender.id, 'name': sender.name} if sender else None,
            'sends': int(self.cadra_invitation_sends or 0),
            'expires_at': expires_at.isoformat() if expires_at else None,
        }


class ResUsersLetterPassword(models.Model):
    _inherit = 'res.users'

    def _notify_security_setting_update(self, subject, content, mail_values=None, **kwargs):
        """Core's security notice — except for the password a letter asked
        for, set through the app's page (`PASSWORD_FROM_LETTER`)."""
        if self.env.context.get(PASSWORD_FROM_LETTER):
            return self.env['mail.mail']
        return super()._notify_security_setting_update(
            subject, content, mail_values=mail_values, **kwargs)


class ResPartnerSignupHost(models.Model):
    _inherit = 'res.partner'

    def _get_signup_url_for_action(self, url=None, action=None, view_type=None,
                                   menu_id=None, res_id=None, model=None):
        """Core's URL, on the host the request came in on.

        Core computes the path and joins it to `partner.get_base_url()`.
        This asks core for the RELATIVE form and joins it itself, to the
        bound request's `url_root` when there is one and to core's own base
        when there is not — so nothing about the path, the token or the
        query changes, only which host the person is sent back to.
        """
        if self.env.context.get('relative_url'):
            return super()._get_signup_url_for_action(
                url=url, action=action, view_type=view_type,
                menu_id=menu_id, res_id=res_id, model=model)
        relative = super(ResPartnerSignupHost, self.with_context(relative_url=True)) \
            ._get_signup_url_for_action(
                url=url, action=action, view_type=view_type,
                menu_id=menu_id, res_id=res_id, model=model)
        out = {}
        for partner in self:
            rel = relative.get(partner.id)
            if not rel:
                out[partner.id] = rel
                continue
            # Only an internal account's letter goes to the app's page; a
            # portal partner's link (core's "grant portal access") keeps core's
            # path — the app cannot set a password for an account it does not
            # serve (verification pass, report 45 §G).
            if partner.sudo().with_context(active_test=False).user_ids.filtered(
                    lambda u: not u.share):
                rel = app_password_path(rel)
            out[partner.id] = urljoin(signup_base_url(partner) + '/', rel.lstrip('/'))
        return out


def align_signup_rows(cr):
    """The two rows the Settings screen reads, set to what the code answers,
    and the reminder cron off. Shared by the 19.0.3.17.0 migration and the
    install hook so a fresh tenant and an upgraded one end up the same."""
    cr.execute("""
        UPDATE ir_config_parameter
           SET value = 'b2b'
         WHERE key = 'auth_signup.invitation_scope'
           AND value IS DISTINCT FROM 'b2b'
    """)
    params = cr.rowcount
    cr.execute("""
        UPDATE website
           SET auth_signup_uninvited = 'b2b'
         WHERE auth_signup_uninvited IS DISTINCT FROM 'b2b'
    """)
    sites = cr.rowcount
    cr.execute("""
        UPDATE ir_cron
           SET active = FALSE
         WHERE active
           AND id IN (SELECT res_id FROM ir_model_data
                       WHERE model = 'ir.cron' AND module = 'auth_signup'
                         AND name = 'ir_cron_auth_signup_send_pending_user_reminder')
    """)
    crons = cr.rowcount
    _logger.info(
        "myservice_api: sign-up scope set to b2b on %s — %d parameter row(s), "
        "%d website row(s) changed, %d reminder cron(s) switched off; the "
        "code answers b2b regardless.", cr.dbname, params, sites, crons)
    return params, sites, crons
