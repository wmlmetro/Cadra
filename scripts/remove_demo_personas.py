"""Take every demo persona off this tenant — and nothing else.

Handoff 46: "at go-live these must come off a live client tenant, and the way
that happens must exist before they go on." This is that way.

    scripts/demo_personas.sh <db> remove            # what it WOULD do
    scripts/demo_personas.sh <db> remove --apply    # do it

WHAT IT TOUCHES
---------------
Only records `seed_demo_personas.py` claimed under `__cadra_demo__.*`, and
only when every mark agrees: a persona must still be a `res.users` on the
`demo.example` domain whose partner is labelled `is_test_fixture`; the
seeding credential must still be `cadra_demo_personas`, flagged test and
archived. A claimed record whose marks disagree is REFUSED by name and left
exactly as it is — something has changed it, and deleting it on the
strength of one mark is how a real account would go. An account on the demo
domain that this file never claimed is reported and never touched.

DELETE, OR ARCHIVE
------------------
A persona is deleted when nothing pins it. Something can: a move request
names its requester, its approver and its decider with `ondelete='restrict'`
(handoff 35), and that request is a record of what was asked and decided,
so it is not this script's to delete. Such a persona is ARCHIVED instead —
it can no longer sign in, it stays on the record that names it — and the
output says which and why. What decides is a trial: every delete is
performed inside a savepoint first, in the dry run as well, so the dry run's
answer is the database's answer and not a prediction.

The dry run changes nothing. The class guard accepts `test`, `client` and
`production` — the last because removal is precisely what a live tenant
needs at go-live — and refuses an unclassified database.
"""
import os

from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    CLIENT, PRODUCTION, TEST, database_class)

#: Shared with seed_demo_personas.py and list_demo_personas.py;
#: `tests/test_demo_personas_agree.py` fails if the three disagree.
XMLID_MODULE = "__cadra_demo__"
EMAIL_DOMAIN = "demo.example"
SEEDER_CLIENT_ID = "cadra_demo_personas"

APPLY = os.environ.get("CADRA_APPLY", "").strip() not in ("", "0", "false", "no")

db_class = database_class(env)  # noqa: F821 — odoo shell
print("database   : %s" % env.cr.dbname)  # noqa: F821
print("class      : %s" % (db_class or "(not set)"))
print("mode       : %s" % ("APPLY — personas will be removed" if APPLY
                           else "DRY RUN — nothing will change"))
if db_class not in (TEST, CLIENT, PRODUCTION):
    print("REFUSED: this database's class is %s. Nothing was read or changed."
          % (db_class or "not set"))
    raise SystemExit(1)

Data = env["ir.model.data"].sudo()  # noqa: F821
Users = env["res.users"].sudo().with_context(active_test=False)  # noqa: F821
Client = env["myservice.api.client"].sudo().with_context(  # noqa: F821
    active_test=False)


class _Rollback(Exception):
    pass


def trial_unlink(records):
    """Delete inside a savepoint and undo it: the database's own answer."""
    try:
        with env.cr.savepoint():  # noqa: F821
            records.unlink()
            raise _Rollback()
    except _Rollback:
        return True, ""
    except Exception as exc:  # catch-all: reported — the refusal IS the answer, printed per record
        return False, "%s: %s" % (type(exc).__name__,
                                  " ".join(str(exc).split())[:160])


def count_users():
    return Users.search_count([]), Users.search_count(
        [("login", "=like", "%@" + EMAIL_DOMAIN)])


before_all, before_demo = count_users()
print("accounts   : %d, of which on @%s: %d" % (before_all, EMAIL_DOMAIN,
                                               before_demo))

rows = Data.search([("module", "=", XMLID_MODULE)])
personas, refused, seeder_rows = [], [], []
for row in rows:
    if row.name.startswith("persona_"):
        user = Users.browse(row.res_id).exists() if row.model == "res.users" else None
        if not user:
            refused.append("%s: claimed, but the record is gone or not an "
                           "account (%s %s)" % (row.name, row.model, row.res_id))
            continue
        if (not user.login.endswith("@" + EMAIL_DOMAIN)
                or not user.partner_id.is_test_fixture):
            refused.append("%s: user %s (%s) no longer carries every mark "
                           "(fixture=%s) — left alone"
                           % (row.name, user.id, user.login,
                              user.partner_id.is_test_fixture))
            continue
        personas.append((row, user))
    else:
        seeder_rows.append(row)

unclaimed = Users.search([("login", "=like", "%@" + EMAIL_DOMAIN),
                          ("id", "not in", [u.id for _r, u in personas])])

#: The asset's append-only records name their actor with `ondelete='set
#: null'`: a persona who verified, moved or handed over an asset would pass
#: the trial delete, and PostgreSQL would then blank the actor on rows whose
#: whole value is that nobody rewrites them (the `*_name` snapshot survives,
#: the link does not). So a persona named on any of them is archived, like
#: one a move request pins. Found by handoff 46's verification pass.
ACTOR_FIELDS = (
    ("nrs.asset.event", "actor_id", "event"),
    ("nrs.asset.movement", "moved_by_id", "movement"),
    ("nrs.asset.custody", "changed_by_id", "custody"),
)


def named_on_history(user):
    for model, field, label in ACTOR_FIELDS:
        Model = env.get(model)  # noqa: F821
        if Model is None:
            continue
        n = Model.sudo().search_count([(field, "=", user.id)])
        if n:
            return "named as the actor on %d %s row(s) (%s)" % (n, label, model)
    return ""


plan_delete, plan_archive = [], []
for row, user in personas:
    partner = user.partner_id
    why = named_on_history(user)
    ok = not why
    if ok:
        ok, why = trial_unlink(user | Users.browse())
    if ok:
        plan_delete.append((row, user, partner))
        print("  delete   %-36s %s" % (user.login, user.name))
    else:
        plan_archive.append((row, user, why))
        print("  ARCHIVE  %-36s %s — cannot be deleted: %s"
              % (user.login, user.name, why))
for line in refused:
    print("  REFUSED  %s" % line)
for user in unclaimed:
    print("  untouched: %s (id %s) is on @%s but was not created by the seed"
          % (user.login, user.id, EMAIL_DOMAIN))

# The seeding credential and its user go last, and only once no persona
# remains that it created — an archived persona keeps its creator.
# Each by its own name and checked against the other, never "every claimed
# row of that model": one edited `ir.model.data` row must not be enough to
# delete an account (handoff 46's verification pass).
by_name = {r.name: r for r in seeder_rows}
seeder = (Client.browse(by_name["seeder_client"].res_id).exists()
          if "seeder_client" in by_name
          and by_name["seeder_client"].model == "myservice.api.client"
          else Client.browse())
seeder_user = (Users.browse(by_name["seeder_user"].res_id).exists()
               if "seeder_user" in by_name
               and by_name["seeder_user"].model == "res.users"
               else Users.browse())
stray = [r.name for r in seeder_rows if r.name not in ("seeder_client", "seeder_user")]
for name in stray:
    print("  REFUSED  %s.%s is not a name the seed writes — left alone"
          % (XMLID_MODULE, name))
remove_seeder = bool(seeder) and not plan_archive and not refused and not stray
if seeder and (seeder.client_id != SEEDER_CLIENT_ID
               or not seeder.is_test_credential or seeder.active
               or seeder.client_secret_hash):
    print("  REFUSED  seeding credential %s no longer looks inert — left "
          "alone" % seeder.client_id)
    remove_seeder = False
expected_login = "cadra_client_%s" % SEEDER_CLIENT_ID
if seeder_user and (seeder_user != seeder.user_id
                    or seeder_user.login != expected_login):
    print("  REFUSED  the claimed seeding user %s (%s) is not the seeding "
          "credential's own user — left alone" % (seeder_user.id,
                                                 seeder_user.login))
    seeder_user = Users.browse()
    remove_seeder = False
if seeder:
    print("  %s seeding credential %s and its user"
          % ("delete  " if remove_seeder else "keep    ", SEEDER_CLIENT_ID))

if not APPLY:
    print()
    print("DRY RUN — would delete %d, archive %d, refuse %d. Nothing changed. "
          "Re-run with --apply." % (len(plan_delete), len(plan_archive),
                                    len(refused)))
    raise SystemExit(0)

for row, user, partner in plan_delete:
    user.unlink()
    # The partner outlives its user in Odoo; it is the persona's too, and
    # labelled. Kept if anything still names it.
    ok, _why = trial_unlink(partner)
    if ok:
        partner.unlink()
    row.exists().unlink()
for row, user, _why in plan_archive:
    user.write({"active": False})
if remove_seeder:
    seeder.unlink()
    for user in seeder_user:
        partner = user.partner_id
        user.unlink()
        if trial_unlink(partner)[0]:
            partner.unlink()
    by_name["seeder_client"].exists().unlink()
    if "seeder_user" in by_name:
        by_name["seeder_user"].exists().unlink()
env.cr.commit()  # noqa: F821
env.registry.signal_changes()  # noqa: F821

after_all, after_demo = count_users()
print()
print("APPLIED — deleted %d, archived %d, refused %d." % (
    len(plan_delete), len(plan_archive), len(refused)))
print("accounts   : %d → %d, of which on @%s: %d → %d (archived ones remain, "
      "unable to sign in)" % (before_all, after_all, EMAIL_DOMAIN,
                              before_demo, after_demo))
