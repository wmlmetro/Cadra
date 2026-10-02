{
    'name': 'Cadra Email Relay',
    'version': '19.0.1.1.0',
    'summary': 'Send outbound mail via an HTTPS relay (bypasses SMTP egress blocks).',
    'description': """
Outbound mail bridge for environments where direct SMTP egress is blocked
(DigitalOcean Kubernetes blocks ports 25/465/587 on new accounts). When
BOTH `cadra.email_relay_url` and `cadra.email_relay_secret` are set in
ir.config_parameter, ir.mail_server opens no SMTP session and
send_email() POSTs each message to that URL instead. When either is
empty, behaviour is unchanged (native SMTP). Nothing is posted while
sending is disabled (a test run, registry init) — same switch as SMTP.

On Odoo 19 the session opener is `_connect__` (15 called it `connect`);
the override follows the 19 name and its test pins it to what mail.mail
calls. Version 19.0.1.0.0 overrode `connect` and was dead on 19.

Relay contract (https://dev-api.akraa.io/api/v1/public/email/send)::

  POST <url>
    Content-Type: application/json
    { "secret": "...", "to_email": "...", "to_name": "...",
      "subject": "...", "body": "<html>" }
  -> 200 { "success": true,  "message": "Email sent successfully" }
  -> 4xx { "success": false, "error": "..." }

Limitations vs. native SMTP:

  - One recipient per request: a message's To/Cc/Bcc become one POST each.
  - No attachments.
  - HTML body only; the plain-text alternative is discarded.
""",
    'author': 'WestMetro Limited',
    'website': 'https://westmetrong.com',
    'category': 'Tools',
    'depends': ['mail'],
    'data': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
