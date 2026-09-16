"""Remove the test-suite residue from a register — dry run unless told otherwise.

    # what it WOULD do, changing nothing:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
      odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http \
      --http-port=8099 --gevent-port=8098 < scripts/remove_test_residue.py

    # to actually remove:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T \
      -e CADRA_APPLY=1 odoo \
      odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http \
      --http-port=8099 --gevent-port=8098 < scripts/remove_test_residue.py

WHAT THIS IS FOR
----------------
Handoff 24 §B measured what the suites wrote into `jaizbankplc`, a register
derived from a live client's data. Handoff 25 §A stopped it happening again.
This is the other half: what to do about what is already there.

THE FOUR RULES
--------------
1. **Dry run by default.** `CADRA_APPLY=1` is the only way through, and it is
   not the default on any host. A database marked `production` is refused
   outright before anything is even read.

2. **Only records that SELF-IDENTIFY.** A `pytest-*` or `H23 *` name, or
   `source = 'test'` on a custody row. Nothing is removed for looking recent
   or for sitting near something that is a fixture.

   The name match is `=like`, NOT `like`. **Odoo wraps a `like` value in
   `%...%`**, so `('name', 'like', 'H23%')` compiles to `name LIKE '%H23%%'`
   — a substring match that would claim a real asset called `PUMP-H23-4` as
   a fixture. Only `=like` passes the pattern through as written.

3. **STOP, never cascade.** The moment a fixture is attached to something
   that does not self-identify, the whole group is left alone and printed.

4. **The dry run MEASURES rather than predicts.** Every candidate that
   survives the rules above is actually unlinked inside a savepoint which is
   then rolled back, so the reported counts are the counts of deletions that
   really succeeded. The first version of this script predicted them from a
   model of the schema and **the model was backwards** — see below.

WHAT IT REFUSES, AND WHY EACH ONE IS NOT NEGOTIABLE
----------------------------------------------------
**An asset carrying ANY chain-of-custody row is not removable at all.**
`nrs.asset.custody.asset_id` is declared `ondelete='restrict'`
(`myservice_asset_register/models/asset_custody.py:93`, with a comment saying
"NOT cascade" in as many words) and `nrs.asset.custody.unlink()` raises
unconditionally. The first cut of this script asserted the opposite — that
Odoo "will happily ON DELETE CASCADE a fixture asset's custody rows out of
existence" — and classified 3,815 assets as removable on that basis, 352 of
them carrying custody rows the database would have refused to release. Under
`CADRA_APPLY=1` it would have raised on the first one and aborted mid-loop.
That is exactly why rule 4 exists: a script that predicts a deletion it has
never attempted is an instrument reporting on itself.

**An asset with an approved disposal is never removed**, even when its name
says `pytest-`. Disposal approval is not reversible by any action in this
system, and deleting the record is not a reversal — it is the same
fabrication one step further on. Report 24 made this call once already and
marked asset 8396 rather than pretending it away;
`scripts/mark_test_fixtures.py` is the right instrument for those.

**Anything a `request.request` points at is left alone.** Neither
`request.request.nrs_asset_id` nor `.generic_location_id` declares an
`ondelete`, so Odoo's default `set null` applies: deleting the fixture would
SUCCEED and silently blank the field on a real request, with nothing
recording that it happened. Report 24 measured 354 of 420 entries in the
PUBLIC homepage location dropdown as fixtures, so a member of the public
choosing one off that dropdown is not hypothetical.

**Custody rows are never removed on their own.** Append-only means
append-only, and the model enforces it.
"""
import os

APPLY = os.environ.get("CADRA_APPLY", "").strip() not in ("", "0", "false", "no")

#: What a fixture calls itself, as ANCHORED `=like` patterns (see rule 2).
#:
#: Enumerated from the register rather than guessed. `jaizbankplc` holds two
#: fixture families, not one: `pytest-*` (1,037 `pytest-tag`, 214 `pytest-grn`,
#: and twenty more shapes) and `idem-*` (`idem-asset-pytest-idem-asset-…`,
#: `idem-race-…`, `idem-test-pytest-idem-loc-…`) written by the idempotency
#: tests, which put their own prefix in FRONT of the `pytest-` one.
#:
#: That second family is why the anchoring had to be checked rather than
#: assumed in the other direction too: switching from `like` to `=like`
#: correctly stopped matching a real `PUMP-H23-4`, and simultaneously stopped
#: matching 201 assets that ARE fixtures. Both patterns are needed, and both
#: are anchored.
ASSET_PATTERNS = ("pytest-%", "idem-%", "H23 %")
LOCATION_PATTERNS = ("pytest-%", "idem-%")


def _name_domain(patterns):
    domain = ["|"] * (len(patterns) - 1)
    return domain + [("name", "=like", p) for p in patterns]


class _Rollback(Exception):
    """Raised to abandon a savepoint after a successful trial deletion."""


def trial_unlink(records):
    """Actually delete `records` inside a savepoint, then roll it back.

    Returns (ok, message). This is the whole of rule 4: the answer comes from
    the database refusing or not refusing, not from our reading of the
    schema.
    """
    try:
        with env.cr.savepoint():                     # noqa: F821 — odoo shell
            records.unlink()
            raise _Rollback()
    except _Rollback:
        return True, ""
    except Exception as exc:                         # noqa: BLE001
        # catch-all: reported, never swallowed. Any refusal the database or
        # the ORM raises is a reason this record stays, and the reason is
        # printed rather than summarised.
        return False, "%s: %s" % (type(exc).__name__, str(exc).strip()[:160])


# The class is read with SQL through the repo's own helper, and NOT with
# `ir.config_parameter.get_param`.
#
# This line used to be `ICP.get_param("cadra.database_class")`, which is the
# exact call handoff 25 had just finished proving unsafe — written INTO this
# script by the handoff that found the leak. `get_param` is `@ormcache`d per
# worker, and under the committed `workers = 2` it answered `"client"` for a
# database whose parameter row had been DELETED while a second worker
# answered `"test"` for the same instant. `myservice_nrs_base/
# database_class.py` carries the measurement.
#
# Everywhere else that mattered had already been moved off it. Here — the one
# guard standing between `CADRA_APPLY=1` and a real client's register — it
# survived, because nobody re-read the new script against the rule the same
# handoff had just written down.
from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    CLIENT, PRODUCTION, TEST, database_class)

db_class = database_class(env)                       # noqa: F821 — odoo shell
print("database   : %s" % env.cr.dbname)             # noqa: F821
print("class      : %s" % (db_class or "(not set)"))
print("mode       : %s" % ("APPLY — records will be deleted" if APPLY
                           else "DRY RUN — every deletion is attempted and "
                                "rolled back"))
print()

# Absent refuses, and that is a TIGHTENING over the first version, which
# refused only `production`.
#
# This script deletes rows from an asset register. An unmarked database is
# not a safe one, it is an unclassified one — and `cadra19`, `nrs19` and
# `gtb19` are all unmarked on this machine today, with `nrs19` holding a real
# NRS staff extract and eleven thousand assets. Letting the blank through
# would mean the one database nobody has thought about is the one the
# delete runs against without a word.
#
# `client` is allowed on purpose: `jaizbankplc` is marked `client` and is
# precisely the register this script was written to clean.
if db_class not in (TEST, CLIENT):
    print("REFUSED: this database's class is %s. Nothing was read or changed."
          % ("`%s`" % db_class if db_class else
             "NOT SET — an unclassified database, not a safe one"))
    print()
    print("This script deletes register rows. It runs only against a database")
    print("that has been classified `%s` or `%s`; `%s` and an absent or"
          % (TEST, CLIENT, PRODUCTION))
    print("unrecognised value both refuse.")
    print()
    print("If this database should be classified, classify it deliberately —")
    print("the command is printed by any refused test run, and the decision")
    print("belongs to whoever knows what is in here, not to this script.")
    raise SystemExit(1)

Asset = env["nrs.asset"].sudo()                      # noqa: F821
Custody = env["nrs.asset.custody"].sudo()            # noqa: F821
Location = env["generic.location"].sudo()            # noqa: F821
Request = env["request.request"].sudo()              # noqa: F821

# ── assets ───────────────────────────────────────────────────────────

fixtures = Asset.search(_name_domain(ASSET_PATTERNS))
print("fixture-named assets     : %d of %d in the register"
      % (len(fixtures), Asset.search_count([])))

candidates, refused = [], []
for asset in fixtures:
    links = Custody.search_count([("asset_id", "=", asset.id)])
    requests = Request.search_count([("nrs_asset_id", "=", asset.id)])
    if asset.disposal_approved_by:
        refused.append((asset, "carries an APPROVED disposal — not reversible; "
                               "mark it instead (scripts/mark_test_fixtures.py)"))
    elif links:
        refused.append((asset, "carries %d chain-of-custody row(s); "
                               "`asset_id` is ondelete=restrict and custody "
                               "is append-only, so the asset cannot be "
                               "released" % links))
    elif requests:
        refused.append((asset, "%d service request(s) point at it; the field "
                               "is `set null`, so removing it would silently "
                               "blank them" % requests))
    else:
        candidates.append(asset)

removable, blocked = [], []
for asset in candidates:
    ok, why = trial_unlink(asset)
    (removable if ok else blocked).append(asset if ok else (asset, why))

print("  removable (trial-deleted and rolled back) : %d" % len(removable))
print("  refused by the rules above                : %d" % len(refused))
print("  refused by the DATABASE on a trial delete  : %d" % len(blocked))
print()

_BY_REASON = {}
for asset, why in refused:
    _BY_REASON.setdefault(why.split(";")[0].split("—")[0].strip(), []).append(asset)
for why, group in sorted(_BY_REASON.items(), key=lambda kv: -len(kv[1])):
    print("REFUSED (%d): %s" % (len(group), why))
    for asset in group[:6]:
        print("    %-7s %s" % (asset.id, (asset.name or "")[:44]))
    if len(group) > 6:
        print("    ... and %d more" % (len(group) - 6))
print()
for asset, why in blocked[:10]:
    print("BLOCKED BY THE DATABASE: %-7s %-30s %s"
          % (asset.id, (asset.name or "")[:30], why))
if len(blocked) > 10:
    print("    ... and %d more" % (len(blocked) - 10))
if blocked:
    print()

# ── locations ────────────────────────────────────────────────────────

locs = Location.search(_name_domain(LOCATION_PATTERNS))
removable_asset_ids = {a.id for a in removable}
loc_candidates, loc_refused = [], []
for loc in locs:
    sited = Asset.search([("location_id", "=", loc.id)])
    stranded = sited.filtered(lambda a: a.id not in removable_asset_ids)
    requests = Request.search_count([("generic_location_id", "=", loc.id)])
    if stranded:
        loc_refused.append((loc, "holds %d asset(s) this script will not "
                                 "remove" % len(stranded)))
    elif requests:
        loc_refused.append((loc, "%d service request(s) are sited here; the "
                                 "field is `set null`, so removing it would "
                                 "silently blank them" % requests))
    else:
        loc_candidates.append(loc)

loc_removable, loc_blocked = [], []
for loc in loc_candidates:
    ok, why = trial_unlink(loc)
    (loc_removable if ok else loc_blocked).append(loc if ok else (loc, why))

print("fixture-named locations  : %d of %d in the register"
      % (len(locs), Location.search_count([])))
print("  removable (trial-deleted and rolled back) : %d" % len(loc_removable))
print("  refused by the rules above                : %d" % len(loc_refused))
print("  refused by the DATABASE on a trial delete  : %d" % len(loc_blocked))
for loc, why in loc_refused[:8]:
    print("    %-7s %-30s %s" % (loc.id, (loc.name or "")[:30], why))
if len(loc_refused) > 8:
    print("    ... and %d more" % (len(loc_refused) - 8))
for loc, why in loc_blocked[:8]:
    print("    BLOCKED %-7s %-28s %s" % (loc.id, (loc.name or "")[:28], why))
print()

# ── what is left behind, said out loud ───────────────────────────────

test_links = Custody.search_count([("source", "=", "test")])
all_requests = Request.search_count([])
print("LEFT IN PLACE, and this script will never remove them:")
print("  chain-of-custody rows `source: test` : %d  (append-only; the model "
      "refuses unlink outright)" % test_links)
print("  service requests                     : %d in total, of which the "
      "fixtures CANNOT BE IDENTIFIED" % all_requests)
print("      `request.request.name` is a sequence (`REQ-000692`), not a name "
      "the suite chooses,")
print("      so a test-created request self-identifies by nothing at all. "
      "Report 24 counted one")
print("      per session. This script does not guess at them, and no rule "
      "here could.")
print()

if not APPLY:
    print("DRY RUN — every deletion above was attempted inside a savepoint and "
          "rolled back. Nothing changed.")
    print("Re-run with CADRA_APPLY=1 to remove %d asset(s) and %d location(s)."
          % (len(removable), len(loc_removable)))
    raise SystemExit(0)

deleted_assets = deleted_locs = 0
for asset in removable:
    ok, why = trial_unlink(asset)
    if not ok:
        print("SKIPPED %s: %s" % (asset.id, why))
        continue
    asset.unlink()
    deleted_assets += 1
for loc in loc_removable:
    ok, why = trial_unlink(loc)
    if not ok:
        print("SKIPPED location %s: %s" % (loc.id, why))
        continue
    loc.unlink()
    deleted_locs += 1
env.cr.commit()                                      # noqa: F821
print("removed %d asset(s) and %d location(s); committed."
      % (deleted_assets, deleted_locs))
print("%d asset(s) refused by the rules and %d by the database remain."
      % (len(refused), len(blocked)))
