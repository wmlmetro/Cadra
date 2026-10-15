"""Mark the test-suite artefacts sitting in a tenant's register for what they are.

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
      odoo shell -c /etc/odoo/odoo.conf -d jaizbankplc \
      --http-port=8099 --gevent-port=8098 --no-http \
      < scripts/mark_test_fixtures.py

WHY THIS EXISTS
---------------
Handoff 24 §B measured what a test run writes and into which database. The
answer, on this machine:

  * The HTTP suite runs against whatever `CADRA_API_BASE` names, and the only
    tenant carrying a full `CLIENT_ID`/`CLIENT_SECRET` pair is `jaizbankplc` —
    a replica of a live client's register. There is no guard of any kind: no
    allowlist, no refusal, no confirmation. The suite reads one environment
    variable and writes wherever it points.
  * It has no teardown, by documented policy, and it could not have one: the
    API publishes exactly one DELETE route (asset categories) and none for
    assets, locations, requests, custody links or disposals.
  * Measured by handoff 24 on 2026-09-15: 3,584 of 4,056 assets (88%) named
    `pytest-*`, accumulating daily since 2026-08-26; 413 of 569
    chain-of-custody rows on fixture assets; 354 of 420 entries in the PUBLIC
    homepage location dropdown; and six fabricated approved disposals sitting
    in the auditor-facing disposal report.
  * **Re-measured later the same day, after handoff 26's own verification
    runs: 3,894 of 4,164 assets, 435 of 591 custody rows, 368 of 440 dropdown
    entries.** Every one of those figures went UP between two measurements
    taken hours apart, because nothing stopped the accumulation until handoff
    25 landed the database-class guard. Quote these with the date attached or
    do not quote them — a fixture count is a rate, not a constant.

No real asset carries a fabricated approval or a fabricated custody link, and
nothing ever reached the production host — every captured response in
`docs/api/test-responses/` names `jaizbankplc.localhost:8069`.

WHAT THIS SCRIPT DOES, AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------------
It does four things, in this order, and refuses outright on a database
classified `production` or on one carrying no class at all.

1. Sets `is_test_credential` on the `Handoff23 Approver` client. The repo
   already has the right convention for this — `myservice.api.client.
   is_test_credential` drives `nrs.asset.custody.source = 'test'`, so links
   written under a test credential say so on their face. The custody chain is
   honest because of it: 352 of its rows self-label. That credential was
   created with the flag off, which is why the approvals it authorised are the
   one class of artefact a reader cannot identify from the record itself.

2. Appends a disclosure to the `disposal_reason` of every fabricated approved
   disposal, so the auditor-facing disposal report shows them for what they
   are rather than listing them beside real ones.

3. **Marks, on their NAME, the fixtures that cannot be removed** (handoff 26
   §D). `scripts/remove_test_residue.py` refuses three groups permanently and
   correctly — assets pinned by an append-only record (append-only, and
   `ondelete='restrict'` means the database refuses too), assets carrying an
   approved disposal, and the assets and locations a REAL service request
   points at (whose foreign keys are `set null`, so deleting the fixture
   would succeed while silently blanking a live request's field). The first
   group was one model when this was written and is now FOUR, each counted
   and printed under its own name: `nrs.asset.custody` (who held it),
   `nrs.asset.movement` (where it has been, handoff 28), `nrs.asset.event`
   (that it was verified, changed status or had a GRN, PO or SAP reference
   changed, handoff 30) and `nrs.asset.change.request` (who asked to move it
   or hand it over, and who agreed, handoff 35). The fourth is NOT
   append-only — it is a state machine — but it pins an asset for the same
   two reasons: `asset_id` is `ondelete='restrict'` and `unlink` refuses
   unconditionally, in every state, a withdrawn request included. Those
   records stay. What changes is that they stop looking like register data:
   a ` [TEST FIXTURE]` suffix goes on the name, which is the field every list
   view, every report and the public homepage dropdown already renders.

4. **Reports what is left unidentifiable, in words rather than as a zero.**
   Chiefly the service requests: `request.request.name` is a sequence, so a
   test-created request never was distinguishable from a real one and cannot
   be made so now.

**The name mark is NOT the same claim as `is_test_fixture`.** That field
(handoff 26 §A, `myservice_api/models/test_fixture.py`) is DERIVED from the
acting credential at creation and is certain. This mark is applied by
matching a name CONVENTION and is only ever as good as the convention was.
Everything created before handoff 26 under no convention — every one of the
460 requests on `jaizbankplc` — is unidentifiable permanently, by this or by
anything else.

**It does not un-approve anything, and that is deliberate.** Disposal approval
is not reversible by any action in this system: there is no
`action_unapprove_disposal`, a second approval is a published 409, the
approver fields are read-only over the API, and the button hides itself once
an approver exists. It is correctable only by a human on the Odoo form, where
`disposal_approved_by` is tracked and the correction leaves a trail — which is
the design `asset_disposal.py` argues for explicitly: "a genuine correction is
made on the form and leaves a trail; a button that quietly replaces one name
with another does not."

Fabricating a reversal would be the same defect as the fabricated approval,
one step further on. Marking is the honest answer; erasing is not.

Re-running is safe: every change is idempotent — the disclosure and the name
mark are both applied only where absent. Re-run it after handoff
25 even if you ran it before — the credential half silently did nothing
on any tenant where that credential is archived, which is every tenant
measured so far.
"""


# The class is read with SQL through the repo's own helper, NOT through
# `ir.config_parameter.get_param`, which is `@ormcache`d per worker and has
# already answered this exact question wrongly once — see
# `myservice_nrs_base/database_class.py` for the measurement.
#
# This script WRITES to a register. `production` refuses, and so does an
# absent class: an unmarked database is not a safe one, it is one nobody has
# classified, and `cadra19` / `nrs19` / `gtb19` are all unmarked on this
# machine today. `client` is allowed because `jaizbankplc` is marked `client`
# and is the register this was written for.
from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    CLIENT, PRODUCTION, TEST, database_class)

_db_class = database_class(env)                      # noqa: F821 — odoo shell
print("database : %s" % env.cr.dbname)               # noqa: F821
print("class    : %s" % (_db_class or "(not set)"))
print()
if _db_class not in (TEST, CLIENT):
    print("REFUSED: this database's class is %s. Nothing was read or changed."
          % ("`%s`" % _db_class if _db_class else
             "NOT SET — an unclassified database, not a safe one"))
    print("This script writes disclosures into a register. It runs against a")
    print("database classified `%s` or `%s`; `%s` and an absent or"
          % (TEST, CLIENT, PRODUCTION))
    print("unrecognised value both refuse.")
    raise SystemExit(1)

DISCLOSURE = (
    "[TEST FIXTURE — not a real disposal. Created by the automated test "
    "suite against a development replica; the approval is a fixture and "
    "authorises nothing. Disclosed in handoff 24.]"
)

#: Appended to the NAME of a fixture that cannot be removed, so a reader of
#: the register sees what it is without consulting a script. The name is the
#: right place precisely because it is the field every list view, every
#: report and the PUBLIC homepage dropdown already renders.
NAME_MARK = " [TEST FIXTURE]"

#: These MUST match `scripts/remove_test_residue.py`, and
#: `tests/test_fixture_patterns_agree.py` fails if they drift. Two scripts
#: disagreeing about what a fixture looks like is how one of them marks a
#: record the other then deletes, or worse, the reverse.
#:
#: `=like`, never `like`. **Odoo wraps a `like` value in `%...%`**, so
#: `('name', 'like', 'H23 %')` compiles to `name LIKE '%H23 %%'` — a
#: substring match that would claim a real `PUMP-H23-4` as a fixture. This
#: script's disposal search carried exactly that bug until handoff 26: its
#: sibling documented the trap as rule 2 and this half was never brought in
#: line.
ASSET_PATTERNS = ("pytest-%", "idem-%", "H23 %")
LOCATION_PATTERNS = ("pytest-%", "idem-%")


def _name_domain(patterns):
    domain = ["|"] * (len(patterns) - 1)
    return domain + [("name", "=like", p) for p in patterns]


Client = env['myservice.api.client'].sudo()          # noqa: F821 — odoo shell
# `cadra_candidates`: receipt candidates (handoff 57) are records too.
Asset = env['nrs.asset'].sudo().with_context(cadra_candidates=True)                      # noqa: F821
Custody = env['nrs.asset.custody'].sudo()            # noqa: F821
# The second append-only pin (handoff 28) — see `remove_test_residue.py`,
# which refuses on it; the two scripts must agree about what stays.
Movement = (env['nrs.asset.movement'].sudo()         # noqa: F821
            if 'nrs.asset.movement' in env else None)  # noqa: F821
# The third (handoff 30). It pins an asset that has been verified, has
# changed `state`, or has had `grn_reference`, `purchase_order_reference` or
# `sap_asset_number` changed — NOT every asset, because an event is a change
# and an asset's opening values write none. `remove_test_residue.py` refuses
# on it by name, so it is counted here by name: a fixture that script will
# not delete and this one does not mark is one that stays in the register
# looking like data.
Event = (env['nrs.asset.event'].sudo()               # noqa: F821
         if 'nrs.asset.event' in env else None)      # noqa: F821
# The fifth (handoff 61 §5): a photo of the asset. Append-only, `asset_id`
# `ondelete='restrict'`, never deleted — superseded instead.
# `remove_test_residue.py` refuses on it by name, so it is counted here.
Photo = (env['nrs.asset.photo'].sudo()               # noqa: F821
         if 'nrs.asset.photo' in env else None)      # noqa: F821
Location = env['generic.location'].sudo()            # noqa: F821
Request = env['request.request'].sudo()              # noqa: F821

# ── 1 · the credential ───────────────────────────────────────────────
#
# `active_test=False`, and it is not a detail: on `jaizbankplc` this
# credential is ARCHIVED, so the plain `search()` this line used to carry
# returned an EMPTY recordset, the loop below never ran, and the script
# printed nothing whatsoever about the credential while reporting success on
# the disposals. It looked like a clean run. Handoff 25 found it by checking
# the database afterwards rather than reading the output.
#
# An archived credential's artefacts are still artefacts, which is exactly
# why `myservice.api.client._is_test_credential_user` searches the same way.
print("1 · the credential that authorised the fabricated approvals")
approver = Client.with_context(active_test=False).search([
    ('name', '=', 'Handoff23 Approver'),
])
if not approver:
    # Says so, rather than succeeding silently. A step that can do nothing
    # without a word is how the first version of this passed for a full run.
    print("  NOTE: no client named 'Handoff23 Approver' on this database — "
          "nothing to flag. If you expected one, check the name.")
for client in approver:
    if not client.is_test_credential:
        client.write({'is_test_credential': True})
        print("  marked credential %r (%s, active=%s) as a test credential"
              % (client.name, client.client_id, client.active))
    else:
        print("  credential %r already marked" % client.name)
print()

# ── 2 · the fabricated approved disposals ────────────────────────────

print("2 · fabricated approved disposals")
fixtures = Asset.search(
    [('disposal_approved_by', '!=', False)] + _name_domain(ASSET_PATTERNS))
print("  found: %d" % len(fixtures))
if not fixtures:
    print("  NOTE: none on this database. Handoff 24 measured six on "
          "`jaizbankplc`; if you expected them, check the tenant.")
for asset in fixtures:
    reason = asset.disposal_reason or ''
    if DISCLOSURE in reason:
        print("  %-6s %-32s already disclosed" % (asset.id, asset.name[:32]))
        continue
    asset.write({'disposal_reason': (reason + '\n' + DISCLOSURE).strip()})
    print("  %-6s %-32s marked (approver %s)"
          % (asset.id, asset.name[:32], asset.disposal_approved_by.login))
print()

# ── 3 · the fixtures that CANNOT be removed, marked instead ──────────
#
# Handoff 26 §D. `scripts/remove_test_residue.py` measured three groups it
# refuses to delete, and every refusal is permanent and correct:
#
#   * assets carrying a chain-of-custody row — `asset_id` is
#     `ondelete='restrict'` and `custody.unlink()` raises unconditionally.
#     Append-only is the property the whole chain is worth having for, and
#     carving one exception for tidiness is how it stops meaning anything.
#     The same two facts hold, word for word, of a movement record
#     (`nrs.asset.movement`, handoff 28), of an event record
#     (`nrs.asset.event`, handoff 30) and of an approval request
#     (`nrs.asset.change.request`, handoff 35 — a state machine rather than
#     an append-only row, but `ondelete='restrict'` and `unlink` refuses in
#     every state), and the removal script refuses on each BY NAME. One group
#     in this list, four models under it.
#   * assets and locations a real service request points at — neither
#     `nrs_asset_id` nor `generic_location_id` declares an `ondelete`, so the
#     default `set null` applies and deleting the fixture would SUCCEED while
#     silently blanking a live request's field.
#   * assets carrying an approved disposal — handled in §2 above.
#
# They stay. What changes is that they stop looking like register data. The
# mark goes on the NAME because that is the field a reader actually sees —
# including the member of the public choosing off the homepage dropdown, of
# whose 420 entries report 24 measured 354 as fixtures.
#
# This is NOT the same claim as `is_test_fixture`, and the difference
# matters. That field is DERIVED from the credential at creation and is
# certain; this mark is applied by matching a NAME CONVENTION and is only as
# good as the convention was. Everything created before handoff 26 that
# carried no convention — every one of the 460 service requests — cannot be
# marked by this or by anything else, ever.

print("3 · fixtures that cannot be removed — marked on their face")


def _mark_names(records, label):
    marked = already = 0
    for record in records:
        name = record.name or ''
        if NAME_MARK in name:
            already += 1
            continue
        record.write({'name': name + NAME_MARK})
        marked += 1
    print("  %-46s marked %4d, already marked %4d"
          % (label, marked, already))
    return marked, already


fixture_assets = Asset.search(_name_domain(ASSET_PATTERNS))
fixture_locs = Location.with_context(active_test=False).search(
    _name_domain(LOCATION_PATTERNS))
print("  fixture-named assets in the register    : %d of %d"
      % (len(fixture_assets), Asset.search_count([])))
print("  fixture-named locations in the register : %d of %d"
      % (len(fixture_locs),
         Location.with_context(active_test=False).search_count([])))

held_by_custody = fixture_assets.filtered(
    lambda a: Custody.search_count([('asset_id', '=', a.id)]))
held_by_movement = fixture_assets.filtered(
    lambda a: Movement is not None
    and Movement.search_count([('asset_id', '=', a.id)]))
held_by_event = fixture_assets.filtered(
    lambda a: Event is not None
    and Event.search_count([('asset_id', '=', a.id)]))
held_by_photo = fixture_assets.filtered(
    lambda a: Photo is not None
    and Photo.search_count([('asset_id', '=', a.id)]))
held_by_request = fixture_assets.filtered(
    lambda a: Request.search_count([('nrs_asset_id', '=', a.id)]))
held_by_disposal = fixture_assets.filtered(lambda a: a.disposal_approved_by)
unremovable_assets = (held_by_custody | held_by_movement | held_by_event
                      | held_by_photo | held_by_request | held_by_disposal)

# A fixture LOCATION stays for a different reason than report 25 recorded.
#
# That report wrote "10 assets a service request points at, and 17 locations
# likewise". The 17 is right and the "likewise" is not: measured on
# `jaizbankplc` on 2026-09-15, **zero** requests on that tenant set
# `generic_location_id` at all. All 17 are refused by the removal script's
# OTHER location rule — they hold an asset the script will not remove.
#
# Which rule holds that asset, measured over exactly those 17 pairs in the
# script's own elif-chain order: **10 because a service request points at the
# ASSET, 5 because the asset carries an approved disposal, 2 because of a
# custody row.** Disjoint, summing to 17.
#
# The script was right and the sentence describing it was not — and handoff
# 26's FIRST correction of that sentence, written on this line, was also
# wrong: it said all 17 were pinned by custody rows, which is 2 of them.
# Both errors are the same shape as everything else this handoff is about,
# one level up: a claim ABOUT the code, asserted without measuring.
#
# Both rules are applied here anyway. The request rule is empty on this
# tenant and is not empty by construction, and a marking step that quietly
# depends on one tenant's data is the thing report 25's §2 was about.
_fixture_asset_ids = set(fixture_assets.ids)
_unremovable_asset_ids = set(unremovable_assets.ids)


def _asset_stays(asset):
    """Would the removal script leave this asset in the register?

    Two ways to stay: it is not a fixture at all, or it is one of the
    fixtures that cannot be released (a custody, movement or event row, an
    approved disposal, a request pointing at it). Either way the location
    holding it cannot go.
    """
    return (asset.id not in _fixture_asset_ids
            or asset.id in _unremovable_asset_ids)


locs_holding_a_survivor = fixture_locs.filtered(
    lambda loc: any(_asset_stays(asset) for asset
                    in Asset.search([('location_id', '=', loc.id)])))
locs_held_by_request = fixture_locs.filtered(
    lambda loc: Request.search_count([('generic_location_id', '=', loc.id)]))
unremovable_locs = locs_holding_a_survivor | locs_held_by_request

if not unremovable_assets and not unremovable_locs:
    # A zero here is legitimate ONLY on a register the removal script has
    # already cleaned, or one the suite never ran against. It is said out
    # loud either way, because "nothing to mark" and "nothing was looked at"
    # print identically when nobody writes the line.
    print("  NOTE: no unremovable fixture found. On `jaizbankplc` handoff 25 "
          "measured 99 + 10 assets and 17 locations; if you expected those, "
          "check the tenant and the patterns above.")

_mark_names(unremovable_assets, "assets that cannot be removed (all reasons)")
# Five reasons, not three. This line named custody, request and disposal
# only, and had already been wrong by omission since handoff 28 added
# movement to the union above without adding it here — so an asset held
# ONLY by a movement record was in the total and in none of the parts, with
# nothing on the page to say why. Every member of the union is printed now.
# They overlap; do not add them up.
print("    of which: %d hold a custody row, %s, %s,"
      % (len(held_by_custody),
         ("%d hold a movement record" % len(held_by_movement)
          if Movement is not None
          else "movement n/a (`nrs.asset.movement` not installed)"),
         ("%d hold an event record" % len(held_by_event)
          if Event is not None
          else "event n/a (`nrs.asset.event` not installed)")))
print("              %s, %d are pointed at by a request, %d carry an "
      "approved disposal (the six overlap)"
      % (("%d hold a photo" % len(held_by_photo)
          if Photo is not None
          else "photo n/a (`nrs.asset.photo` not installed)"),
         len(held_by_request), len(held_by_disposal)))
_mark_names(locs_holding_a_survivor, "locations holding an asset that stays")
_mark_names(locs_held_by_request, "locations a service request points at")
print()

# ── 4 · what is left unmarked, said in words rather than counted as 0 ─

print("4 · what remains unidentifiable, and why")

requests_total = Request.search_count([])
requests_labelled = Request.search_count([('is_test_fixture', '=', True)])
print("  service requests on this database        : %d" % requests_total)
print("  of those, self-labelled (`is_test_fixture`): %d" % requests_labelled)
print("  UNIDENTIFIABLE, PERMANENTLY               : %d"
      % (requests_total - requests_labelled))
print("    `request.request.name` is a SEQUENCE (REQ-000692), so a")
print("    test-created request has never been distinguishable from a real")
print("    one by any rule a script can apply. `is_test_fixture` closes this")
print("    going FORWARD only — it is derived at creation and cannot be")
print("    reconstructed for a record created before it existed.")
print()

unmarked_assets = Asset.search_count([]) - len(fixture_assets)
print("  assets carrying NO fixture name          : %d" % unmarked_assets)
print("    Some of these are real and some are fixtures the suite wrote")
print("    before it used a prefix. Nothing can tell them apart now.")
print()

# Public reachability, measured rather than asserted. `/api/myservice/
# form-data` (auth='public') returns every ACTIVE location, and the security
# incident form lists them unfiltered — so an unmarked fixture location is
# something a member of the public can still choose.
public_locs = Location.search_count([('active', '=', True)])
public_fixture_locs = Location.search_count(
    [('active', '=', True)] + _name_domain(LOCATION_PATTERNS))
# A DELIBERATE substring match, and it spells its own wildcards. `=like`
# with explicit `%` on both sides says "contains" in the code; bare `like`
# would mean the same thing to Odoo while looking like an anchored match,
# which is the confusion that put a substring match into the disposal search
# and left it there for two handoffs.
_marked_public = Location.search_count(
    [('active', '=', True),
     ('name', '=like', '%' + NAME_MARK.strip() + '%')]
    + _name_domain(LOCATION_PATTERNS))
still_unmarked_public = public_fixture_locs - _marked_public
print("  PUBLIC homepage location dropdown        : %d entries"
      % public_locs)
print("    of those, fixture-named                : %d" % public_fixture_locs)
print("    fixture-named and STILL UNMARKED       : %d"
      % still_unmarked_public)
print("    A fixture location left unmarked is one a member of the public")
print("    can pick off `/api/myservice/form-data` and file a real request")
print("    against. The ones above that this script did not mark are the")
print("    ones `scripts/remove_test_residue.py` can actually DELETE —")
print("    run it, or re-run this with the marking widened.")
print()

env.cr.commit()                                      # noqa: F821 — odoo shell
print("committed")
