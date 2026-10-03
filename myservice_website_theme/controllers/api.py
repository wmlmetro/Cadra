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

# Returned when the body named something this form does not collect. Also
# written to be read by a member of the public on a phone: nothing they typed
# is wrong, so there is nothing for them to correct — the page sent a key the
# server does not accept, which means a stale tab or a modified form.
_UNRECOGNISED_FIELDS = (
    "Sorry — we could not submit your request. Some of the information sent "
    "with this form was not recognised. Please reload the page and try again."
)

#: **Every key `quick_submit` reads, and the whole of what either door
#: accepts.** `quick_submit` takes `**kwargs`, so until handoff 32 it
#: accepted anything and dropped what it does not read: the sibling
#: `POST /api/v1/requests` key `request_text` raised a request with no
#: description and answered 201. That is `CLAUDE.md` rule 3 verbatim.
#:
#: The set lives here, once, because the same method answers TWO doors — the
#: public homepage form at `/api/myservice/quick-submit` and the authenticated
#: `POST /api/v1/home/quick-submit`. They render a refusal differently (a
#: sentence for a visitor, `details.rejected_fields` for an integration) but
#: they must not disagree about WHAT is refused.
QUICK_SUBMIT_FIELDS = (
    'type_id',
    'service_id',
    'location_id',
    'priority',
    'description',
    'reporter_name',
    'reporter_contact',
)

#: The three keys that must name a record. Ordered, because the refusal names
#: them in this order and a test pins it.
QUICK_SUBMIT_ID_FIELDS = (
    ('type_id', 'request.type'),
    ('service_id', 'generic.service'),
    ('location_id', 'generic.location'),
)

#: What each of those is called on the form. A refusal shown to a visitor says
#: "the service", never `service_id` — the same rule the asset-history
#: statements are held to by `myservice_api/tests/test_asset_history.py::
#: test_the_statements_are_words_not_field_names`.
_QUICK_SUBMIT_LABELS = {
    'type_id': 'request type',
    'service_id': 'service',
    'location_id': 'location',
}


def quick_submit_rejected_keys(body):
    """The keys in `body` that `quick_submit` does not accept, as sent.

    Pure: no environment, no records. The order is the caller's, so an
    integration reading `details.rejected_fields` sees its own body back.
    """
    return [k for k in (body or {}) if k not in QUICK_SUBMIT_FIELDS]


def _say_what_is_missing(keys):
    """The sentence a person reads when the form sent no type or no text.

    Held to the same rule as `_choose_from_the_list`: words, never field
    names, because the live form enforces both fields in JavaScript and the
    only person who can read this arrived through a stale tab or a modified
    page — there is nothing of ours to name at them.
    """
    parts = []
    if 'type_id' in keys:
        parts.append('choose a request type from the list on the form')
    if 'description' in keys:
        parts.append('describe what you need')
    return 'Please %s, then send your request again.' % ' and '.join(parts)


def _choose_from_the_list(keys):
    """The sentence a person filling in the form reads when an id is unusable.

    Unusable means one of two things and neither is worth distinguishing to
    somebody on a phone: the value is not a number at all (what the bare
    `except (ValueError, TypeError): pass` used to swallow), or it is a number
    naming no record (what `if rec.exists()` used to swallow). Both used to
    submit a request quietly missing that detail and answer success.
    """
    labels = [_QUICK_SUBMIT_LABELS[k] for k in keys]
    if len(labels) == 1:
        subject, lists = 'the %s' % labels[0], 'the list'
    else:
        subject = 'the %s and %s' % (', '.join(labels[:-1]), labels[-1])
        lists = 'the lists'
    return ('Please choose %s from %s on the form, then send your request '
            'again.' % (subject, lists))


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
        """Handle homepage quick-submit form.

        **Nothing is written until the body has been read whole** (handoff
        32 §B). Two refusals come first and both used to be silences:

        - a key this form does not collect — `request_text`, say, the sibling
          `POST /api/v1/requests` key, which raised a request with no
          description at all and answered 201;
        - one of the three ids that cannot be resolved, either because it is
          not a number (a bare `except (ValueError, TypeError): pass`) or
          because it names no record (`if rec.exists()`), both of which used
          to submit the request without that detail and report success.

        The failure dict carries the machine-readable lists alongside the
        sentence, because `myservice_api.controllers.v1.home_quick_submit`
        delegates here and owes its callers the same
        `details.rejected_fields` / `details.writable` 400 as the other
        eleven write routes. One validator, two renderings.
        """
        env = request.env

        rejected = quick_submit_rejected_keys(kwargs)
        if rejected:
            return {
                'success': False,
                'error': _UNRECOGNISED_FIELDS,
                'rejected_fields': rejected,
            }

        # The schema has declared `type_id` and `description` required since
        # the route was annotated; the route now does too (handoff 37,
        # closing 33 §C). Before resolution, because presence comes before
        # value: an absent type used to fall back to whichever request type
        # happened to be first and active, and an absent description created
        # a record titled "Quick facilities request" that says nothing — on
        # the public twin, an unauthenticated way to create an empty record.
        missing = []
        if kwargs.get('type_id') in (None, '', False):
            missing.append('type_id')
        description = kwargs.get('description')
        if not isinstance(description, str) or not description.strip():
            missing.append('description')
        if missing:
            return {
                'success': False,
                'error': _say_what_is_missing(missing),
                'missing_fields': missing,
            }

        # The three ids, resolved before anything is created. A key that is
        # absent is not an error — only one that is present and unusable.
        resolved = {}
        unusable = []
        for key, model in QUICK_SUBMIT_ID_FIELDS:
            raw = kwargs.get(key)
            if raw in (None, '', False):
                continue
            try:
                rec_id = int(raw)
            except (ValueError, TypeError):
                unusable.append(key)
                continue
            rec = env[model].sudo().browse(rec_id)
            if not rec.exists():
                unusable.append(key)
                continue
            resolved[key] = rec.id

        if unusable:
            return {
                'success': False,
                'error': _choose_from_the_list(unusable),
                'unusable_fields': unusable,
            }

        # Present (the required check above) and resolvable (the id check
        # above), so this is a plain read. The fallback that stood here —
        # no type sent, take the first active one — is gone with handoff 37:
        # it is what let an empty body create a request against whichever
        # type happened to sort first.
        type_id = resolved['type_id']

        # Build request text with reporter info. `description` is required
        # above, so the "Quick facilities request" placeholder title is gone
        # too — every request now says what it is about.
        lines = []
        if kwargs.get('reporter_name'):
            lines.append('Reported by: %s' % kwargs['reporter_name'])
        if kwargs.get('reporter_contact'):
            lines.append('Contact: %s' % kwargs['reporter_contact'])
        if lines:
            lines.append('')
        lines.append(description)

        req_text = '<br/>'.join(lines)

        # Prepare creation data (mirrors WSD controller logic)
        vals = {
            'type_id': type_id,
            'request_text': req_text,
        }

        # Service and location — already resolved above, or the request was
        # refused. Nothing is dropped here any more.
        #
        # `generic_location_id` and not `location_id`: the model's field was
        # renamed in the move to Odoo 19 and handoff 31 found the sibling
        # `POST /api/v1/requests` still asking for the old name and answering
        # 201 without it. The published KEY stays `location_id` on both doors.
        if 'service_id' in resolved:
            vals['service_id'] = resolved['service_id']
        if 'location_id' in resolved:
            vals['generic_location_id'] = resolved['location_id']

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

        email = (kwargs.get('reporter_contact') or '').strip()

        try:
            # INSIDE the try, and that is the whole point of the note above.
            # The method this replaces sat outside it, which is why a visitor
            # typing an address with an "@" in it got a raw 500 instead of
            # the JSON error this handler exists to return. Moving the call
            # and leaving its replacement outside would have fixed the name
            # and kept the defect.
            #
            # Author from contact info, resolved directly the same way the
            # security portal does, rather than through a model method this
            # model does not have.
            if '@' in email:
                partner = env['res.partner'].sudo().search(
                    [('email', '=ilike', email)], limit=1)
                if not partner:
                    partner = env['res.partner'].sudo().create({
                        'name': kwargs.get('reporter_name') or email,
                        'email': email,
                    })
                vals['author_id'] = partner.id

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
