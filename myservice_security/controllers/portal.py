from odoo import http
from odoo.http import request


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
            except Exception as e:
                values['error'] = str(e)

        return request.render('myservice_security.portal_report_incident', values)
