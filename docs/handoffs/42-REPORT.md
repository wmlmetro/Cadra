# Handoff 42 — Report: the grant, and the refusal

**Branch:** `fix/the-grant-and-the-refusal` · **Base:** `dev` at `e3c0a0b` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/42-evidence/` (the drive transcript, three screenshots).

## In plain words, first

The line that must never be crossed is now in the register itself, under
every door, and the write that NRS needs sits behind it.

**What the line says.** Over the API, the only groups anybody can give or
take are our four — Asset User, Asset Manager, Tag-Issuing Unit, Auditor.
Odoo's own groups, including the one that makes somebody a system
administrator, cannot be touched from the API at all. And nobody can add a
role to their own account; another administrator has to. Removing your own
is allowed.

**Where it lives, and how it knows who is asking.** In the model, not on
the route, because membership can be written from six directions and a
guard on one route is a guard on one of them. It tells our API from
everything else by the one thing only our API sets on a request: the
decoded token. The back office, the bootstrap script, module upgrades,
migrations and Odoo's own sign-up all lack it and are untouched. There is
no switch to turn the guard off, on purpose — a switch is how a guard gets
found switched off.

**Driven, as asked.** A credential with the `admin` scope, stripped first
of its administrator group so it is what report 41 wrongly said it already
was, asked for that group on its own user and on somebody else's: refused,
in a sentence, nothing written. The administrator asked for a role on
their own account: refused, naming them. The same administrator dropped one
of their own roles: allowed, recorded with their name. The back office put
everything back, unguarded, and the record wrote that down too. A grant
made from the new screen was read back out of the access-changes report
with the admin session's own name on it.

**Two corrections to earlier claims.** The bootstrap script makes the
user of every admin-scoped credential a system administrator, so report
41's "deliberately not a system administrator" was false on every tenant
bootstrap has touched. And the first draft of the route would have refused
every change on an administrator's own row for the wrong reason (trying to
remove the administrator group it was not asked about); fixed before it
shipped.

**Also:** the seven remaining groups are on the user form (11 of 11), and
the cluster's self-sign-up page is shut on all four hosts, measured ahead
of handoff 43.

## A · The refusal — `myservice_api/models/access_guard.py`

**Where.** Two `_inherit` classes, `res.users` (`create`, `write`,
`unlink`) and `res.groups` (`create`, `write`, `unlink`), imported after
`access_recorder` so the guard wraps the recorder. Every door the
recorder's docstring enumerates meets it.

**How it tells our API from the system.**

```python
def api_caller():
    if not request:                      # unbound proxy → False; getattr would RAISE
        return None
    claims = getattr(request, 'jwt_claims', None)
    if not claims:
        return None
    return claims.get('uid'), claims
```

`require_jwt` sets `request.jwt_claims` on every `@cadra_route`
(`controllers/utils.py:760`); nothing else does. Measured in the container:
outside an HTTP request `bool(request)` is False and `getattr(request, …)`
raises `RuntimeError: object is not bound`, so the order of the two checks
is load-bearing. The markers considered and rejected — `install_mode`,
`env.su`, `uid == 1` — each both over- and under-match: `_provision_client_user`
runs from the back-office form as a logged-in user under `sudo()`, the
19.0.3.2.0 migration runs as uid 1 with an empty context, a UI-started
upgrade runs with a request bound. The JWT matches exactly the population
the rulings are about (`docs/DECISIONS.md`, 2026-10-02).

**What it refuses, in the API's population only.**

| Door | Rule |
|---|---|
| `res.users.write` (groups in vals) | added ∪ removed ⊆ the four, else *"Over the API only these roles…"*; then added and `user.id == env.uid` → *"Nobody grants themselves a role…"* |
| `res.users.create` | the new account's groups ⊆ the four ∪ `_default_groups()` (what Odoo gives every internal user) |
| `res.users.unlink` | *"An account cannot be deleted over the API. Deactivate it instead."* |
| `res.groups.write` with `user_ids` | per-user diff, the same two rules, from the other side |
| `res.groups.write` with `implied_ids` / `implied_by_ids` | *"What a group means cannot be changed over the API…"* |
| `res.groups.create` / `unlink` | *"Groups cannot be created or deleted over the API."* |

**Diff-then-raise.** The guard snapshots real membership before and after
`super()` (the recorder's own snapshot helpers) and raises `AccessError` on
the diff — `vals` cannot be parsed honestly, for the four reasons
`access_change.py` gives. The exception rolls the transaction back,
recorder rows included; `cadra_endpoint` maps it to `403 forbidden` with
the sentence verbatim. **The proof is in the access record's ids:** on
`test19` the drive's rows are 17133, 17137, 17140, 17141 — the gaps are the
refused writes, whose recorder rows took sequence numbers and were rolled
back.

**What is deliberately not guarded.** Anything without a JWT. The back
office's user form, XML-RPC, `odoo shell` (bootstrap), migrations,
`post_init_hook`s, security XML on install and upgrade, `auth_signup`'s
template copy, mail's notification-preference self-write, cron. Odoo's own
two guards (`_check_disjoint_groups`, `_check_at_least_one_administrator`)
stand underneath for everybody.

## B · The write — `POST /api/v1/users/<id>/roles` · `myservice_api` 19.0.3.16.0

Body `{"roles": [keys], "dry_run": false}`; `roles` is the desired set of
DIRECT roles among the grantable four. The route replaces only those four
and leaves every other group where it is — `base.group_user`, a mail or
fleet group, and a vocabulary role that is not grantable. **A non-grantable
key (`system`) is forwarded to the write on purpose**, so the refusal the
caller reads is the model's and not a copy on the route; the route itself
refuses only what is not a role at all (400 `allowed_values`), a stray
body key (400 `rejected_fields` / `writable`), a key whose group is not
installed on the tenant (400), and an unknown, structural or portal target
(404). `idempotent=True`; a 403 is never stored, a 200 replays verbatim.

**The dry run is a real write inside a savepoint, rolled back** by a
private exception. So `after.roles_effective` is read off `all_group_ids`
after Odoo computed it — implication included — and a change that would be
refused is refused on preview, before anybody clicks Apply.

Response: `{user, before: {roles_direct, roles_effective}, after: {…},
granted, revoked, applied}`. `GET /roles` carries `grantable` (exactly four
true), read from the guard's constant.

**Corrected before shipping.** The first draft computed
`new = (current − vocabulary) | desired`, so any change from the screen on
a row holding a non-grantable vocabulary role — every administrator's own
row holds `system` — tried to REMOVE `base.group_system` and was refused by
ruling 1 for that rather than by ruling 2 for what was asked. Found on the
first live probe (`drive-refusals.txt` was the second). Now
`new = (current − grantable) | desired`.

## C · The screen

In the Users page's detail panel, one new section, *Change roles*
(`user-section-change-roles`); hidden for a credential, replaced by *A
credential's roles follow its scopes and are not changed here.* One
checkbox per grantable role with the group's own description; implication
notes under the boxes (*Asset Manager also confers Asset User*); **Preview**
runs the dry run and shows *Will grant / Will revoke*, then *Roles held*
and *Can act as (with implication)* before → after in names; **Apply** is
enabled only on a successful preview whose boxes have not changed since
and that changes something; every refusal renders the server's sentence
verbatim in the same red panel as the tag dialog's. Nothing on the viewer's
own row is pre-empted: the server refuses and the page shows its words
(`42-evidence/02-self-grant-refused-in-words.png`). A fresh idempotency key
per call, so a replayed preview can never stand in for an apply.

**No second audit.** The section calls the route; the recorder's hooks do
the rest. Confirmed by making a grant from the screen and reading the row
back: see §E, spec 42 test 1.

## D · The drive — transcript

`42-evidence/drive-refusals.txt`, verbatim, access-record count after each
step (the suite credential is `cadra_client_test_client`, user 6; the
person is `admin`, user 2):

| Step | Who | Asked | Answer | Rows |
|---|---|---|---|---|
| A | back office (XML-RPC as admin, no JWT) | remove `base.group_system` from user 6 | written | 9 → 10 |
| B | credential, `admin` scope, user 6 now NOT an administrator | `system` on its OWN user | `403 forbidden: Over the API only these roles can be granted or removed: Asset User, Asset Manager, Tag-Issuing Unit, Auditor. 'Role / Administrator' is not one of them. Making somebody a system administrator, or changing any other Odoo group, is done in the Odoo back office, signed in as a person.` | 10 |
| C | the same credential | `system` on `h41_manager` | the same sentence | 10 |
| D | person `admin` | Auditor on their own account | `403 forbidden: Nobody grants themselves a role. admin asked to add Auditor to their own account; another administrator has to do that. Removing your own roles is allowed.` | 10 |
| E | person `admin` | remove their own Asset Manager | 200 — `revoked: ["asset_manager"]`, effective loses Asset User, `applied: true` | 11 |
| E′ | person `admin` | Asset Manager back on themselves | `403 … Nobody grants themselves a role. admin asked to add Asset Manager…` | 11 |
| F | person `admin` | `dry_run` Tag-Issuing Unit on `h41_manager` | 200 — `granted: ["tag_issuing_unit"]`, `after.roles_effective` = Asset User, Asset Manager, Tag-Issuing Unit, `applied: false` | 11 |
| G | back office | Asset Manager back on admin; `base.group_system` back on user 6 | written, unguarded | 13 |

Rows written: `17133 removed cadra_client_test_client Role / Administrator`
(A), `17137 removed admin Asset Register / Asset Manager` (E — actor
`Administrator`, `changed_by_login admin`, attributable, `user_write`),
`17140`, `17141` (G). **Every refused step left the count where it was.**

**Odoo's last-administrator guard** is proved in the in-registry suite
(`test_vii_…`): removing `base.group_system` from every account that holds
it raises `ValidationError`. On `test19` it cannot be driven live without
stripping three accounts, one of them the suite's own credential.

**`scripts/bootstrap.py` and a module upgrade.** Its group-writing step,
`ensure_admin_groups()`, run inside `odoo shell` on `test19` the way
`bootstrap.sh` runs the whole script (`PROBE request bound? False uid 1 su
True`): *admin already in 'Asset Manager'*, *admin already in 'Security
Administrator'*, access record 27 → 27 — no noise. Then, deliberately, a
grant the way bootstrap writes one (`group.write({'user_ids': [(4, …)]})`)
and its reversal: both pass the guard, both recorded — rows 17938/17939,
`actor __system__`, `attributable f`, `source group_write`. The whole
script was not run because its client step rotates `test19`'s credential
secrets. Module upgrades: the fan-out table below, access record unchanged
on every tenant. (The bootstrap finding in F.2 is about what that script
GRANTS, not whether it runs.)

## E · Verification — suites, with denominators

**Browser** (`e2e/tests/41-…` and `42-…`, `test19`): **10 passed of 10.**
Spec 42: a grant through the screen on `h41_manager` → preview → apply →
the row's pill → `GET /users` agrees → `GET /reports/access-changes`
walked by cursor has a `granted` event for that login, `attributable:
true`, `actor.name` equal to `GET /auth/whoami`'s name for the admin
session — the person who clicked, not what the route ran as; then
reverted the same way with the `removed` event asserted. The self-grant
refusal in words with Apply dark; one checkbox per grantable role, none
for `system`; the credential's sentence.

**HTTP suite**, CI order first — `CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q -rs`:

```
1162 passed, 11 skipped in 1218.42s (0:20:18)
```

The 11 skips are `test19`'s standing ten (2 Turnstile, 3 partition-data-absent, 1 no `workflow.config`, 1 no SAP asset number, 1 documented `is_tagged`, 1 administrators-withdraw-by-design, 1 untagged-serial-in-registry — every reason in the log) plus ONE new one, and it is a finding rather than a gap: `tests/test_user_roles.py:193` — *the suite's credential user 'cadra_client_test_client' already holds `system` directly (1 of 1); nothing to escalate to* — which is F.2. The drive in §D strips the group first and proves the refusal the test cannot; the in-registry suite proves it on a credential that never held it. `tests/test_user_roles.py` itself: 14 of 15 passed, that one skipped.

**In-registry**, `-u myservice_api --test-enable --test-tags /myservice_api --workers=0`, three runs, the first two failing in the TEST not the guard:

```
run 1:  0 failed, 5 error(s) of 310 tests   — every test that binds a fake request:
        AttributeError: '_FakeApiRequest' object has no attribute 'env'
        (the guard HAD raised; `_()` then asked request.env.lang for the language)
run 2:  0 failed, 1 error(s) of 310 tests   — the create test: website's get_current_website
        reads request.session when a request is bound
run 3:  0 failed, 0 error(s) of 310 tests
```

`test_access_guard.py` is 15 of those 310 (i–viii as asked, plus the group-side door, `implied_by_ids`, a create under the API, and `/roles` marking exactly the four); `test_users_endpoint.py` 8. Every refused call in it asserts membership, `res_groups_users_rel`, `res_groups_implied_rel` AND the access record unchanged; the last-administrator guard fires (`ValidationError`) when `base.group_system` is taken from every holder; a plain ORM write with no request bound adds `base.group_system` freely.

**Fan-out** — `-u myservice_api,myservice_security,myservice_staff_bus,myservice_workflow,myservice_identity` on each tenant, serially, after the suites:

| Tenant | rc | ERROR/CRITICAL | Modules loaded | first-party groups with a privilege | access rows before → after |
|---|---|---|---|---|---|
| cadra19 | 0 | 0 | yes | 11 of 11 | 0 → 0 |
| nrs19 | 0 | 0 | yes | 11 of 11 | 3 → 3 |
| gtb19 | 0 | 0 | yes | 11 of 11 | 0 → 0 |
| test19 | 0 | 0 | yes | 11 of 11 | 27 → 27 |
| nrs | 0 | 0 | yes | 11 of 11 | 0 → 0 |
| lasg | 0 | 0 | yes | 11 of 11 | 0 → 0 |
| gtb | 0 | 0 | yes | 11 of 11 | 0 → 0 |
| jaizbankplc | 0 | 0 | yes | 11 of 11 | 0 → 0 |

Odoo restarted; `/api/v1/brand` 200.

## F · What the verification found on the way

1. **The route's set arithmetic** (§B) — found on the first live probe.
2. **`bootstrap.py:509` grants `base.group_system` to every admin-scoped
   credential's user.** Report 41 §G said the opposite. The guard does not
   care whether the caller already holds the group; the drive strips it
   first so the exposure §G named is the one refused. The claim is
   corrected in `docs/GO-LIVE.md` §18.2 and §19.2. Whether bootstrap SHOULD
   do that is for the Architect — it is what makes the credential able to
   call `/meta/diagnostics`-class routes that read as the user, and it is
   also exactly the power ruling 1 says a credential must not reach by
   itself.
3. **Spec 41's absence proof** now exempts exactly the one section 42
   added, and nothing else; a rewrite of it lost a `let` on the way, caught
   on the first run.
4. **Spec 42 could not find the grant it had just made**: `Date.parse` on
   the report's zoneless UTC `at` reads local time, an hour early in Lagos.
   Report 39's bug, in the spec this time. Fixed in the spec.
5. **The refusal names Odoo's `full_name`** — *Role / Administrator* for
   `base.group_system` — not the API's published alias *System
   Administrator*. The model does not import the controller's alias table.
   Open for the Architect (§H).
6. **The recorder's group-side hook does not watch `implied_by_ids`**; the
   guard refuses it over the API, the back office could make one unrecorded.
   `docs/GO-LIVE.md` §19.2.
7. **`ACCESS_CHANGE_SKIP_KEY` / `ACCESS_CHANGE_SOURCE_KEY` are read and set
   nowhere**, and `caller_ip.py:49`'s bare `getattr(request, …)` would raise
   outside HTTP. Both §19.2.

## G · The sign-up door, measured ahead of 43

Anonymous, from this machine:

| Host | `/web/signup` | `/web/login` | `/web/reset_password` |
|---|---|---|---|
| staging.app.cadra.ng | 404 (Odoo's *Page Not Found*) | 200 | 200 |
| jaizbankplc.cadra.ng | 404 | 200 | 200 |
| lasg.cadra.ng | 404 | 200 | 200 |
| gtb.cadra.ng | 404 | 200 | 200 |

Shut. Why it is shut — the parameter's value on the cluster, and what the
route checks — is 43 §0's question and is not claimed here.

## H · Open questions

- The refusal sentence names `Role / Administrator`; the API elsewhere
  says *System Administrator*. Same group, two names, in one response
  stream. The alias lives in the controller; moving it to the model is a
  small change if the Architect wants one name.
- `bootstrap.py` making every admin-scoped credential's user a system
  administrator (F.2).
- Ruling 2 and first-ever setup: on a fresh tenant the only person is
  `admin`, who cannot add a role to themselves over the API — but holds
  `base.group_system`, whose `admin` scope satisfies every route without
  the role, and the back office is unguarded. **Measured, not argued: the
  rule does not block bootstrapping**, because the first person's power
  comes from a group the API cannot grant anyway.
- For 43 (from the builder): `res.users.create` over the API allows the
  four ∪ `_default_groups()`. If 43 creates through `auth_signup`'s
  template copy and `base.default_user` implies a group outside that set
  on some tenant, the create is refused — read the template's groups
  before building on it.

## Deviations from the handoff

- **A key whose group is not installed on the tenant is a 400** at the
  route — the builder's addition, kept: the model could not name a group
  that does not exist.
- **The probe users and the suite credential's group were put back** after
  the drive through the back office; `test19` is as it was, plus the
  recorded rows.
- **Specs 39/40 not re-run**; nothing on the station changed.

## Needs the owner

- **Merge the PR.**
- **Run `upgrade-19` with the PINNED image** (`…cadra-odoo-19:dev-<merge sha>`,
  never blank — report 41's roll on `dev-latest` re-used a cached image),
  `upgrade_modules=myservice_api,myservice_security,myservice_staff_bus,myservice_workflow,myservice_identity`,
  `scale_down=false` (no schema change).
- The `SMTP_*` answer for 43 (the handoff says it was given on 2 October).

## Commits

| Hash | What |
|---|---|
| `8be1c0c` / `e3c0a0b` | docs: handoffs 42 and 43 — the instruction files, on `dev` |
| `fbcb3d6` | feat: the guard, the route, the screen, the seven privileges, the suites, the docs, the evidence, this report |
| (next) | docs: report 42 — this file with the hashes filled in |
