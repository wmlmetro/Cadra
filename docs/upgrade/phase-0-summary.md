# Phase 0 Summary — Pre-flight & GO/NO-GO #1

**Date:** 2026-05-24
**Status:** **CONDITIONAL GO** — proceed to Phase 1 contingent on three user actions listed at the bottom of this document.

---

## What changed from the plan estimate

The plan estimated "80–90 of 103" dist/ addons in scope after retirement trimming. **Actual: 19 of 113** — a much larger scope reduction than expected, because most dist/ addons (94 of them, including the entire bureaucrat_* family, generic_contract_*, generic_assignment_*, generic_equipment_*, generic_request_action_* / _sla_* / _condition_* extensions, generic_resource_* extensions, generic_system_event_* extensions, and all but one of the crnd_wsd_* extensions) are **dead weight** — they sit in dist/ but no in-house module depends on them, directly or transitively.

This makes the audit and the upgrade dramatically less risky than originally feared.

---

## The 19 in-scope dist/ addons

See [addon-audit.csv](addon-audit.csv) for the full matrix. Summary:

### Definitively VERIFIED present on Odoo 18 (9 addons)
- `generic_mixin`, `generic_tag`, `generic_rule`, `generic_m2o`, `base_field_m2m_view` (all in [crnd-opensource/generic-addons](https://gitlab.crnd.pro/crnd-opensource/generic-addons/-/tree/18.0))
- `crnd_web_diagram_plus`, `crnd_web_field_domain`, `crnd_web_m2o_info_widget`, `crnd_web_tree_colored_field` (all in [crnd-opensource/crnd-web](https://gitlab.crnd.pro/crnd-opensource/crnd-web/-/tree/18.0))

These were probed via CRND's public raw-file API, which reliably returns HTTP 200 vs 404 on the `crnd-opensource/generic-addons` and `crnd-opensource/crnd-web` repos. **No further action required for these 9.**

### Likely OK but require user login to confirm (9 addons)
| Addon | Repo |
|---|---|
| `generic_request` | [crnd-opensource/generic-request](https://gitlab.crnd.pro/crnd-opensource/generic-request/-/tree/18.0) |
| `generic_request_location` | same |
| `generic_location` | [crnd-opensource/generic-location](https://gitlab.crnd.pro/crnd-opensource/generic-location/-/tree/18.0) |
| `generic_resource` | [crnd-opensource/generic-resource](https://gitlab.crnd.pro/crnd-opensource/generic-resource/-/tree/18.0) |
| `generic_service` | [crnd-opensource/generic-service](https://gitlab.crnd.pro/crnd-opensource/generic-service/-/tree/18.0) |
| `generic_team` | [crnd-opensource/generic-team](https://gitlab.crnd.pro/crnd-opensource/generic-team/-/tree/18.0) |
| `generic_system_event` | [crnd-opensource/generic-system-event](https://gitlab.crnd.pro/crnd-opensource/generic-system-event/-/tree/18.0) |
| `crnd_wsd` | [crnd-opensource/crnd-wsd](https://gitlab.crnd.pro/crnd-opensource/crnd-wsd/-/tree/18.0) |
| `crnd_service_desk` | [crnd-opensource/crnd-service-desk](https://gitlab.crnd.pro/crnd-opensource/crnd-service-desk/-/tree/18.0) |

For each of these, the **18.0 branch is confirmed to exist** (HTML browse returns 200), but CRND's raw-file API for these per-feature repos is auth-gated, so the **specific addon directory under 18.0/ cannot be verified from outside**. Action required: log into gitlab.crnd.pro and click each link above to confirm the addon directory is present on the 18.0 branch. **Estimated user time: ~15 minutes total.**

### Confirmed MISSING on Odoo 18 (1 addon — the only real blocker)
- `crnd_web_list_popover_widget` — present on `crnd-web/15.0`, returns HTTP 404 on `crnd-web/16.0`, `17.0`, and `18.0`. Likely renamed, merged into core Odoo, or simply removed by CRND. Confirmed absent on OCA/web 16.0/17.0/18.0 too.

**Decision needed:** investigate usage and pick one of:
1. **Drop it** — if no in-house code or kept dist/ addon actually instantiates the widget at runtime (it may be a transitive dep that nothing calls).
2. **Fork it** — vendor the 15.0 source under `dist/` and port it forward as our own. ~2 days of OWL2 work (this is one of the legacy-widget addons).
3. **Find a replacement** — another OCA web extension that gives equivalent UX.

The "where is this widget actually invoked" investigation can be done in ~30 minutes of grepping during early Phase 1.

---

## GO/NO-GO #1 against plan exit criteria

| Criterion | Status |
|---|---|
| Audit matrix 100% filled | ✅ Done — [addon-audit.csv](addon-audit.csv) |
| No kept addon is `MISSING` without a fork/replace owner | ⚠️ Conditional — 1 missing (`crnd_web_list_popover_widget`); owner = lead engineer; decision deferred to early Phase 1 |
| Total dist/ port effort estimate < 15 engineer-days | ✅ Done — current estimate is **~3–6 engineer-days** dominated by `crnd_web_list_popover_widget` (2d) + `crnd_wsd` smoke-fix budget (1d) + verification clicks (negligible) |
| Staging boots Odoo 15 from restored prod snapshot; backup-restore roundtrip verified | ❌ Not done — requires user-side infrastructure access (see handoff section) |

**Verdict: CONDITIONAL GO.** The vendor-availability picture is much better than feared. The one confirmed gap is small. Phase 1 can begin in parallel with the user's verification clicks.

---

## STOP-GO trigger from the plan

The plan said: "if any kept addon is `MISSING` with no upstream 18 port, no OCA replacement exists, and fork would exceed 8 days — pause and reconsider Odoo 17 LTS." That trigger is **NOT** activated: the only confirmed-missing addon is a UI widget with a 2-day fork budget, well under the 8-day threshold.

---

## Handoff items — actions the user must do before Phase 1

I cannot do these from a local Mac dev session; they need access to your production infrastructure or CRND credentials.

### IMMEDIATE (blocks Phase 1)

1. **Verify the 9 "likely OK" addon directories on 18.0** (~15 min). Click each link in the "Likely OK" table above; for each, confirm the addon directory is visible on the 18.0 branch tree. Update [addon-audit.csv](addon-audit.csv) status column from `LIKELY_OK` to `OK` (or open an investigation if any are missing).

2. **Run the production "installed modules" query** (~5 min). On the prod NRS database:
   ```sql
   SELECT name, latest_version FROM ir_module_module
   WHERE state = 'installed'
   ORDER BY name;
   ```
   Save the result to [docs/upgrade/prod-installed-modules.csv](prod-installed-modules.csv). The audit so far covers addons reachable from in-house manifests; this query catches anything installed manually via the Odoo UI that we'd miss. Likely outcome: nothing surprising — but we don't know until we look.

### BEFORE PHASE 2 (the first version step)

3. **Production data snapshot + backup-restore verification** (~half a day):
   ```bash
   pg_dump -Fc -j 4 myservice > nrs_prod_$(date +%Y%m%d).dump
   tar czf nrs_filestore_$(date +%Y%m%d).tgz /var/lib/odoo/filestore/myservice/
   # Then on a separate machine/VPS:
   createdb -O odoo myservice_restore_test
   pg_restore -d myservice_restore_test nrs_prod_*.dump
   # Boot Odoo 15 against myservice_restore_test, confirm login works
   ```
   Store three copies off-system (S3 or NAS). Untested backups are not backups.

4. **Provision the staging environment** (~1 day):
   - Dedicated VPS sized to mirror prod, OR a beefy dev box running an adapted [docker-compose.dev.yml](../../docker-compose.dev.yml).
   - Must be DNS-isolated: no live SAP webhooks reach it, no outbound mail.
   - Restore the prod dump + filestore.
   - Confirm Odoo 15 boots and login works against the restored DB.

5. **Tooling install on the staging VPS** (~half a day):
   - OpenUpgrade per-version branches (`git clone -b 15.0 https://github.com/OCA/OpenUpgrade`; repeat for 16.0, 17.0, 18.0).
   - `pip install click-odoo click-odoo-contrib` for `click-odoo-update` and `click-odoo-uninstall`.
   - Two Python venvs: 3.10 (for steps 15→16 and 16→17) and 3.11 (for 17→18).

---

## Phase 1 can begin now in parallel

While the user does items 1 and 2 above, I can start Phase 1.1–1.5 on the codebase here:
- Remove [myservice_osint/](../../myservice_osint/), [myservice_ai_patterns/](../../myservice_ai_patterns/), [myservice_security_scc/](../../myservice_security_scc/), [myservice_security_soc/](../../myservice_security_soc/), [nrs_watchlist/](../../nrs_watchlist/) from the working tree
- Clean up [myservice_api/__manifest__.py](../../myservice_api/__manifest__.py) and [myservice_api/controllers/v1.py](../../myservice_api/controllers/v1.py) to drop the retired deps and ~14 dead endpoints
- Split [myservice_security/](../../myservice_security/) — keep incident + guard + roster + access_log; drop watchlist + state_threat (and refactor the dashboard JS to match)
- Tag `pre-upgrade-baseline`

The data-export step of Phase 1.3 (CSV archives of retired-model tables) needs to happen on the prod or staging DB, not locally — that's the only Phase 1 sub-task that depends on user-side infrastructure.
