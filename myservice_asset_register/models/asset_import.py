from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
from datetime import date


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
        except Exception:
            raise ValidationError(_('Invalid JSON format.'))

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
                    # No `status_note` key when there is nothing to say, so the
                    # validation step's own note survives instead of being
                    # blanked.
                    existing.write(vals)
                    line.write(line_vals)

            except Exception as e:
                line.write({'status': 'error', 'status_note': str(e)[:200]})

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
