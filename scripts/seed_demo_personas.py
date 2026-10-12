"""One demo account per role — marked in the data, re-runnable, removable.

Handoff 46. A demo signs in as a storekeeper, a tagger, an auditor and an
administrator, and each one's screen is their own job. These are those
people. Run it through the wrapper, which keeps the passwords off the
terminal and out of the repository:

    scripts/demo_personas.sh <db> seed      # this file
    scripts/demo_personas.sh <db> list      # list_demo_personas.py
    scripts/demo_personas.sh <db> remove    # remove_demo_personas.py, dry run
    scripts/demo_personas.sh <db> remove --apply

WHY THE MARKING IS THE WHOLE OF THIS FILE
-----------------------------------------
The owner ruled two things: every tenant, including the ones holding a
client's real data, and realistic names. Together they are the risk. On
`nrs19` these invented people sit beside 11,386 real employees, and in six
months somebody will ask whether *Halima Danjuma, Store Officer* is a real
officer. So every account carries three independent marks, and the removal
script refuses a record unless all three agree:

1. **`is_test_fixture`, derived — the repository's own label, not a third
   convention.** The personas are created by an INERT credential flagged
   `is_test_credential` (`cadra_demo_personas`: archived, no secret, no
   scopes — it can never mint a token), so `cadra.test.fixture.mixin` stamps
   each persona's partner exactly as it stamps anything else a test
   credential creates. Nothing here sets the flag; nothing can. And since
   handoff 46 an account that is itself a fixture is a test ACTOR as well
   (`myservice.api.client._is_test_credential_user`), so what a persona does
   during a demo — a verification, a custody change, an approval — is
   labelled too, not only the persona.
2. **A reserved email domain.** `demo.example` is under `.example`, which
   RFC 2606 reserves: it can never be delegated, so it can never be anybody's
   address, and a letter to it can never reach a person. The login IS that
   address.
3. **An external id in a namespace no module can own.** `__cadra_demo__.*`
   (`ir.model.data`): double underscores are not a valid module name, so no
   module upgrade will ever adopt or delete these rows, and the removal
   script finds exactly what this file created and nothing else.

WHAT IT REFUSES
---------------
* A database whose class is not `test` or `client` — absent included, the
  same rule as every script that writes here. `production` is refused too:
  at go-live these come OFF, they do not go on.
* A login or a credential that already exists without this file's external
  id. It is never adopted: a collision with something we did not create is
  reported and left alone.
* A persona whose NAME is already an employee's or a contact's name on this
  tenant: every word of it, case-insensitively, in any order. Measured before any
  name was chosen: the handoff's own example, *Aisha Bello*, is four real
  employees on `nrs19`, and *Ibrahim Musa* is seven. A realistic Nigerian
  name on an 11,386-person Nigerian staff list collides; the six below
  collide with nobody on any of the nine local databases.

WHAT IT DOES NOT CREATE
-----------------------
No `hr.employee`. Odoo 19 creates one for a new user only when asked
(`create_employee` defaults to False), so a persona has no IR number, cannot
be a custodian and is not on any staff list. The wrapper's `list` prints the
employee count either side as the proof.

RE-RUNNABLE
-----------
A second run creates nobody, changes no password and writes nothing unless a
persona has drifted from its definition (roles, job title, active), which it
reports and puts back. A lost password is replaced only on request:
`CADRA_DEMO_RESET_PASSWORDS=1`.

Passwords are generated here, printed ONLY between the two sentinel lines
below, and the wrapper moves them into `docs/api/.personas.<db>` (mode 600,
gitignored) without echoing them.
"""
import os
import secrets

from odoo.addons.myservice_nrs_base.database_class import (  # noqa: E402
    CLIENT, TEST, database_class)

#: Shared with list_demo_personas.py and remove_demo_personas.py;
#: `tests/test_demo_personas_agree.py` fails if the three disagree.
XMLID_MODULE = "__cadra_demo__"
EMAIL_DOMAIN = "demo.example"
SEEDER_CLIENT_ID = "cadra_demo_personas"
SENTINEL_BEGIN = "CADRA_PERSONAS_BEGIN"
SENTINEL_END = "CADRA_PERSONAS_END"

ASSET_USER = "myservice_asset_register.group_asset_user"
ASSET_MANAGER = "myservice_asset_register.group_asset_manager"
TAG_ISSUING_UNIT = "myservice_asset_register.group_tag_issuing_unit"
AUDITOR = "myservice_api.group_auditor"
SYSTEM = "base.group_system"
ASSET_OFFICER = "myservice_asset_register.group_asset_officer"
# Handoff 57 — the five gate roles of Addendum A (the gates ride on
# `nrs.asset.register_state`, kept there by handoff 58). Each
# implies Asset User, so each persona can read the register it is gating.
IAD_VFM_OFFICER = "myservice_asset_register.group_iad_vfm_officer"
IAD_VFM_APPROVER = "myservice_asset_register.group_iad_vfm_approver"
ASSET_CONTROLLER = "myservice_asset_register.group_asset_controller"
REGISTER_MAKER = "myservice_asset_register.group_register_maker"
REGISTER_CHECKER = "myservice_asset_register.group_register_checker"

#: (key, name, job title, groups). One per role this system has, plus the two
#: combinations the demo needs: the tagger a person actually is (Asset User +
#: Tag-Issuing Unit — the unit's role alone opens no screen, handoff 41), and
#: an administrator. The unit's role ALONE is kept as a persona on purpose:
#: it is the evidence that the role does not fit a person.
#:
#: Handoff 57: the Store Officer holds the Asset Officer role (handoff 47's
#: answer to 46's finding that Asset User cannot register) — receiving a unit
#: and submitting it to Internal Audit is `assets:write`, and the gated demo
#: starts with her. The five gate personas follow the six, one role each.
#: Every name below was checked at zero employees and zero contacts on all
#: nine local databases on 7 October 2026 (`nrs19`: 0 of 11,386 employees).
PERSONAS = (
    ("storekeeper", "Halima Danjuma", "Store Officer", (ASSET_OFFICER,)),
    ("asset_manager", "Chukwudi Anyanwu", "Asset Manager", (ASSET_MANAGER,)),
    ("tag_unit", "Nkechi Obiora", "Tag-Issuing Unit Officer",
     (TAG_ISSUING_UNIT,)),
    ("tagger", "Babatunde Olaniyan", "Tagging Officer",
     (ASSET_USER, TAG_ISSUING_UNIT)),
    ("auditor", "Zainab Garba", "Internal Auditor", (AUDITOR,)),
    ("administrator", "Oluwaseun Ajayi", "Systems Administrator",
     (SYSTEM, ASSET_MANAGER)),
    ("iad_officer", "Folasade Ogunbiyi", "IAD Value-for-Money Officer",
     (IAD_VFM_OFFICER,)),
    ("iad_approver", "Kelechi Ihenacho", "IAD Value-for-Money Approver",
     (IAD_VFM_APPROVER,)),
    ("asset_controller", "Hauwa Dikko", "Asset Controller",
     (ASSET_CONTROLLER,)),
    ("register_maker", "Temitope Oyelaran", "Register Maker",
     (REGISTER_MAKER,)),
    ("register_checker", "Obinna Ezeagu", "Register Checker",
     (REGISTER_CHECKER,)),
)


def login_for(name):
    return "%s@%s" % (".".join(name.lower().split()), EMAIL_DOMAIN)


RESET = os.environ.get("CADRA_DEMO_RESET_PASSWORDS", "").strip() not in (
    "", "0", "false", "no")

db_class = database_class(env)  # noqa: F821 — odoo shell
print("database   : %s" % env.cr.dbname)  # noqa: F821
print("class      : %s" % (db_class or "(not set)"))
if db_class not in (TEST, CLIENT):
    print("REFUSED: this database's class is %s. Demo personas go on a "
          "database classified `test` or `client` and nowhere else — absent "
          "and `production` included. Nothing was read or changed."
          % (db_class or "not set"))
    raise SystemExit(1)

Data = env["ir.model.data"].sudo()  # noqa: F821
Users = env["res.users"].sudo().with_context(  # noqa: F821
    active_test=False, no_reset_password=True)
Client = env["myservice.api.client"].sudo().with_context(  # noqa: F821
    active_test=False)


def ours(model, name):
    """The record this file created under `name`, or an empty recordset."""
    Model = env[model].sudo().with_context(active_test=False)  # noqa: F821
    row = Data.search([("module", "=", XMLID_MODULE), ("name", "=", name),
                       ("model", "=", model)], limit=1)
    return Model.browse(row.res_id).exists() if row else Model.browse()


def claim(record, name):
    Data.create({"module": XMLID_MODULE, "name": name, "model": record._name,
                 "res_id": record.id, "noupdate": True})


def group(xmlid):
    return env.ref(xmlid)  # noqa: F821


refusals = []
created, drifted, unchanged = [], [], []
passwords = []

# ── 1. the inert credential the personas are created BY ──────────────
seeder = ours("myservice.api.client", "seeder_client")
if not seeder:
    stranger = Client.search([("client_id", "=", SEEDER_CLIENT_ID)], limit=1)
    if stranger:
        print("REFUSED: a credential `%s` exists that this script did not "
              "create (id %s). Nothing was changed." % (SEEDER_CLIENT_ID,
                                                       stranger.id))
        raise SystemExit(1)
    # Created directly rather than through a test helper: this is the one
    # credential whose whole purpose is to say it is not real. No secret is
    # ever set and it is archived at once, so `/auth/token` cannot find it.
    seeder = Client.create({
        "name": "Demo personas (inert seeding credential)",
        "client_id": SEEDER_CLIENT_ID,
        "scopes": "",
        "is_test_credential": True,
    })
    seeder.write({"active": False})
    # Its user too: it has no password and its credential is archived, but
    # an active internal account is one an administrator could give a
    # password to. Archived, it can still be the uid records are created
    # under, which is all it is for.
    seeder.user_id.write({"active": False})
    claim(seeder, "seeder_client")
    claim(seeder.user_id, "seeder_user")
    print("seeder     : created %s (archived, no secret, no scopes)"
          % SEEDER_CLIENT_ID)
elif not seeder.is_test_credential or seeder.active or seeder.client_secret_hash:
    print("REFUSED: the seeding credential is no longer inert (test=%s, "
          "active=%s, secret=%s). Somebody changed it; nothing was changed."
          % (seeder.is_test_credential, seeder.active,
             bool(seeder.client_secret_hash)))
    raise SystemExit(1)
else:
    if seeder.user_id.active:
        seeder.user_id.write({"active": False})
        print("seeder     : %s present, inert; its user archived (it was "
              "left active before handoff 46's verification pass)"
              % SEEDER_CLIENT_ID)
    else:
        print("seeder     : %s present, inert" % SEEDER_CLIENT_ID)

AsSeeder = Users.with_user(seeder.user_id).sudo()
default_groups = Users._default_groups()

Employee = env["hr.employee"].sudo().with_context(  # noqa: F821
    active_test=False)
Partner = env["res.partner"].sudo().with_context(  # noqa: F821
    active_test=False)

# ── 2. the personas ──────────────────────────────────────────────────
for key, name, title, xmlids in PERSONAS:
    login = login_for(name)
    wanted_groups = default_groups | Users.env["res.groups"].browse(
        [group(x).id for x in xmlids])
    user = ours("res.users", "persona_%s" % key)

    if not user:
        stranger = Users.search([("login", "=", login)], limit=1)
        if stranger:
            refusals.append("%s: login %s belongs to user %s, which this "
                            "script did not create — left alone"
                            % (key, login, stranger.id))
            continue
        # Every word of the name, in any order and with anything between —
        # "DANJUMA Halima" and "Halima A. Danjuma" are the same person to a
        # reader, and a contiguous substring would miss both.
        words = [("name", "ilike", w) for w in name.split()]
        clash_e = Employee.search_count(words)
        clash_p = Partner.search_count(words)
        if clash_e or clash_p:
            refusals.append("%s: %r is already the name of %d employee(s) "
                            "and %d contact(s) on this tenant — a demo "
                            "account must not be mistakable for them; pick "
                            "another name" % (key, name, clash_e, clash_p))
            continue
        password = secrets.token_urlsafe(15)
        user = AsSeeder.create({
            "name": name,
            "login": login,
            "email": login,
            "function": title,
            "tz": "Africa/Lagos",
            "password": password,
            "group_ids": [(6, 0, wanted_groups.ids)],
        })
        claim(user, "persona_%s" % key)
        if not user.partner_id.is_test_fixture:
            # The derivation is the marker; without it this account is
            # indistinguishable from a real officer. Stop, and roll back.
            env.cr.rollback()  # noqa: F821
            print("ABORTED: %s was created without `is_test_fixture` — the "
                  "derivation did not fire. Rolled back, nothing written."
                  % login)
            raise SystemExit(1)
        created.append(key)
        passwords.append((key, login, password))
        continue

    if not user.partner_id.is_test_fixture or user.login != login:
        refusals.append("%s: user %s carries this script's id but not its "
                        "marks (fixture=%s, login=%s) — left alone"
                        % (key, user.id, user.partner_id.is_test_fixture,
                           user.login))
        continue
    changes = {}
    if set(user.group_ids.ids) != set(wanted_groups.ids):
        changes["group_ids"] = [(6, 0, wanted_groups.ids)]
    if user.function != title:
        changes["function"] = title
    if not user.active:
        changes["active"] = True
    if RESET:
        password = secrets.token_urlsafe(15)
        changes["password"] = password
        passwords.append((key, login, password))
    if changes:
        user.write(changes)
        drifted.append("%s (%s)" % (key, ", ".join(sorted(changes))))
    else:
        unchanged.append(key)

env.cr.commit()  # noqa: F821
# Running workers hold group membership in their caches.
env.registry.signal_changes()  # noqa: F821

print("created    : %d %s" % (len(created), " ".join(created)))
print("updated    : %d %s" % (len(drifted), "; ".join(drifted)))
print("unchanged  : %d %s" % (len(unchanged), " ".join(unchanged)))
for line in refusals:
    print("REFUSED    : %s" % line)
print(SENTINEL_BEGIN)
for key, login, password in passwords:
    print("%s %s %s" % (key, login, password))
print(SENTINEL_END)
if refusals:
    raise SystemExit(2)
