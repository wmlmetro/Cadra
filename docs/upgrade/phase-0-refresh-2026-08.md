# Upgrade Re-plan Refresh — 2026-08-04

Supersedes the vendor-availability section of [phase-0-summary.md](phase-0-summary.md) (May 2026).
Trigger: decision to target **Odoo 19** instead of Odoo 18. This refresh re-checked CRND
vendor availability against today's public Odoo Apps Store and found a **hard blocker** that
changes the recommended target.

## Current state (confirmed today)

- Running **Odoo 15.0 Community** (`FROM odoo:15.0` — Dockerfile.odoo.dev / .k8s; image `cadra-odoo:15.0-dev`).
- Phase 1 cleanup was executed: the 5 retired modules are gone, `pre-upgrade-baseline` tag exists.
- 20 in-house modules (`myservice_*` + `cadra_brand_*`); 114 dist/ CRND modules, of which ~19 are actually in-scope.
- In-house hard deps on the CRND stack (from manifests):
  `generic_request`, `crnd_wsd`, `generic_request_location`, `generic_location`,
  `generic_team`, `generic_service`, `generic_resource`, `generic_tag`, `generic_rule`.

## Odoo 19 facts

- Released **2025-09-18**. Requires **Python 3.12+**.
- 19.0 is the current stable Community branch.
- No supported direct 15→19 jump; OpenUpgrade is per-version: 15→16→17→18→19 (5 steps).

## Vendor availability — the blocker (Odoo Apps Store, authoritative commercial channel)

| CRND module | In-house dependents | Max version available | 17.0? |
|---|---|---|---|
| `generic_request` | request_fields, security, nrs_base, workflow, dashboard, fleet, asset, fm | **19.0** | yes |
| `generic_service` | nrs_base, fm_dashboard | **19.0** | **NO (16→18)** |
| `generic_resource` | asset_register, nrs_base | **19.0** | **NO (16→18)** |
| `generic_location` | many | **19.0** | **NO (16→18)** |
| `generic_team` | nrs_base, request_fields | **19.0** | **NO (16→18)** |
| `generic_tag`, `generic_rule` | nrs_base | 18/19 (generic-addons) | — |
| **`crnd_wsd`** (Website Service Desk) | **request_fields, security** | **16.0 — 404 on 17/18/19** | no |
| **`crnd_service_desk`** (Service Desk app) | transitive under crnd_wsd | **16.0 — 404 on 17/18/19** | no |

### Conclusion
**Odoo 19 (and 18, and 17) is NOT reachable off-the-shelf** while the app depends on
`crnd_wsd` + `crnd_service_desk`. CRND has not published those two past **16.0** on the
public Apps Store. They are the ticket-submission portal + service-desk core that the NRS
request workflow is built on. This contradicts the May Phase 0 note that "18.0 branches exist"
— a gitlab *branch* existing is not the same as the *addon* being published/installable, and
the Apps Store is the authoritative source for what can actually be bought and installed.

## Revised target options

### Option A — Odoo 16 (recommended safe target)
Highest version where the **entire** current CRND stack (incl. crnd_wsd + crnd_service_desk)
ships off-the-shelf. Single conceptual hop (15→16). Python 3.10-compatible. Lowest risk,
no re-architecture, all in-house modules port with the OWL2/asset-bundle changes that 16 requires.
Buys ~support runway to ~2026 (16 is older but still the CRND-supported ceiling for the desk layer).

### Option B — Odoo 18/19, drop the CRND service-desk layer
Reachable only by **removing `crnd_wsd` + `crnd_service_desk`** and either:
  - (b1) rebuilding the request portal on `generic_request` alone (which IS on 19) + a custom
        in-house web portal, or
  - (b2) replacing the whole desk layer with a different helpdesk (Odoo core Helpdesk is
        Enterprise-only; OCA has partial alternatives).
Large scope — this is a re-platform of the request UX, not a migration. Weeks, not days.

### Option C — Odoo 18/19, obtain private CRND ports
Contact CRND commercially for a private/unreleased 17→19 port of crnd_wsd + crnd_service_desk,
or a fork licence. Cost + timeline unknown; depends entirely on CRND. Removes the engineering
risk of B if they'll sell it.

### Option D — Fork & port crnd_wsd + crnd_service_desk ourselves
Vendor the 16.0 source and port 16→17→18→19 in-house. These are large modules (website
controllers, OWL views, portal templates). Realistically the largest of all options; only
sensible if we have the source licence and deep CRND familiarity.

## Recommendation
Target **Odoo 16** now (Option A) as the concrete, low-risk upgrade — it clears Odoo 15 EOL,
requires no re-architecture, and all vendor deps exist. Treat 18/19 as a **separate future
initiative** gated on a business decision about the service-desk layer (Options B/C/D), because
that is a re-platform, not a version bump.

## Immediate next steps for the 15→16 path
1. Stand up a 16.0 dev image (`FROM odoo:16.0`, Python 3.10) alongside the existing 15 image.
2. Pull CRND 16.0 sources for the ~19 in-scope addons (generic_* + crnd_wsd + crnd_service_desk + crnd_web_*).
3. Resolve `crnd_web_list_popover_widget` (confirmed missing on 16 in May audit — drop/fork).
4. OpenUpgrade 15→16 on a restored copy of a real tenant DB (staging/NRS first).
5. Port each in-house module's manifest/views/JS to 16 (OWL2 + assets bundle changes).
6. Per-tenant smoke test (NRS, GTB, Jaiz, LASG) against restored snapshots.
