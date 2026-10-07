"""The SAP side of the register — INT-06 / INT-07 and the dual-code control.

Three things live here, and they are deliberately in the asset register rather
than in the transport module:

1. **What SAP told us** — the asset master figures returned on INT-07. Held as
   SAP's *reported* values, never fed into Cadra's own depreciation engine.
   Two systems computing one number is how they come to disagree; one system
   computing it and the other displaying what it was told cannot.

2. **Where the SAP code came from** — `sap_code_source`. A SAP asset number
   typed in by a person and one returned by SAP are the same string and very
   different facts. The dual-code control is an audit control, so the audit
   has to be able to tell them apart. Same instinct as `label_state` against
   `state`, and `depreciation_start_source` against a bare date.

3. **Whether the asset is reconciled** — the completeness control the
   September Integration Flow names:

       "An asset is complete only when both the Cadra Asset Code and the SAP
        asset code are linked on the register."

   Half of that was made real in handoff 02, when `asset_code` became unique
   and NOT NULL. This is the other half: an asset carrying only one of the two
   codes is an exception somebody must SEE, not a quiet row.

`sap_asset_number` itself is not defined here — it already existed on the
register (`asset_tag.py`) as an import field and is still legitimately written
by the legacy importer. It is deliberately NOT write-guarded: linking existing
SAP asset numbers onto the ~11,880 legacy assets is exactly how the opening
balance of this control gets built. `sap_code_source` is what keeps that
honest instead.
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Where a SAP asset number on the register came from.
SAP_SOURCE_INTEGRATION = 'integration'
SAP_SOURCE_IMPORT = 'import'
SAP_SOURCE_MANUAL = 'manual'

# How far the INT-06 posting has got. Maintained by the transport module; a
# plain stored field rather than a compute over dispatch rows, so the asset
# register does not have to know that a queue exists.
POSTING_NONE = 'none'
POSTING_QUEUED = 'queued'
POSTING_POSTED = 'posted'
POSTING_FAILED = 'failed'

# The dual-code states.
RECON_NOT_TAGGED = 'not_tagged'
RECON_PENDING = 'pending'
RECON_RECONCILED = 'reconciled'
RECON_EXCEPTION = 'exception'


class NRSAssetSAP(models.Model):
    _inherit = 'nrs.asset'

    # ── What SAP returned (INT-07) ────────────────────────────────────
    #
    # Every one of these is SAP's answer, not ours. They are shown on the
    # register so an asset manager can see finance's numbers without a SAP
    # login, and they are never inputs to anything Cadra calculates.
    sap_asset_subnumber = fields.Char(
        'SAP Sub-Number', copy=False,
        help='SAP fixed assets are identified by a main number and a '
             'sub-number. Storing only the main number would not identify '
             'the asset where sub-numbers are in use.')
    sap_company_code = fields.Char(
        'SAP Company Code', copy=False,
        help='The same SAP asset number can exist under two company codes, '
             'so the number alone is not unique.')
    sap_asset_class = fields.Char(
        'SAP Asset Class (as posted)', copy=False,
        help='The class SAP actually used. If it differs from the class Cadra '
             'derived from the category, the mapping is wrong and this is '
             'where that shows.')
    sap_capitalisation_date = fields.Date(
        'SAP Capitalisation Date', copy=False,
        help='The date SAP posted, which may differ from the tagging date '
             'Cadra proposed — period-close rules are SAP\'s to apply.')
    sap_capitalised_amount = fields.Monetary(
        'SAP Capitalised Amount', currency_field='currency_id', copy=False,
        help='The value SAP actually capitalised. Where this differs from '
             'the cost Cadra sent, SAP is right and this is the figure to '
             'show.')
    sap_net_book_value = fields.Monetary(
        'SAP Net Book Value', currency_field='currency_id', copy=False,
        help='As reported by SAP. Display only — this never feeds Cadra\'s '
             'depreciation engine, which would put two systems in charge of '
             'one number.')
    sap_accumulated_depreciation = fields.Monetary(
        'SAP Accumulated Depreciation', currency_field='currency_id',
        copy=False, help='As reported by SAP. Display only.')
    sap_synced_at = fields.Datetime(
        'SAP Last Synced', copy=False, readonly=True,
        help='When Cadra last received asset master figures from SAP.')

    sap_code_source = fields.Selection([
        (SAP_SOURCE_INTEGRATION, 'Returned by SAP (INT-07)'),
        (SAP_SOURCE_IMPORT, 'Loaded from a legacy extract'),
        (SAP_SOURCE_MANUAL, 'Entered by hand'),
    ], string='SAP Code Source', copy=False, index=True,
       help='How the SAP asset number got onto this record. A code returned '
            'by SAP is evidence that finance booked the asset; a code typed '
            'in by a person is a claim that they did. The dual-code control '
            'is an audit control, so the two must not look alike.')

    # ── Posting progress (INT-06) ─────────────────────────────────────
    sap_posting_state = fields.Selection([
        (POSTING_NONE, 'Not posted'),
        (POSTING_QUEUED, 'Queued for SAP'),
        (POSTING_POSTED, 'Delivered to SAP'),
        (POSTING_FAILED, 'Delivery abandoned'),
    ], string='SAP Posting', default=POSTING_NONE, readonly=True, copy=False,
       index=True,
       help='How far the INT-06 asset master posting has got. Maintained by '
            'the outbound event queue.')

    # ── The dual-code control ─────────────────────────────────────────
    sap_reconciliation_state = fields.Selection([
        (RECON_NOT_TAGGED, 'Not tagged — SAP posting not due'),
        (RECON_PENDING, 'Posted to SAP — awaiting asset code'),
        (RECON_RECONCILED, 'Reconciled — both codes linked'),
        (RECON_EXCEPTION, 'EXCEPTION — tagged with no SAP code'),
    ], string='Dual-Code Status',
       compute='_compute_sap_reconciliation_state', store=True, index=True,
       help='The September Integration Flow completeness control: an asset '
            'is complete only when both the Cadra Asset Code and the SAP '
            'asset code are linked on the register.')

    @api.depends('sap_asset_number', 'tag_label_state', 'sap_posting_state')
    def _compute_sap_reconciliation_state(self):
        """Four states, and only one of them is a finding.

        The ordering matters. `reconciled` is checked FIRST and on the
        presence of the SAP code alone, because a legacy asset linked to an
        existing SAP asset number is genuinely complete even though Cadra
        never posted it and it may never be tagged — refusing to call that
        reconciled would turn the opening balance of this control into twelve
        thousand permanent exceptions.

        `not_tagged` is not an exception either. INT-06 fires on tagging
        confirmed, so an untagged asset has no SAP code because it is not yet
        due one. Colouring that red would bury the 34 real cases in 11,880
        false ones, and an exception report nobody can read is the same as no
        exception report.
        """
        for r in self:
            if r.sap_asset_number:
                r.sap_reconciliation_state = RECON_RECONCILED
            elif r.tag_label_state != 'affixed':
                r.sap_reconciliation_state = RECON_NOT_TAGGED
            elif r.sap_posting_state in (POSTING_QUEUED, POSTING_POSTED):
                # In flight, or delivered and awaiting a deferred code. Not a
                # finding yet — it becomes one when the queue gives up, which
                # sets `failed` and drops it into the branch below.
                r.sap_reconciliation_state = RECON_PENDING
            else:
                # Tagged, and either nothing was ever posted or the posting
                # was abandoned. Finance has not booked a physical asset that
                # demonstrably exists: an audit finding.
                r.sap_reconciliation_state = RECON_EXCEPTION

    @api.constrains('sap_asset_number', 'sap_company_code',
                    'sap_asset_subnumber')
    def _check_sap_asset_number_unique(self):
        """One SAP asset, one Cadra asset. The other half of handoff 02.

        Handoff 02 made `asset_code` unique and NOT NULL on the reasoning
        that "INT-06/07 assumes one asset per code — without the constraint
        two assets can share a code and the reconciliation silently matches
        the wrong one". That argument is symmetrical and only one side of it
        was built: nothing stopped two Cadra assets carrying the SAME SAP
        asset number, which is the same defect pointed the other way and a
        worse one to find, because it means finance's single asset master is
        claimed by two physical things.

        Found live, not theorised: a mock SAP restarted, re-issued an asset
        number it had already issued, and Cadra linked it to a second asset
        without complaint.

        The key is the TRIPLE, not the number alone, because a SAP asset
        number is only unique within a company code — the same reasoning that
        makes `company_code` a required field in the INT-07 response (see the
        requirements document §2.6). A sub-number distinguishes components of
        one asset master, so it belongs in the key too.

        This is a Python constraint rather than a database one deliberately.
        The true key depends on whether NRS uses more than one company code,
        which is an OPEN QUESTION we have asked SAP (§5.3) and not yet had
        answered. A UNIQUE index over three nullable columns would enforce
        nothing on exactly the rows that matter today — Postgres does not
        compare NULLs, and the legacy extract will land asset numbers with no
        company code at all. Once §5.3 is answered the constraint should
        become a database one on the settled key; until then this catches
        every ORM path, including the integration, which is where the
        duplicate actually came from.
        """
        for record in self:
            if not record.sap_asset_number:
                continue
            # A receipt candidate's typed SAP code counts (handoff 57).
            duplicate = self.sudo().with_context(
                cadra_candidates=True).search([
                ('id', '!=', record.id),
                ('sap_asset_number', '=', record.sap_asset_number),
                ('sap_company_code', '=', record.sap_company_code or False),
                ('sap_asset_subnumber', '=', record.sap_asset_subnumber or False),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'SAP asset number %(number)s is already linked to asset '
                    '%(code)s. An asset is complete only when both codes are '
                    'linked, and that control assumes one SAP asset master '
                    'per physical asset — two assets sharing one SAP number '
                    'means finance has booked one thing and the register '
                    'holds two.'
                ) % {'number': record.sap_asset_number,
                     'code': duplicate.asset_code or duplicate.display_name})

    # ── Guarding the evidence ─────────────────────────────────────────
    #
    # `sap_code_source` is the field that separates a SAP asset number SAP
    # returned from one a person typed in, and `sap_synced_at` is the claim
    # that Cadra heard from SAP at all. Both are evidence, and this repo has
    # already ruled that `readonly=True` is a web-client hint rather than an
    # ORM guard (handoff 03, the tag capture fields).
    #
    # The guard is deliberately narrow. A person may still say a code was
    # entered by hand or loaded from a legacy extract — those are honest
    # self-descriptions and the legacy linking exercise needs them. What
    # nobody may do is CLAIM THE INTEGRATION returned it: that would turn a
    # hand-typed number into apparent evidence that finance booked the asset,
    # which is the one thing the dual-code control is there to detect.
    _SAP_EVIDENCE_CONTEXT = 'cadra_sap_int07'

    @api.model
    def _assert_sap_evidence_allowed(self, vals):
        if self.env.context.get(self._SAP_EVIDENCE_CONTEXT):
            return
        if vals.get('sap_code_source') == SAP_SOURCE_INTEGRATION:
            raise ValidationError(_(
                'Only the SAP integration can record that a SAP asset number '
                'was returned by SAP. A code entered by hand or loaded from '
                'an extract is a claim that finance booked this asset; a code '
                'returned on INT-07 is evidence that it did. Recording one as '
                'the other would defeat the dual-code control. Choose '
                '"Entered by hand" or "Loaded from a legacy extract".'))
        if 'sap_synced_at' in vals:
            raise ValidationError(_(
                '"SAP Last Synced" records when Cadra last heard from SAP and '
                'is written by the integration, not by hand.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._assert_sap_evidence_allowed(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._assert_sap_evidence_allowed(vals)
        return super().write(vals)

    def _set_sap_master(self, values, source=SAP_SOURCE_INTEGRATION):
        """Record what SAP returned for this asset.

        Kept here rather than in the transport module so that a future INT-07
        route — the reconciliation query, a callback, a legacy extract loader
        — writes the register through one method with one set of rules,
        instead of three call sites each deciding what a missing field means.

        Only keys SAP actually sent are written. A response that omits the
        net book value must not blank the one we already had; absent and zero
        are different answers and only one of them is a figure.
        """
        self.ensure_one()
        mapping = {
            'sap_asset_number': 'sap_asset_number',
            'sap_asset_subnumber': 'sap_asset_subnumber',
            'company_code': 'sap_company_code',
            'asset_class': 'sap_asset_class',
            'capitalisation_date': 'sap_capitalisation_date',
            'capitalised_amount': 'sap_capitalised_amount',
            'net_book_value': 'sap_net_book_value',
            'accumulated_depreciation': 'sap_accumulated_depreciation',
        }
        vals = {}
        for wire_key, field_name in mapping.items():
            value = values.get(wire_key)
            # `is None` and `== ''`, NOT `not in (None, '', False)`: Python
            # makes `0 == False` true, so the tuple form silently threw away
            # every zero — and a fully depreciated asset's net book value is
            # exactly 0.00. That is SAP's answer, not the absence of one, and
            # discarding it was this method's own rule inverted.
            if value is None or value == '':
                continue
            vals[field_name] = value
        if not vals:
            return False
        vals['sap_synced_at'] = fields.Datetime.now()
        if vals.get('sap_asset_number') and not self.sap_code_source:
            vals['sap_code_source'] = source
        self.sudo().with_context(**{self._SAP_EVIDENCE_CONTEXT: True}).write(vals)
        return True


class NRSAssetCategorySAP(models.Model):
    """The asset class mapping — one identifier meaning two things (§5.1).

    Cadra classifies into 22 categories; SAP has its own asset classes, and
    the two are not the same list. This field is where NRS's mapping is
    recorded when it arrives. It is deliberately BLANK by default and the
    INT-06 payload sends null rather than falling back to the Cadra code: an
    asset posted to the wrong SAP class gets the wrong useful life and the
    wrong depreciation key, and none of that looks like a failure afterwards.
    A null is rejected on the way in, which does.
    """
    _inherit = 'nrs.asset.category'

    sap_asset_class = fields.Char(
        'SAP Asset Class',
        help='The SAP asset class this Cadra category maps to. Supplied by '
             'the NRS SAP team; see docs/integrations/'
             'INT-06-07-09-sap-requirements.md §5.1. Assets in a category '
             'with no mapping are posted with a null asset class so SAP '
             'rejects them, rather than being guessed into a class.')
