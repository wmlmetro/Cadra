# Odoo 19 stack on cadra-dev (additive, alongside live 15)

The 19 rebuild is deployed into the **same `cadra-dev` namespace** as the live
Odoo 15 stack, as a parallel set of `-19` resources. The live 15
Deployment/Service/Ingress and DBs are never touched, so live tenants keep
running as an instant rollback until the DNS flip.

## Resources (all `-19`, shared bits reused)

| Concern | 15 (live) | 19 (rebuild) |
|---|---|---|
| Image | `cadra-odoo` (`Dockerfile.odoo.k8s`, odoo:15 — **deleted in handoff 20**) | `cadra-odoo-19` (`Dockerfile.odoo.19.k8s`, odoo:19) |
| Deployment / Service | `odoo` | `odoo-19` |
| Odoo config | `odoo-config` | `odoo-config-19` (gevent_port, crnd-19/oca-19 addons) |
| Bootstrap config | `odoo-bootstrap` | `odoo-bootstrap-19` (ported module set) |
| Filestore PVC | `odoo-filestore` | `odoo-19-filestore` |
| Bootstrap Job | `cadra-bootstrap` | `cadra-bootstrap-19` |
| Ingress | `cadra` (`<tenant>.cadra.ng`) | `cadra-19` (`<tenant>19.cadra.ng`) |
| **Shared** | Postgres `db`, Secrets `cadra-db`/`cadra-odoo`, `frontend` (SPA) | ← same |

19 tenant DBs are named `<tenant>19` (e.g. `staging19`, `gtb19`) and served on
`<tenant>19` hostnames via `dbfilter = ^%d$`, so they coexist with the 15 DBs in
the one Postgres and never collide.

## Deploy (manual only — `deploy-19.yml`, workflow_dispatch)

Never runs on push. First roll per tenant:

- **gtb / jaiz / lasg** — one run each:
  `run_bootstrap=true`, `bootstrap_db=<tenant>19`,
  `bootstrap_extra_modules=cadra_brand_<tenant>`, `bootstrap_seed_profile=<tenant>`.
- **NRS** — run with `bootstrap_db=staging19`, `bootstrap_extra_modules=cadra_brand_nrs`,
  a structure profile, then run the location bridge + asset/employee import
  separately (they need the NRS_asset_seed CSV pack + a staging location
  export) — see `docs/upgrade/nrs-cutover-runbook.md`.

Prereqs (owned by the 15 `deploy-dev.yml`, already present): namespace,
`cadra-db`/`cadra-odoo` Secrets, Postgres `db`, `frontend`. DNS: point each
`<tenant>19` host at the ingress LB before it can serve.

## Cutover flip

When a 19 tenant is validated: repoint the real host (`<tenant>.cadra.ng`) to
`odoo-19` (add it to `cadra-19` ingress / move it off `cadra`), rename/point the
19 DB to the label the real host resolves to, then scale down the 15 `odoo`
Deployment once all tenants are flipped.
