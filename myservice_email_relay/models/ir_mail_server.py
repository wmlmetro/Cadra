"""Outbound mail bridge — POST to an HTTPS relay instead of opening SMTP.

DigitalOcean Kubernetes blocks outbound SMTP (25/465/587) on new accounts,
so a direct smtplib connection from a pod hangs and times out. This override
detects whether a relay is configured via ir.config_parameter and routes
mail through HTTPS (port 443, never blocked) instead.

When `cadra.email_relay_url` or `cadra.email_relay_secret` is empty the
native SMTP path runs unchanged.

Where the hook is, and why it moved
-----------------------------------
`mail.mail.send()` opens ONE SMTP session per batch and hands it to
`ir.mail_server.send_email()` for each message. On Odoo 15 the opener was
`connect()`; **Odoo 19 renamed it `_connect__`** (`odoo/addons/base/models/
ir_mail_server.py`, called from `odoo/addons/mail/models/mail_mail.py`).
The 15-era override of `connect()` was carried onto 19 with only its
manifest version changed, so on 19 the core opener ran, found no SMTP server
and refused every mail before `send_email` — the relay's own method — was
ever reached. The override is on `_connect__` now, and
`tests/test_relay.py` asserts that the name this module overrides is the
name `mail.mail` calls, so a second rename fails a test instead of
silently disconnecting the relay again.

Relay contract (https://dev-api.akraa.io/api/v1/public/email/send):
  POST <url>   Content-Type: application/json
    {"secret": "...", "to_email": "...", "to_name": "...",
     "subject": "...", "body": "<html>"}
  200 {"success": true,  "message": "Email sent successfully"}
  4xx {"success": false, "error": "..."}

One recipient per request, so a message with several To/Cc/Bcc addresses
is delivered as one POST per address. No attachments; HTML body only.
"""
import email.utils
import logging

import requests

from odoo import _, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RELAY_TIMEOUT_SECONDS = 30


class _RelaySession:
    """Stand-in for an smtplib.SMTP instance while the relay is active.

    `mail.mail.send()` opens a session before its per-message loop and quits
    it afterwards; `send_email()` receives it as `smtp_session`. With the
    relay there is no socket, so this object keeps that lifecycle happy and
    does nothing. Delivery happens in `send_email()` over HTTPS.

    Anything else — the SMTP verbs the *Test Connection* button speaks —
    raises a UserError that says what is going on, instead of an
    AttributeError that says nothing.
    """

    def __init__(self, url):
        self.url = url

    def quit(self):
        pass

    def close(self):
        pass

    def noop(self):
        return (250, b"OK")

    def __getattr__(self, name):
        # Dunders and private names stay ordinary attribute misses, so
        # hasattr(), copy, mock and Odoo's own frame-walking `_()` — which
        # reads the caller's `self` — behave. No `_()` here on purpose: it
        # inspects this object and would recurse into this method.
        if name.startswith("_"):
            raise AttributeError(name)
        raise UserError(
            "Outbound mail is routed through the HTTPS relay at %s; "
            "there is no SMTP connection to %s." % (self.url, name)
        )


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    # ─── configuration ──────────────────────────────────────────────

    def _cadra_relay_config(self):
        """Return (url, secret) when both are set, else (None, None).

        Both are required because the relay refuses a request without a
        secret (`Field validation for 'Secret' failed on the 'required'
        tag`), so a URL alone could never deliver anything.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        url = (ICP.get_param("cadra.email_relay_url") or "").strip()
        secret = (ICP.get_param("cadra.email_relay_secret") or "").strip()
        return (url, secret) if (url and secret) else (None, None)

    def _cadra_relay_active(self):
        """The relay is configured AND sending is not disabled.

        `_disable_send()` is core's own switch: no mail leaves during a test
        run or while the registry is initialising. The relay honours it for
        the same reason SMTP does — an in-registry suite on a tenant with
        the relay configured must not mail anybody.
        """
        url, secret = self._cadra_relay_config()
        return bool(url and secret) and not self._disable_send()

    # ─── the two hooks mail.mail.send() calls ───────────────────────

    def _connect__(self, *args, **kwargs):  # noqa: PLW3201
        # Odoo 19's name for the session opener (15 called it `connect`).
        # `mail.mail.send()` calls it once per batch, BEFORE `send_email`;
        # on a cluster with no SMTP route the real one fails here and the
        # relay is never reached. Return a placeholder session instead.
        if self._cadra_relay_active():
            url, _secret = self._cadra_relay_config()
            _logger.debug("email relay active — skipping SMTP connect")
            return _RelaySession(url)
        return super()._connect__(*args, **kwargs)

    def send_email(self, message, mail_server_id=None, smtp_server=None,
                   smtp_port=None, smtp_user=None, smtp_password=None,
                   smtp_encryption=None, smtp_ssl_certificate=None,
                   smtp_ssl_private_key=None, smtp_debug=False,
                   smtp_session=None):
        if not self._cadra_relay_active():
            return super().send_email(
                message, mail_server_id=mail_server_id, smtp_server=smtp_server,
                smtp_port=smtp_port, smtp_user=smtp_user,
                smtp_password=smtp_password, smtp_encryption=smtp_encryption,
                smtp_ssl_certificate=smtp_ssl_certificate,
                smtp_ssl_private_key=smtp_ssl_private_key,
                smtp_debug=smtp_debug, smtp_session=smtp_session,
            )
        return self._cadra_relay_deliver(message)

    # ─── delivery ───────────────────────────────────────────────────

    def _cadra_relay_deliver(self, message):
        """POST `message` to the relay, once per recipient.

        Returns the Message-Id on success. Raises MailDeliveryException on
        the first failure, naming how many recipients were already sent so
        the failure reason on the mail.mail row tells the whole story.
        Does NOT consult `_disable_send()`: that is the caller's gate, and
        the tests call this directly with the HTTP client mocked.
        """
        relay_url, relay_secret = self._cadra_relay_config()
        if not relay_url:
            raise MailDeliveryException(
                _("Email relay is not configured"),
                "cadra.email_relay_url / cadra.email_relay_secret are unset",
            )
        recipients = self._cadra_relay_recipients(message)
        if not recipients:
            raise MailDeliveryException(
                _("Email relay: message has no recipient"),
                message.get("Subject", "") or "",
            )
        subject = message.get("Subject", "") or ""
        body = self._extract_html_body(message)

        sent = 0
        for to_email, to_name in recipients:
            payload = {
                "secret": relay_secret,
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "body": body,
            }
            try:
                self._cadra_relay_post(relay_url, payload)
            except MailDeliveryException as exc:
                if sent:
                    raise MailDeliveryException(
                        exc.args[0],
                        "%s (after %d of %d recipient(s) were delivered)"
                        % (exc.args[1] if len(exc.args) > 1 else "",
                           sent, len(recipients)),
                    ) from exc
                raise
            sent += 1
            _logger.info(
                "email relay: sent to %s (subject=%r) via %s",
                to_email, subject, relay_url,
            )

        return message.get("Message-Id") or email.utils.make_msgid()

    @staticmethod
    def _cadra_relay_post(url, payload):
        """One relay request. Raises MailDeliveryException on any refusal.

        A refusal is three things, in the order the relay produces them: no
        answer at all, an HTTP error, or a 200 whose body says
        `success: false`. The relay's own `error`/`message` text is carried
        into the exception verbatim, because it is what the owner reads on
        the mail.mail row.
        """
        try:
            response = requests.post(
                url, json=payload, timeout=RELAY_TIMEOUT_SECONDS,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise MailDeliveryException(
                _("Email relay request failed"), str(exc)
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        detail = body.get("error") or body.get("message") or response.text[:500]

        if response.status_code >= 400:
            raise MailDeliveryException(
                _("Email relay returned HTTP %s", response.status_code), detail,
            )
        if not body.get("success", True):
            raise MailDeliveryException(
                _("Email relay rejected the message"), detail,
            )
        return body

    # ─── message → payload ──────────────────────────────────────────

    @staticmethod
    def _cadra_relay_recipients(message):
        """Every (email, name) across To, Cc and Bcc, deduplicated, in order.

        The relay takes one recipient per request, so each of these becomes
        its own POST. Core's own path (`_prepare_email_message__`) reads the
        same three headers for the SMTP envelope.
        """
        raw = []
        for header in ("To", "Cc", "Bcc"):
            raw.extend(message.get_all(header, []) or [])
        seen = set()
        out = []
        for name, address in email.utils.getaddresses(raw):
            address = (address or "").strip()
            if not address or address.lower() in seen:
                continue
            seen.add(address.lower())
            out.append((address, name or ""))
        return out

    @staticmethod
    def _extract_html_body(message):
        """Pull the text/html part out of a (possibly multipart) message.

        Falls back to text/plain wrapped in <pre> if no HTML part exists,
        which keeps text-only mails (a password reset, by default) readable.
        """
        html_part = None
        text_part = None
        if message.is_multipart():
            for part in message.walk():
                ctype = part.get_content_type()
                if ctype == "text/html" and html_part is None:
                    html_part = part
                elif ctype == "text/plain" and text_part is None:
                    text_part = part
        else:
            if message.get_content_type() == "text/html":
                html_part = message
            else:
                text_part = message

        if html_part is not None:
            payload = html_part.get_payload(decode=True)
            charset = html_part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace") if payload else ""

        if text_part is not None:
            payload = text_part.get_payload(decode=True)
            charset = text_part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace") if payload else ""
            return "<pre>%s</pre>" % text

        return ""
