"""Redhubs / external asset-register export.

Handoff 17 item B. Two things about these routes were wrong in the same way.

**The credential had a default baked into the source.** Both routes resolved
the expected key with ``get_param('...redhubs_api_key', 'NRS_REDHUBS_KEY_...')``
— so on any tenant where that parameter was never set, the thing standing
between an unauthenticated caller and a full dump of the asset register was a
string committed to this repository. Unset configuration now REFUSES. An
absent credential is the one case where "no check" and "check passed" are the
same code path, and it is not a state this route may serve from.

Note the falsy handling: ``get_param`` with no default returns ``False`` for a
parameter that does not exist, and a stored empty string is just as empty. Both
refuse; neither is allowed to compare-equal to an absent header.

**The CSV route took its credential in the query string**, where it lands in
nginx access logs, every intervening proxy's logs and browser history. It is
header-only now (``X-API-Key``, matching its JSON sibling); ``?api_key=``
still works for ONE more release and logs a deprecation WARNING naming the
caller each time it is the thing that supplied the credential.

The literals that used to sit here are in git history and cannot be removed
from it. Whatever they authenticate must be rotated on the box — see
``docs/handoffs/17-REPORT.md``.
"""
import csv
import hmac
import io
import logging

from odoo import http, fields
from odoo.http import request

from odoo.addons.myservice_nrs_base.caller_ip import caller_ip_label

_logger = logging.getLogger(__name__)

#: The ONE name of the Redhubs credential in this module. Resolved in exactly
#: one place below, so a default cannot be reintroduced in only one of the two
#: routes that use it — which is how it survived here for as long as it did.
REDHUBS_KEY_PARAM = 'myservice_identity.redhubs_api_key'


def _expected_redhubs_key():
    """The configured Redhubs key, or ``None`` when the tenant has none.

    Called with NO default on purpose. ``get_param`` returns ``False`` for a
    parameter that was never set; a stored empty value is treated the same way.
    Either answer means "this route is not configured", and the caller must
    refuse rather than compare against nothing.
    """
    value = request.env['ir.config_parameter'].sudo().get_param(REDHUBS_KEY_PARAM)
    return value or None


def _secrets_equal(supplied, expected):
    """Constant-time comparison of two credentials.

    ``hmac.compare_digest`` refuses non-ASCII ``str`` operands, and a header is
    caller-supplied text, so both sides are encoded to bytes first.
    """
    return hmac.compare_digest(
        str(supplied or '').encode('utf-8'),
        str(expected or '').encode('utf-8'),
    )


def _log_unconfigured(route):
    """Say — at ERROR — that a published route is standing unconfigured.

    ERROR, not WARNING: a route that dumps the entire asset register with no
    credential behind it is an error state. It must be findable in a log by an
    operator rather than discovered from a leak.

    The response body deliberately does not carry any of this. These are
    ``auth='none'`` routes; naming our own configuration to an unauthenticated
    caller tells them exactly which parameter to hope stays unset.
    """
    _logger.error(
        'REFUSED %s: the credential is not configured. Set the '
        'ir.config_parameter %r on database %s; until then this route '
        'answers Unauthorized to every caller.',
        route, REDHUBS_KEY_PARAM, request.env.cr.dbname,
    )


def _log_bad_credential(route):
    """Say who failed, at WARNING.

    Both of these routes used to refuse a wrong key in silence. The SAP
    webhook and the WorkSpace callback both log a named caller on the same
    event, and the asymmetry was the wrong way round: these two return a
    FULL DUMP OF THE ASSET REGISTER, so a brute force against them is the
    one worth being able to see. It left no trace at all.

    The caller comes from `caller_ip_label`, which parses the value before
    printing it — the key itself is never logged, for the same reason
    `POST /auth/token` logs a sanitised client id and never the secret.
    """
    _logger.warning('%s: invalid API key. %s', route, caller_ip_label())


class RedhubsAPIController(http.Controller):

    def _check_api_key(self):
        """True only when a CONFIGURED key matches the ``X-API-Key`` header."""
        expected = _expected_redhubs_key()
        if expected is None:
            _log_unconfigured('/api/myservice/assets/export')
            return False
        if _secrets_equal(request.httprequest.headers.get('X-API-Key'), expected):
            return True
        _log_bad_credential('/api/myservice/assets/export')
        return False

    @http.route(
        '/api/myservice/assets/export', type='json', auth='none',
        methods=['POST'], csrf=False,
    )
    def export_assets(self, **kwargs):
        """Outbound asset register for Redhubs / external systems.

        Authenticated by the ``X-API-Key`` header against
        ``myservice_identity.redhubs_api_key``. An unset parameter refuses.
        """
        if not self._check_api_key():
            return {'success': False, 'error': 'Unauthorized'}

        assets = request.env['nrs.asset'].sudo().search([])
        result = []
        for a in assets:
            result.append({
                'asset_code': a.asset_code,
                'name': a.name,
                'category': a.category_id.name if a.category_id else None,
                'condition': a.condition,
                'state': a.state,
                'location': a.location_id.name if a.location_id else None,
                'assigned_to': a.custodian_id.name if a.custodian_id else None,
                'assigned_ir': a.assigned_ir_number or None,
                'assigned_dept': a.assigned_employee_dept or None,
                'assignment_date': str(a.assignment_date) if a.assignment_date else None,
                'retrieval_flag': a.retrieval_flag,
                'serial_number': a.serial_number or None,
                'last_updated': str(fields.Datetime.now()),
            })
        return {
            'success': True,
            'count': len(result),
            'assets': result,
            'exported_at': str(fields.Datetime.now()),
        }

    def _csv_supplied_key(self):
        """The credential this CSV request presented, or ``None``.

        Header first. ``?api_key=`` is DEPRECATED and is read only when no
        header was sent — and every time it is the thing that supplied the
        credential, the caller is named in a WARNING, so the migration has a
        visible end date instead of an open-ended one.

        The IP comes from ``caller_ip_label``, which parses the value before
        printing it. A header value may legally contain spaces, and ``ip=`` is
        the last field on the line — interpolating a raw one would let an
        unauthenticated caller append fields to our own log.
        """
        header = request.httprequest.headers.get('X-API-Key')
        if header is not None:
            return header
        query = request.httprequest.args.get('api_key')
        if query is not None:
            _logger.warning(
                'DEPRECATED: /api/myservice/assets/export/csv was '
                'authenticated by the ?api_key= query parameter, which lands '
                'in proxy access logs and browser history. Send the X-API-Key '
                'header instead; the query parameter is removed in the next '
                'release. %s', caller_ip_label(),
            )
            return query
        return None

    @http.route(
        '/api/myservice/assets/export/csv', type='http', auth='none',
        methods=['GET'], csrf=False,
    )
    def export_assets_csv(self, **kwargs):
        """CSV export for systems that don't support JSON.

        Authenticated by the ``X-API-Key`` header, matching this route's JSON
        sibling.

        .. deprecated::
           The ``?api_key=`` query parameter is still accepted for ONE more
           release and each use is logged as a WARNING naming the caller. It
           puts a live credential into every access log between the caller and
           this process. Send the header.
        """
        expected = _expected_redhubs_key()
        if expected is None:
            _log_unconfigured('/api/myservice/assets/export/csv')
            return request.make_response('Unauthorized', status=401)
        if not _secrets_equal(self._csv_supplied_key(), expected):
            _log_bad_credential('/api/myservice/assets/export/csv')
            return request.make_response('Unauthorized', status=401)

        assets = request.env['nrs.asset'].sudo().search([])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Asset Code', 'Name', 'Category', 'Condition', 'State',
            'Location', 'Assigned To', 'IR Number', 'Department',
            'Assignment Date', 'Retrieval Flag', 'Serial Number',
        ])
        for a in assets:
            writer.writerow([
                a.asset_code,
                a.name,
                a.category_id.name if a.category_id else '',
                a.condition or '',
                a.state or '',
                a.location_id.name if a.location_id else '',
                a.custodian_id.name if a.custodian_id else '',
                a.assigned_ir_number or '',
                a.assigned_employee_dept or '',
                str(a.assignment_date) if a.assignment_date else '',
                'YES' if a.retrieval_flag else 'NO',
                a.serial_number or '',
            ])
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'text/csv'),
                ('Content-Disposition', 'attachment; filename=nrs_assets.csv'),
            ],
        )
