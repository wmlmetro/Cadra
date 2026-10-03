"""Take `base.group_system` off API-credential users — dry run unless told otherwise.

    # what it WOULD do, changing nothing:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
      odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http \
      --http-port=8099 --gevent-port=8098 < scripts/strip_credential_system_group.py

    # to actually do it:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T \
      -e CADRA_APPLY=1 odoo \
      odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http \
      --http-port=8099 --gevent-port=8098 < scripts/strip_credential_system_group.py

WHY
---
Handoff 44. Two provisioning paths granted `base.group_system` to an API
credential's user until 2026-10-02: `scripts/bootstrap.py`, to every run's
smoke-test client (`test_client`), and the `19.0.3.2.0` migration, to any
client holding the `admin` scope when it ran. A system administrator can execute arbitrary server
actions, so for that credential the API guard of handoff 42 was advisory.
Report 44 §A stripped it on `test19` and drove the whole HTTP suite as the
credential; what it costs is in that report, and what an API credential is
entitled to is `docs/DECISIONS.md` 2026-10-02.

Both stopped GRANTING it. It does not take it off a credential that
already holds it, because bootstrap is the production deploy path and that
would change every live tenant on the next deploy without anybody deciding
to. This script is the deciding.

WHAT IT TOUCHES
---------------
Only the `res.users` behind a `myservice.api.client` (archived clients
included — an archived credential's user is still a user), and only their
DIRECT membership of `base.group_system`. A person is never touched, whatever
they hold. A credential user that holds the group only through implication
from another group is NAMED and not touched: removing the other group is a
different decision.

WHAT IT DOES NOT NEED
---------------------
No database-class refusal: removing root from a credential is as right on a
client's database as on a test one, and more urgent there. Nothing is
deleted. The change is recorded in `myservice.api.access.change` like any
other membership change (actor: the shell's superuser, labelled as such),
and it is reversible by an administrator in the back office.

THE DRY RUN MEASURES
--------------------
Every removal is performed inside a savepoint that is then rolled back, so a
refusal from Odoo (the last-administrator check, say) shows up in the dry run
as a refusal and not in the apply as a surprise.

WHAT AN OPERATOR SEES IF IT GOES WRONG
--------------------------------------
Nothing in the API depends on the group — report 44 §A. If that proves wrong
for some route on some tenant, the symptom is a `403` or `400` whose message
names an Odoo model or group on a call made with that credential; put the
group back from Settings > Users (the user is `cadra_client_<client_id>`) and
report the route. Do not re-add it to bootstrap.
"""
import os

APPLY = os.environ.get("CADRA_APPLY", "").strip() not in ("", "0", "false", "no")


class _DryRun(Exception):
    """Raised inside the savepoint to roll a measured removal back."""


system = env.ref("base.group_system")                     # noqa: F821 — odoo shell
Users = env["res.users"].sudo().with_context(active_test=False)  # noqa: F821
clients = env["myservice.api.client"].sudo().with_context(  # noqa: F821
    active_test=False).search([], order="id")
groups_field = "group_ids" if "group_ids" in Users._fields else "groups_id"

print("database: %s · %s" % (env.cr.dbname,                # noqa: F821
                             "APPLY" if APPLY else "dry run"))
print("%d API client(s) on this database" % len(clients))

erp_manager = env.ref("base.group_erp_manager")          # noqa: F821
prefix = env["myservice.api.client"].CLIENT_USER_LOGIN_PREFIX  # noqa: F821

direct, implied, clean, people = [], [], [], []
for c in clients:
    user = c.user_id
    if not user:
        clean.append((c, "no user"))
        continue
    if not (user.login or "").startswith(prefix):
        # A credential still running as a PERSON — `base.user_admin` on a
        # database the 19.0.3.2.0 migration has not reached, or a hand-linked
        # human. Taking the group off would take it off that person. Named,
        # never touched (verification pass, report 44 §G).
        people.append(c)
        continue
    if system in user[groups_field]:
        direct.append(c)
    elif user.has_group("base.group_system"):
        implied.append(c)
    else:
        clean.append((c, "does not hold it"))

for c, why in clean:
    print("  -  %-24s %-34s %s" % (c.client_id, c.user_id.login or "-", why))
for c in people:
    print("  !  %-24s %-34s runs as a PERSON, not its own %s* user — not "
          "touched; re-home it first (Settings > API Clients > Provision user)"
          % (c.client_id, c.user_id.login, prefix))
for c in clients:
    # `_is_admin()` reads `base.group_erp_manager`, which the system group
    # implies. A DIRECT row of it is the same power by another door; named,
    # not removed — 0 of 12 local credentials hold one.
    if c.user_id and c.user_id.login.startswith(prefix) \
            and erp_manager in c.user_id[groups_field]:
        print("  !  %-24s %-34s holds base.group_erp_manager DIRECTLY — not "
              "touched by this script; decide separately"
              % (c.client_id, c.user_id.login))
for c in implied:
    print("  !  %-24s %-34s holds it THROUGH ANOTHER GROUP — not touched; "
          "name the group and decide separately" % (c.client_id, c.user_id.login))

if not direct:
    print("0 of %d client users hold base.group_system directly. Nothing to do."
          % len(clients))
else:
    done, refused = [], []
    for c in direct:
        user = c.user_id
        try:
            with env.cr.savepoint(flush=True):             # noqa: F821
                user.write({groups_field: [(3, system.id)]})
                env.flush_all()                            # noqa: F821
                still = user.with_context(active_test=False).has_group(
                    "base.group_system")
                if still:
                    raise RuntimeError(
                        "removed the direct row and still holds it — "
                        "through implication")
                if not APPLY:
                    raise _DryRun()
            done.append(c)
        except _DryRun:
            done.append(c)
        except Exception as exc:                            # noqa: BLE001
            # catch-all: reported — printed with the client it refused on,
            # and nothing for that client is written.
            refused.append((c, "%s: %s" % (type(exc).__name__, exc)))
    for c in done:
        print("  %s %-24s %-34s scopes: %s" % (
            "✓" if APPLY else "~", c.client_id, c.user_id.login, c.scopes))
        scopes = set((c.scopes or "").split())
        if scopes & {"admin", "*"} and "approvals:write" not in scopes:
            # The one thing a credential loses that a SCOPE may promise:
            # deciding a change request or a tag replacement. The token's
            # `admin` wildcard passes the route's scope gate, and the MODEL
            # then asks `_may_decide`, which without the system group needs
            # Asset Manager — which `SCOPE_GROUPS` gives for
            # `approvals:write`, and gives `admin` nothing (report 44 §G).
            print("     note: %s holds `admin` without `approvals:write`, so "
                  "after this it can no longer approve, reject or be asked "
                  "to approve. Add `approvals:write` to its scopes if it "
                  "must." % c.client_id)
    for c, why in refused:
        print("  ✗  %-24s %-34s REFUSED — %s" % (c.client_id, c.user_id.login, why))
    print("%d of %d client users hold base.group_system directly; %d %s, %d "
          "refused." % (len(direct), len(clients), len(done),
                        "removed" if APPLY else "would be removed", len(refused)))
    if not APPLY:
        print("Re-run with CADRA_APPLY=1 to remove it.")

if APPLY:
    env.cr.commit()                                        # noqa: F821
    # Tell the running server. `odoo shell` never signals on exit, so
    # without this every worker keeps its cached copy of the user's groups —
    # and goes on treating the credential as a system administrator — until
    # it restarts (verification pass, report 44 §G). The write invalidated
    # the caches in THIS process; this inserts into `orm_signaling_*`, which
    # every worker polls at the start of each request.
    env.registry.signal_changes()                          # noqa: F821
    print("signalled the running server: caches invalidated")
else:
    env.cr.rollback()                                      # noqa: F821
    env.registry.reset_changes()                           # noqa: F821
