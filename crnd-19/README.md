# crnd-19 — CRND foundation for the Odoo 19 rebuild

Vendored CRND modules on the **19.0** branch, consumed via `addons_path` in
`config/odoo.19.conf`. Populated by `scripts/fetch-crnd-19.sh`.

## Tiers (by licence / availability)

| Tier | Modules | Status |
|---|---|---|
| **Free** (public monorepo, LGPL-3) | `generic_mixin`, `generic_m2o`, `generic_tag`, `generic_rule`, `generic_condition*`, `generic_crypto_utils`, `base_field_*` | vendored here |
| **LGPL, gated 19.0 source** | `generic_service`, `generic_resource`, `generic_location`, `generic_team` | get via CRND account, or port `dist/<mod>` 15.0 → 19.0 (allowed under LGPL-3) |
| **Paid, proprietary** | `generic_request` (OPL-1) | needs a CRND 19.0 licence — the one hard commercial dependency |

`crnd_wsd` / `crnd_service_desk` are **dropped** in the rebuild (used in one
place; the request portal is served by the React SPA + `myservice_api`).

Re-fetch the free tier any time with `./scripts/fetch-crnd-19.sh`.
