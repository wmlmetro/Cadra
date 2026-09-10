"""Disposal — the paper trail, and the period report that asks for it.

INT-10 §2.9 measured what Cadra could answer about a disposal and the answer
was "partly": `state = 'disposed'`, an untracked `disposal_date` and an
untracked `disposal_reason`, filterable by state and nothing else. **There
was no documentation reference of any kind** — no board minute, no approval
memo, no disposal certificate — no approver, no proceeds, and no period
report. `action_condemn` was two lines and wrote a condition and a state.

An auditor's test on a disposal is always the same question in three parts:
**was it authorised, by whom, and is the paper there?** None of the three
had a field to be answered in, so this module adds them and then reports on
them. The order matters: a reference has to exist before a report can cite
it, and a report over fields nobody can fill is a report of nothing.

Three rulings from earlier handoffs are load-bearing here and are applied
rather than re-argued:

**Nothing here repairs anything.** `disposal_report` is read-only and the
tests fingerprint the database around it. A report that quietly fixes what it
finds can never honestly report zero — the same argument report 19 made for
reconciliation in the Vendra repository.

**A reconstructed value says so on its face.** The migration recovers a
missing `disposal_date` from the tracked `state → disposed` transition, which
is evidence and not invention; but a recovered date written into the same
column as a recorded one is indistinguishable from it, and that is exactly
the defect `nrs.asset.custody.source = 'tracking_backfill'` exists to
prevent. So `disposal_date_reconstructed` marks the rows the migration
filled, the report publishes it, and it is a finding in its own right.

**Nothing is invented.** The migration sets no approver, because no evidence
anywhere in the database says who authorised a disposal made before there was
a field to record it in. A visible gap is the correct output; handoff 08's
289 affix records carrying `Administrator` were left alone on the same
reasoning.

**And `state = 'missing'` is not a disposal.** An asset that cannot be found
has not been disposed of, and conflating the two would let a loss be written
off as a disposal — INT-10 §2.9 and the SAP requirements §4.3 both say so
explicitly. The report guards it twice: once in the domain and once after
the search — the second is belt and braces today, and it is there because
whether the first one binds is a property of how the domain is assembled
rather than of what the report promises.
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# ── The disposal routes, and how each maps onto SAP ───────────────────────
#
# SAP takes one of two words for a disposal instruction —
# `docs/integrations/INT-06-07-09-sap-requirements.md` §4.2 defines
# `disposal_type` as `disposal` or `retirement` — so whatever Cadra records
# has to collapse onto those two without losing the distinction an auditor
# cares about. The line SAP draws is the one accounting draws: an asset that
# LEAVES the estate through a transaction with somebody is a *disposal*; an
# asset that ceases to exist in place, with nobody on the other side of it,
# is a *retirement*.
#
# The Cadra values are the routes a Nigerian public-sector board of survey
# actually records, which is what makes them recognisable on an audit
# schedule: sale, public auction, transfer to another government body,
# donation, trade-in, scrapping, and an authorised write-off.
#
# `other` exists so that a route nobody anticipated is recorded as an
# explicit choice with a reason beside it, rather than pushed into the
# nearest wrong value. It maps to `disposal`, the conservative side: SAP
# treating a scrapping as a disposal produces a retirement posting with no
# revenue, which is recoverable; the reverse under-states a loss.
SAP_DISPOSAL_TYPE = {
    'sale':      'disposal',
    'auction':   'disposal',
    'transfer':  'disposal',
    'donation':  'disposal',
    'trade_in':  'disposal',
    # Nothing changed hands. The asset was destroyed, cannibalised or written
    # off as beyond economic repair, and NRS is simply no longer carrying it.
    'scrapped':  'retirement',
    'write_off': 'retirement',
    'other':     'disposal',
}

# What `asset.disposed` carried before this module existed: the literal
# string `'disposal'`, hard-coded. It stays the value sent when no method has
# been recorded, so adding the field is additive for SAP rather than a
# change of behaviour on every event already in flight.
DEFAULT_SAP_DISPOSAL_TYPE = 'disposal'

# Routes where money should have come in. A scrapping with no proceeds is
# ordinary; a *sale* with no proceeds is a finding, and the report says so
# only for the routes where the absence means something.
PROCEEDS_EXPECTED_METHODS = ('sale', 'auction', 'trade_in')

# ── The findings ──────────────────────────────────────────────────────────
#
# Machine-readable strings, because the point of a finding is that somebody
# can count them and filter on them. They are published in the report's rows
# AND tallied in its summary, so "41 of 63 disposals have no authorising
# reference" is one read rather than a walk through pages.
FINDING_NO_REFERENCE = 'no_authorising_reference'
FINDING_NO_APPROVER = 'no_approver'
FINDING_NO_APPROVAL_DATE = 'no_approval_date'
FINDING_NO_METHOD = 'no_disposal_method'
FINDING_NO_DATE = 'no_disposal_date'
FINDING_NO_REASON = 'no_disposal_reason'
FINDING_NO_PROCEEDS = 'no_proceeds_recorded'
FINDING_RECONSTRUCTED_DATE = 'disposal_date_reconstructed'
FINDING_NO_SAP_NUMBER = 'no_sap_asset_number'

# Where the date on a report row came from. An auditor reconciling a period
# total has to know whether the date placing a row in that period was
# recorded at the time or worked out afterwards.
DATE_SOURCE_RECORDED = 'recorded'
DATE_SOURCE_RECONSTRUCTED = 'reconstructed'
DATE_SOURCE_TRACKING = 'state_transition'
DATE_SOURCE_NONE = 'none'


# The transition into `disposed`, read out of the chatter tracking values.
#
# Three facts about this query, all of them learned the hard way in the
# 19.0.1.12.0 custody backfill and repeated here so the next reader does not
# have to find them again:
#
#   * the field is reached through `mtv.field_id → ir_model_fields`, on
#     (`f.model`, `f.name`) — there is no model or field name on the tracking
#     row itself;
#   * `mail_message` carries the timestamp and the record id, so the join to
#     it is not optional; and
#   * for a Selection the `*_value_char` columns hold the **translated
#     label**, not the key, so matching on the string `'disposed'` finds
#     nothing and matching on `'Disposed'` finds nothing on a tenant running
#     in another language.
#
# That last one is why this query does not filter on the value at all. It
# takes the LATEST `state` tracking row for each asset, and the caller passes
# only assets that are currently `disposed` — for which the most recent state
# change is, by definition, the change into `disposed`. The label never has
# to be parsed, so the answer is the same in every language.
#
# The acting user is available here — `mail_message.author_id` — and is
# deliberately NOT selected. Whoever pressed the button that moved the state
# is not the authority who approved the disposal, and reading one as the
# other would fabricate exactly the evidence an auditor came for. The date is
# a fact about when; there is no fact about who.
_DISPOSED_TRACKING_SQL = """
    SELECT DISTINCT ON (m.res_id)
           m.res_id AS asset_id,
           m.date   AS changed_at
      FROM mail_tracking_value mtv
      JOIN ir_model_fields f ON f.id = mtv.field_id
      JOIN mail_message m ON m.id = mtv.mail_message_id
     WHERE f.model = 'nrs.asset'
       AND f.name = 'state'
       AND m.model = 'nrs.asset'
       AND m.res_id = ANY(%s)
     ORDER BY m.res_id, m.date DESC, m.id DESC
"""


def _not_disposed_message():
    return _(
        "This asset is not disposed of, so there is nothing to approve. "
        "A disposal approval recorded against an asset still on the "
        "register is an approval of nothing."
    )


def _already_approved_message(user_name, when):
    return _(
        "This disposal was already approved by %(user)s on %(when)s. An "
        "approval records who authorised the disposal and is not re-taken; "
        "correct the field on the form if it is wrong, where the change is "
        "tracked."
    ) % {'user': user_name, 'when': when}


class NRSAssetDisposal(models.Model):
    """The disposal fields, the approval act, and the period report.

    `_inherit` without `_name`: these are columns on `nrs.asset`, not a
    separate model. A disposal is a state an asset is in, not a document —
    Cadra has one row per physical unit and a disposal happens to that row
    once.
    """

    _inherit = 'nrs.asset'

    # ── The route out of the estate ───────────────────────────
    disposal_method = fields.Selection([
        ('sale',      'Sale'),
        ('auction',   'Public Auction'),
        ('transfer',  'Transfer to Another Entity'),
        ('donation',  'Donation'),
        ('trade_in',  'Trade-In'),
        ('scrapped',  'Scrapped / Destroyed'),
        ('write_off', 'Written Off'),
        ('other',     'Other'),
    ], string='Disposal Method', tracking=True,
        help='How the asset left the estate. Maps onto SAP\'s '
             'disposal/retirement distinction — see SAP_DISPOSAL_TYPE.')

    # The authorising document. Char and free text on purpose: the minute,
    # the memo and the certificate live in NRS's own filing, and modelling a
    # document register here would mean maintaining a shadow copy of it.
    # Indexed because "show me everything disposed under BOS/2026/014" is the
    # lookup this field exists for, and an auditor asks it holding a
    # reference and nothing else.
    disposal_reference = fields.Char(
        string='Authorising Reference', index=True, tracking=True,
        help='Board minute, approval memo or disposal certificate that '
             'authorised this disposal.')

    disposal_approved_by = fields.Many2one(
        'res.users', string='Disposal Approved By', tracking=True,
        help='Who authorised the disposal. Recorded by '
             'action_approve_disposal from the acting user.')
    disposal_approved_date = fields.Datetime(
        string='Disposal Approved On', tracking=True)

    # Money RECEIVED for the asset. This is NOT `salvage_value`, which lives
    # in myservice_asset_depreciation: that one is an ESTIMATE of residual
    # worth used to truncate a depreciation board, it is computed from a
    # percentage policy, and it exists on assets that will never be sold.
    # This one is a fact about a transaction that happened. Conflating them
    # would put a policy assumption into a disposal schedule an auditor is
    # reconciling against a bank statement.
    disposal_proceeds = fields.Monetary(
        string='Disposal Proceeds', currency_field='currency_id',
        tracking=True,
        help='Money actually received for the asset. Not salvage_value, '
             'which is an estimate used by the depreciation board.')

    # Set by the 19.0.1.14.0 migration on rows whose date it recovered from
    # the tracked state change, and by nothing else.
    #
    # Without it a recovered date is indistinguishable from a recorded one,
    # which is precisely the failure `nrs.asset.custody.source` exists to
    # prevent: an auditor told where a reconstruction begins can work with
    # it, one who discovers it later cannot trust any of it. A Boolean rather
    # than a source Selection because there are exactly two cases and a
    # null-means-two-things enum would be worse than the gap it documents.
    disposal_date_reconstructed = fields.Boolean(
        string='Disposal Date Reconstructed', readonly=True, tracking=True,
        help='This disposal date was recovered from the tracked state '
             'change, not recorded when the asset was disposed of.')

    # ── Two existing fields, now tracked ──────────────────────
    #
    # Re-declared here for one reason: to add `tracking=True`. They carry
    # exactly the definitions they have in `asset.py` and no other change.
    #
    # INT-10 §2.4 lists both among the untracked fields and the sentence that
    # matters is: every value an auditor would challenge could be changed
    # silently. A disposal date that can be moved between financial years
    # with no record, and a disposal reason that can be rewritten after a
    # query, are audit-material by any reading — and handoff 16 §B1 is
    # simultaneously establishing that an untracked field cannot be rolled
    # back to a historical date at all. A field with no history is a field
    # the snapshot report has to disclaim.
    disposal_date = fields.Date('Disposal Date', tracking=True)
    disposal_reason = fields.Text('Disposal Reason', tracking=True)

    # ── Recording an approval ─────────────────────────────────

    def action_approve_disposal(self):
        """Record who authorised this disposal — from the acting user.

        Shaped after `nrs.asset.transfer.action_approve`, and for the same
        reason: the approver is **who pressed the button**, which is evidence,
        rather than a name typed into a field, which is a claim. Since
        handoff 08 an API client acts as its own `res.users`, so a disposal
        approved through an integration names that integration rather than
        `Administrator`.

        Two refusals, both deliberate:

        * **Not disposed of.** An approval against a live asset records
          authority for something that has not happened. Cadra has no
          pre-approval workflow for disposals — `nrs.asset.transfer` is the
          model to copy if NRS wants one — so what this records is the
          confirmation that an executed disposal was authorised.
        * **Already approved.** Silently overwriting an approver erases the
          only record of who authorised the disposal. The fields are tracked,
          so a genuine correction is made on the form and leaves a trail;
          a button that quietly replaces one name with another does not.
        """
        for record in self:
            if record.state != 'disposed':
                raise UserError(_not_disposed_message())
            if record.disposal_approved_by:
                raise UserError(_already_approved_message(
                    record.disposal_approved_by.name,
                    fields.Datetime.to_string(record.disposal_approved_date)
                    if record.disposal_approved_date else _('an unknown date'),
                ))
            record.write({
                'disposal_approved_by': self.env.uid,
                'disposal_approved_date': fields.Datetime.now(),
            })
            record.message_post(body=_(
                'Disposal approved by %(user)s%(reference)s'
            ) % {
                'user': self.env.user.name,
                'reference': (
                    _(' under reference %s') % record.disposal_reference
                    if record.disposal_reference else ''),
            })

    # ── Recovering a missing disposal date ────────────────────

    @api.model
    def _recovered_disposal_datetimes(self, asset_ids):
        """{asset_id: naive UTC datetime} for the change into `disposed`.

        Read-only — one SELECT and nothing else. The caller must pass only
        assets currently at `state = 'disposed'`; see `_DISPOSED_TRACKING_SQL`
        for why that precondition is what makes the query language-proof.

        Assets with no tracking row come back absent rather than with a null,
        so a caller cannot mistake "no record of when" for "disposed at
        epoch". That happens on every tenant seeded by direct SQL and on
        every asset created already disposed.
        """
        if not asset_ids:
            return {}
        self.env.cr.execute(_DISPOSED_TRACKING_SQL, (list(asset_ids),))
        return {
            row['asset_id']: row['changed_at']
            for row in self.env.cr.dictfetchall()
            if row['changed_at']
        }

    # ── The period report ─────────────────────────────────────

    @api.model
    def disposal_report(self, date_from, date_to, extra_domain=None):
        """Every disposal in a period, with what is missing from each named.

        Specification §13.4 asks for a *"disposal report with documentation
        refs (per period)"*. This is it. It answers the auditor's three-part
        test — was it authorised, by whom, and is the paper there — and where
        it cannot answer, it says which part is missing rather than dropping
        the row.

        **Nothing is filtered out for having a finding.** A disposal with no
        authorising reference IS the finding; a report that showed only the
        well-documented ones would be a report of the paperwork rather than
        of the estate.

        **It never writes.** No repair, no backfill, no chatter post, no
        stamped field. A report that quietly fixes what it finds can never
        honestly report zero, and the second time it runs it reports a
        cleanliness it created itself.

        `date_from` and `date_to` are **both inclusive**, on whole dates. An
        auditor asks for a quarter by naming its first and last day, and a
        report whose upper bound is exclusive silently loses everything
        disposed of on 31 March.

        Returns `{'period': …, 'rows': […], 'unplaceable': […], 'summary': …}`.

        **`unplaceable` is the honest half of the period question.** A
        disposal with no recorded date and no tracked state change cannot be
        placed in any period. Dropping it would make it invisible in every
        report — the silent hole this report exists to close — and putting it
        in the period would double-count it in the next one. So it is
        returned in full, in its own key, in every report, with its own
        count, and it is never mixed into the period totals.
        """
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            raise UserError(_(
                'A disposal report needs both a start and an end date.'))
        if date_from > date_to:
            raise UserError(_(
                'The disposal report period ends before it starts: '
                '%(from)s to %(to)s.'
            ) % {'from': date_from, 'to': date_to})

        # `state = 'missing'` is NOT a disposal. An asset that cannot be
        # found has not been disposed of — INT-10 §2.9 and the SAP
        # requirements §4.3 both state it — and conflating them would let a
        # loss be written off as a disposal, which is the single most
        # consequential wrong answer this report could give.
        domain = [('state', '=', 'disposed')]
        if extra_domain:
            domain = domain + list(extra_domain)

        # No `limit`. A count or a schedule taken from a bounded fetch is the
        # defect handoff 13 spent itself removing, and "the first eighty
        # disposals" is precisely the answer an auditor cannot use: a
        # truncated schedule cannot be told from a complete one.
        assets = self.sudo().search(domain, order='disposal_date, id')

        # The second guard on `missing`, and it is deliberately belt and
        # braces. Concatenating `extra_domain` onto the clause above cannot
        # widen it today — Odoo normalises a list of expressions into an AND
        # of all of them, so a caller cannot OR their way back to `missing`.
        # It is here because that is a property of how the domain is
        # ASSEMBLED, not of what the report guarantees: the day somebody
        # builds it with `expression.OR`, or hands `domain` in whole, the
        # state clause silently stops binding and this report's single most
        # consequential wrong answer — a loss written off as a disposal — is
        # back with nothing to notice it. It logs if it ever fires.
        disposed = assets.filtered(lambda a: a.state == 'disposed')
        if len(disposed) != len(assets):
            _logger.warning(
                "disposal_report: %d record(s) matched the domain without "
                "being disposed of and were excluded. `extra_domain` widened "
                "the state clause.", len(assets) - len(disposed))

        recovered = self._recovered_disposal_datetimes(
            [a.id for a in disposed if not a.disposal_date])

        rows = []
        unplaceable = []
        for asset in disposed:
            row = self._disposal_report_row(asset, recovered)
            when = row['disposal_date']
            if when is None:
                unplaceable.append(row)
            elif date_from <= fields.Date.to_date(when) <= date_to:
                rows.append(row)

        return {
            'period': {
                'date_from': fields.Date.to_string(date_from),
                'date_to': fields.Date.to_string(date_to),
                'inclusive': 'both',
            },
            'rows': rows,
            'unplaceable': unplaceable,
            'summary': self._disposal_report_summary(rows, unplaceable),
        }

    @api.model
    def _disposal_report_row(self, asset, recovered):
        """One disposal, and everything missing from it, named.

        `recovered` is the map from `_recovered_disposal_datetimes`; the row
        falls back to it only where `disposal_date` is genuinely absent.
        """
        findings = []

        # Which date places this disposal in a period, and how much it is
        # worth. Four cases, and the row says which one it is rather than
        # presenting all four as the same column.
        if asset.disposal_date:
            when = fields.Date.to_string(asset.disposal_date)
            if asset.disposal_date_reconstructed:
                date_source = DATE_SOURCE_RECONSTRUCTED
                findings.append(FINDING_RECONSTRUCTED_DATE)
            else:
                date_source = DATE_SOURCE_RECORDED
        else:
            findings.append(FINDING_NO_DATE)
            changed_at = recovered.get(asset.id)
            if changed_at:
                # `mail_message.date` is naive UTC. Taking its date in UTC
                # rather than in a user's timezone is the honest reading: a
                # timezone conversion here would invent a precision the
                # source does not have, and could move a disposal across a
                # financial year boundary on the strength of a session
                # setting.
                when = fields.Date.to_string(changed_at.date())
                date_source = DATE_SOURCE_TRACKING
            else:
                when = None
                date_source = DATE_SOURCE_NONE

        if not asset.disposal_reference:
            findings.append(FINDING_NO_REFERENCE)
        if not asset.disposal_approved_by:
            findings.append(FINDING_NO_APPROVER)
        elif not asset.disposal_approved_date:
            # An approver with no date is a weaker finding than no approver
            # at all, and a different one: somebody is named, but the
            # disposal cannot be placed against the authority in time.
            findings.append(FINDING_NO_APPROVAL_DATE)
        if not asset.disposal_method:
            findings.append(FINDING_NO_METHOD)
        if not asset.disposal_reason:
            findings.append(FINDING_NO_REASON)
        if (asset.disposal_method in PROCEEDS_EXPECTED_METHODS
                and not asset.disposal_proceeds):
            # Only where the route means money should have come in. A
            # scrapping with no proceeds is ordinary and flagging it would
            # bury the sales that are missing theirs.
            findings.append(FINDING_NO_PROCEEDS)
        if not asset.sap_asset_number:
            # No SAP asset number means the asset was never capitalised
            # there, so INT-09 sent no disposal instruction — by design, and
            # documented in the SAP requirements §4.1. The consequence for
            # this report is that the disposal never reached the financial
            # system, which is a finding whatever the reason for it.
            #
            # This will fire on close to every row on today's tenants: 2 of
            # 11,942 assets on `nrs19` carry a SAP number and none on
            # `jaizbankplc`. That is the true picture of the dual-code
            # position and it belongs in the report rather than in a footnote.
            findings.append(FINDING_NO_SAP_NUMBER)

        return {
            'asset_id': asset.id,
            'name': asset.name or None,
            'asset_code': asset.asset_code or None,
            'sap_asset_number': asset.sap_asset_number or None,
            'disposal_date': when,
            'date_source': date_source,
            'disposal_method': asset.disposal_method or None,
            'sap_disposal_type': SAP_DISPOSAL_TYPE.get(
                asset.disposal_method, DEFAULT_SAP_DISPOSAL_TYPE),
            'disposal_reference': asset.disposal_reference or None,
            'approved_by_id': asset.disposal_approved_by.id or None,
            'approved_by': asset.disposal_approved_by.name or None,
            'approved_at': (
                fields.Datetime.to_string(asset.disposal_approved_date)
                if asset.disposal_approved_date else None),
            'proceeds': asset.disposal_proceeds or 0.0,
            'currency': asset.currency_id.name or None,
            'disposal_reason': asset.disposal_reason or None,
            'condition_at_disposal': asset.condition or None,
            'findings': findings,
        }

    @api.model
    def _disposal_report_summary(self, rows, unplaceable):
        """The counts an auditor reads before opening the schedule.

        The findings tally is over the PERIOD's rows. `unplaceable` gets a
        count of its own and its rows carry their own findings, because
        merging the two would produce a per-period total that changes
        meaning depending on how much undated data the tenant holds.

        Proceeds are totalled **per currency and never across them**. Every
        tenant here is single-currency today, which is exactly the condition
        under which a cross-currency sum looks correct for years.
        """
        findings = {}
        for row in rows:
            for finding in row['findings']:
                findings[finding] = findings.get(finding, 0) + 1

        by_method = {}
        proceeds = {}
        for row in rows:
            method = row['disposal_method'] or 'unspecified'
            by_method[method] = by_method.get(method, 0) + 1
            currency = row['currency'] or 'unknown'
            proceeds[currency] = proceeds.get(currency, 0.0) + (
                row['proceeds'] or 0.0)

        return {
            # Both counts are over an UNLIMITED search — `disposal_report`
            # takes no `limit`, precisely so that these two numbers are
            # counts of the register and not of a page of it.
            'total': len(rows),
            'unplaceable': len(unplaceable),
            'clean': sum(1 for row in rows if not row['findings']),
            'findings': findings,
            'by_method': by_method,
            'proceeds_by_currency': proceeds,
        }

    # ── The action that produces a disposal ───────────────────

    def action_condemn(self):
        """Record WHEN, alongside the condition and the state.

        `action_condemn` wrote a condition and a state and nothing else, so
        every disposal made through the Odoo button arrived with a null
        `disposal_date` — the hole the migration recovers from tracking
        values, still open for every disposal made after it. The
        depreciation module already stamps the date for the reason that
        depreciation must stop; this makes the date a property of the
        disposal itself, so a tenant without the depreciation module
        installed does not silently produce undated disposals.

        Deliberately NOT stamped here: the approver. Condemning an asset is
        not authorising its disposal, and recording the person who pressed
        this button as the approving authority would manufacture exactly the
        evidence an auditor is asking for.
        """
        result = super().action_condemn()
        for record in self:
            if not record.disposal_date:
                record.disposal_date = fields.Date.context_today(record)
        return result
