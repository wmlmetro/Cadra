"""The HTTPS mail relay on Odoo 19 — that it is reached, and what it sends.

The 15-era module overrode `ir.mail_server.connect()`. Odoo 19 renamed the
session opener `_connect__`, so the override went dead on the upgrade and
every outbound mail stopped at *Unable to connect to SMTP Server* before the
relay was ever consulted. The first class below pins the hook to the name
`mail.mail` actually calls, by reading core, so a second rename fails here
rather than in production.

Nothing in this file talks to the network: `requests.post` is mocked at the
module that imports it. And nothing in this file can mail anybody even if it
were not — `_disable_send()` is true under `--test-enable`, and the second
class proves the relay honours it.

Run with:
    odoo -d <db> -u myservice_email_relay --test-enable \\
         --test-tags /myservice_email_relay --stop-after-init --workers=0
"""
import inspect
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from odoo.addons.base.models import ir_mail_server as core_mail_server
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.addons.mail.models import mail_mail as core_mail_mail
from odoo.addons.myservice_email_relay.models import ir_mail_server as relay
from odoo.exceptions import UserError
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.tests import tagged

POST = "odoo.addons.myservice_email_relay.models.ir_mail_server.requests.post"
RELAY_URL = "https://dev-api.akraa.io/api/v1/public/email/send"
RELAY_SECRET = "test-secret-not-real"


def _message(to="Michael Mamman <michaelyak66@example.com>", cc=None, bcc=None,
             subject="Test", html="<p>hello</p>", text="hello"):
    msg = EmailMessage()
    msg["From"] = "Cadra <noreply@example.com>"
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg["Message-Id"] = "<probe@example.com>"
    if text is not None:
        msg.set_content(text)
    if html is not None:
        if text is not None:
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(html, subtype="html")
    return msg


def _response(status=200, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    if body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = body
    return resp


class RelayCase(CadraTransactionCase):
    def setUp(self):
        super().setUp()
        self.Mail = self.env["ir.mail_server"]
        self.ICP = self.env["ir.config_parameter"].sudo()

    def configure(self, url=RELAY_URL, secret=RELAY_SECRET, text_field=None):
        self.ICP.set_param("cadra.email_relay_url", url or "")
        self.ICP.set_param("cadra.email_relay_secret", secret or "")
        # `False` deletes the row (an absent parameter); "" would store an
        # empty one. Both must mean "send no text field" — tested below.
        self.ICP.set_param(relay.TEXT_FIELD_PARAM, text_field if text_field is not None else False)


@tagged("post_install", "-at_install")
class TestTheHookIsTheOneMailCalls(RelayCase):
    """The defect this module carried from 15 to 19, kept as a guard."""

    def test_mail_mail_opens_its_session_with_the_name_we_override(self):
        source = inspect.getsource(core_mail_mail.MailMail.send)
        self.assertIn(
            "._connect__(", source,
            "mail.mail.send() no longer calls _connect__; move the relay's "
            "override to whatever it calls now, or the relay is never reached",
        )
        self.assertIn("_connect__", relay.IrMailServer.__dict__)
        self.assertNotIn(
            "connect", relay.IrMailServer.__dict__,
            "a `connect` override is dead code on 19 and misleads the reader",
        )

    def test_send_email_accepts_every_argument_core_declares(self):
        core_params = inspect.signature(core_mail_server.IrMail_Server.send_email).parameters
        ours = inspect.signature(relay.IrMailServer.send_email).parameters
        missing = set(core_params) - set(ours)
        self.assertFalse(
            missing, f"relay's send_email() lacks core's arguments {sorted(missing)}",
        )


@tagged("post_install", "-at_install")
class TestNothingLeavesInTestMode(RelayCase):
    """`_disable_send()` is true here, and the relay must obey it."""

    def test_unconfigured_relay_delegates_and_posts_nothing(self):
        self.configure(url="", secret="")
        with patch(POST) as post:
            self.assertIsNone(self.Mail._connect__())
            msg_id = self.Mail.send_email(_message())
        self.assertEqual(msg_id, "<probe@example.com>")
        post.assert_not_called()

    def test_configured_relay_still_posts_nothing_under_test(self):
        self.configure()
        self.assertTrue(self.Mail._disable_send())
        self.assertFalse(self.Mail._cadra_relay_active())
        with patch(POST) as post:
            self.assertIsNone(self.Mail._connect__())
            msg_id = self.Mail.send_email(_message())
        self.assertEqual(msg_id, "<probe@example.com>")
        post.assert_not_called()

    def test_url_without_secret_is_not_configured(self):
        # The relay refuses a request without a secret, so a URL alone could
        # never deliver; treating it as "configured" would only swap one
        # failure reason for another.
        self.configure(secret="")
        self.assertEqual(self.Mail._cadra_relay_config(), (None, None))

    def test_session_opener_returns_a_placeholder_when_live(self):
        self.configure()
        with patch.object(type(self.Mail), "_disable_send", return_value=False):
            session = self.Mail._connect__()
        self.assertIsInstance(session, relay._RelaySession)
        session.quit()
        session.close()
        self.assertEqual(session.noop(), (250, b"OK"))
        # The Test Connection button speaks SMTP verbs; it gets an answer.
        with self.assertRaises(UserError) as caught:
            session.mail("x@example.com")
        self.assertIn(RELAY_URL, str(caught.exception))

    def test_send_email_posts_when_live(self):
        self.configure()
        with patch.object(type(self.Mail), "_disable_send", return_value=False), \
                patch(POST, return_value=_response(200, {"success": True})) as post:
            msg_id = self.Mail.send_email(_message(), smtp_session=relay._RelaySession(RELAY_URL))
        self.assertEqual(msg_id, "<probe@example.com>")
        post.assert_called_once()


@tagged("post_install", "-at_install")
class TestWhatIsPosted(RelayCase):
    """The relay's contract, keyed exactly."""

    def setUp(self):
        super().setUp()
        self.configure()

    def test_payload_is_the_five_keys_the_relay_accepts(self):
        with patch(POST, return_value=_response(200, {"success": True})) as post:
            msg_id = self.Mail._cadra_relay_deliver(_message())
        self.assertEqual(msg_id, "<probe@example.com>")
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], RELAY_URL)
        self.assertEqual(kwargs["timeout"], relay.RELAY_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["headers"], {"Content-Type": "application/json"})
        self.assertEqual(
            kwargs["json"],
            {
                "secret": RELAY_SECRET,
                "to_email": "michaelyak66@example.com",
                "to_name": "Michael Mamman",
                "subject": "Test",
                "body": "<p>hello</p>\n",
            },
        )

    def test_one_post_per_recipient_across_to_cc_bcc(self):
        msg = _message(
            to="A <a@example.com>, b@example.com",
            cc="C <c@example.com>, A again <A@example.com>",
            bcc="d@example.com",
        )
        with patch(POST, return_value=_response(200, {"success": True})) as post:
            self.Mail._cadra_relay_deliver(msg)
        sent = [c.kwargs["json"]["to_email"] for c in post.call_args_list]
        self.assertEqual(
            sent, ["a@example.com", "b@example.com", "c@example.com", "d@example.com"],
        )
        self.assertEqual(post.call_args_list[0].kwargs["json"]["to_name"], "A")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["to_name"], "")

    def test_no_recipient_is_a_delivery_exception_before_any_post(self):
        msg = _message(to="")
        del msg["To"]
        with patch(POST) as post, self.assertRaises(MailDeliveryException):
            self.Mail._cadra_relay_deliver(msg)
        post.assert_not_called()

    def test_text_only_message_is_wrapped_in_pre(self):
        msg = _message(html=None, text="reset your password")
        with patch(POST, return_value=_response(200, {"success": True})) as post:
            self.Mail._cadra_relay_deliver(msg)
        self.assertEqual(
            post.call_args.kwargs["json"]["body"], "<pre>reset your password\n</pre>",
        )


@tagged("post_install", "-at_install")
class TestRefusals(RelayCase):
    """Every way the relay says no becomes a MailDeliveryException carrying
    the relay's own words, because that text is what lands on the
    mail.mail row's failure_reason."""

    def setUp(self):
        super().setUp()
        self.configure()

    def test_http_400_carries_the_relay_error_text(self):
        # Verbatim from the dev relay on 2026-10-02 for an empty secret.
        refusal = {
            "success": False,
            "error": "Invalid request body: Key: 'PublicSendEmailRequest.Secret' "
                     "Error:Field validation for 'Secret' failed on the 'required' tag",
        }
        with patch(POST, return_value=_response(400, refusal)), \
                self.assertRaises(MailDeliveryException) as caught:
            self.Mail._cadra_relay_deliver(_message())
        self.assertIn("HTTP 400", str(caught.exception.args[0]))
        self.assertIn("'Secret' failed on the 'required' tag", caught.exception.args[1])

    def test_200_with_success_false_is_a_refusal(self):
        with patch(POST, return_value=_response(200, {"success": False, "message": "quota"})), \
                self.assertRaises(MailDeliveryException) as caught:
            self.Mail._cadra_relay_deliver(_message())
        self.assertEqual(caught.exception.args[1], "quota")

    def test_200_with_no_json_body_is_a_success(self):
        with patch(POST, return_value=_response(200, None, text="ok")):
            msg_id = self.Mail._cadra_relay_deliver(_message())
        self.assertEqual(msg_id, "<probe@example.com>")

    def test_network_failure_is_a_delivery_exception(self):
        with patch(POST, side_effect=relay.requests.ConnectionError("dns")), \
                self.assertRaises(MailDeliveryException) as caught:
            self.Mail._cadra_relay_deliver(_message())
        self.assertEqual(caught.exception.args[1], "dns")

    def test_a_failure_after_a_success_says_how_many_were_delivered(self):
        msg = _message(to="a@example.com, b@example.com, c@example.com")
        responses = [
            _response(200, {"success": True}),
            _response(502, None, text="bad gateway"),
        ]
        with patch(POST, side_effect=responses) as post, \
                self.assertRaises(MailDeliveryException) as caught:
            self.Mail._cadra_relay_deliver(msg)
        self.assertEqual(post.call_count, 2)
        self.assertIn("after 1 of 3 recipient(s) were delivered", caught.exception.args[1])
        self.assertIn("bad gateway", caught.exception.args[1])


@tagged("post_install", "-at_install")
class TestThePlainTextPart(RelayCase):
    """Handoff 45 H.3. Odoo builds every HTML mail with a text/plain
    alternative, and a reader with HTML switched off reads that part. The
    relay's five keys carried the HTML only, so through the relay that
    reader received nothing.

    The relay is not ours and its plain-text field name is unconfirmed, so
    the field is named by `cadra.email_relay_text_field` — and absent or
    empty must post EXACTLY the five keys it always did, because a relay
    that refuses an unknown key would otherwise refuse every mail."""

    def setUp(self):
        super().setUp()
        self.configure()

    def _post(self, msg):
        with patch(POST, return_value=_response(200, {"success": True})) as post:
            self.Mail._cadra_relay_deliver(msg)
        post.assert_called_once()
        return post.call_args.kwargs["json"]

    def test_absent_parameter_posts_the_five_keys_and_nothing_else(self):
        self.assertFalse(self.ICP.get_param(relay.TEXT_FIELD_PARAM))
        self.assertEqual(set(self._post(_message())), set(relay.RELAY_KEYS))

    def test_empty_parameter_is_the_same_as_absent(self):
        # set_param(key, "") on 19 stores an empty string rather than
        # deleting the row; it must not be read as a field named "".
        self.configure(text_field="  ")
        self.assertEqual(set(self._post(_message())), set(relay.RELAY_KEYS))

    def test_named_field_carries_the_text_part(self):
        self.configure(text_field="body_text")
        payload = self._post(_message(html="<p>hello</p>", text="hello, in plain words"))
        self.assertEqual(payload["body_text"], "hello, in plain words\n")
        self.assertEqual(payload["body"], "<p>hello</p>\n", "the HTML body is unchanged")
        self.assertEqual(set(payload), set(relay.RELAY_KEYS) | {"body_text"})

    def test_every_recipient_gets_the_text_part(self):
        self.configure(text_field="body_text")
        msg = _message(to="a@example.com, b@example.com", text="plain")
        with patch(POST, return_value=_response(200, {"success": True})) as post:
            self.Mail._cadra_relay_deliver(msg)
        self.assertEqual(
            [c.kwargs["json"].get("body_text") for c in post.call_args_list],
            ["plain\n", "plain\n"],
        )

    def test_html_only_message_sends_no_text_field(self):
        # Nothing is derived from the HTML here: no text part, no key.
        self.configure(text_field="body_text")
        payload = self._post(_message(html="<p>only html</p>", text=None))
        self.assertNotIn("body_text", payload)
        self.assertEqual(payload["body"], "<p>only html</p>\n")

    def test_text_only_message_keeps_its_pre_body_and_adds_the_text(self):
        self.configure(text_field="body_text")
        payload = self._post(_message(html=None, text="reset your password"))
        self.assertEqual(payload["body"], "<pre>reset your password\n</pre>")
        self.assertEqual(payload["body_text"], "reset your password\n")

    def test_a_base64_text_part_is_decoded(self):
        # Non-ASCII makes the stdlib choose base64 or quoted-printable for the
        # part; the relay must receive the words, not the transfer encoding.
        self.configure(text_field="body_text")
        words = "Dear Adébáyọ̀, your account is ready. " * 6
        msg = EmailMessage()
        msg["To"] = "a@example.com"
        msg["Subject"] = "Test"
        msg.add_alternative(words, subtype="plain", charset="utf-8", cte="base64")
        msg.add_alternative("<p>x</p>", subtype="html", charset="utf-8")
        self.assertEqual(
            next(p for p in msg.walk() if p.get_content_type() == "text/plain")
            ["Content-Transfer-Encoding"], "base64")
        self.assertEqual(self._post(msg)["body_text"], words + "\n")

    def test_a_quoted_printable_text_part_is_decoded(self):
        self.configure(text_field="body_text")
        words = "Café = coffee; the link is https://example.com/?a=1&b=2"
        msg = EmailMessage()
        msg["To"] = "a@example.com"
        msg["Subject"] = "Test"
        msg.add_alternative(words, subtype="plain", charset="utf-8",
                            cte="quoted-printable")
        msg.add_alternative("<p>x</p>", subtype="html", charset="utf-8")
        self.assertEqual(self._post(msg)["body_text"], words + "\n")

    def test_an_attached_text_file_is_not_the_body(self):
        self.configure(text_field="body_text")
        msg = _message(html=None, text="the letter")
        msg.add_attachment(b"not the letter", "text", "plain", filename="notes.txt")
        payload = self._post(msg)
        self.assertEqual(payload["body_text"], "the letter\n")
        self.assertEqual(payload["body"], "<pre>the letter\n</pre>")

    def test_a_name_colliding_with_a_relay_key_is_refused_before_any_post(self):
        for name in relay.RELAY_KEYS:
            self.configure(text_field=name)
            with patch(POST) as post, \
                    self.assertRaises(MailDeliveryException) as caught:
                self.Mail._cadra_relay_deliver(_message())
            post.assert_not_called()
            self.assertIn(relay.TEXT_FIELD_PARAM, caught.exception.args[1])
