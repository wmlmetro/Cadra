"""Backfill the chain of custody from the chatter tracking values.

Until `nrs.asset.custody` existed, every custody change Cadra ever recorded
lived in `mail_tracking_value` — reachable from the Odoo chatter, exposed by
no API route, and deletable by any user holding the groups that let them
delete a message. This script moves that history into the append-only model
so an auditor can read it.

**Every row this writes carries `source = 'tracking_backfill'` on its face,
and the API returns that field.** The reconstruction is faithful — a tracking
value carries the old and new employee, the acting user and the timestamp, so
nothing here is invented — but it is still a reconstruction, and a reader has
to be able to tell one from a link recorded as it happened.

**It will look sparser than the register, and that is the correct picture.**
It covers only changes made since `custodian_id` became a tracked field, and
only on tenants whose data was created through the ORM: a tenant seeded by
direct SQL has no tracking rows and therefore gets no history at all. An
auditor told where the record begins can work with it. One who discovers the
gap later cannot trust any of it, including the part that is complete.

The counts are logged per tenant — rows read against rows written — because
the two agreeing is the only evidence that nothing was dropped.
"""
import logging

_logger = logging.getLogger(__name__)

# Ordered oldest-first so the reconstructed chain reads in the direction it
# happened. `mail_message.date` is when the change was recorded; `id` breaks
# ties inside a single import transaction, where hundreds share one second.
_TRACKING_SQL = """
    SELECT m.res_id           AS asset_id,
           mtv.old_value_integer AS from_id,
           mtv.new_value_integer AS to_id,
           mtv.old_value_char AS from_name,
           mtv.new_value_char AS to_name,
           m.date             AS changed_at,
           m.author_id        AS author_partner_id,
           m.create_uid       AS message_uid
      FROM mail_tracking_value mtv
      JOIN ir_model_fields f ON f.id = mtv.field_id
      JOIN mail_message m ON m.id = mtv.mail_message_id
     WHERE f.model = 'nrs.asset'
       AND f.name = 'custodian_id'
       AND m.model = 'nrs.asset'
     ORDER BY m.date, m.id
"""


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    # `create` on this model refuses a link that did not come from a
    # custodian moving. A backfill IS the exception, and it declares
    # itself as one rather than the model quietly allowing everything.
    from odoo.addons.myservice_asset_register.models.asset_custody import (
        CUSTODY_APPEND_KEY,
    )
    Custody = env["nrs.asset.custody"].sudo().with_context(
        **{CUSTODY_APPEND_KEY: True})

    # Re-running must not double the history. A migration script runs once per
    # version per database, but a tenant restored from a backup taken mid-run
    # would otherwise get two of everything, and duplicated links in an
    # append-only record cannot be removed afterwards.
    if Custody.search_count([("source", "=", "tracking_backfill")]):
        _logger.info(
            "myservice_asset_register: custody backfill already present on "
            "%s — nothing to do.", cr.dbname)
        return

    cr.execute(_TRACKING_SQL)
    rows = cr.dictfetchall()
    if not rows:
        _logger.info(
            "myservice_asset_register: no custodian tracking values on %s — "
            "this tenant's chain of custody starts empty.", cr.dbname)
        return

    # Resolve the acting user once. `mail_message.author_id` is a PARTNER, and
    # it is the faithful answer to "who made the change": `create_uid` on the
    # message is whichever database user inserted the row, which on a seeded
    # tenant is the superuser for every record regardless of who acted.
    cr.execute("SELECT partner_id, id FROM res_users WHERE partner_id IS NOT NULL")
    user_by_partner = dict(cr.fetchall())
    # `res.users` has NO `name` column: it `_inherits` `res.partner`, so the
    # name lives on the partner row and `SELECT name FROM res_users` is a
    # hard SQL error. It took down the first `nrs19` run and NOT the
    # `cadra19` one, because a tenant with no tracking values returns above
    # this line and never reaches it — the shape of bug that hides on the
    # small database you test against.
    cr.execute("""
        SELECT u.id, p.name
          FROM res_users u
          JOIN res_partner p ON p.id = u.partner_id
    """)
    name_by_uid = dict(cr.fetchall())

    live_assets = set(env["nrs.asset"].sudo().with_context(
        active_test=False).search([]).ids)
    cr.execute("SELECT id FROM hr_employee")
    live_employees = {row[0] for row in cr.fetchall()}

    vals_list = []
    skipped_missing_asset = 0
    skipped_no_change = 0
    for row in rows:
        if row["asset_id"] not in live_assets:
            # The asset was deleted after its custody change was recorded.
            # There is nothing to attach the link to, and inventing an asset
            # to hold it would be worse than the gap.
            skipped_missing_asset += 1
            continue
        from_id = row["from_id"] or False
        to_id = row["to_id"] or False
        if from_id == to_id:
            skipped_no_change += 1
            continue
        uid = user_by_partner.get(row["author_partner_id"]) or row["message_uid"]
        vals_list.append({
            "asset_id": row["asset_id"],
            # An employee deleted since the change was recorded cannot be
            # linked — the foreign key would refuse the row and take the
            # whole backfill with it. The NAME is kept regardless, which is
            # what the two `*_name` columns are for: the link degrades, the
            # evidence does not.
            "from_custodian_id": from_id if from_id in live_employees else False,
            "to_custodian_id": to_id if to_id in live_employees else False,
            "from_custodian_name": row["from_name"] or False,
            "to_custodian_name": row["to_name"] or False,
            "changed_at": row["changed_at"],
            "changed_by_id": uid or False,
            "changed_by_name": name_by_uid.get(uid) or False,
            "reason": False,
            "source": "tracking_backfill",
        })

    written = len(Custody.create(vals_list)) if vals_list else 0
    _logger.info(
        "myservice_asset_register: custody backfill on %s — %d tracking "
        "value(s) read, %d row(s) written (%d skipped: asset deleted, "
        "%d skipped: no custodian change).",
        cr.dbname, len(rows), written, skipped_missing_asset, skipped_no_change)
