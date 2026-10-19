"""What a photo was said to show, and what a person did with it (handoff 64).

Ruling R11 (`docs/AI-CAPTURE-EVALUATION.md` §2): Cadra's SERVER asks an
existing vision model what a photographed item is; no model is trained or
shipped, and the phone and the browser never call the provider. The AI
proposes and a person confirms — no field is written from a suggestion
without somebody accepting it. Two records carry that here:

* `nrs.ai.suggestion` — one row per call to the provider, append-only
  through the same guard as custody, movement, the event record and the
  photo. It holds what was asked about (the photo, by id and by hash), who
  asked, which provider and model answered, the prompt version, how long it
  took, what it cost in tokens, and either the suggestion as JSON or why
  there is none (`result`). A call that failed is a row too: it was made,
  it counts against the tenant's daily cap, and an answer that failed the
  schema is counted here and never shown to anybody.

* `nrs.ai.pending.photo` — the "add a new asset" case. `nrs.asset.photo`
  requires an asset and is append-only, so a photo taken BEFORE the asset
  exists cannot be one. It waits here, checked by exactly the photo's own
  rules (`check_photo_size`, `sniff_photo`), until a save claims it — the
  bytes then become the asset's photo through `nrs.asset.photo._upload`,
  the one writer — or until it expires, when the cron deletes it. It is
  NOT append-only: it is a holding area, and deleting it is its job. The
  suggestion keeps the photo's hash, so what was identified stays named
  after the bytes are gone.

What the person did is a third thing, and it is an `nrs.asset.event`
(`ai_suggestion_applied`), written by `_apply` in the same transaction as
the save: per field, accepted, changed (from → to) or ignored. AI-NFR-05's
audit trail, read by the history as one line.
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .asset_event import EVENT_AI_SUGGESTION_APPLIED
from .asset_photo import (
    PhotoRefused, check_photo_size, sniff_photo, JPEG, PNG,
    MAX_PHOTOS_PER_ASSET)

#: The flag `_record` sets on itself; `create` refuses without it.
SUGGESTION_APPEND_KEY = 'cadra_ai_suggestion_append'

#: How long a photo taken for an asset that does not exist yet waits for a
#: save to claim it. A working day and the night after it: long enough for a
#: form left open over lunch, short enough that the holding area never
#: becomes a second photo store.
PENDING_PHOTO_HOURS = 24

#: What a call came to. `ok` is the only one with a suggestion to show.
RESULTS = [
    ('ok', 'Identified'),
    # The provider answered, and the answer failed the schema or named a
    # class the tenant does not have. Discarded, counted, never shown.
    ('invalid', 'Answer discarded (failed the schema)'),
    ('timeout', 'Provider did not answer in time'),
    ('error', 'Provider error'),
    # The provider declined to describe the photo (its own safety refusal).
    ('refused', 'Provider declined'),
]

#: The asset fields a suggestion proposes a value for, in the order the
#: history and the form read them. NOT `sap_asset_number`: the matcher's
#: candidates are shown, but no asset route writes that number — the
#: Register Maker's gate and SAP's own answer do (the SAP block in `v1_assets`
#: says why) — so a candidate is information for the person, never a field
#: a save can accept.
SUGGESTED_FIELDS = (
    'category_id', 'name', 'colour', 'material', 'make', 'model_name',
    'dimensions', 'condition')

OUTCOME_ACCEPTED = 'accepted'
OUTCOME_CHANGED = 'changed'
OUTCOME_IGNORED = 'ignored'

_LAGOS = pytz.timezone('Africa/Lagos')


def lagos_today():
    """Today, in Lagos — the day the daily cap is counted in."""
    return datetime.now(pytz.utc).astimezone(_LAGOS).date()


def lagos_day_bounds_utc(day):
    """`(start, end)` of a Lagos day as naive UTC datetimes."""
    start = _LAGOS.localize(datetime.combine(day, datetime.min.time()))
    end = start + timedelta(days=1)
    return (start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None))


class SuggestionRefused(UserError):
    """A refusal at the save, carrying what the envelope needs — the photo's
    `PhotoRefused` shape, so the route maps both the same way."""

    def __init__(self, message, *, status=400, code='validation_failed',
                 details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details or {}


def _norm(value):
    """A value as compared for "did the person keep the suggestion": text
    trimmed and case-folded (a person retyping *Black* for *BLACK* accepted
    it), an id as an int, nothing as None."""
    if value in (None, False, ''):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    return text.casefold() or None


class NRSAiPendingPhoto(models.Model):
    _name = 'nrs.ai.pending.photo'
    _description = 'Photo awaiting an asset (AI identification)'
    _order = 'uploaded_at desc, id desc'

    image = fields.Binary(string='Photo', attachment=True, required=True)
    filename = fields.Char(string='File Name (as sent)')
    mimetype = fields.Selection(
        [(JPEG, 'JPEG'), (PNG, 'PNG')], string='Type (sniffed)',
        required=True)
    size = fields.Integer(string='Size (bytes)', required=True)
    sha256 = fields.Char(string='SHA-256', required=True, index=True)
    width = fields.Integer(string='Width (px)', required=True)
    height = fields.Integer(string='Height (px)', required=True)
    source = fields.Selection(
        [('web', 'Web app'), ('mobile', 'Mobile app')],
        string='Taken From', required=True)
    uploaded_by_id = fields.Many2one(
        'res.users', string='Uploaded By', required=True, ondelete='cascade')
    uploaded_at = fields.Datetime(
        string='Uploaded At', required=True,
        default=lambda self: fields.Datetime.now())
    expires_at = fields.Datetime(string='Expires At', required=True,
                                 index=True)

    @api.model
    def _hold(self, data, *, source, filename=None, actor=None):
        """Check the bytes by the photo's own rules, then hold them.

        The same two checks `nrs.asset.photo._upload` runs, in the same
        order and with the same sentences, so a photo refused here would be
        refused there and one accepted here can always be claimed."""
        user = actor if actor is not None else self.env.user
        if source not in ('web', 'mobile'):
            raise PhotoRefused(
                _("`source` must be one of: web, mobile — which app the "
                  "photo was taken from. Nothing was written."),
                details={'field': 'source', 'allowed_values': ['web', 'mobile'],
                         'received': source})
        size = len(data or b'')
        check_photo_size(size)
        mimetype, width, height = sniff_photo(data)
        now = fields.Datetime.now()
        return self.sudo().with_context(image_no_postprocess=True).create({
            'image': base64.b64encode(data),
            'filename': (filename or '').strip() or False,
            'mimetype': mimetype,
            'size': size,
            'sha256': hashlib.sha256(data).hexdigest(),
            'width': width,
            'height': height,
            'source': source,
            'uploaded_by_id': user.id,
            'uploaded_at': now,
            'expires_at': now + timedelta(hours=PENDING_PHOTO_HOURS),
        })

    def _bytes(self):
        self.ensure_one()
        return base64.b64decode(self.sudo().image or b'')

    @api.model
    def _cron_purge_expired(self):
        """Delete the photos nobody's save claimed before they expired.

        A suggestion that named one keeps its hash; only the bytes go."""
        expired = self.sudo().search(
            [('expires_at', '<', fields.Datetime.now())])
        count = len(expired)
        expired.unlink()
        return count


class NRSAiSuggestion(models.Model):
    _name = 'nrs.ai.suggestion'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'AI suggestion from a photo (append-only)'
    _order = 'requested_at desc, id desc'

    _append_key = SUGGESTION_APPEND_KEY

    # WHAT WAS ASKED ABOUT. One of the two photo links is set at creation;
    # the hash is always, because a pending photo is deleted once claimed or
    # expired and the record must still say which picture it was.
    photo_id = fields.Many2one(
        'nrs.asset.photo', string='Asset Photo', index=True,
        ondelete='restrict')
    pending_photo_id = fields.Many2one(
        'nrs.ai.pending.photo', string='Pending Photo', index=True,
        ondelete='set null')
    photo_sha256 = fields.Char(string='Photo SHA-256', required=True)
    photo_size = fields.Integer(string='Photo Size (bytes)')

    # WHO ASKED AND WHEN — from the acting user, never from the body.
    actor_id = fields.Many2one(
        'res.users', string='Requested By', required=True,
        ondelete='restrict')
    actor_name = fields.Char(string='Requested By (as recorded)')
    requested_at = fields.Datetime(
        string='Requested At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO ANSWERED.
    provider = fields.Char(string='Provider', required=True)
    model = fields.Char(string='Model')
    prompt_version = fields.Char(string='Prompt Version', required=True)

    result = fields.Selection(RESULTS, string='Result', required=True,
                              index=True)
    # The suggestion as published to the caller (category, attributes,
    # condition, text read, SAP candidates). Empty unless `result = ok`.
    suggestion_json = fields.Text(string='Suggestion (JSON)')
    # WHY there is no suggestion, in words Cadra wrote — never the
    # provider's own message, which is not ours to vouch for.
    failure = fields.Char(string='Why Not Identified')

    latency_ms = fields.Integer(string='Latency (ms)')
    input_tokens = fields.Integer(string='Input Tokens')
    output_tokens = fields.Integer(string='Output Tokens')
    cache_read_tokens = fields.Integer(string='Cache-read Tokens')
    cache_write_tokens = fields.Integer(string='Cache-write Tokens')
    cost_usd = fields.Float(string='Cost (USD, at published prices)',
                            digits=(12, 6))

    def _append_only_message(self):
        return _(
            "A suggestion from a photo is append-only. It cannot be edited "
            "or deleted once written — not through the interface, not over "
            "the API, and not as an administrator with sudo. What a person "
            "did with it is recorded on the asset when they save."
        )

    def _no_hand_written_rows_message(self):
        return _(
            "A suggestion from a photo cannot be created directly. One is "
            "written only when Cadra has actually asked the provider about a "
            "photo, so that the record says what was answered."
        )

    # ── the one way a row is written ──────────────────────────────────

    @api.model
    def _record(self, *, photo=None, pending=None, provider, model,
                prompt_version, result, suggestion=None, failure=None,
                latency_ms=None, usage=None, actor=None):
        user = actor if actor is not None else self.env.user
        holder = photo if photo else pending
        usage = usage or {}
        return self.sudo().with_context(**{SUGGESTION_APPEND_KEY: True}).create({
            'photo_id': photo.id if photo else False,
            'pending_photo_id': pending.id if pending else False,
            'photo_sha256': holder.sha256,
            'photo_size': holder.size,
            'actor_id': user.id,
            'actor_name': user.display_name,
            'requested_at': fields.Datetime.now(),
            'provider': provider,
            'model': model or False,
            'prompt_version': prompt_version,
            'result': result,
            'suggestion_json': json.dumps(suggestion, sort_keys=True)
            if suggestion is not None else False,
            'failure': failure or False,
            'latency_ms': latency_ms,
            'input_tokens': usage.get('input_tokens'),
            'output_tokens': usage.get('output_tokens'),
            'cache_read_tokens': usage.get('cache_read_tokens'),
            'cache_write_tokens': usage.get('cache_write_tokens'),
            'cost_usd': usage.get('cost_usd'),
        })

    # ── the daily cap ─────────────────────────────────────────────────

    @api.model
    def _calls_today(self):
        """Provider calls made today (Lagos), every result counted: a call
        that failed was still made."""
        start, end = lagos_day_bounds_utc(lagos_today())
        self.env.cr.execute(
            "SELECT count(*) FROM nrs_ai_suggestion "
            "WHERE requested_at >= %s AND requested_at < %s", (start, end))
        return self.env.cr.fetchone()[0]

    # ── what was proposed ─────────────────────────────────────────────

    def _suggestion(self):
        self.ensure_one()
        return json.loads(self.suggestion_json or '{}')

    def _proposed(self):
        """`{field: proposed value}` for the fields this suggestion offered
        a value for — nothing for a field it left empty."""
        data = self._suggestion()
        out = {}
        category = data.get('category') or {}
        if category.get('id'):
            out['category_id'] = category['id']
        for key, value in (data.get('attributes') or {}).items():
            if key in SUGGESTED_FIELDS and value not in (None, ''):
                out[key] = value
        condition = (data.get('condition') or {}).get('value')
        if condition:
            out['condition'] = condition
        return out

    def _applied_event(self):
        self.ensure_one()
        return self.env['nrs.asset.event'].sudo().search(
            [('event_type', '=', EVENT_AI_SUGGESTION_APPLIED),
             ('ai_suggestion_id', '=', self.id)], limit=1)

    # ── the save ──────────────────────────────────────────────────────

    def _check_applicable(self, asset=None, actor=None):
        """Refuse BEFORE the save writes anything (CLAUDE.md: a refusal
        happens before anything is written). `asset` is the asset being
        saved, or None for a create.

        Only the person who asked for the suggestion saves it: the record
        says who confirmed what the AI proposed, and a second person
        claiming somebody else's held photo onto their asset would make that
        two people under one name (verification pass)."""
        self.ensure_one()
        user = actor if actor is not None else self.env.user
        if self.actor_id and self.actor_id != user:
            raise SuggestionRefused(
                _("Suggestion %(id)s was asked for by %(who)s; only they can "
                  "save it. Identify the photo again as yourself. Nothing "
                  "was written.", id=self.id,
                  who=self.actor_name or self.actor_id.display_name),
                status=403, code='forbidden',
                details={'reason': 'not_yours', 'ai_suggestion_id': self.id})
        if self.result != 'ok':
            raise SuggestionRefused(
                _("Suggestion %(id)s has nothing to apply: the photo was not "
                  "identified (%(why)s). Save without it. Nothing was "
                  "written.", id=self.id,
                  why=self.failure or dict(RESULTS).get(self.result)),
                details={'reason': 'not_identified',
                         'ai_suggestion_id': self.id,
                         'result': self.result})
        earlier = self._applied_event()
        if earlier:
            raise SuggestionRefused(
                _("Suggestion %(id)s was already saved to asset %(code)s on "
                  "%(when)s. A suggestion is applied once. Nothing was "
                  "written.", id=self.id,
                  code=earlier.asset_id.asset_code or earlier.asset_id.id,
                  when=fields.Datetime.to_string(earlier.occurred_at)),
                status=409, code='conflict',
                details={'reason': 'already_applied',
                         'ai_suggestion_id': self.id,
                         'asset_id': earlier.asset_id.id,
                         'event_id': earlier.id})
        if self.photo_id and (asset is None or self.photo_id.asset_id != asset):
            raise SuggestionRefused(
                _("Suggestion %(id)s is about a photo of asset %(code)s; it "
                  "can only be saved to that asset. Nothing was written.",
                  id=self.id,
                  code=self.photo_id.asset_id.asset_code
                  or self.photo_id.asset_id.id),
                details={'reason': 'other_asset', 'ai_suggestion_id': self.id,
                         'asset_id': self.photo_id.asset_id.id})
        pending = self.pending_photo_id
        if pending and pending.expires_at < fields.Datetime.now():
            # Past its 24 hours, waiting only for the hourly cron.
            pending = False
        if not self.photo_id and not pending:
            raise SuggestionRefused(
                _("The photo suggestion %(id)s was made from has expired "
                  "(a photo waits %(hours)d hours for an asset to claim it). "
                  "Take the photo again. Nothing was written.",
                  id=self.id, hours=PENDING_PHOTO_HOURS),
                status=409, code='conflict',
                details={'reason': 'photo_expired',
                         'ai_suggestion_id': self.id})
        if self.pending_photo_id and asset is not None:
            standing = self.env['nrs.asset.photo']._standing_count(asset)
            if standing >= MAX_PHOTOS_PER_ASSET:
                raise SuggestionRefused(
                    _("This asset already has %(n)d photos, the most it may "
                      "hold, so the photo this suggestion came from cannot "
                      "be added. Supersede one first. Nothing was written.",
                      n=standing),
                    status=409, code='conflict',
                    details={'reason': 'photo_limit',
                             'max_photos': MAX_PHOTOS_PER_ASSET})

    def _outcomes(self, written, ignored=()):
        """Per proposed field: accepted, changed (from → to) or ignored.

        `written` is what the save wrote — `{field: value}` as sent, a
        many2one as its id. A field the person said they ignored is
        ignored; a field the save did not send is ignored; otherwise the
        saved value is compared with the proposal, text case-folded."""
        self.ensure_one()
        ignored = set(ignored or ())
        out = {}
        for field, proposed in self._proposed().items():
            if field in ignored or field not in written:
                out[field] = {'outcome': OUTCOME_IGNORED,
                              'suggested': proposed}
                continue
            saved = written[field]
            if _norm(saved) == _norm(proposed):
                out[field] = {'outcome': OUTCOME_ACCEPTED,
                              'suggested': proposed}
            else:
                out[field] = {'outcome': OUTCOME_CHANGED,
                              'from': proposed,
                              'to': saved if saved not in (False, '') else None}
        return out

    def _apply(self, asset, written, ignored=(), actor=None):
        """Record what the person did with this suggestion on `asset`, and
        give the asset the photo it came from if that photo was pending.

        Called by the save, AFTER its write and in the same transaction;
        `_check_applicable` has already run before the write."""
        self.ensure_one()
        user = actor if actor is not None else self.env.user
        photo = self.photo_id
        pending = self.pending_photo_id
        if pending:
            photo = self.env['nrs.asset.photo']._upload(
                asset, pending._bytes(), source=pending.source,
                filename=pending.filename, actor=user)
            # The suggestion keeps the hash; the holding row has done its
            # job. Its foreign key on the suggestion goes NULL in the
            # database, which is not a write to the append-only row.
            pending.sudo().unlink()
        outcomes = self._outcomes(written, ignored)
        counts = {k: 0 for k in (OUTCOME_ACCEPTED, OUTCOME_CHANGED,
                                 OUTCOME_IGNORED)}
        for item in outcomes.values():
            counts[item['outcome']] += 1
        notes = {'fields': outcomes, 'counts': counts,
                 'provider': self.provider, 'model': self.model,
                 'prompt_version': self.prompt_version}
        event = self.env['nrs.asset.event']._record(
            asset, EVENT_AI_SUGGESTION_APPLIED, source='api_write',
            actor=user, ai_suggestion_id=self.id,
            photo_id=photo.id if photo else False,
            notes=json.dumps(notes, sort_keys=True))
        return event, outcomes, counts
