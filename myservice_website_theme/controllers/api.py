import logging
from werkzeug.utils import redirect as wz_redirect
from odoo import http, SUPERUSER_ID
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

# Returned when the failure is ours, not the caller's. These routes are
# `auth='public'`, so whatever goes in `error` is read by an unauthenticated
# visitor; the detail belongs in the log.
_INTERNAL_ERROR = (
    "Sorry — we could not submit your request. Please try again shortly."
)


class NRSHomepageAPI(http.Controller):

    @http.route('/a/<string:asset_code>', type='http', auth='public', website=True)
    def asset_short_url(self, asset_code, **kwargs):
        """Short URL redirect for QR codes: /a/NRS-AST-000042 -> /asset-scan?code=..."""
        return wz_redirect('/asset-scan?code=%s' % asset_code, code=301)

    @http.route(
        '/api/myservice/form-data', type='json', auth='public',
        methods=['POST'], csrf=False,
    )
    def get_form_data(self, **kwargs):
        """Return dropdown data for the homepage quick-submit form."""
        env = request.env

        # Services
        services = env['generic.service'].sudo().search(
            [('active', '=', True)], order='sequence, name')

        # Request types via classifiers (only valid combos)
        classifiers = env['request.classifier'].sudo().search(
            [('active', '=', True)],
        )
        type_map = {}
        for clf in classifiers:
            t = clf.type_id
            if t.active and t.id not in type_map:
                type_map[t.id] = {
                    'id': t.id,
                    'name': t.name,
                    'service_id': clf.service_id.id if clf.service_id else None,
                }
        request_types = sorted(type_map.values(), key=lambda x: x['name'])

        # Locations (deduplicated, same logic as portal controller)
        all_locs = env['generic.location'].sudo().search(
            [('active', '=', True)], order='name')
        seen = set()
        locations = []
        for loc in all_locs:
            key = loc.name.strip().upper()
            if key not in seen:
                seen.add(key)
                locations.append({
                    'id': loc.id,
                    'name': loc.name,
                    'parent_id': loc.parent_id.id if loc.parent_id else None,
                    'parent_name': loc.parent_id.name if loc.parent_id else None,
                })

        return {
            'services': [{'id': s.id, 'name': s.name} for s in services],
            'request_types': request_types,
            'locations': locations,
        }

    @http.route(
        '/api/myservice/quick-submit', type='json', auth='public',
        methods=['POST'], csrf=False,
    )
    def quick_submit(self, **kwargs):
        """Handle homepage quick-submit form."""
        env = request.env

        # Resolve type_id — required
        type_id = None
        raw_type = kwargs.get('type_id')
        if raw_type:
            try:
                type_id = int(raw_type)
            except (ValueError, TypeError):
                pass

        if not type_id:
            # Fall back to first active type
            first_type = env['request.type'].sudo().search(
                [('active', '=', True)], limit=1)
            if first_type:
                type_id = first_type.id
            else:
                return {'success': False, 'error': 'No request type available'}

        req_type = env['request.type'].sudo().browse(type_id)
        if not req_type.exists():
            return {'success': False, 'error': 'Invalid request type'}

        # Build request text with reporter info
        lines = []
        if kwargs.get('reporter_name'):
            lines.append('Reported by: %s' % kwargs['reporter_name'])
        if kwargs.get('reporter_contact'):
            lines.append('Contact: %s' % kwargs['reporter_contact'])
        if lines:
            lines.append('')
        if kwargs.get('description'):
            lines.append(kwargs['description'])

        req_text = '<br/>'.join(lines) if lines else 'Quick facilities request'

        # Prepare creation data (mirrors WSD controller logic)
        vals = {
            'type_id': type_id,
            'request_text': req_text,
        }

        # Service
        raw_service = kwargs.get('service_id')
        if raw_service:
            try:
                svc = env['generic.service'].sudo().browse(int(raw_service))
                if svc.exists():
                    vals['service_id'] = svc.id
            except (ValueError, TypeError):
                pass

        # Location
        raw_loc = kwargs.get('location_id')
        if raw_loc:
            try:
                loc = env['generic.location'].sudo().browse(int(raw_loc))
                if loc.exists():
                    vals['generic_location_id'] = loc.id
            except (ValueError, TypeError):
                pass

        # Priority
        if kwargs.get('priority'):
            vals['priority'] = kwargs['priority']

        # Intake channel.
        #
        # Three lines used to live here, and between them they meant this
        # endpoint COULD NOT SUCCEED ON ODOO 19 — every homepage quick-submit
        # returned `{'success': False}`:
        #
        #   `vals['channel_id']`  — `request.request` on 19 is first-party
        #     (`myservice_request_core`) and has no `channel_id`; the concept
        #     came from `generic_request`, which is not on the 19 addons path.
        #     Inert only by luck: the `env.ref` above it could never resolve,
        #     so the assignment never ran. `docs/upgrade/rebuild-on-19-plan.md`
        #     lists this one as a "runtime ref to fix" — it is the harmless one
        #     of the three.
        #
        #   `vals['website_id']` — not a field on `request.request` either, and
        #     nothing guarded it: `get_current_website()` always returns a
        #     website, so this key was on EVERY create and every create raised
        #     `Invalid field 'website_id'` into the handler below. Not flagged
        #     anywhere.
        #
        #   `_get_or_create_partner_from_email` — a `crnd_wsd` method that does
        #     not exist on the 19 model. It sat OUTSIDE the try, so any visitor
        #     who typed an address with an "@" in it got a 500 rather than the
        #     JSON error, and the log line said nothing about the form.
        #
        # `intake_channel` (from `myservice_request_fields`) is the field that
        # carries what `channel_id` meant, and it already defaults to
        # 'portal' — which this form is — so nothing needs setting here.

        # Author from contact info. Resolves the partner directly, the same
        # way the security portal does, rather than through a model method
        # this model does not have.
        email = (kwargs.get('reporter_contact') or '').strip()
        if '@' in email:
            partner = env['res.partner'].sudo().search(
                [('email', '=ilike', email)], limit=1)
            if not partner:
                partner = env['res.partner'].sudo().create({
                    'name': kwargs.get('reporter_name') or email,
                    'email': email,
                })
            vals['author_id'] = partner.id

        try:
            req = env['request.request'].with_user(SUPERUSER_ID).create(vals)
            return {
                'success': True,
                'request_name': req.name,
                'request_id': req.id,
            }
        except (AccessError, MissingError):
            # Caught before UserError because on Odoo 19 both subclass it, so
            # placed after they would be reported to the caller as their own
            # mistake — handoff 09's ordering finding. Neither is.
            _logger.exception('Quick-submit refused')
            return {'success': False, 'error': _INTERNAL_ERROR}
        except (UserError, ValidationError, ValueError) as e:
            # Optional: what a bad submission looks like. `priority` arrives
            # from a public POST and goes into a Selection unvalidated, so an
            # unexpected value raises ValueError here; a constraint on
            # `request.request` raises UserError or ValidationError. These
            # messages are written to be read and the form has somewhere to
            # show them.
            return {'success': False, 'error': str(e)}
        except Exception:
            # catch-all: reported — the caller is told the submission failed
            # and the traceback goes to the log. Broad because the create
            # reaches every module that extends `request.request`, so what it
            # can meet is not enumerable from here.
            #
            # It stays broad because a homepage form should say it failed
            # rather than hand a visitor a JSON-RPC fault. What changed is the
            # answer: `str(e)` used to put ORM internals on a public endpoint,
            # and for three years the string it put there was
            # "Invalid field 'website_id'" — a message that describes our bug
            # while reading, to anyone watching the form, like theirs.
            _logger.exception('Quick-submit failed')
            return {'success': False, 'error': _INTERNAL_ERROR}
