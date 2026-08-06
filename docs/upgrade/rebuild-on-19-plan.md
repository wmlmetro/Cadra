# Rebuild on Odoo 19 — Plan

**Date:** 2026-08-04
**Decision:** Instead of sequential OpenUpgrade (15→16→17→18→19, blocked at 16 by CRND
service-desk availability), **rebuild the app fresh on an Odoo 19 base**. Bring the
functionality we have on 15 forward by reimplementing the in-house modules against 19 APIs,
installing the CRND generic layer (which ships for 19), and **dropping the crnd_wsd /
crnd_service_desk service-desk layer** (barely used — see below).
**Data:** fresh start per tenant — re-seed on 19, no ETL. Historical/closed records are an
accepted loss; capture *current* operational state into seed form for the two live tenants.

## Why the rebuild is tractable (evidence)

- crnd_wsd/crnd_service_desk are referenced in exactly one meaningful place:
  `myservice_request_fields/controllers/portal.py` extends `crnd_wsd`'s `WebsiteRequest`.
  (`myservice_security/controllers/portal.py`'s import is vestigial — plain `http.Controller`.)
- The real backbone model is `request.request` (from `generic_request`, **available on 19**);
  5 in-house models inherit it.
- Other inherits are stable core Odoo: `fleet.vehicle`, `hr.employee`, `ir.http`, `ir.mail_server`.
- Primary UX is the React SPA + `myservice_api` (~59 routes), which never touches CRND's portal.
- Net: dropping the CRND desk layer costs **one portal submission flow**, replaced by the
  existing React/`v1_requests.py` path or a small custom controller.

## Foundation on 19 — licensing reality (2026-08-04, verified against CRND git)

The foundation splits into three tiers. This is the crux of the whole rebuild: **the only hard
commercial blocker is `generic_request`.**

| Tier | Modules | 19.0 source | Action |
|---|---|---|---|
| **Free** (LGPL-3) | `generic_mixin`, `generic_m2o`, `generic_tag`, `generic_rule`, `generic_condition*`, `base_field_*` | public monorepo, 19.0 branch | **Vendored** → `crnd-19/` via `scripts/fetch-crnd-19.sh` |
| **LGPL-3, gated source** | `generic_service`, `generic_resource`, `generic_location`, `generic_team` | gated CRND repo (needs account) | Get via CRND account **or port our 15.0 `dist/<mod>` forward** (allowed under LGPL-3) |
| **Paid (OPL-1)** | **`generic_request`** — the `request.request` backbone | gated, proprietary | **Buy a CRND 19.0 licence, OR replace with an in-house request model** |

Notes: the public `generic-addons` monorepo no longer ships the service/resource/location/team
modules on 19.0 (they did at 16.0) — they're LGPL but only in gated repos now. `crnd_wsd` /
`crnd_service_desk` and all `crnd_web_*` widgets are **dropped**. **To verify:**
`generic_request_location` (dep of request_fields) — fold into request_fields if unavailable.

## The one strategic decision: `generic_request` → DECIDED: REPLACE (full CRND independence)
Built in-house as module **`myservice_request_core`**, which *provides* the `request.request`
model name (plus `request.stage`, `request.stage.type`, `request.stage.route`, `request.type`,
`request.category`, `request.tag`, `request.event`, `request.event.type`). Keeping the model
names means the 5 dependent modules + the API serializer change only a one-line manifest dep
(`generic_request` → `myservice_request_core`) instead of a 63-site rename.
Field surface derived from the API contract (`v1_requests.py` serializer): stages with
codes+types+routes, events, ITIL `impact`/`urgency`/`kanban_state`, `response_text`,
`parent_id` subrequests, `tag_ids`, `date_assigned`/`date_moved`. **Status: written &
syntax-validated; not yet booted** (needs the LGPL generics below present at 19).

## Infra scaffolded (P0, done on branch feat/rebuild-odoo-19)
- `Dockerfile.odoo.19.dev` — `FROM odoo:19.0` (Python 3.12) + pip deps.
- `config/odoo.19.conf` — 19 config (`gevent_port` replaces `longpolling_port`; addons_path =
  core + repo root + `crnd-19/`; `dist/` deliberately off-path).
- `docker-compose.19.yml` — full override, used as
  `docker compose -f docker-compose.yml -f docker-compose.19.yml up -d` (replaces dev.yml).
- `crnd-19/` — free LGPL foundation vendored; `scripts/fetch-crnd-19.sh` reproduces it.
- **Boot is blocked only on** the LGPL generics (port/fetch) + `generic_request` (decision above).
  Docker CLI isn't available in the agent shell, so the first boot is run by the user.

## Reimplementation order (topological, from manifests)

| # | Module | LOC | Key work driver |
|---|---|---|---|
| 1 | `myservice_nrs_base` | 261 | base for all; light |
| 2 | `myservice_request_fields` | 734 | **replace crnd_wsd portal**; `request.request` extension |
| 3 | `myservice_asset_register` | 3260 | 10 models; views (`attrs=`/`states=` rewrite) |
| 4 | `myservice_identity` | 1365 | 5 models; hr/fleet inherits |
| 5 | `myservice_fleet_maintenance` | 1347 | fleet + generic_request |
| 6 | `myservice_fm_dashboard` | 637 | OWL2 JS |
| 7 | `myservice_staff_bus` | 1797 | 7 models |
| 8 | `myservice_security` | 2945 | 6 models; **OWL2 JS** (dashboards); portal template |
| 9 | `myservice_workflow` | 1231 | 5 models; request automation |
| 10 | `myservice_dashboard` | 1021 | **OWL2 JS** |
| 11 | `myservice_barcode_station` | 1006 | **OWL2 JS** (scanner UI) |
| 12 | `myservice_theme_v5` / `_theme` / `_website_theme` | ~970 | assets + OWL2 |
| 13 | `myservice_email_relay` | 223 | `ir.mail_server` inherit |
| 14 | `myservice_api` | 4128 | **59 routes** ported to 19 `odoo.http`; last |
| 15 | `cadra_brand_{nrs,jaiz,gtb,lasg}` | ~260 | per-tenant brand; trivial |

Trivial modules (brands, themes) are fast; the effort concentrates in asset_register, security,
api, staff_bus, and the OWL2 JS in dashboard/barcode/fm_dashboard/security.

## Cross-cutting port work (Odoo 15 → 19)

- **View syntax:** Odoo 17 removed `attrs=` and `states=` — rewrite to inline attribute
  conditions across all XML views. Mechanical but broad.
- **OWL2 JS:** legacy widgets → OWL2 components in the JS-heavy modules.
- **Asset bundles:** manifest `assets` blocks already used; verify bundle names for 19.
- **Python:** ORM largely stable; touch-ups for deprecated APIs. Target **Python 3.12**.
- **Portal replacement:** fold the request-submission flow into React/`myservice_api`, or a
  small standalone controller — no dependency on `crnd_wsd`.

## Infrastructure

- New base image: `FROM odoo:19.0` (Python 3.12) — new `Dockerfile.odoo.dev` / `.k8s`.
- `odoo.conf` addons_path unchanged in shape; point at CRND-19 generic addons + in-house.
- Update `docker-compose.*.yml` image tags and the k8s dev manifests to the 19 image.
- Keep the existing multi-tenant dbfilter / brand-at-runtime approach intact.

## Per-tenant bring-up (fresh start)

For each tenant (staging/NRS, GTB, Jaiz, LASG):
1. Fresh 19 DB, install foundation + in-house module set + tenant brand module.
2. Re-seed via `myservice_master_seed.py` + `load_offices.py` (adapt to 19 if needed).
3. For **live** tenants (Jaiz, LASG): capture current-state (open requests, live assets,
   active staff) into seed data so they don't launch empty.
4. Per-tenant smoke test: `/web/login`, `/api/v1/brand`, React `/app`, request submission,
   asset register, dashboards.

## Suggested phasing

- **P0 — Spike:** stand up Odoo 19 base + install CRND foundation + get `myservice_nrs_base`
  and `myservice_request_fields` (with replaced portal) booting on one clean DB. Proves the
  foundation and the crnd_wsd-drop before committing to the full port.
- **P1 — Core data modules:** asset_register, identity, fleet_maintenance, staff_bus, workflow.
- **P2 — UX/JS:** dashboards, fm_dashboard, barcode_station, themes (OWL2).
- **P3 — API + security portal:** myservice_api (59 routes), myservice_security.
- **P4 — Brands + per-tenant re-seed + smoke tests.**
- **P5 — Cutover:** deploy 19 per tenant, re-onboard, retire 15 stack.

## VALIDATED MILESTONE (2026-08-04)
On a fresh Odoo 19 DB (`test19`), the CRND-free foundation **installs and functions**:
`generic_service`, `generic_team`, `generic_location` (ported LGPL, 19) + `myservice_request_core`
all `installed`, exit 0. Smoke test: `env['request.request'].create(...)` → `REQ-000001`, default
stage "New", `closed=False`; moving to "Resolved" → `closed=True`, `date_closed` set, 2 events logged.
The "replace generic_request" architecture is proven on real 19.
- Reproduce: `docker` at `/usr/local/bin` (prepend PATH); `docker compose -f docker-compose.yml -f
  docker-compose.19.yml run --rm --no-deps odoo odoo -d test19 --data-dir=/tmp/o19
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons/crnd-19,/mnt/extra-addons
  -i myservice_request_core --without-demo=1 --stop-after-init`
- Deferred (cosmetic backend views, re-add later): generic_location/service `res.config.settings`
  views + `res_partner` smart buttons; generic_team `res_users` Teams tab. Models kept; only views dropped.
- Not yet ported: `generic_resource` (needed at the asset_register stage, not before).

## Odoo 15→19 migration cheat-sheet (empirically found porting the generics)
Apply these to every remaining module port:
- **res.groups refactor:** `category_id` removed (now via `res.groups.privilege`) — drop it; `users` →
  `user_ids`; `ir.ui.view.groups_id` → `group_ids`; `res.users.groups_id` → `group_ids`; domain paths
  `...users...` → `...user_ids...`.
- **Views:** `<tree>` → `<list>`; `attrs="{...}"` → inline `invisible=/readonly=/required=` expressions;
  `t-esc` → `t-out`. Search views: group-by `<group>` takes **only `name`** (no `expand`, no `string`);
  no `<field>` after `<filter>`/`<separator>`.
- **Actions:** `act_window.target` has no `inline` (use `current`/`new`/`fullscreen`/`main`).
- **res.config.settings** view structure changed (`<div class="settings">`/`app_settings_block` →
  `<setting>`); partner/users smart-button form inheritance changed — port later or defer.
- **Python:** `name_get()` → `_compute_display_name`; `create` must be `@api.model_create_multi`
  (list); `_name_search(name, domain, ...)` new signature.
- **Infra:** base `odoo:19.0` = Python 3.12; conf uses `gevent_port` (not `longpolling_port`);
  `--without-demo=1` (not `all`); give test runs their own `--data-dir` to dodge shared-volume perms.

## STATUS: full app installs on Odoo 19 (2026-08-04)
Every module installs on a fresh Odoo 19 DB (`test19`), exit 0, and the backend
web client serves authenticated (`/web` = 200; `web.assets_backend.js` bundle
compiles). Commits: `1c4fb04`, `fa1ac9a`, `180a592`, `217a26b`, `8e45ec9`.

**Installed & boot-verified (27):** LGPL foundation (generic_service/team/
location/resource/mixin/tag/rule/m2o) + OCA `web_responsive` (oca-19/) +
`myservice_request_core` + all 14 feature modules (nrs_base, request_fields,
asset_register, identity, fleet_maintenance, staff_bus, security, workflow,
dashboard, fm_dashboard, barcode_station, theme, theme_v5, website_theme,
email_relay, api) + `cadra_brand_nrs`. Brands gtb/jaiz/lasg got identical
transforms (per-tenant, not co-installed).

**Remaining known work (needs a browser to validate — not caught by
--stop-after-init):** legacy OWL/JS in 6 modules still uses `odoo.define` +
`require('web.*')` (dashboard, fm_dashboard, barcode_station, security, theme,
theme_v5). The bundle *includes* them (Odoo 19 still processes odoo.define), but
whether each executes depends on legacy base classes (e.g. web.AbstractAction)
still existing in 19. Validate in-browser; rewrite to OWL2 (or disable pending
rewrite) any that throw. React SPA UX (/app) is independent of this.

**Deferred cosmetic — DONE (2026-08-06):** generic_location/service
res.config.settings (ported to 19 `<app>/<block>/<setting>`) + res_partner
smart buttons (Locations stat button, Service Info page); generic_team
res_users Teams tab. All 5 views re-added to manifests and browser-verified
rendering on cadra19 (Odoo 19). 19 gotcha applied: inherited views can't set
`group_ids` on the record — moved `groups=` onto the button/page elements.
**Runtime ref to fix:** website_theme api.py uses env.ref('generic_request.
request_channel_website') — request_core has no channels (runtime-only).

## Risks / open items

- `generic_request_location` on 19 unconfirmed — verify early in P0 (fallback: fold its fields
  into request_fields directly).
- OWL2 rewrites are the least predictable effort — front-load one JS module in P0/P1 to calibrate.
- Live-tenant "current-state capture" scope (what counts as launch-critical) needs a per-tenant
  decision with the client before cutover.
- Frontend (React SPA) may need API-contract updates if `myservice_api` route shapes change on 19.
