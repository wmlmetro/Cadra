"""Outbound mail bridge — POST to an HTTPS relay instead of opening SMTP.

DigitalOcean Kubernetes blocks outbound SMTP (25/465/587) on new accounts,
so direct smtplib.connect() from a pod hangs and times out. This override
detects whether a relay is configured via ir.config_parameter and routes
mail through HTTPS (port 443, never blocked) instead.

When `cadra.email_relay_url` is empty the native SMTP path runs unchanged,
so local dev with Zoho keeps working.
"""
import email.utils
import logging

import requests

from odoo import models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)

RELAY_TIMEOUT_SECONDS = 30


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    def send_email(self, message, mail_server_id=None, smtp_server=None,
                   smtp_port=None, smtp_user=None, smtp_password=None,
                   smtp_encryption=None, smtp_debug=False, smtp_session=None):
        ICP = self.env["ir.config_parameter"].sudo()
        relay_url = (ICP.get_param("cadra.email_relay_url") or "").strip()
        relay_secret = (ICP.get_param("cadra.email_relay_secret") or "").strip()

        if not relay_url or not relay_secret:
            return super().send_email(
                message, mail_server_id=mail_server_id, smtp_server=smtp_server,
                smtp_port=smtp_port, smtp_user=smtp_user, smtp_password=smtp_password,
                smtp_encryption=smtp_encryption, smtp_debug=smtp_debug,
                smtp_session=smtp_session,
            )

        payload = self._build_relay_payload(message, relay_secret)
        try:
            response = requests.post(
                relay_url, json=payload, timeout=RELAY_TIMEOUT_SECONDS,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise MailDeliveryException(
                "Email relay request failed", str(exc)
            ) from exc

        if response.status_code >= 400:
            raise MailDeliveryException(
                "Email relay returned HTTP %s" % response.status_code,
                response.text[:500],
            )

        try:
            body = response.json()
        except ValueError:
            body = {}
        if not body.get("success", True):
            raise MailDeliveryException(
                "Email relay rejected the message",
                body.get("message") or response.text[:500],
            )

        message_id = message.get("Message-Id") or email.utils.make_msgid()
        _logger.info(
            "email relay: sent to %s (subject=%r) via %s",
            payload["to_email"], payload["subject"], relay_url,
        )
        return message_id

    @staticmethod
    def _build_relay_payload(message, secret):
        """Flatten an EmailMessage into the relay's JSON contract."""
        to_email, to_name = IrMailServer._first_recipient(message)
        return {
            "secret": secret,
            "to_email": to_email,
            "to_name": to_name,
            "subject": message.get("Subject", "") or "",
            "body": IrMailServer._extract_html_body(message),
        }

    @staticmethod
    def _first_recipient(message):
        """Return (email, name) for the first To recipient.

        The relay API accepts only a single recipient. If the original
        message had multiple, the rest are dropped (and a warning logged
        by the caller's audit trail in mail.mail).
        """
        raw_to = message.get_all("To", []) or [message.get("To", "")]
        addresses = email.utils.getaddresses(raw_to)
        if not addresses:
            return "", ""
        first_name, first_email = addresses[0]
        if len(addresses) > 1:
            _logger.warning(
                "email relay: dropping %d extra recipient(s); relay API supports only one",
                len(addresses) - 1,
            )
        return first_email, first_name

    @staticmethod
    def _extract_html_body(message):
        """Pull the text/html part out of a (possibly multipart) message.

        Falls back to text/plain wrapped in <pre> if no HTML part exists,
        which keeps password-reset mails (text-only by default) readable.
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
