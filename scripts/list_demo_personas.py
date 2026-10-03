"""Which accounts on this tenant are demo accounts? — one command, read-only.

Handoff 46. Answers the question without reading the seed: every account on
the tenant is classified by the three marks `seed_demo_personas.py` puts on
a persona, and an account carrying SOME of them but not all is named, because
that is the case a reader needs to see.

    scripts/demo_personas.sh <db> list

Reads only. Runs on a database of any class, unclassified included — a
question about what is there must be answerable everywhere, and asking it
changes nothing.
"""
from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    database_class)

#: Shared with seed_demo_personas.py and remove_demo_personas.py;
#: `tests/test_demo_personas_agree.py` fails if the three disagree.
XMLID_MODULE = "__cadra_demo__"
EMAIL_DOMAIN = "demo.example"
SEEDER_CLIENT_ID = "cadra_demo_personas"

ROLE_XMLIDS = (
    ("asset_user", "myservice_asset_register.group_asset_user"),
    ("asset_manager", "myservice_asset_register.group_asset_manager"),
    ("tag_issuing_unit", "myservice_asset_register.group_tag_issuing_unit"),
    ("auditor", "myservice_api.group_auditor"),
    ("system", "base.group_system"),
)

db_class = database_class(env)  # noqa: F821 — odoo shell
print("database   : %s" % env.cr.dbname)  # noqa: F821
print("class      : %s" % (db_class or "(not set)"))

Users = env["res.users"].sudo().with_context(active_test=False)  # noqa: F821
Data = env["ir.model.data"].sudo()  # noqa: F821
Employee = env["hr.employee"].sudo().with_context(  # noqa: F821
    active_test=False)

claimed = Data.search([("module", "=", XMLID_MODULE),
                       ("model", "=", "res.users")])
claimed_ids = {row.res_id: row.name for row in claimed}
on_domain = Users.search([("login", "=like", "%@" + EMAIL_DOMAIN)])
labelled = Users.search([("partner_id.is_test_fixture", "=", True)])

all_users = Users.search([])
people = all_users.filtered(lambda u: not u.share)
installed = [(key, x) for key, x in ROLE_XMLIDS
             if env.ref(x, raise_if_not_found=False)]  # noqa: F821


def roles_of(user):
    return " + ".join(key for key, x in installed if user.has_group(x)) or "-"


personas = Users.browse([uid for uid, name in claimed_ids.items()
                         if name.startswith("persona_")]).exists()
print()
print("DEMO ACCOUNTS (all three marks: %s.persona_*, @%s, is_test_fixture)"
      % (XMLID_MODULE, EMAIL_DOMAIN))
print("  %-15s %-36s %-20s %-6s %-26s %s"
      % ("persona", "login", "name", "active", "roles", "last sign-in"))
complete = Users.browse()
for user in personas.sorted("login"):
    marks_ok = (user.login.endswith("@" + EMAIL_DOMAIN)
                and user.partner_id.is_test_fixture)
    if marks_ok:
        complete |= user
    print("  %-15s %-36s %-20s %-6s %-26s %s%s"
          % (claimed_ids[user.id][len("persona_"):], user.login, user.name,
             "yes" if user.active else "no", roles_of(user),
             user.login_date or "never",
             "" if marks_ok else "   <-- MARKS DISAGREE"))
if not personas:
    print("  (none)")

# Anything carrying one mark without the others is the case to look at.
partial = (on_domain | Users.browse(list(claimed_ids))) - complete
partial = partial.exists().filtered(
    lambda u: claimed_ids.get(u.id) != "seeder_user")
print()
print("ON THE DEMO DOMAIN OR CLAIMED, BUT NOT ALL THREE MARKS: %d" % len(partial))
for user in partial:
    print("  id %-6s %-36s fixture=%s claimed=%s"
          % (user.id, user.login, user.partner_id.is_test_fixture,
             claimed_ids.get(user.id, "no")))

seeder = Data.search([("module", "=", XMLID_MODULE),
                      ("name", "=", "seeder_client")], limit=1)
print()
print("seeding credential        : %s"
      % ("%s (archived, inert)" % SEEDER_CLIENT_ID if seeder else "absent"))
print()
print("ACCOUNTS ON THIS TENANT")
print("  all accounts (any state)          : %d" % len(all_users))
print("  of which internal (not portal)    : %d" % len(people))
print("  of which demo personas            : %d" % len(complete))
print("  of which labelled is_test_fixture : %d   (demo personas + accounts "
      "the test suites created)" % len(labelled))
# The seeding credential's own user is created by the superuser (client
# provisioning), so it carries no label of its own; its credential does.
seeder_user = Users.browse([uid for uid, name in claimed_ids.items()
                            if name == "seeder_user"]).exists()
print("  of which the seeding credential   : %d   (cadra_client_%s; "
      "labelled through its credential)" % (len(seeder_user), SEEDER_CLIENT_ID))
print("  real-looking (internal, unlabelled): %d"
      % len(people - labelled - seeder_user))
print()
print("EMPLOYEES — a persona is never one")
print("  employees (any state)             : %d" % Employee.search_count([]))
print("  linked to a demo persona          : %d"
      % Employee.search_count([("user_id", "in", complete.ids)]))
print("  carrying a persona's name         : %d" % sum(
    Employee.search_count([("name", "=ilike", u.name)]) for u in complete))

# What the personas have DONE, so a removal is not a surprise. Only the
# records that pin an account (a decided request) or that a reader would
# ask about; each is labelled `is_test_fixture` / `source='test'` since
# handoff 46 because the actor is.
if complete:
    def count(model, domain):
        Model = env.get(model)  # noqa: F821
        return (Model.sudo().with_context(active_test=False).search_count(domain)
                if Model is not None else 0)
    print()
    print("WHAT THE PERSONAS HAVE DONE")
    print("  assets created                    : %d"
          % count("nrs.asset", [("create_uid", "in", complete.ids)]))
    print("  custody rows recorded by them     : %d"
          % count("nrs.asset.custody", [("changed_by_id", "in", complete.ids)]))
    print("  movements recorded by them        : %d"
          % count("nrs.asset.movement", [("moved_by_id", "in", complete.ids)]))
    print("  events recorded by them           : %d"
          % count("nrs.asset.event", [("actor_id", "in", complete.ids)]))
    # The one thing the label cannot get right by itself: an account a
    # persona creates is labelled a fixture for good, because the persona is
    # a test actor. If a real colleague was ever created from a persona's
    # session, this is where it shows — and it stays labelled; the remover
    # does not touch it.
    made = Users.search([("create_uid", "in", complete.ids)])
    print("  ACCOUNTS created by them          : %d%s"
          % (len(made), "   <-- labelled a fixture for good: %s"
             % ", ".join(made.mapped("login")) if made else ""))
    print("  change requests raised            : %d"
          % count("nrs.asset.change.request",
                  [("requested_by_id", "in", complete.ids)]))
    print("  change requests asked of them     : %d"
          % count("nrs.asset.change.request",
                  [("approver_id", "in", complete.ids)]))
    print("  change requests decided by them   : %d"
          % count("nrs.asset.change.request",
                  [("approved_by_id", "in", complete.ids)]))
