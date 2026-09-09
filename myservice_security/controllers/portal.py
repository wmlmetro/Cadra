import logging

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

# Shown to the visitor when the failure is ours, not theirs. Deliberately says
# nothing: this page is `auth='public'`, so whatever goes in `values['error']`
# is rendered to an unauthenticated caller.
_INTERNAL_ERROR = (
    "Sorry — we could not record your report. Please try again, or contact "
    "the security desk directly."
)


class SecurityPortalController(http.Controller):

    @http.route('/security/incident/report', type='http',
                auth='public', website=True, methods=['GET', 'POST'])
    def report_incident(self, **kwargs):
        """Public portal form for staff to report security incidents."""
        locations = request.env['generic.location'].sudo().search(
            [], order='name asc')

        values = {
            'locations': locations,
            'incident_types': request.env['security.incident']._fields['incident_type'].selection,
            'submitted': False,
            'error': '',
        }

        if request.httprequest.method == 'POST':
            try:
                # A savepoint, not a bare try. `security.incident` requires
                # `location_id` and `description`, and this form is public
                # HTML with no server-side validation in front of it — so the
                # single most likely failure here is a NOT NULL violation,
                # which aborts the transaction. Without the savepoint the
                # handlers below would set `values['error']` correctly and then
                # `request.render()` would die on the same aborted cursor,
                # because a `website=True` render reads the view, the website
                # and the company. The error page was unreachable for the error
                # it was written for.
                with request.env.cr.savepoint():
                    vals = {
                        'incident_type':  kwargs.get('incident_type', 'other'),
                        'severity':       kwargs.get('severity', 'medium'),
                        'location_id':    int(kwargs.get('location_id', 0)) or False,
                        'description':    kwargs.get('description', ''),
                        'suspect_description': kwargs.get('suspect_description', ''),
                        'is_portal_report': True,
                    }
                    if kwargs.get('reporter_name'):
                        partner = request.env['res.partner'].sudo().search(
                            [('name', '=', kwargs['reporter_name'])], limit=1)
                        if not partner:
                            partner = request.env['res.partner'].sudo().create(
                                {'name': kwargs['reporter_name'],
                                 'phone': kwargs.get('reporter_phone', '')})
                        vals['reported_by'] = partner.id

                    request.env['security.incident'].sudo().create(vals)
                values['submitted'] = True
            except (AccessError, MissingError):
                # Both subclass UserError in Odoo 19, so they have to be caught
                # BEFORE it or the clause below swallows them and shows their
                # text — handoff 09's finding, one controller further on.
                # Neither is the visitor's mistake, and an AccessError message
                # names Odoo groups, which is not something a public page
                # should read out. It goes to the log instead.
                _logger.warning(
                    "security portal: incident report refused", exc_info=True)
                values['error'] = _INTERNAL_ERROR
            except (UserError, ValidationError, ValueError) as e:
                # Optional: this is what a bad submission looks like. `int()`
                # on a location the form did not send raises ValueError, a
                # missing required field or a Selection value outside the
                # published list raises ValidationError, and a model
                # constraint raises UserError. All three are the caller's
                # input, all three carry a message written to be read, and
                # showing it is the whole point of the `error` slot on this
                # template. Narrowed from `except Exception`, which showed the
                # visitor whatever internal text happened to be attached to
                # anything else that went wrong.
                values['error'] = str(e)
            except Exception:
                # catch-all: reported — the visitor is told the report did
                # not save and the traceback goes to the log. A public form is
                # the wrong place to find out what else can arrive, and also
                # the wrong place to answer an Odoo traceback page.
                #
                # It stays broad because this is an `auth='public'` route with
                # a rendered error slot: a visitor reporting a security
                # incident should be told it did not save, not shown a 500. It
                # no longer shows them `str(e)` — that was an internal detail
                # on an unauthenticated page — and the log now carries the
                # traceback, which it never did.
                _logger.warning(
                    "security portal: incident report failed", exc_info=True)
                values['error'] = _INTERNAL_ERROR

        return request.render('myservice_security.portal_report_incident', values)
