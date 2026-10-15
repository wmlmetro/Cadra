"""Photos on an asset — handoff 61 §5. Append-only, through THE mixin.

WHAT THIS IS
------------
A photograph of an asset is evidence: AD-10 (Store may attach a photo on
receipt), AD-34 (a photo showing the tag on the item), and the AI addendum's
capture flow. One row per picture: which asset, the bytes, what they are
(sniffed, never declared), how big, a hash, the dimensions, a caption, where
it was taken from (`web` or `mobile`), who sent it and when.

**A photo is never deleted and never replaced.** The fifth append-only record
inherits `nrs.asset.append.only.mixin` (`models/append_only.py`), as
`CLAUDE.md` says a new one does — it does not copy it: `write` and `unlink`
raise unconditionally (under `sudo()` too), `create` refuses without this
model's own context flag, and the ACL grants `create` to nobody. A photo
that should no longer stand is SUPERSEDED, with a reason: that is an
`nrs.asset.event` of type `photo_superseded` naming the photo, whose actor is
who superseded it (`action_supersede`). The row itself is untouched; whether
it is superseded is DERIVED from that event (`superseded_event_id`), so a
reader of the photo learns it from the record nobody can alter either.

It holds its asset with `ondelete='restrict'`, like custody, movement and the
event record: **an asset with a photo can no longer be deleted.**
`scripts/remove_test_residue.py` and `scripts/mark_test_fixtures.py` name it.

THE CAPS (AI-NFR-07, and the handoff's fallback)
------------------------------------------------
* **300 KB per photo** — AI-NFR-07: *"Photos are compressed to a maximum of
  300 KB each on the device before sync."* Read as 300 × 1024 bytes.
* **12 per asset** — AI-NFR-07 gives no count, so the handoff's fallback.
  What counts is the photos that are NOT superseded: nothing is ever
  deleted, so a superseded photo frees its slot or the cap would be a
  lifetime limit no correction could get under.
* **JPEG or PNG**, judged by SNIFFING the bytes — the magic number, then
  Pillow opening and checking them — never by the file name or the declared
  content type. A PDF renamed `.jpg` is a PDF.
* **50 megapixels** — not from the NFR: a safety rule. A 300 KB PNG of a flat
  colour can declare a picture large enough to exhaust the server when
  decoded, so the dimensions are read from the header and refused above
  this before anything is decoded. No real 300 KB photograph comes near it.

Every refusal is a `PhotoRefused` carrying the HTTP status, the code and the
details the API publishes — raised BEFORE anything is written, so a route
may return the envelope without rolling back.

WHY `Binary(attachment=True)` AND NOT A LINKED `ir.attachment`
--------------------------------------------------------------
The bytes live in the filestore through the field's own attachment, which
Odoo creates inside `create` (`fields_binary.Binary.create`, under sudo) —
not through a first-party `ir.attachment.create`. So:

* the photo IS the row: there is no second record to orphan, re-point or
  list by accident (`_gate_evidence` reads attachments named by its events,
  and a field attachment carries `res_field`, which every plain attachment
  search excludes);
* `ir.attachment`'s entry in `tests/test_source_guards.py::ALREADY_LABELLED`
  stays true — its reason says first-party code creates attachments only as
  IAD's verification evidence;
* the attachment is created with `image_no_postprocess`, because
  `ir.attachment._postprocess_contents` otherwise RESIZES any image larger
  than `base.image_autoresize_max_px` (1920×1920 by default) and re-encodes
  it — a photo would come back as different bytes from the ones sent, with
  a hash and dimensions that no longer describe it. (IAD's evidence images
  ARE resized that way today: `_store_gate_evidence` does not pass the
  flag. Reported, not changed here.)

The row keeps the SHA-256 of the bytes as received, and the bytes route
checks it on every read: an attachment altered underneath the row (an
administrator can write `ir.attachment`; nothing else can) is answered as
an integrity failure rather than served as the photo.
"""
import base64
import hashlib
import io
import struct

import pytz
from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from .asset_event import EVENT_PHOTO_SUPERSEDED

#: The flag `_upload` sets on itself; `create` refuses without it. Only this
#: model's — one model's flag opening another's lock is what the mixin's
#: tests exist to stop.
PHOTO_APPEND_KEY = 'cadra_photo_append'

#: AI-NFR-07. 300 KB, read as KiB.
MAX_PHOTO_BYTES = 300 * 1024
#: The handoff's fallback: AI-NFR-07 names no count.
MAX_PHOTOS_PER_ASSET = 12
#: A safety rule, not the NFR's — see the module docstring.
MAX_PHOTO_PIXELS = 50_000_000

JPEG = 'image/jpeg'
PNG = 'image/png'
ALLOWED_MIMETYPES = (JPEG, PNG)

#: What a caller may declare a photo was taken from. `gate_evidence` is NOT
#: here: it labels Internal Audit's evidence in the list, and is never
#: something a photo is uploaded as.
UPLOAD_SOURCES = ('web', 'mobile')

_JPEG_MAGIC = b'\xff\xd8\xff'
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
#: Pillow's format names for each sniffed type. `MPO` is a JPEG carrying a
#: second picture (many phone cameras write one); it is a JPEG on the wire.
_PIL_FORMATS = {JPEG: ('JPEG', 'MPO'), PNG: ('PNG',)}

#: First half of the advisory lock taken per asset while a photo is counted
#: and written, or superseded — so two uploads at once cannot both pass the
#: twelfth slot, and two supersedes at once cannot both find none earlier.
#: Transaction-scoped; it locks nothing else about the asset.
_PHOTO_LOCK_CLASS = 61005

_LAGOS = pytz.timezone('Africa/Lagos')

#: What Pillow raises on bytes it cannot read. Named rather than caught
#: broadly: anything else out of it is our fault, and says so as a 500.
_UNREADABLE = (OSError, SyntaxError, ValueError, EOFError, struct.error,
               IndexError, TypeError)


class PhotoRefused(UserError):
    """A refusal, carrying what the API needs to say it in the envelope.

    A `UserError`, so any other caller (the back office, a script) still
    gets the sentence. Raised before anything is written."""

    def __init__(self, message, *, status=400, code='validation_failed',
                 details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details or {}


def _kb(size):
    """A byte count as people say it: 301 KB, 1.4 MB."""
    if size < 1024 * 1024:
        return '%d KB' % round(size / 1024.0)
    return '%.1f MB' % (size / (1024.0 * 1024.0))


def lagos_moment(dt):
    """`15 Oct 2026 at 14:05` in Lagos — for a sentence, not for a key."""
    if not dt:
        return ''
    local = pytz.utc.localize(dt).astimezone(_LAGOS)
    return '%d %s at %s' % (local.day, local.strftime('%b %Y'),
                            local.strftime('%H:%M'))


def check_photo_size(size):
    """Refuse a photo over `MAX_PHOTO_BYTES`, naming the cap and what came.

    Its own function so that a caller holding only the SIZE — the upload
    route, which measures the part without reading it — refuses with the
    same sentence `_upload` does, and an oversized file is never read."""
    if size > MAX_PHOTO_BYTES:
        raise PhotoRefused(
            _("A photo may be at most %(cap_kb)s (%(cap)s bytes); this one "
              "is %(size)s bytes (%(size_kb)s). Compress it and send it "
              "again. Nothing was written.",
              cap_kb=_kb(MAX_PHOTO_BYTES),
              cap='{:,}'.format(MAX_PHOTO_BYTES),
              size='{:,}'.format(size), size_kb=_kb(size)),
            status=413,
            details={'reason': 'too_large',
                     'max_bytes': MAX_PHOTO_BYTES,
                     'received_bytes': size})


def _unreadable(mimetype):
    return PhotoRefused(
        _("This file begins like a %(kind)s but cannot be read as one — it "
          "may be truncated or damaged. Nothing was written.",
          kind='JPEG' if mimetype == JPEG else 'PNG'),
        details={'reason': 'unreadable_image', 'detected': mimetype})


def _too_many_pixels(width, height):
    declared = (_("this one declares %(w)d × %(h)d", w=width, h=height)
                if width and height else
                _("this one declares more than Pillow will open"))
    return PhotoRefused(
        _("A photo may be at most %(cap)d megapixels; %(declared)s. Nothing "
          "was written.", cap=MAX_PHOTO_PIXELS // 1_000_000,
          declared=declared),
        details={'reason': 'too_many_pixels', 'max_pixels': MAX_PHOTO_PIXELS,
                 'width': width, 'height': height})


def sniff_photo(data):
    """`(mimetype, width, height)` of the bytes, or raise `PhotoRefused`.

    THE check of what a photo is, and the only one: it reads the bytes and
    nothing else. The magic number decides the type; Pillow must then open
    the bytes AS that type, report dimensions within `MAX_PHOTO_PIXELS`, and
    read them through — a PNG's every chunk checksummed (`verify`), a JPEG
    decoded at an eighth of its size (`draft`), which walks the whole
    compressed stream for a fraction of the memory. A truncated or corrupt
    file is refused, as is a file of one type wearing another's header.

    The one thing NOT checked, on purpose: a PNG's pixels are not decoded
    (its chunks are checksummed, so truncation and damage are caught). A
    PNG whose checksummed image data simply holds fewer pixels than its
    header declares is accepted; decoding up to 50 megapixels per upload to
    rule that out would cost the server more than the case is worth.
    """
    if not data:
        raise PhotoRefused(
            _("The file is empty (0 bytes). Nothing was written."),
            details={'reason': 'empty', 'received_bytes': 0})
    if data[:3] == _JPEG_MAGIC:
        mimetype = JPEG
    elif data[:8] == _PNG_MAGIC:
        mimetype = PNG
    else:
        detected = guess_mimetype(data, default='application/octet-stream')
        raise PhotoRefused(
            _("A photo must be a JPEG or a PNG. This file is %(detected)s, "
              "judged from its contents — its name and the type it was sent "
              "as are not consulted. Nothing was written.",
              detected=detected),
            status=415,
            details={'reason': 'unsupported_type',
                     'allowed': list(ALLOWED_MIMETYPES),
                     'detected': detected})
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in _PIL_FORMATS[mimetype]:
            raise _unreadable(mimetype)
        width, height = image.size
        if width <= 0 or height <= 0:
            raise _unreadable(mimetype)
        if width * height > MAX_PHOTO_PIXELS:
            raise _too_many_pixels(width, height)
        if mimetype == PNG:
            image.verify()
        else:
            image.draft('RGB', (max(1, width // 8), max(1, height // 8)))
            image.load()
    except PhotoRefused:
        raise
    except Image.DecompressionBombError:
        # Pillow's own ceiling (twice `Image.MAX_IMAGE_PIXELS`), met at
        # `open` before the dimensions reach the check above.
        raise _too_many_pixels(None, None) from None
    except _UNREADABLE:
        raise _unreadable(mimetype) from None
    return mimetype, width, height


class NRSAssetPhoto(models.Model):
    _name = 'nrs.asset.photo'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'Asset Photo (append-only)'
    # Newest first: the list answers "what pictures does this asset have",
    # and the one just taken is the one a person looks for.
    _order = 'uploaded_at desc, id desc'

    _append_key = PHOTO_APPEND_KEY

    asset_id = fields.Many2one(
        'nrs.asset', string='Asset', required=True, index=True,
        # NOT cascade, for custody's reason: deleting the asset would erase
        # the evidence of what it looked like.
        ondelete='restrict')

    # The bytes, exactly as received — see the module docstring for why a
    # field attachment and why `image_no_postprocess`.
    image = fields.Binary(string='Photo', attachment=True, required=True)
    filename = fields.Char(string='File Name (as sent)')
    mimetype = fields.Selection(
        [(JPEG, 'JPEG'), (PNG, 'PNG')], string='Type (sniffed)',
        required=True)
    size = fields.Integer(string='Size (bytes)', required=True)
    sha256 = fields.Char(string='SHA-256', required=True, index=True)
    width = fields.Integer(string='Width (px)', required=True)
    height = fields.Integer(string='Height (px)', required=True)
    caption = fields.Text(string='Caption')
    source = fields.Selection(
        [('web', 'Web app'), ('mobile', 'Mobile app')],
        string='Taken From', required=True, index=True,
        help="Declared by the caller — which app the picture came through. "
             "A statement about the channel, not about the evidence: "
             "whether a test credential sent it is `is_test_fixture`, "
             "derived from the acting user and not settable.")

    # WHO SENT IT. From the acting user, never from the body — the same rule
    # as the renomination's `renominated_by_id`. `restrict`, with the name
    # beside it as recorded, for that model's reason.
    uploaded_by_id = fields.Many2one(
        'res.users', string='Uploaded By', required=True, ondelete='restrict')
    uploaded_by_name = fields.Char(string='Uploaded By (as recorded)')
    uploaded_at = fields.Datetime(
        string='Uploaded At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # DERIVED from the append-only event, never stored on the row: the row
    # is immutable, so "superseded" can only be a second record about it.
    superseded_event_id = fields.Many2one(
        'nrs.asset.event', string='Superseded By Event',
        compute='_compute_superseded_event_id')

    def _append_only_message(self):
        return _(
            "A photo of an asset is append-only. It cannot be edited, "
            "replaced or deleted once added — not through the interface, "
            "not over the API, and not as an administrator with sudo. If it "
            "no longer stands, supersede it with a reason; the photo stays "
            "as evidence."
        )

    def _no_hand_written_rows_message(self):
        return _(
            "An asset photo cannot be created directly. One is written only "
            "when a photo is uploaded and its bytes have been checked, so "
            "that the record describes the picture that was actually sent."
        )

    # ── superseding, derived ──────────────────────────────────────────

    def _supersede_events(self):
        """`{photo id: its photo_superseded event}` for these photos."""
        if not self.ids:
            return {}
        events = self.env['nrs.asset.event'].sudo().search(
            [('event_type', '=', EVENT_PHOTO_SUPERSEDED),
             ('photo_id', 'in', self.ids)], order='occurred_at, id')
        out = {}
        for event in events:
            # The first one stands; `action_supersede` refuses a second.
            out.setdefault(event.photo_id.id, event)
        return out

    @api.depends()
    def _compute_superseded_event_id(self):
        found = self._supersede_events()
        for photo in self:
            photo.superseded_event_id = found.get(photo.id, False)

    # ── the counts ────────────────────────────────────────────────────

    @api.model
    def _standing_count(self, asset):
        """How many of the asset's photos count against the cap — those
        not superseded."""
        photos = self.sudo().search([('asset_id', '=', asset.id)])
        return len(photos) - len(photos._supersede_events())

    def _lock(self, asset):
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            (_PHOTO_LOCK_CLASS, asset.id))

    # ── the one way a row is written ──────────────────────────────────

    @api.model
    def _upload(self, asset, data, *, source, caption=None, filename=None,
                actor=None):
        """Check the bytes and the asset's count, then append one photo.

        The ONLY way a row is ever written, and every check runs before it:
        a `PhotoRefused` from here has written nothing. The size is checked
        before the bytes are opened, so an oversized file is never decoded.
        """
        user = actor if actor is not None else self.env.user
        if source not in UPLOAD_SOURCES:
            raise PhotoRefused(
                _("`source` must be one of: %(allowed)s — which app the "
                  "photo was taken from.%(more)s Nothing was written.",
                  allowed=', '.join(UPLOAD_SOURCES),
                  more=_(" `gate_evidence` labels Internal Audit's evidence "
                         "in the list; it is not something a photo is "
                         "uploaded as.")
                  if source == 'gate_evidence' else ''),
                details={'field': 'source',
                         'allowed_values': list(UPLOAD_SOURCES),
                         'received': source})
        size = len(data or b'')
        check_photo_size(size)
        mimetype, width, height = sniff_photo(data)

        self._lock(asset)
        standing = self._standing_count(asset)
        if standing >= MAX_PHOTOS_PER_ASSET:
            raise PhotoRefused(
                _("This asset already has %(n)d photos, the most it may "
                  "hold (%(cap)d per asset). Supersede one it no longer "
                  "needs — a superseded photo is kept and stops counting — "
                  "and add this one again. Nothing was written.",
                  n=standing, cap=MAX_PHOTOS_PER_ASSET),
                status=409, code='conflict',
                details={'reason': 'photo_limit',
                         'max_photos': MAX_PHOTOS_PER_ASSET,
                         'photos': standing})

        vals = {
            'asset_id': asset.id,
            'image': base64.b64encode(data),
            'filename': (filename or '').strip() or False,
            'mimetype': mimetype,
            'size': size,
            'sha256': hashlib.sha256(data).hexdigest(),
            'width': width,
            'height': height,
            'caption': (caption or '').strip() or False,
            'source': source,
            'uploaded_by_id': user.id,
            'uploaded_by_name': user.display_name,
            'uploaded_at': fields.Datetime.now(),
        }
        return self.sudo().with_context(
            image_no_postprocess=True,
            **{PHOTO_APPEND_KEY: True}).create(vals)

    # ── superseding ───────────────────────────────────────────────────

    def action_supersede(self, reason, actor=None):
        """Say this photo no longer stands, and why. Writes ONE
        `photo_superseded` event; the photo itself is untouched.

        A reason is required. A photo is superseded once: a second attempt
        is refused naming who did it, when, and why."""
        self.ensure_one()
        user = actor if actor is not None else self.env.user
        reason = (reason or '').strip()
        if not reason:
            raise PhotoRefused(
                _("A reason is required to supersede a photo — say why it "
                  "no longer stands. Nothing was written."),
                details={'field': 'reason'})
        self._lock(self.asset_id)
        earlier = self._supersede_events().get(self.id)
        if earlier:
            raise PhotoRefused(
                _("This photo was already superseded on %(when)s by "
                  "%(who)s: “%(why)s”. A photo is superseded once. "
                  "Nothing was written.",
                  when=lagos_moment(earlier.occurred_at),
                  who=earlier.actor_name or _('somebody unrecorded'),
                  why=earlier.reason or ''),
                status=409, code='conflict',
                details={'reason': 'already_superseded',
                         'superseded': {
                             'event_id': earlier.id,
                             'at': fields.Datetime.to_string(
                                 earlier.occurred_at),
                             'by': earlier.actor_name or None,
                             'reason': earlier.reason or None}})
        return self.env['nrs.asset.event']._record(
            self.asset_id, EVENT_PHOTO_SUPERSEDED, source='api_photo',
            actor=user, photo_id=self.id, reason=reason)

    # ── the bytes ─────────────────────────────────────────────────────

    def _bytes(self):
        """`(data, intact)` — the stored bytes and whether they still hash
        to what was recorded when they were uploaded."""
        self.ensure_one()
        data = base64.b64decode(self.sudo().image or b'')
        return data, hashlib.sha256(data).hexdigest() == self.sha256
