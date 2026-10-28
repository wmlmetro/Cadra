"""A refused capture sync, kept (handoff 69 §5 C2).

A refused `POST /api/v1/audit/captures` writes nothing — by design: the
request's transaction is rolled back with the refusal. So a capture the
phone failed to send left no trace anybody but a log reader could see, and
the person holding the phone believed it submitted (handoff 69 Part A, H5).
This model is that trace: one row per refused POST, a replay refused again
is a second row.

WHAT IS KEPT is what identifies the attempt — who, from which device, for
which campaign and room, the capture's own id and code as sent, and the
answer the phone was given (status, code, reason, the sentence,
`request_id`). **Never the body's photos, fields or GPS**: a refusal is not
a capture, and what a capture would have held is not kept for one that was
not taken. Every as-sent value is text, cut at 200 characters, and an id is
linked only when it names a record that exists — a refusal is often BECAUSE
it does not.

ON ITS OWN CURSOR, for the reason `nrs.asset.tag.label._record_affix_refusal`
measured in handoff 51: the API decorator rolls the request back before the
answer leaves, so a row written on the request's cursor before that is
unwound with everything else. Under a running test the row goes on the
current cursor instead (the same branch, the same reason: a plain
`TransactionCase` would otherwise wait on its own uncommitted rows).

Append-only: created only by `_record`, never written, deleted only by the
retention cron once older than `RETENTION_DAYS`.
"""
import logging
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)

#: How long a refusal is kept (handoff 69 §5 C2).
RETENTION_DAYS = 90
#: The longest as-sent value kept; anything longer is cut, never refused.
_AS_SENT_MAX = 200
_CREATE_KEY = 'cadra_capture_refusal'
_PURGE_KEY = 'cadra_capture_refusal_purge'


def _text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return value.strip()[:_AS_SENT_MAX]


def _uuid_text(value):
    """The capture id as stored on a capture when it is one; as sent
    otherwise, so a malformed id is still findable by what the phone holds."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return _text(value)


class NRSAuditCaptureRefusal(models.Model):
    _name = 'nrs.audit.capture.refusal'
    _description = 'Refused capture sync'
    _order = 'id desc'
    _rec_name = 'request_id'

    refused_at = fields.Datetime(required=True, index=True, readonly=True)
    capture_uuid = fields.Char('Capture ID (as sent)', index=True,
                               readonly=True)
    user_id = fields.Many2one('res.users', 'Sent By', index=True,
                              readonly=True, ondelete='set null')
    device_code = fields.Char('Device (as sent)', readonly=True)
    device_id = fields.Many2one('nrs.audit.device', index=True, readonly=True,
                                ondelete='set null')
    campaign_id = fields.Many2one('nrs.audit.campaign', readonly=True,
                                  ondelete='set null')
    location_id = fields.Many2one('generic.location', 'Room', readonly=True,
                                  ondelete='set null')
    outcome = fields.Char('Outcome (as sent)', readonly=True)
    code = fields.Char('Code (as sent)', readonly=True)
    http_status = fields.Integer(required=True, readonly=True)
    error_code = fields.Char(readonly=True)
    reason = fields.Char(readonly=True)
    message = fields.Text('The sentence sent back', readonly=True)
    request_id = fields.Char(index=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(_CREATE_KEY):
            raise UserError(_(
                'A refused sync is recorded by the capture route, never '
                'entered by hand.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('A refused sync is a record of what the server '
                          'answered; it is never changed.'))

    def unlink(self):
        cutoff = fields.Datetime.now() - timedelta(days=RETENTION_DAYS)
        if not self.env.context.get(_PURGE_KEY) or any(
                r.refused_at > cutoff for r in self):
            raise UserError(_(
                'A refused sync is kept %d days and removed only by the '
                'retention job after that.') % RETENTION_DAYS)
        return super().unlink()

    @api.model
    def _values(self, body, header, answer):
        """The row for one refused POST: `body` the request's JSON as
        parsed (only the identifying keys are read), `header` the
        `X-Cadra-Device` value, `answer` the error object sent back."""
        body = body if isinstance(body, dict) else {}
        answer = answer if isinstance(answer, dict) else {}
        details = answer.get('details')
        details = details if isinstance(details, dict) else {}

        def linked(model, value):
            if not isinstance(value, int) or isinstance(value, bool) \
                    or value <= 0:
                return False
            return self.env[model].sudo().browse(value).exists().id or False

        device_code = _text(header)
        device = self.env['nrs.audit.device'].sudo().with_context(
            active_test=False).search(
                [('device_code', '=', device_code)], limit=1) \
            if device_code else self.env['nrs.audit.device']
        status = details.get('http_status')
        return {
            'refused_at': fields.Datetime.now(),
            'capture_uuid': _uuid_text(body.get('capture_id')),
            'user_id': self.env.uid,
            'device_code': device_code,
            'device_id': device.id or False,
            'campaign_id': linked('nrs.audit.campaign',
                                  body.get('campaign_id')),
            'location_id': linked('generic.location',
                                  body.get('location_id')),
            'outcome': _text(body.get('outcome')),
            'code': _text(body.get('code')),
            'http_status': status if isinstance(status, int) else 0,
            'error_code': _text(answer.get('code')),
            'reason': _text(details.get('reason')),
            'message': answer.get('message') if isinstance(
                answer.get('message'), str) else False,
            'request_id': _text(answer.get('request_id')),
        }

    @api.model
    def _record(self, body, header, answer):
        """Keep one refused sync, on its own cursor (the module docstring
        says why). A failure to record is an ERROR line and never changes
        the refusal the phone is sent."""
        try:
            vals = self._values(body, header, answer)
            if odoo_module.current_test:
                self.with_context(**{_CREATE_KEY: True}).sudo().create(vals)
                return
            with Registry(self.env.cr.dbname).cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                env['nrs.audit.capture.refusal'].with_context(
                    **{_CREATE_KEY: True}).sudo().create(vals)
                cr.commit()
        except Exception:   # noqa: BLE001
            # catch-all: reported — the refusal must reach the phone
            # whatever went wrong with its own bookkeeping, and an
            # unrecorded refusal leaves an ERROR line rather than nothing.
            _logger.exception("could not record the refused capture sync "
                              "(request %s)", (answer or {}).get('request_id'))

    @api.model
    def _cron_purge_old(self):
        cutoff = fields.Datetime.now() - timedelta(days=RETENTION_DAYS)
        old = self.sudo().search([('refused_at', '<', cutoff)])
        old.with_context(**{_PURGE_KEY: True}).unlink()
        return len(old)
