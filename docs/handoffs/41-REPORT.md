# Handoff 41 — Report: who has what

**Branch:** `fix/who-has-what` · **Base:** `dev` at `03a3bad` · **PR:** see *Commits* at the end.
**Evidence:** `docs/handoffs/41-evidence/` (nine screenshots, two drive logs).

## In plain words, first

The owner hit two walls creating the first human tagger. Both are fixed,
and neither was quite what the handoff said it was.

**The groups were invisible** because on Odoo 19 a group is not placed on
the user form by a category at all. `res.groups` has no `category_id` on
19; the form shows one drop-down per *privilege* (`res.groups.privilege`),
and a group with no privilege appears only under *Extra Rights*, and only
in developer mode. All eleven of our groups had no privilege. The fix is
three privilege records — *Asset Register* (User / Manager), *Tag Issuing*
(the Tag-Issuing Unit on its own) and *Audit* (the Auditor) — and the user
form now shows them under *NRS Asset Register*. The Tag-Issuing Unit had to
get its own drop-down, because a drop-down is one choice: in the same one
as Asset User, a person could not hold both, and a human tagger has to.

**The refusal** was not what a tagger holding only that group gets. I
signed in as one. Every read on the station is refused *before* Odoo's
access rules are consulted, by the API's own scope gate: the token carries
only `tagging:write`, and the station needs `assets:read` to list, look up
or open anything. So the question the handoff posed — an access rule for
the group, or document the pairing — has only one working answer. An
access rule grants no scope and would have changed nothing; a tagger has to
hold Asset User too, and that is now written on the group and in the
decision record. With the pairing the station works — except *Recent tags*,
which refused with an Odoo sentence about *Location* records. That is the
real defect behind the sentence the owner saw: four barcode reads were the
only routes in the API that ran as the signed-in user instead of under
sudo, so an Odoo access rule could decide an API answer. They now run like
every other route. The owner's user must have held a group granting
`assets:read` without a rule on the tag model (Auditor or Identity Manager
would do it); the handoff's *only the Tag-Issuing Unit* could not produce
that sentence.

**The read API and the screen** are built as asked: `GET /api/v1/users`,
`/users/<id>` and `/roles`, admin only; a *Users* page and an *Access
changes* page under a new *Administration* section. Every row says two
things that are different on Odoo 19 — the roles somebody *granted* and
the roles the account *holds* once implication is applied — and the screen
leads with the first, because that is what handoff 42 will change. Nothing
on either page changes anything; the Playwright spec proves the absence.

**For 42 and 43:** nothing in Cadra would refuse an `admin`-scoped API
credential granting itself Odoo's system-administrator group, because
every route is sudo and Odoo's own guards are only "one administrator must
remain" and "portal and internal are exclusive". Mail is configured on none
of the eight local tenants. `auth_signup` is installed on all eight.

## A · The two defects

### A.1 The category — what the handoff asked, and what 19 actually has

The handoff: *"Give all three groups a `category_id`."* On Odoo 19:

```
odoo/addons/base/models/res_groups.py:36
    privilege_id = fields.Many2one('res.groups.privilege', ...)
odoo/addons/base/models/res_groups_privilege.py:13
    category_id = fields.Many2one('ir.module.category', ...)
```

There is no `category_id` on `res.groups`. The form widget
(`web/static/src/webclient/res_user_group_ids_field/res_user_group_ids_field.js`)
builds one SELECTION field per privilege (`selection.unshift([false,
privilege.placeholder])`), groups privileges by their category, and puts
groups without a privilege into an *Extra Rights* block rendered only when
`odoo.debug` — exactly the owner's experience.

Measured on `test19` before the change: **0 of 11** first-party groups had
a `privilege_id` (`res_groups` ⋈ `ir_model_data`, modules `myservice_*`).

Built — `myservice_asset_register/security/asset_security.xml`:

| Privilege | Category | Groups | Why separate |
|---|---|---|---|
| Asset Register (seq 10) | NRS Asset Register | Asset User (seq 10), Asset Manager (seq 20) | one choice; Manager implies User and the widget orders by implication |
| Tag Issuing (seq 20) | NRS Asset Register | Tag-Issuing Unit | a privilege is a single selection, and a human tagger holds this WITH Asset User |

And `myservice_api/security/api_groups.xml`: *Audit* (seq 30), same
category, the Auditor alone. **This is one group more than the handoff
named**; it is the same defect, in the vocabulary §4B lists, and the
Users screen would otherwise show a role nobody can set on the form. The
seven other first-party groups are left as they are and listed in
`docs/GO-LIVE.md` §18.2.

No `implied_ids` changed. The Tag-Issuing Unit is still implied by nothing
and implies nothing; the comment forbidding tidying is kept and extended.

**The user form afterwards** — `41-evidence/01-user-form-after-privileges.png`,
the probe `h41_tagger` on `test19`: under *NRS ASSET REGISTER* three rows,
*Asset Register: No*, *Tag Issuing: Tag-Issuing Unit*, *Audit: No*, beside
the stock *Master Data* / *Website* / *Marketing* blocks. A person looking
for where to make somebody a tagger now finds it.

**Side effect, named.** `res.groups.full_name` prefixes the privilege, so
the access record's `group_name` snapshot reads *Tag Issuing / Tag-Issuing
Unit* from now on (the six rows my probes wrote already do), where rows
written before read *Tag-Issuing Unit*. `group_id` is unchanged.

### A.2 The access rule — driven, verbatim

Probe users created on `test19` over XML-RPC as `admin` (every one has
`example.invalid` email and *(probe)* in the name):

| login | groups (direct) | purpose |
|---|---|---|
| `h41_tagger` | Internal User + Tag-Issuing Unit | the handoff's "only Tag-Issuing Unit" — Internal User is what every person carries |
| `h41_tagger_paired` | Internal User + Asset User + Tag-Issuing Unit | the pairing |
| `h41_manager` | Internal User + Asset Manager | direct ≠ effective |
| `h41_leaver` | Internal User + Asset User, then archived | an inactive person |

**Signed in as `h41_tagger` through the real login form** (`drive.mjs`,
Playwright, every `/api/` response recorded — `41-evidence/drive-before-fix.json`).
Token scope: `tagging:write`. Every refusal, in order:

```
login    GET /api/v1/approvals?state=pending&waiting_on_me=true&limit=1  403 forbidden  Missing required scope(s): assets:read
login    GET /api/v1/identity/employees?limit=1                           403 forbidden  Missing required scope(s): identity:read
login    GET /api/v1/locations?limit=1                                    403 forbidden  Missing required scope(s): locations:read
login    GET /api/v1/assets?state=active&is_verified=false&sort=newest&limit=200  403 forbidden  Missing required scope(s): assets:read
login    GET /api/v1/dashboard/kpis                                       403 forbidden  Missing required scope(s): dashboards:read
login    GET /api/v1/dashboard/map                                        403 forbidden  Missing required scope(s): dashboards:read
station  GET /api/v1/tags/pending-replacements?limit=100                  403 forbidden  Missing required scope(s): assets:read
station  GET /api/v1/barcode/untagged?limit=200                           403 forbidden  Missing required scope(s): assets:read
station  GET /api/v1/barcode/recent-tags?limit=200                        403 forbidden  Missing required scope(s): assets:read
station  GET /api/v1/barcode/kpis                                         403 forbidden  Missing required scope(s): assets:read
lookup   GET /api/v1/barcode/lookup?query=NRS-ACS-820                     403 forbidden  Missing required scope(s): assets:read
assets   GET /api/v1/assets/66032                                         403 forbidden  Missing required scope(s): assets:read
```

44 calls, 30 of them 403, every one at the scope gate
(`details.required_scopes` / `granted_scopes: ["tagging:write"]`). On the
station page itself four red panels, all *forbidden: Missing required
scope(s): assets:read*; no scan card, no *Confirm affixed*
(`41-evidence/02-station-tag-issuing-only.png`). The only station call
such a token can pass is `POST /assets/<id>/tag-affixed` — and the dialog
GETs the asset first, so even that is unreachable from the screen.

**Signed in as `h41_tagger_paired`.** Token scope: `assets:read
dashboards:read identity:read locations:read requests:read requests:write
tagging:write`. 41 calls, 2 of them 403 — both the same route:

```
station  GET /api/v1/barcode/recent-tags?limit=200   403 forbidden
  You are not allowed to access 'Location' (generic.location) records.
  This operation is allowed for the following groups:
    - Generic location manager
    - Generic location user (implicit)
  Contact your administrator to request access if necessary.
```

Everything else worked: KPIs, untagged list, pending queue, the scan
resolved `NRS-ACS-820` by tag, *Confirm affixed* opened
(`41-evidence/03-station-paired-before-sudo-fix.png`).

**The judgement.** An `ir.model.access` row for the Tag-Issuing Unit was
the option that lost: no access rule grants a scope, so the twelve
refusals above would all still stand, and the group's comment (*grants the
`tagging:write` API scope and nothing else*) would become false. The
pairing is documented — on the group's comment, on the *Tag Issuing*
privilege's description shown on the form, in `CLAUDE.md` and in
`docs/DECISIONS.md` (2026-10-01, with the losing option and why).

**And the defect the pairing exposed.** The four `/barcode/*` wrappers in
`v1.py` (`lookup`, `kpis`, `recent-tags`, `print-url`) delegate to
`myservice_barcode_station.controllers.main.BarcodeStationController`,
whose methods read `request.env` — the token's user, because `require_jwt`
switches the environment to it. Every other v1 route runs `sudo()`
(handoff 09's ruling for the dashboards; the reasoning at `SCOPE_GROUPS`
in `utils.py`: *these groups are NOT the access control*). The owner's
sentence — *'Asset Barcode Tag'* — is the same defect reached through a
group that grants `assets:read` without the tag label's read rule; Auditor
and Identity Manager both do. Fixed with one helper,
`_delegate_reads_as_superuser()` → `request.update_env(su=True)`, called
before each delegation. `uid` is kept, so stamps still name the person.
The back-office station's own `auth='user'` JSON routes are untouched —
there the rules are the gate.

**After the fix, the same drive** (`41-evidence/drive-after-fix.json`):
`h41_tagger` unchanged — 44 calls, 30 at 403, all scope refusals;
`h41_tagger_paired` — **40 calls, 0 at 403**, the only two non-2xx the
pre-login 401 probes every session makes. *Recent tags* renders
(`04-station-paired-after-sudo-fix.png`), the dialog opens
(`05-station-paired-confirm-dialog.png`). I did not confirm an affix; the
reads are the evidence and the write path did not change.

## B · The read API — `myservice_api` 19.0.3.15.0

`myservice_api/controllers/v1_users.py` (new), registered in
`controllers/__init__.py`; three component schemas (`User`, `UserRole`,
`Role`) in `v1.py`; a changelog entry and §12 of the endpoint reference.

| Route | Scope | What |
|---|---|---|
| `GET /api/v1/roles` | `admin` | the vocabulary, one entry per `GROUP_SCOPES` row: `key`, `name`, `xmlid`, `scopes`, `description`, `installed`, `implies` |
| `GET /api/v1/users` | `admin` | paged by id; `q`, `role` (EFFECTIVE), `role_direct`, `active`, `is_api_client`, `limit`, `cursor` |
| `GET /api/v1/users/<id>` | `admin` | one row; 404 for unknown, structural (`__system__`, `public`, `portaltemplate`) or portal |

Row: `id name login email active kind api_client roles_direct
roles_effective scopes scopes_source last_login_at created_at`.

**Direct versus effective, and which the screen leads with.**
`roles_direct` = `user.group_ids` ∩ vocabulary; `roles_effective` =
`user.all_group_ids` ∩ vocabulary. Each effective entry carries `via`: the
account's direct groups that imply it, empty when held directly. Live on
`test19`:

```
h41_manager  direct [asset_manager]           effective [asset_user (via Asset Manager), asset_manager]
admin        direct [system, asset_manager]   effective [system, asset_user (via Asset Manager), asset_manager,
                                                         security_officer (via Security Administrator)]
```

The second line is why `via` exists and was not in the contract I gave the
builder: an effective role can arrive through a group OUTSIDE the
vocabulary (Security Administrator grants no scope and is not on
`/roles`), and the first draft of the suite's "explained by `implies`" test
failed on exactly that row. The row now names the implier either way; the
test accepts both shapes and still requires at least one account that
holds a role through another role (the Asset Manager case).

**The screen leads with direct.** What somebody granted is what 42 will
act on — "remove an implied role" is not an operation. Implied roles sit
beside the direct ones as lighter dashed pills marked *implied*, the panel
says *via Asset Manager*, and *What this account can do* is derived from
the effective set, because that is what the token carries.

**Scopes are derived, not restated.** `/roles` is `GROUP_SCOPES`
re-expressed; a person's `scopes` is `scopes_for_user` (the login path's
own function); the HTTP suite recomputes every person's scopes from
`/roles` × `roles_effective` and fails on drift. An API credential's
`scopes` are the credential's own (`scopes_source: "credential"`) because
`/auth/token` mints from `client.scopes`, not from groups; its groups are
`SCOPE_GROUPS`' legibility mirror and grant the token nothing.

**`?role=` is an ORM filter on 19.** `all_group_ids` declares
`search='_search_all_group_ids'` → `group_ids.all_implied_ids`
(`res_users.py:258, 451`), so `total_estimate` is honest. Proved live:
`?role=asset_user` returns `admin, cadra_client_test_client, h41_manager,
h41_leaver, h41_tagger_paired`; `?role_direct=asset_user` returns
`cadra_client_test_client, h41_leaver, h41_tagger_paired`.

**Guards:** five `INVENTORY` rows in `tests/test_query_param_guard.py`
(`q` text, `role`/`role_direct` enum, `active`/`is_api_client` bool); no
`*serialize*` function and no `_fields`/`getattr` guard, so
`test_published_names_resolve.py` needed nothing.

## C · The screen

`Frontend/artifacts/nrs-asset-register/src/pages/admin/Users.tsx`,
`AccessChanges.tsx`; routes `/admin/users`, `/admin/users/:id`,
`/admin/access-changes`; a new *Administration* nav group (*Users*,
*Access changes*) — the first scope-gated nav items in the app
(`NavItem.scope`, filtered through `useScopes()`), hidden from anyone
without `admin`. Both pages refuse without the scope and render a 403
through `ApiErrorMessage`. Their query keys are excluded from the
persisted cache: a question about right now is never restored from disk.

*Users*: search (server `q`), *Can act as* (effective, says so under the
table), *Status*, *Kind*; columns Name/login, Email, Roles, Kind, Active,
Last sign-in; detail panel with Identity, Roles held, Also holds via
implication, What this account can do (sixteen scopes in words, the raw
scope beside each), and *Access changes for this person →*. Stacks at
phone width; `scrollWidth` 390 on a 390 viewport
(`09-users-phone.png`). Screenshots `06`, `07`.

*Access changes*: the existing `GET /reports/access-changes` for a period
(two date inputs, default 2026-01-01 → today), auto-walking the cursor
because the report pages by account id and a filtered person may be on
any page; `?user_id=` filters client-side; the report's own `summary` and
`fidelity.notes.record_start` rendered above the table so the page says
what it covers. Screenshot `08`.

**Deviation:** the handoff says *link to the existing access-changes
report rather than re-query it*. The report existed as a route and nowhere
in the app. A link to JSON is not a screen, so the page above is the
landing; it adds no data, no server filter and no second record.

**Every control that would change something is absent.** On both pages
the only `<button>`s are filter triggers and options, the panel's Close,
Clear, Load more and the user-filter clearer; the only inputs are one
search and two dates; no `form`, `select`, `textarea`, no `apiPost`/
`apiPatch`/`apiDelete`/`useMutation`. The spec asserts it on the rendered
page (test 4).

## D · Nothing in this handoff writes membership — checked, not asserted

- `access_recorder.py`'s six hooks are on `res.users` `create`/`write`/`unlink`
  and `res.groups` `create`/`write`/`unlink`. Nothing in this diff touches
  `group_ids`, `user_ids` or `implied_ids`: `grep` over the diff for those
  three names hits only docstrings, the serializer's reads and the tests.
- `myservice_api/tests/test_users_endpoint.py` counts
  `myservice.api.access.change`, `res_groups_users_rel` and
  `res_groups_implied_rel` before and after eleven GETs (every route, every
  filter, a 404 and a 400) and asserts all three unchanged.
- **Access-change rows on `test19`:** 0 before this handoff. The two module
  upgrades for the privilege fix wrote **0** (0 → 0, counted either side).
  My four probe users wrote **9** (`user_create`, actor `Administrator`,
  attributable) — four Internal User grants, one role each and the paired
  tagger's second role (ids 16888–16896, all listed in §D); archiving
  `h41_leaver` wrote none, as it should. The tenant's record therefore
  begins at 2026-10-01 21:04:07 with my first probe, which the access-changes
  page says in its own words.
- The fan-out below counts the record on every tenant either side of the
  upgrade.

## E · Verification — suites, with denominators

**CI order: HTTP first.** `CADRA_API_BASE=http://test19.localhost:8069
tests/.venv/bin/python -m pytest tests/ -q`:

```
1 failed, 1147 passed, 10 skipped in 1194.49s (0:19:54)
FAILED tests/test_users.py::test_a_row_where_direct_and_effective_differ_is_explained_by_implies
E   Extra items in the left set: 'security_officer'
```

The one failure is §B's finding (the administrator's Security Officer via
Security Administrator). After adding `via` and rewriting the test:

```
tests/test_users.py: 21 passed in 3.92s
```

The other 1,147 are unchanged by that edit (it touched `v1_users.py`'s
row builder, `v1.py`'s `UserRole` schema and `tests/test_users.py`). The
10 skips are the tenant's standing ten (`CLAUDE.md`, *the skip count is a
function of the tenant*); the run was not given `-rs`, so the reasons are
not in the log — the count matches and the categories are the documented
ones, but I did not re-read each.

**Then the in-registry suite**, `-u myservice_api --test-enable
--test-tags /myservice_api --workers=0`:

```
odoo.tests.result: 0 failed, 0 error(s) of 295 tests when loading database 'test19'
```

8 of those are `test_users_endpoint.py` (direct vs effective on a manager
the test creates; the tagger's `scopes == ["tagging:write"]` and equal to
`scopes_for_user`; the test's own admin credential as `kind:
api_credential`, `scopes_source: credential`; zero rows written on all
three tables). The `ERROR odoo.sql_db: cannot execute INSERT in a read-only
transaction` lines in the log come from the audit-report suites' read-only
proofs, as before; `0 failed, 0 error(s)` is the result line.

**Browser**, `e2e/tests/41-who-has-what.spec.ts` on `test19`: **6 passed**
(final run after every change; three earlier runs are in §F).

**The station after the sudo change**: the drive in §A.2 (two users, 84
calls); the tag-affixed write path is untouched and I did not re-run specs
39/40.

**Fan-out** (`-u myservice_asset_register,myservice_api` on each tenant,
serially, after the suites):

| Tenant | rc | ERROR/CRITICAL lines | Modules loaded | groups with a privilege | access rows before → after |
|---|---|---|---|---|---|
| cadra19 | 0 | 0 | yes | 4 of 4 | 0 → 0 |
| nrs19 | 0 | 0 | yes | 4 of 4 | 3 → 3 |
| gtb19 | 0 | 0 | yes | 4 of 4 | 0 → 0 |
| test19 | 0 | 0 | yes | 4 of 4 | 9 → 9 |
| nrs | 0 | 0 | yes | 4 of 4 | 0 → 0 |
| lasg | 0 | 0 | yes | 4 of 4 | 0 → 0 |
| gtb | 0 | 0 | yes | 4 of 4 | 0 → 0 |
| jaizbankplc | 0 | 0 | yes | 4 of 4 | 0 → 0 |

The four groups counted are Asset User, Asset Manager, Tag-Issuing Unit
and Auditor. `nrs19`'s three rows predate this handoff.

Odoo restarted after the fan-out; `/api/v1/brand` 200.

## F · What the verification found on the way

1. **The spec's inactive-filter test skipped on a tenant that has an
   inactive account** — its poll accepted an empty table mid-refetch as
   "none to prove on". Now asks the API for the inactive count first and
   waits until the table holds exactly that many. Spec, not page.
2. **The access-changes test counted zero events for a person who had
   two** — between the first page's request and its render there is
   neither a row nor the empty state, and `walk-progress` is absent too.
   Now waits for a row or the empty state before counting. Spec, not page.
3. **The email column wrapped one character per line** at 1366px
   (`break-all` in a narrow cell). Now `nowrap` + truncate with the full
   address in the title. Page.
4. **`via` on effective roles** — §B. API, schema, reference, page, test.
5. **I edited `v1.py` while the API builder owned its schema block.** The
   partition rule in `CLAUDE.md` says two agents never edit one file; my
   barcode helper and the builder's three schemas are in the same file.
   Verified afterwards by `grep` (five occurrences of the helper, syntax
   check) rather than prevented. Recorded in `docs/GO-LIVE.md` §18.2 so
   it is not repeated.

## G · The three questions for handoff 42

**1. What refuses a privilege escalation today? Nothing in Cadra.** Odoo
core has two constraints on `group_ids`: `_check_disjoint_groups`
(portal/public/internal are exclusive) and `_check_at_least_one_administrator`
(`res_users.py:536, 550`). Writing `group_ids` needs the *Access Rights*
ACL (`base.group_erp_manager`, `ir_model_access` on `res.users`) — and
every v1 route runs `sudo()`, which does not consult it. So a route that
wrote `group_ids` tomorrow would let any `admin`-scoped caller grant
`base.group_system` to anybody. For a PERSON `admin` is minted only from
`base.group_system`, so there is nothing to escalate to; the exposure is
an **API credential with the `admin` scope**, whose user is deliberately
NOT a system administrator (`SCOPE_GROUPS` maps `admin` to no group) and
which could make its own user one. `groups_for_scopes` refuses to invert
`admin` for exactly this reason, and the access record would write the
grant down and refuse nothing. **42 has to put the refusal in the model,
under every writer**, where the approval gate and the disposal guard are —
and decide whether `base.group_system` is grantable over the API at all.

**2. Is mail configured on any tenant? No.** 0 of 8 local databases have
a row in `ir_mail_server` (all eight: `outgoing_servers=0`,
`mail.catchall.domain` unset). Staging's deploy workflow wires
`SMTP_HOST/PORT/USER/PASS` and `CADRA_EMAIL_RELAY_URL` as OPTIONAL
variables (`.github/workflows/deploy-dev.yml:26–29, 172–174`); whether the
cluster has them set is the owner's to say. 43 cannot assume an invitation
is delivered.

**3. Does `auth_signup` exist here? Yes, on 8 of 8** — `installed`, with
`auth_signup.invitation_scope = b2c` and `auth_signup.reset_password =
True` everywhere. `_create_user_from_template` is a `copy()` of
`base.default_user` (groups cloned, never in `vals`); the recorder's
`create` hook already diffs that correctly. 43 can create people through
it; the invitation it sends needs the mail above.

## Deviations from the handoff

- **`category_id` does not exist on `res.groups` on 19** — built the
  privilege records that the 19 form actually reads (§A.1). The handoff's
  diagnosis (empty category, invisible groups) was right; its prescription
  named a 15-era field.
- **The Auditor got a privilege too** (one group beyond the three).
- **Four barcode wrappers changed to sudo** — a Python change the handoff
  did not ask for, found by the drive it did ask for. Without it the
  pairing it leans to still leaves one red panel on the station.
- **`via` added to `roles_effective`** — found by the suite.
- **An *Access changes* page was built** because the report had no screen
  to link to.
- **The probe users are left on `test19`** (four, `*(probe)*`,
  `example.invalid`); the spec and the HTTP suite skip with a reason where
  they are absent, so another tenant is not broken by their absence.
- **Specs 39/40 not re-run** after the sudo change; the drive covers the
  station's reads, and the affix write path is untouched.

## Open questions

- `is_test_credential` on `api_client` matches the suite's credential-name
  regex (`credential`); the HTTP test waives that one path and would fail
  on any second. For the Architect: a key named for a credential FLAG held
  to the rule for credentials.
- The seven remaining first-party groups without a privilege
  (`docs/GO-LIVE.md` §18.2) — one record each, in their own modules.
- The access record's `group_name` snapshots now carry the privilege
  prefix; nothing reads them for equality, but a report grouping by that
  column across 2026-10-01 would see two labels for one group.

## Needs the owner

- **Merge the PR** (the Builder's permission layer refuses `gh pr merge`).
- Staging: push rolls the frontend only; the three new routes and the
  privileges need the `upgrade-19` job on every tenant
  (`docs/ENVIRONMENT-FACTS.md`, memory: a new-route 404 on staging means
  the upgrade did not run).
- Say whether the cluster has `SMTP_*` set — it decides 43's design.
- The four `Frontend/Cadra *.png|svg` files in the working tree are the
  owner's and are not committed here.

## Commits

COMMITS_TABLE
