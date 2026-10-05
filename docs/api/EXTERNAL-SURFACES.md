# HTTP surfaces outside `/api/v1`

**What this is:** an inventory of every first-party HTTP route in this repo
that is **not** under `/api/v1/*`, with who calls it, whether its shape is
published anywhere, and whether changing it breaks something.

**Why it exists.** Handoff 15 changed three status codes on
`/myservice/workflow/callback` — correctly, and the change was right — and
then found that `docs/api/CHANGELOG.md`'s own rule does not reach it, because
the rule is scoped to `/api/v1/*`. That route is POSTed to by the NRS
WorkSpace, and Cadra publishes its URL to that system from
`workflow_config.py`. So there was a surface an external organisation calls,
whose behaviour we changed, with no document anywhere that owed anyone a
word about it. Nobody knew how many more of those there were.

> **Handoff 17 closed the three findings below.** The section
> [Three things a reader must not have to derive](#three-things-a-reader-must-not-have-to-derive)
> is kept, rewritten, because a reader arriving at these routes still has to
> know what they used to be: the credentials involved were published in this
> repository's history and are being rotated, and a route whose defect has
> been fixed in `dev` is still open on anything not yet deployed. Each entry
> now says what was true, what is true now, and what still needs doing.

**This is an inventory, not a contract.** Nothing here is promised to
anybody. It says what exists, who is on the other end of it, and what would
break — so that the next person changing one of these knows, in one place,
whether they are touching a private detail or somebody else's integration.
See [What would make one of these a contract](#what-would-make-one-of-these-a-contract).

---

## The counts

**27 routes**, across **9 controller files** in **7 modules**.

| | routes |
|---|---|
| Called by an **external organisation** | **4** |
| Called by an **anonymous browser** (public portal / homepage) | **5** |
| Called by **our own Odoo web client**, and nothing else | **8** |
| **No caller at all** | **10** |
| **Total** | **27** |

**Published shape: 0 of 27.** Not one of these paths appears in
`docs/api/cadra_api_endpoint_reference.md`, the OpenAPI spec, the demo guide,
`README.md`'s endpoint table or `docs/api/CHANGELOG.md`. Every `docs/` hit for
one of these paths turns out to be its `/api/v1` mirror — the reference
documents `POST /api/v1/integrations/workflow/callback`, which is a
**separate handler** from the legacy callback, and `GET /api/v1/tags/lookup`,
which is a separate handler from `/tags/lookup`. Five of the 27 are described
in `docs/retired-screens.md`, but that document records that they are dead,
not what they answer.

**How the number was arrived at** (original derivation, 2026-09; re-derived
2026-10-04 by handoff 50). The 2026-09 derivation said 36 `@http.route`
decorators, 9 of them raw pre-envelope `/api/v1` routes, 65 `@cadra_route`
sites, 36 − 9 = 27. The API has grown since: as of 2026-10-04 there are 13
raw `/api/v1` `@http.route` sites (v1.py 8, v1_brand 2, v1_signup 3) and
~107 `@cadra_route` sites — and the 27 routes OUTSIDE `/api/v1` inventoried
here are still exactly 27 (25 take a body or are non-GET, 2 are GET-only),
plus the four `backoffice.py` overrides of core routes, counted separately
below. **Since handoff 50 the count is no longer maintained by hand:** the
widened census in `myservice_api/tests/test_published_names_resolve.py`
walks every first-party `controllers/*.py` and FAILS on any body-taking
route that is not classified — this file describes the callers; the census
guards the set.

---

## Core routes Cadra changes the behaviour of — handoffs 43 and 45

Not first-party routes, so not in the inventory below, but a reader of
this file would otherwise have to derive them. Since handoff 45 every one of
them is overridden in `myservice_api/controllers/backoffice.py` (one class,
`CadraBackOfficeDoor`, a subclass of core's `AuthSignupHome`), and the rule
they share is *the back office is for system administrators; everybody else
is sent to the app*.

| Route | What Cadra does to it | Where |
|---|---|---|
| `GET/POST /web/signup` | **Always 404 without an invitation token**, on every tenant, whatever `auth_signup.invitation_scope` or `website.auth_signup_uninvited` say. `res.users._get_signup_invitation_scope` returns `b2b` as a constant — the owner's ruling that nobody signs themselves up to a government asset register. With a token (the letter's link) the page works as before | `myservice_api/models/invitation.py` |
| `GET/POST /web/reset_password` | The **email it sends is Cadra's** (tenant brand, organisation name, link on the request's host) instead of Odoo's QWeb letter, because the one method every reset and invitation ends in, `res.users._action_reset_password`, is overridden | same file; `myservice_api/data/mail_templates.xml` |
| `GET /web/signup?token=…`, `GET /web/reset_password?token=…` (handoff 45) | **303 to `/app/accept-invite?token=…` / `/app/reset-password?token=…`**, the same token — every letter sent before handoff 45 carries the old link. A token-less `GET /web/reset_password` goes to `/app/forgot-password`. POST is core's, untouched | `myservice_api/controllers/backoffice.py` |
| `/web`, `/odoo`, `/odoo/<path>`, `/scoped_app/<path>` (handoff 45) | A signed-in **non-administrator** is signed out of Odoo and sent to `/app/`; an **anonymous** visitor is sent to `/app/`; a system administrator gets the back office as before | same file |
| `POST /web/login` (handoff 45) | Core's login, then — for a **non-administrator** — the Odoo session is ended and the person is sent to `/app/`. `GET /web/login` is untouched (the administrators' door, and the k8s probes' target) | same file |

Measured before the change, 2026-10-02: `/web/signup` already answered 404
on all 4 cluster hosts and all 8 local tenants — not because of the
parameter (`b2c` on 8 of 8) but because the `website` module's per-site
field, `b2b` by default, overrides it. One click in *Settings › Customer
Account* would have opened it. Now nothing does.

## Three things a reader must not have to derive

### `/myservice/workflow/callback` had optional authentication — FIXED in handoff 17

It is `auth='public'`, `csrf=False`, `methods=['POST']`, and it mutates
`request.request` state. Its token check **used to be conditional**:

```python
# the defect, as it stood
if config.callback_token:
    provided = (request.httprequest.headers.get('X-Callback-Token')
                or kwargs.get('token', ''))
    if provided != config.callback_token:
        ... 401
```

A tenant whose `workflow.config` had no `callback_token` had **no
authentication on this route at all** — an anonymous POST could approve or
reject a request. The token was a field an administrator may or may not have
filled in; nothing forced it and nothing warned when it was empty.

**This was not hypothetical and it was not rare. It was the state of every
tenant.** Measured on this machine at handoff 17: `callback_token` was set on
**0 of 8** local tenants. Proved live before the fix, on `test19` with a
`workspace` config carrying no token — an anonymous POST, and a POST with a
deliberately *wrong* token, both answered

```
HTTP 404  {"error": "Request 'H17-PROBE-NO-SUCH' not found"}
```

A route that reports a reference lookup to a caller holding a wrong credential
has already passed its authentication gate. The only thing between an
anonymous POST and an approval was knowing a reference name.

**Now:** a missing token refuses every callback with `503` and the same opaque
body an unwired tenant already gets, and logs at ERROR naming
`workflow.config.callback_token` and the tenant database. The `?token=` query
parameter is still accepted **for one more release** and every use logs a
WARNING naming the caller, so the migration has a visible end date. The header
is `X-Callback-Token`.

**Still open, and it is its own piece of work:** a replayed callback is **not
idempotent**. A second byte-identical POST answers `200 {"ok": true}`, appends
a second dispatch-log row, re-posts chatter, and — where
`approved_stage_id`/`rejected_stage_id` is configured — re-applies the stage
write, which drags a request a human had moved onward back to the approved
stage and appends a `request.event` row through `_log_event('stage_changed')`
even when the stage does not change. Nothing here fires on a *transition*, the
way `_mark_affixed` does for INT-05.

### The Redhubs and SAP credentials had a default baked into source — FIXED in handoff 17

`export_assets_csv` read its key from `request.httprequest.args.get('api_key')`
— a query string, which lands in nginx access logs, any intervening proxy's
logs, and browser history. Its JSON sibling used an `X-API-Key` header, which
is the right shape.

Worse than the query string: **all three routes fell back to a literal in
source.**

```python
# the defect, as it stood
get_param('myservice_identity.redhubs_api_key',  'NRS_REDHUBS_KEY_2025')
get_param('myservice_identity.sap_webhook_secret', 'NRS_SAP_WEBHOOK_SECRET_2025')
```

The second argument is the default. **Measured at handoff 17: neither
parameter was set on any of the eight local tenants** — `myservice_identity.*`
returned zero rows on all of them. So the credential guarding a full dump of
the asset register, and the one guarding inbound employee writes, was in every
case a string committed to this repository, present in every clone, every fork
and every CI log since it was written.

**Now:** unset configuration refuses and says so at ERROR naming the parameter
and the database; the CSV route is header-first with `?api_key=` deprecated
for one release under a WARNING naming the caller; each credential is resolved
in exactly one place per module; comparisons are `hmac.compare_digest`.

**Both literals are compromised and must be rotated on the box** — they are in
git history and cannot be taken out of it. They are quoted above deliberately:
a rotation list that will not name what it is rotating is not one an operator
can work through. `tests/test_source_guards.py` now fails the build on any
credential resolved with a non-empty literal default, and pins these two
strings out of first-party source.

**This is a live cutover, not a silent one.** Any tenant relying on the
default now answers Unauthorized to Redhubs and to SAP until an operator sets
the parameter.

### `/tags/lookup` is unauthenticated where its `/api/v1` twin is scope-gated

`GET /api/v1/tags/lookup` requires a JWT carrying `assets:read`.
`/tags/lookup` is `auth='public'`, `type='json'`, runs `sudo()`, and has no
scope check of any kind. Both answer the same question — hand it a tag number,
an asset code or, since handoff 38, a serial number, and it returns the
asset's name, category, location, condition, state and last service date, plus
`matched_by` saying which of the three it was. (Until handoff 38 the serial
branch did not exist on either route while the `/api/v1` twins documented it,
so the serial of a tagged asset found nothing.) Both resolve through one
helper, `_resolve_lookup` in `myservice_barcode_station/controllers/main.py`,
so they cannot drift apart again. The public one exists for the field-team portal
scanner at `/tags`, which is deliberately login-free; the point is only that
the gate on one is not the gate on the other, and a reader who has seen the
`/api/v1` route will assume it is.

---

## 1 · Called by an external organisation — 4 routes

These are the ones that matter. Something outside this codebase, owned by
someone else, sends requests here.

| Route | File | Auth | Who calls it | Shape published? | Is a change breaking? |
|---|---|---|---|---|---|
| `POST /myservice/workflow/callback` | `myservice_workflow/controllers/callback.py:43` | `public`, `csrf=False`; **optional** shared token | **NRS WorkSpace.** Cadra tells it this URL: `workflow_config.py:243` computes `callback_url_hint` as `<web.base.url>/myservice/workflow/callback` and shows it in Settings | No | **Yes.** This is the only route in the repo whose URL Cadra actively publishes to a third party. Status codes, the accepted payload keys (`reference`, `workspace_ref`, `outcome`, `payment_ref`, `comment`) and the `outcome` enum are all load-bearing for WorkSpace. Handoff 15 changed three status codes here |
| `POST /api/myservice/assets/export` | `myservice_identity/controllers/redhubs_api.py:117` | `none`, `csrf=False`; `X-API-Key` header | **Redhubs**, an external system | No | **Yes.** It returns the whole asset register with a fixed 13-key row shape. Renaming or dropping a key breaks their parser silently; there is no version marker in the payload to hang a migration on |
| `GET /api/myservice/assets/export/csv` | `redhubs_api.py:183` | `none`; `?api_key=` **query parameter** | Redhubs, for systems that cannot do JSON | No | **Yes**, and worse than the JSON one: the CSV is positional. Inserting a column in the middle silently shifts every field after it, and a CSV consumer has no way to notice |
| `POST /api/sap/employee-sync` | `myservice_identity/controllers/sap_webhook.py:73` | `none`, `csrf=False`; `X-SAP-Webhook-Secret` header | **SAP SuccessFactors**, pushing employee change events — **but nothing ever has, and nothing can**: the secret is set on 0 of 8 tenants, nothing in the repo provisions it, and 0 of 287 sync-log rows are `webhook` (measured 2026-10-03) | No | **Ruled for retirement (handoff 37 §A): SAP gets pointed at `POST /api/v1/integrations/sap/employee-sync`**, which authenticates and validates; this door stays up unchanged until that conversation lands. A request key the feed does not read is now an `error` row naming it (handoff 37 §2B, a narrowing announced in `CHANGELOG.md` — reachable by no caller while the secret is unset). Know before relying on this door: **on Odoo 19 it cannot create or update an employee at all** (`hr_version.last_modified_uid` NOT NULL vs an `auth='none'` environment with no user — every write errors per-row under a top-level `success: true`), and the list shape its docstring offers is refused by the JSON-RPC dispatcher before the route runs. The **response** shape (`success`, `processed`, `results[]` with `ir_number`/`status`/`employee_id`/`changes`) is read by whatever calls it |

**The callback's twin, and how handoff 17 resolved it.**
`POST /api/v1/integrations/workflow/callback` exists, is scope-gated on
`integrations:write`, returns the PRD §10.7 envelope, validates against a JSON
schema and is fully documented — and it is a **different function** from the
legacy one. Two callbacks, one documented and one in use.

**They are genuinely different contracts, and the documentation is wrong about
which is which.** Handoff 17 was asked to choose between making the legacy
route a thin delegate to the `/api/v1` one, repointing WorkSpace, or accepting
that they differ. The answer is the third, and the deciding fact is that
**"one implementation and two paths" is already true of everything that can be
shared.** Both controllers call the same three model methods —
`request.request._workflow_callback_approved` / `_rejected` / `_queried` — so
there is exactly one implementation of what an outcome *does*. What is left
duplicated is only the HTTP layer, and every part of it differs for a reason
that cannot be delegated away:

| | `/myservice/workflow/callback` | `/api/v1/integrations/workflow/callback` |
|---|---|---|
| Authentication | shared token from `workflow.config` | JWT bearer, `integrations:write` |
| Body | JSON **or form-encoded** | JSON only, schema-validated |
| Response | bare `{"ok": true, …}` | PRD §10.7 envelope |
| Idempotency | none | `X-Idempotency-Key` |
| Dispatch log | **reconciles** the outbound `sent` row it answers | ~~always appends a new inbound row~~ — **fixed in handoff 18**: both now share `workflow.dispatch.log._reconcile_callback` |
| Replay | fires on the transition; a replay does not re-apply the outcome and answers `200 {"replayed": true}` | same decision, same model method, `"replayed": true` in `data` |
| Late `payment_ref` on a replay | **recorded** on the request and reported as `stored_fields` (handoff 20) | same, as `data.stored_fields` |
| Repeat `queried` | dedups on `(outcome, comment)`: the same question again is a replay, a NEW question **applies** (handoff 20) | same decision, same model method |
| Contradiction | `409` naming both outcomes | `409 conflict`, `details.current_outcome` / `details.attempted_outcome` |
| Unconfigured tenant | `503`, opaque body (handoff 15) | `503 server_misconfigured`, opaque body (**handoff 18**) |

The authentication line is the one that settles it: WorkSpace holds a shared
token, not a Cadra client credential, and a public route cannot delegate into
a decorator that demands a JWT without either issuing WorkSpace a client (that
is the "repoint WorkSpace" option, a coordinated change with another team) or
weakening `/api/v1`. Neither is a refactor.

**So what needs doing is documentation, not code** — and two defects fall out
of writing the table:

1. **The v1 twin never reconciles the outbound dispatch.** The legacy route
   finds the `direction='outbound', status='sent'` row it is answering and
   rewrites it to the outcome; the v1 route always appends a fresh inbound
   row. On a tenant using v1 an answered dispatch reads `sent` forever, so
   "which dispatches are still unanswered" cannot be asked. The legacy
   behaviour is the better one.
2. **The v1 twin leaks the unconfigured-tenant message that handoff 15 removed
   from the legacy route.** It does not resolve `workflow.config` itself;
   `_workflow_callback_approved` calls `get_active_config()` (defaulting to
   `purpose='workspace'`), which raises `UserError` on a tenant with no
   workspace config. `cadra_route`'s `except (UserError, ValidationError)`
   clause renders `str(e)`, so the documented route answers **`400
   validation_failed`** carrying *"No active Workflow integration
   configuration found … Please configure one under Settings → WorkSpace
   Integration"* — an internal menu path in the published envelope, and a
   validation code for what is a tenant-configuration state. Read from source,
   not probed live: reaching it needs a real request reference on a tenant
   with no workspace config, and creating one on a demo tenant to prove a
   documentation finding is not a trade worth making.

**Both were scheduled as handoff 18 B and both are now fixed.**

1. `workflow.dispatch.log._reconcile_callback` is shared by both controllers,
   so the v1 route answers the dispatch it is a reply to. It is scoped to
   exclude `event_type` rows — INT-05 asset events live in the same table and
   also pass through `sent`, and one of those is not an answer to an approval
   request. The defect was **latent, not live**: `_send_to_workflow` has never
   run on any of the eight local tenants, so there is no outbound
   request-approval row anywhere to have been left at `sent`.
2. The v1 route resolves `workflow.config` itself and answers **`503
   server_misconfigured`** with the body *"Workflow integration is not
   available"*, the configuration sentence going to the log at WARNING. This
   WAS probed live in the end, on `jaizbankplc`, before and after: the source
   reading was right, and it turned out cheap to confirm because every tenant
   is an unconfigured tenant (0 of 8 have an active workspace config).
   It now refuses `queried` too, which used to succeed on an unconfigured
   tenant because only the approved/rejected handlers looked a config up.

---

## 2 · Called by an anonymous browser — 5 routes

Public web surfaces. No external organisation integrates against them, but
they are reachable by anyone who can reach the host, and a change is visible
to a member of the public.

| Route | File | Auth | Who calls it | Shape published? | Is a change breaking? |
|---|---|---|---|---|---|
| `GET/POST /security/incident/report` | `myservice_security/controllers/portal.py:20` | `public`, `website=True`, **CSRF enforced** | A public HTML form rendered by the same route (`views/portal_templates.xml:16`) | No | **No.** Route and form ship together in one module, and the form carries `request.csrf_token()`, so nothing can post to it from off-site anyway. **Note it has no inbound link from anywhere in the repo** — it is reachable only by a typed or shared URL |
| `GET /tags` | `myservice_barcode_station/controllers/main.py:341` | `public`, `website=True` | A field team, from a printed/shared URL, and from the backend barcode station's own button (`static/src/xml/barcode_station.xml:213`) | No | **No** — it renders a template that ships beside it. The **URL itself** is quoted to users as `myservice.com.ng/tags` in the station UI, so the path is the thing not to rename |
| `POST /tags/lookup` | `main.py:266` | **`public`, no scope check** | The public portal scanner, `static/src/js/barcode_portal.js:12` | No | **No** for the JS, which ships with it. See the flagged finding above for why it still deserves a look |
| `POST /api/myservice/form-data` | `myservice_website_theme/controllers/api.py:116` | `public`, `csrf=False` | The **static homepage**, `homepage/index.html:527` — deployed by `install.sh:371` to `/var/www/html/index.html` and served by nginx at `location = /` | Effectively | **Yes in practice.** The caller is a static file copied outside the Odoo tree at install time, so it does **not** move when the module upgrades. A shape change here goes live for Odoo and not for the page calling it |
| `POST /api/myservice/quick-submit` | `api.py:165` | `public`, `csrf=False` | Same homepage, `index.html:579` | Effectively | Same as above, and this one **creates records** from an unauthenticated form |

---

## 3 · Called by our own Odoo web client, and nothing else — 8 routes

Internal plumbing between a controller and the JavaScript that ships in the
same module. `auth='user'`, `type='json'`, no external consumer.

| Route | File | Caller | Is a change breaking? |
|---|---|---|---|
| `/myservice/dashboard/kpis` | `myservice_dashboard/controllers/main.py:8` | `static/src/js/dashboard.js:114` | **No** — route and caller ship in one module and upgrade together |
| `/myservice/dashboard/map` | `main.py:13` | `dashboard.js:115` | No |
| `/myservice/dashboard/fleet_command` | `main.py:18` | `dashboard.js:290` | No |
| `/myservice/fm_dashboard/data` | `myservice_fm_dashboard/controllers/dashboard.py:33` | `static/src/js/fm_dashboard.js:80`, and `tests/test_honest_counts.py:69` | No |
| `/barcode/lookup` | `myservice_barcode_station/controllers/main.py` (`lookup_tag`, over `_resolve_lookup`) | `static/src/js/barcode_station.js:135`; the SPA calls its `/api/v1/barcode/lookup` twin | No — handoff 38 ADDED `matched_by`, `serial_number` and `tagged`, and made `tag_id` null (and `tag_number`/`tag_state` empty) for an asset found by code or serial that has no active tag; before that such an asset was a miss |
| `/barcode/kpis` | `main.py:80` | `barcode_station.js:104` | No |
| `/barcode/recent_tags` | `main.py:97` | `barcode_station.js:116` | No |
| `/barcode/print_url` | `main.py:199` | `barcode_station.js:178` and `:236`; covered by `myservice_barcode_station/tests/test_print_url_route.py` | No — but it is the **only path in the repo that renders a label PDF end to end** (handoff 10), so "not breaking for an integrator" is not the same as "safe to break" |

All eight are live: `myservice_dashboard`, `myservice_fm_dashboard` and
`myservice_barcode_station` each ship their JS in a populated
`web.assets_backend` bundle, and all three client-action tags mount in a
browser (see `docs/ENVIRONMENT-FACTS.md`, the legacy shim entry).

---

## 4 · No caller at all — 10 routes

Reachable over HTTP; nothing in this repository calls them, and no external
system is known to.

| Route | File | Auth | Why it has no caller | Is a change breaking? |
|---|---|---|---|---|
| `GET /myservice/workflow/callback/test` | `myservice_workflow/controllers/callback.py:410` | `user` | A manual probe. No JS, no test, no doc references it | **No**, but it is a **status check somebody may be running by hand or from monitoring outside this repo**. Handoff 15 changed it from 200 to 503 for an unconfigured tenant — deliberately, because 200 read a never-wired tenant as healthy |
| `POST /api/sap/employee-sync/test` | `sap_webhook.py:137` | `user` | Same: an authenticated probe for verifying the SAP integration by hand | No |
| `POST /myservice/fleet_dashboard/data` | `myservice_fleet_maintenance/controllers/fleet_dashboard.py:11` | `user` | Its JS caller exists (`fleet_dashboard.js:68`) but **ships in an empty bundle** — `__manifest__.py:42` sets `'web.assets_backend': []`, with a comment explaining the retirement. The tag `myservice_fleet_dashboard` is not in the browser registry. Still exercised by `tests/test_honest_counts.py:49` | No |
| `POST /myservice/security/kpis` | `myservice_security/controllers/main.py:8` | `user` | **`myservice_security/__manifest__.py` has no `assets` key at all** — the module ships no JavaScript. `security_tabs.js` and `security_dashboard.js` exist on disk and are in no bundle | No |
| `POST /myservice/security/map_data` | `main.py:34` | `user` | Same | No |
| `POST /myservice/security/trend` | `main.py:83` | `user` | Same, and it has **never** had a caller in either direction — no JS file references it even among the unbundled ones | No |
| `POST /myservice/security/recent` | `main.py:96` | `user` | Same | No |
| `POST /barcode/untagged` | `myservice_barcode_station/controllers/main.py:120` | `user` | The station's JS does not call it; the SPA uses `GET /api/v1/barcode/untagged` | No |
| `POST /barcode/generate` | `main.py:152` | `user` | Same — the SPA uses `POST /api/v1/barcode/generate` | No |
| `GET /a/<string:asset_code>` | `myservice_website_theme/controllers/api.py:19` | `public` | **Dead in both directions.** No QR generator in the repo emits a `/a/…` URL — the label templates encode the bare `asset_tag` string into the QR (`views/asset_tag_report.xml:98,155`) — and the target it 301s to, `/asset-scan`, **is declared by no controller and no `website.page`**. The only `/asset-scan` references anywhere are two navigation links (`homepage/index.html:478`, `views/website_layout.xml:23`), both of which 404 | No. It is a redirect from nothing to nothing |

The four security routes and the fleet one are the five described in
`docs/retired-screens.md`, which also records two things in that module that
must **not** be tidied up.

---

## What would make one of these a contract

Nothing here is published, so nothing here is owed. Turning one of these into
a real contract takes four things, and the first is the one that costs:

1. **A named consumer, written down.** "Redhubs calls it" is a fact about
   today. A contract names who, at which organisation, so that a change has
   somebody to tell.
2. **The shape in `docs/api/cadra_api_endpoint_reference.md`** — request,
   response, status codes, error bodies — or a dedicated `docs/integrations/`
   document, the way INT-05 has one.
3. **A test that fails when the shape moves**, in the same commit. Rule 6 in
   `CLAUDE.md`. Without it the document drifts and becomes a worse lie than no
   document.
4. **The route in `docs/api/CHANGELOG.md`'s scope**, so a change to it has
   somewhere to be announced. That step is now done for all 27 collectively;
   the other three are per-route.

The obvious candidate for all four is `/myservice/workflow/callback`, because
it is the one Cadra publishes to somebody else. The obvious candidate for
retirement rather than documentation is `/a/<asset_code>`, and the obvious
candidate for a security decision rather than either is the pair of Redhubs
export routes.

---

*Verified against the tree at handoff 16. If you add a route outside
`/api/v1`, add it here — the count at the top is the thing this document is
for.*
