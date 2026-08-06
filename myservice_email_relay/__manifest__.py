{
    'name': 'Cadra Email Relay',
    'version': '19.0.1.0.0',
    'summary': 'Send outbound mail via an HTTPS relay (bypasses SMTP egress blocks).',
    'description': """
Temporary outbound mail bridge for environments where direct SMTP egress
is blocked (e.g. DigitalOcean Kubernetes blocks ports 25/465/587 on new
accounts). When `cadra.email_relay_url` is set in ir.config_parameter,
ir.mail_server.send_email() POSTs to that URL instead of opening an
SMTP connection. When the parameter is empty, behaviour is unchanged
(falls through to native SMTP) — so local dev keeps using Zoho directly.

Relay contract (matches https://staging.akraa.io spec):
  POST <url>
    Content-Type: application/json
    { "secret": "...", "to_email": "...", "to_name": "...",
      "subject": "...", "body": "<html>" }
  -> 200 { "success": true, "message": "Email sent successfully" }

Limitations vs. native SMTP:
  - Single To recipient (no Cc/Bcc — the relay API doesn't accept them).
  - No attachments.
  - HTML body only; plain-text alternative is discarded.
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
