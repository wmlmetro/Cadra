from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging
from datetime import date

_logger = logging.getLogger(__name__)


class NRSAssetImport(models.Model):
    _name = 'nrs.asset.import'
    _description = 'Asset Import Session (SAP / Third Party)'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char('Import Reference', required=True)
    source = fields.Selection([
        ('sap',     'SAP'),
        ('redhubb', 'Redhubb'),
        ('excel',   'Excel / CSV'),
        ('other',   'Other'),
    ], required=True, default='excel')

    state = fields.Selection([
        ('draft',     'Draft'),
        ('validated', 'Validated'),
        ('imported',  'Imported'),
        ('error',     'Error'),
    ], default='draft', tracking=True)

    import_date = fields.Date('Import Date', default=fields.Date.today)
    raw_data = fields.Text(
        'Raw Data (JSON)',
        help='Paste JSON array of asset records for import')
    line_ids = fields.One2many('nrs.asset.import.line', 'import_id', string='Lines')
    total_lines = fields.Integer('Total', compute='_compute_stats')
    new_count = fields.Integer('New', compute='_compute_stats')
    update_count = fields.Integer('Updates', compute='_compute_stats')
    skip_count = fields.Integer('Skipped', compute='_compute_stats')
    error_count = fields.Integer('Errors', compute='_compute_stats')
    notes = fields.Text('Notes')

    @api.depends('line_ids.status')
    def _compute_stats(self):
        for r in self:
            lines = r.line_ids
            r.total_lines = len(lines)
            r.new_count = len(lines.filtered(lambda l: l.status == 'new'))
            r.update_count = len(lines.filtered(lambda l: l.status == 'update'))
            r.skip_count = len(lines.filtered(lambda l: l.status == 'skip'))
            r.error_count = len(lines.filtered(lambda l: l.status == 'error'))

    def action_validate(self):
        """Parse raw_data JSON and create import lines."""
        self.line_ids.unlink()
        if not self.raw_data:
            raise ValidationError(_('No data to validate.'))
        try:
            records = json.loads(self.raw_data)
        except ValueError as e:
            # Narrow, and it is the whole of what this try can raise: the body
            # is one `json.loads` over a Text field already known to be
            # non-empty, so the only failure is malformed input —
            # json.JSONDecodeError, which is a ValueError. The broad catch that
            # stood here also claimed 'Invalid JSON format.' for anything else
            # that ever got added to the block, and the position that says
            # WHERE the JSON is broken was thrown away.
            raise ValidationError(
                _('Invalid JSON format: %s') % e) from e

        if not isinstance(records, list):
            # Valid JSON, wrong shape. A pasted object rather than an array
            # used to iterate its KEYS, so `row.get` raised AttributeError on a
            # string and the operator got an Odoo traceback instead of the
            # message this method already has for bad input.
            raise ValidationError(_(
                'Expected a JSON array of asset records, got %s.'
            ) % type(records).__name__)

        lines = []
        for row in records:
            asset_code = row.get('asset_code') or row.get('sap_asset_number', '')
            existing = self.env['nrs.asset'].search(
                [('asset_code', '=', asset_code)], limit=1) if asset_code else False
            tag_exists = False
            if row.get('asset_tag'):
                tag_exists = self.env['nrs.asset.tag.label'].search_count(
                    [('name', '=', row['asset_tag']), ('state', '=', 'active')])

            if not asset_code:
                status = 'error'
                status_note = 'Missing asset_code'
            elif existing:
                status = 'update'
                status_note = 'Will update existing asset %s' % existing.name
            elif tag_exists:
                status = 'skip'
                status_note = 'Tag %s already active on another asset' % row.get('asset_tag')
            else:
                status = 'new'
                status_note = 'Will create new asset'

            lines.append({
                'import_id':    self.id,
                'asset_code':   asset_code,
                'asset_name':   row.get('name', ''),
                'asset_tag':    row.get('asset_tag', ''),
                'sap_number':   row.get('sap_asset_number', ''),
                'category':     row.get('category', ''),
                'domain':       row.get('domain', 'other'),
                'location':     row.get('location', ''),
                'custodian':    row.get('custodian', ''),
                'cost':         float(row.get('acquisition_cost', 0)),
                'condition':    row.get('condition', 'good'),
                'raw_line':     json.dumps(row),
                'status':       status,
                'status_note':  status_note,
            })
        self.env['nrs.asset.import.line'].create(lines)
        self.write({'state': 'validated'})

    def action_import(self):
        """Execute import for validated lines."""
        if self.state != 'validated':
            raise ValidationError(_('Please validate before importing.'))

        Cat = self.env['nrs.asset.category']
        Loc = self.env['generic.location']

        for line in self.line_ids.filtered(lambda l: l.status in ['new', 'update']):
            try:
                # One savepoint per line. The handler below reports the failure
                # by WRITING it onto the line — and a failed `nrs.asset` create
                # is usually a database error (a duplicate `asset_code`, a
                # NOT NULL), which leaves the transaction aborted, so that
                # write raised too and took the whole import down with a
                # message about the wrong thing. A per-line report is only a
                # report if the line can still be written after the failure.
                with self.env.cr.savepoint():
                    row = json.loads(line.raw_line)
                    # Resolve category
                    cat = Cat.search([('name', 'ilike', line.category)], limit=1)
                    # Resolve location
                    loc = Loc.search([('name', 'ilike', line.location)], limit=1) if line.location else False

                    vals = {
                        'name':             line.asset_name,
                        'asset_code':       line.asset_code,
                        'category_id':      cat.id if cat else False,
                        'domain':           line.domain or 'other',
                        'location_id':      loc.id if loc else False,
                        'acquisition_cost': line.cost,
                        'condition':        line.condition or 'good',
                        'sap_asset_number': line.sap_number,
                        'import_source':    self.source,
                        'import_date':      self.import_date,
                        'import_ref':       self.name,
                        'tag_source':       'sap' if self.source == 'sap' else 'other',
                    }
                    if line.status == 'new':
                        # On create the spreadsheet's tag is the number already on
                        # the physical asset, and nrs.asset.create mints a matching
                        # label record for it.
                        if line.asset_tag:
                            vals['asset_tag'] = line.asset_tag
                        asset = self.env['nrs.asset'].create(vals)
                        line.write({'asset_id': asset.id, 'status': 'imported'})
                    else:
                        existing = self.env['nrs.asset'].search(
                            [('asset_code', '=', line.asset_code)], limit=1)
                        if not existing:
                            # `write()` on an empty recordset is a silent no-op, so
                            # this used to mark the line `imported` having changed
                            # nothing at all.
                            line.write({
                                'status': 'error',
                                'status_note': 'No asset with code %s to update' % (
                                    line.asset_code or '(blank)'),
                            })
                            continue
                        # `asset_tag` is deliberately NOT written on update. Writing
                        # it on an existing asset changes the number the register
                        # shows without touching the tag label — no label record is
                        # created for it, nothing is reprinted, and nobody goes near
                        # the asset — so the register drifts away from the sticker
                        # in the room. That is the same defect the API's
                        # writable-field allow-list closes. A tag genuinely changes
                        # only through the replacement flow, which prints a new
                        # label and takes an affix confirmation.
                        incoming = (line.asset_tag or '').strip()
                        line_vals = {'asset_id': existing.id, 'status': 'imported'}
                        if incoming and incoming != (existing.asset_tag or '').strip():
                            line_vals['status_note'] = (
                                'Tag %s in the file was NOT applied: the asset '
                                'carries %s. Request a tag replacement to change '
                                'it.' % (incoming, existing.asset_tag or '(none)'))
                        # `location_id` is NOT written on update unless the file
                        # named a location that was FOUND. `vals` always carries
                        # the key, so a blank cell — or a name with a typo in it,
                        # which `ilike` resolves to nothing — used to write
                        # `False` and move the asset to nowhere. That was already
                        # wrong; since handoff 28 it would also be PERMANENT,
                        # because every change of `location_id` is appended to
                        # `nrs.asset.movement`, which refuses correction by
                        # design. A file that does not say where an asset is has
                        # not said it moved. Same care as `asset_tag` above, for
                        # the same reason: the register must not drift from the
                        # room on the strength of an empty column.
                        update_vals = dict(vals)
                        if not loc:
                            update_vals.pop('location_id', None)
                            if (line.location or '').strip():
                                unresolved = (
                                    'Location "%s" in the file matched no '
                                    'location, so the asset was left at %s.' % (
                                        line.location.strip(),
                                        existing.location_id.display_name
                                        or '(no location)'))
                                line_vals['status_note'] = ' '.join(filter(None, [
                                    line_vals.get('status_note'), unresolved]))
                        # No `status_note` key when there is nothing to say, so the
                        # validation step's own note survives instead of being
                        # blanked.
                        existing.write(update_vals)
                        line.write(line_vals)

            except Exception as e:
                # catch-all: reported — a line is a create or write of an
                # `nrs.asset` from spreadsheet text, so the set is open by
                # construction: a ValueError for a `condition` or `domain`
                # value the selection does not have, a ValidationError from an
                # asset constraint, psycopg2 for a duplicate `asset_code`,
                # KeyError for `generic.location` where the FM modules are not
                # installed. The failure is written onto the line, which is
                # where the operator reads the result of the import.
                _logger.warning(
                    'Asset import %s: line %s (%s) failed',
                    self.name, line.id, line.asset_code or '(blank)',
                    exc_info=True,
                )
                # The type as well as the text: several ORM errors stringify
                # to '' and the note then read as a blank cell beside the word
                # "Error".
                line.write({
                    'status': 'error',
                    'status_note': ('%s: %s' % (type(e).__name__, e))[:200],
                })

        self.write({'state': 'imported'})


class NRSAssetImportLine(models.Model):
    _name = 'nrs.asset.import.line'
    _description = 'Asset Import Line'

    import_id = fields.Many2one('nrs.asset.import', ondelete='cascade')
    asset_code = fields.Char('Asset Code')
    asset_name = fields.Char('Asset Name')
    asset_tag = fields.Char('Tag Number')
    sap_number = fields.Char('SAP Number')
    category = fields.Char('Category')
    domain = fields.Char('Domain')
    location = fields.Char('Location')
    custodian = fields.Char('Custodian')
    cost = fields.Float('Cost')
    condition = fields.Char('Condition')
    raw_line = fields.Text('Raw Data')
    status = fields.Selection([
        ('new',      'New'),
        ('update',   'Update'),
        ('skip',     'Skip'),
        ('error',    'Error'),
        ('imported', 'Imported'),
    ], default='new')
    status_note = fields.Char('Note')
    asset_id = fields.Many2one('nrs.asset', string='Created/Updated Asset')
