# Retired screens

**Status:** current as of handoff 11 (2026-09-08) · **Ruling:** R54

Three backend screens do not render on Odoo 19 and are not being ported in the
NRS integration programme. Reviving any of them is a project with its own
scope; this note is the estimate.

They are **retired in place**: the source stays in the tree, the entry points
are gone. A menu that opens a broken screen is worse than an absent one, and
code that ships to every browser for a screen nobody can open is worse still.

`tests/test_source_guards.py::test_the_retired_screens_stay_retired` asserts
none of the four tags below comes back into a bundle without an action record
in the same change.

---

## What was retired, and what it was

| Screen | Client-action tag | Files | Verdict |
|---|---|---|---|
| SOC Dashboard | `myservice_security_dashboard` | `myservice_security/static/src/{js/security_dashboard.js, xml/security_dashboard.xml, css/security.css}` — 1,263 lines | **Archive. Do not port.** |
| Security Command Center + Case Management | `nrs_security_command_center`, `nrs_case_management` | `myservice_security/static/src/{js/security_tabs.js, xml/security_tabs.xml, css/security_tabs.css}` — 615 lines | Portable, mechanical, ~2 days |
| Fleet Command Center | `myservice_fleet_dashboard` | `myservice_fleet_maintenance/static/src/{js/fleet_dashboard.js, xml/fleet_dashboard.xml, css/fleet_dashboard.css}` — ~500 lines | Portable, but decide what it is for first |

### What was actually changed in this handoff

Only two manifests:

- `myservice_security/__manifest__.py` — dropped `security.css` and
  `security_tabs.css` from `web.assets_backend`. **`security_navbar.css` was
  deliberately kept** (see the warning below).
- `myservice_fleet_maintenance/__manifest__.py` — `web.assets_backend` is now
  empty; the JS, its QWeb template and its CSS no longer ship.

Nothing else. No JS, XML, CSS, Python or test file was deleted.

---

## Why each one is dead

The reason is **not** "Odoo 19 removed `web.AbstractAction` and `web.rpc`".
It did, but `myservice_nrs_base/static/src/js/legacy_compat.js` re-provides
`web.core`, `web.rpc`, `web.ajax`, `web.session` and `web.AbstractAction` as
OWL-backed shims, and **five other legacy dashboards render on 19 through
exactly that path** — verified in a browser on `jaizbankplc`, each mounting
with real data and zero console errors:

| Client action | Rendered |
|---|---|
| `myservice_barcode_station.action_barcode_station` | 47 KB of DOM, "2316 TOTAL ASSETS / 2316 ACTIVE TAGS" |
| `myservice_asset_register.action_asset_dashboard` | 24 KB |
| `myservice_fm_dashboard.action_fm_dashboard` | 45 KB, "249 open requests" |
| `myservice_staff_bus.action_bus_dashboard` | 6 KB |
| `myservice_dashboard.action_myservice_dashboard` | 19 KB |

The actual reasons are per-screen and mundane.

### The two security screens — not in any bundle, and no action record

`myservice_security/__manifest__.py` listed **only CSS**. Neither JS file nor
either QWeb template was in any bundle, so the browser never fetched them,
`odoo.define` never ran, and `core.action_registry.add` never registered the
three tags. Confirmed live: reading the `actions` registry in a logged-in
backend session returns `false` for all three, and `true` for all five working
dashboards.

There is also nothing to dispatch to them. Commit `17aba57` (2026-04-08,
*"replace broken JS client actions with standard act_window views"*) converted
every `ir.actions.client` in `myservice_security` to an `ir.actions.act_window`
and re-pointed `views/menu.xml` at those. **The Security menus work today** —
they open ordinary list views over `security.incident` and `security.guard`.

The mechanical story in one line: commit `2cdac30` (*"legacy backend dashboards
working on Odoo 19"*) gave both security JS files the correct three-argument
`odoo.define(name, [deps], factory)` signature and moved eight modules'
templates out of the removed `web.assets_qweb` bundle. `myservice_security` was
the one module it did not touch, because `17aba57` had already stripped both of
its bundles four months earlier. **The 19 port fixed the syntax of two files
for a bundle they were no longer in.**

### The fleet dashboard — bundled, registered, and unreachable

The opposite defect. `fleet_dashboard.js` **was** in `web.assets_backend`, so
it was downloaded, parsed and registered `myservice_fleet_dashboard` into the
actions registry on every backend page load in every app — and
`core.action_registry.add('myservice_fleet_dashboard', …)` at
`fleet_dashboard.js:287` is the **only** occurrence of that string in the
repository. No `ir.actions.client` record carries it. Both menuitems in
`myservice_fleet_maintenance/views/menu.xml` are `active="0"`. The only
dashboard-named action in the module,
`action_fleet_maintenance_dashboard`, is an `act_window` over a vehicle list —
a different thing entirely.

Confirmed live: the tag is present in the registry and nothing reaches it.

It carries a second, latent defect. `myservice_fleet_maintenance` is the one
module of the six whose `depends` does not reach `myservice_nrs_base`, which
is what provides the shim its `require('web.AbstractAction')` needs. It only
ever loaded because `myservice_dashboard` happens to drag `nrs_base` in.

---

## ⚠️ Two things that must not be tidied up

**`myservice_security/static/src/css/security_navbar.css` is live and global.**
Despite its name and its own header comment — *"Target: `.o_menu_sections`
(top nav tabs when Security & Safety is active)"* — it scopes to nothing. Every
selector is a core web-client class (`.o_main_navbar`, `.o_menu_sections`,
`.o_menu_systray`, `.o_menu_brand`, `.dropdown-menu`), so it restyles the top
navbar of **every backend screen in every app for every user**. Where
`myservice_theme_v5` also sets a property it wins (it appends after), but
`security_navbar.css` alone supplies the uppercase / condensed / letter-spaced
nav labels, the red active-tab underline, and the dark `.o_menu_sections
.dropdown-menu` treatment. Removing it is a visible change on every screen —
arguably a fix, since a dark dropdown under a white navbar is a bug — but it is
a design decision, not a retirement, and it needs a screenshot pass.

**`myservice_security/static/lib/leaflet/` must not be deleted.**
`fleet_dashboard.js:227,230` hard-codes `/myservice_security/static/lib/
leaflet/leaflet.{css,js}` — a cross-module URL dependency nothing declares.
`myservice_dashboard` and `myservice_staff_bus` each vendor their own copy and
are unaffected.

---

## What porting would take

### Security Command Center (`security_tabs.js`, 324 + 66 lines) — mechanical

Every model, field, ordering key and route this file names **exists today**.
Its five `search_read` calls over `security.incident`, `security.guard`,
`security.access.log` and `security.duty.roster` are all truthful, and both
routes it calls (`/myservice/security/kpis`, `/myservice/security/recent`) are
defined in `myservice_security/controllers/main.py`. It is correct code that is
simply unreachable. Roughly 400 lines of OWL to replace 390 lines of Widget
code:

1. Add the JS **and** `security_tabs.xml` to `web.assets_backend` (Odoo 19
   registers QWeb templates from the normal bundle; there is no separate qweb
   bundle any more).
2. Add an `ir.actions.client` record per tag and point `views/menu.xml` at it —
   or keep the `act_window` records that replaced them.
3. Replace the hard-coded numeric `data-action="331|332|333|336"` in
   `security_tabs.xml:25,29,33,37,57`, consumed by `parseInt` at
   `security_tabs.js:95`. Raw database ids are not portable across installs.
4. Rewrite the render layer. `renderTable` (`security_tabs.js:43-70`) builds an
   HTML string and calls `$el.html(...)` with unescaped record values — an XSS
   surface via any incident name. A `<t t-foreach>` template escapes for free.
5. `rpc.query` → `useService("orm").searchRead(...)`; the two route calls →
   `rpc(...)` from `@web/core/network/rpc`.
6. jQuery event delegation → `t-on-click` and `useState`.
7. Update `tests/test_security_tabs_fields.py` — its `CALL_RE` will stop
   matching the moment the calls become `orm.searchRead`. Update the parser;
   do not lower `MIN_CALLS`, which sits at exactly the 5 calls in the file so
   that a regex which stops matching fails loudly instead of asserting nothing.

### SOC Dashboard (`security_dashboard.js`, 967 lines) — a rebuild, not a port

**The JS is the smallest part of it.** Four of the models it queries do not
exist anywhere in the repository, in any addon tree:
`security.watchlist`, `ai.pattern.alert`, `acled.sync.log` (with a
`get_acled_heatmap_data` method) and `security.osint.feed`. Two of the five
HTTP routes it calls are undefined — `/myservice/security/osint` and
`/myservice/security/state_threats` — and all five sit in one `Promise.all`, so
even with everything else fixed the whole body would fail to render on either
missing feed. The `watchlist` KPI card reads a key the controller has never
returned, and displays a confident zero.

So reviving it means: four models with fields, views, ACLs and menus; two
controllers; an ACLED ingestion pipeline behind them; plus the OWL port at 3×
the volume of the Command Center. Scope it as a project or leave it archived.
The Odoo 15 CSV extracts for the missing models are under
`docs/upgrade/archive/`.

Note in passing: `/myservice/security/trend` is defined in
`controllers/main.py:83` and no JS calls it — dead in the other direction.

### Fleet Command Center (`fleet_dashboard.js`, ~500 lines)

Same mechanical port as the Command Center, plus:

1. Add `myservice_nrs_base` to the module's `depends`, or port off the shim.
2. Give it an `ir.actions.client` record and a menu — it has never had either,
   so decide what the screen is for before porting it. `myservice_dashboard`'s
   own "Fleet Command" tab already covers some of the same ground.
3. Fix the Leaflet path, or vendor a copy the way the other two dashboards do.

---

## The one shared defect worth knowing about

`legacy_compat.js` does not provide `do_notify`. Only the barcode station calls
it (`barcode_station.js:204`), on the "Request replacement" button: the RPC
succeeds and the record is written, then the `.then()` throws
`self.do_notify is not a function`, so the list never refreshes. It reads as
"nothing happened" while the write landed. Three lines in the shim
(`useService("notification")`) fix it. Not in scope for handoff 11 — recorded
here because this is where someone will look.

Separately, `t-on-click="refresh"` in `barcode_station.xml:24` and
`bus_dashboard.xml:16` resolves against the render context rather than the
component, so the Refresh button is inert on both. Cosmetic; both screens
render.

---

## Rulings considered and declined (handoff 51, 2026-10-05)

**Deleting the Security Command Center source was considered on 5 October
2026 and declined**, for three reasons: it ships to nobody (not in any
bundle means not fetched, so leaving it costs no runtime); it is already
guarded by tag against silently coming back
(`tests/test_source_guards.py::test_the_retired_screens_stay_retired`); and
this file carries the port estimate (*portable, mechanical, ~2 days*), so
deleting the source would turn a documented, reversible decision into a
git-archaeology exercise and buy nothing. The next person with the same
idea should stop here.

**Demoting the IT Assets Command page (`ITAssetsCommand.tsx`) to a saved
view on the asset list was considered and withdrawn** in the same handoff:
the page is a condition breakdown and a site map, which a saved view is
not, and the thing that actually motivated the demotion — one category
holding a top-level command centre when no other does — is already
answered by handoff 48's per-tenant sidebar switches. A tenant that does
not run IT assets as a programme switches the page off; that is the right
control, and it is shipped.
