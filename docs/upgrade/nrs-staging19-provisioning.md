# NRS (staging) → Odoo 19 provisioning + cutover plan

NRS is the last tenant on 15 and the only one with **real master data** (≈11.4k
employees, ≈11.9k assets, ≈850 locations, ≈1.6k fleet). Unlike gtb/jaiz/lasg
(regenerated from seed scripts), NRS is reproduced from source: the location
tree exported from the live `staging` DB + the `NRS_asset_seed` CSV pack, loaded
via the validated `scripts/migrate_nrs_locations.py` and `scripts/seed_nrs_assets.py`
(both proven locally on `nrs19`: 11,386 employees + 11,878 assets, 100% of the pack).

Target 19 DB: **`staging19`**, served on `staging19.app.cadra.ng` until the flip,
then `staging.app.cadra.ng` is repointed to `odoo-19`.

## Prereqs (in place)
- Zero-downtime bootstrap: the `cadra-bootstrap-19` Job now uses an ephemeral
  emptyDir filestore and `deploy-19` skips the `odoo-19` re-roll on seed runs, so
  provisioning `staging19` does NOT disturb the live gtb/jaiz/lasg on odoo-19.
- gtb/jaiz/lasg already on 19; `staging` still on 15 (untouched, rollback).

## The one open decision — how to deliver the data to a cluster Job
The import runs as an in-cluster Job that talks to the `odoo-19` Service over
XML-RPC. It needs two inputs that are NOT in the normal image:
1. **`NRS_asset_seed` CSV pack** — `docs/seed/NRS_asset_seed/` is gitignored
   (size + real staff/asset data), so it is not in the git checkout the GitHub
   Actions build uses, nor in `cadra-odoo-19`.
2. **Staging location export** — derived from the live `staging` (15) DB.

Pick one delivery method for the pack (my recommendation: **A**):
- **A. One-off import image built locally.** Someone with the pack + registry
  access builds `Dockerfile.nrs-import` (bakes the pack + `scripts/`) and pushes
  `cadra-nrs-import:latest`; the Job runs it. Keeps the pack out of git and off
  object storage. Simple, one-time.
- **B. Object storage.** Upload the pack to DO Spaces (private); the Job fetches
  it with a scoped key. Better if the import will be re-run often.
- **C. Local run.** A workstation with `kubectl` + the pack runs the scripts via
  `kubectl port-forward svc/odoo-19 8069`. Rejected here — no kubectl access.

The **location export** needs no external delivery: an in-cluster Job runs the
documented `COPY … generic_location …` against the `staging` DB (same shared
Postgres) to produce `nrs_locations_export.csv` on a shared volume the import
Job reads. See `scripts/migrate_nrs_locations.py` header for the exact SQL.

## Sequence (once a delivery method is chosen)

1. **Seed staging19 structure** (zero-downtime; does not touch live tenants):
   ```
   gh workflow run deploy-19.yml -f run_bootstrap=true \
     -f bootstrap_db=staging19 -f bootstrap_extra_modules=cadra_brand_nrs \
     -f bootstrap_seed_profile=core        # ITSM structure + groups + jwt + client
   ```
   (`core` also lays a Nigeria location skeleton; the real NRS offices come from
   the staging export in step 3 and resolve by the `nrs_loc_<N>` external ids —
   confirm no unwanted duplication, or add an ITSM-only profile to bootstrap.py.)

2. **Grant admin the asset/security groups** on `staging19` (bootstrap.py already
   does the operational groups; verify Asset Manager, else the asset load is
   denied — same gotcha as the local nrs19 validation), then restart odoo-19's
   registry view of it (a fresh request suffices; no re-roll needed).

3. **Location bridge** — export staging's tree + import to staging19 + rebuild the
   `__export__.generic_location_<N>_<hash>` external ids the asset CSVs reference:
   ```
   python scripts/migrate_nrs_locations.py --url http://odoo-19:8069 \
     --db staging19 --user admin --password <pw> \
     --locations-csv nrs_locations_export.csv --asset-pack docs/seed/NRS_asset_seed
   ```
   ~5s; ~98% of refs resolve (7 source ids absent from staging → ~460 assets
   land unlocated; map by hand or accept — documented residual).

4. **Employees + assets** — `scripts/seed_nrs_assets.py --ensure-fields` against
   `staging19` (departments → jobs → 11,385 employees → 10,259 ICT → 1,619 fleet).
   ~5-10 min via XML-RPC.

5. **Verify** on `staging19.app.cadra.ng` (in-pod Host header, DNS-independent):
   counts (~11.4k emp / ~11.9k assets), `myservice_request_core` installed,
   `/api/v1/brand` = Nigeria Revenue Service, spot-check the SPA + dashboards.

6. **Flip** — route `staging.app.cadra.ng` → `odoo-19` in `60-ingress.yaml`, and
   run `tenant-cutover-19` (`host_label=staging`, `source_db=staging19`,
   `tenant_host=staging.app.cadra.ng`): renames `staging`→`staging_15bak`
   (rollback) and `staging19`→`staging`, applies ingress, restarts odoo-19,
   verifies. Retire the 15 `odoo`/`cadra` stack once confirmed.

## Rollback
Per tenant: `ALTER DATABASE staging RENAME TO staging19; ALTER DATABASE
staging_15bak RENAME TO staging;` and revert the `staging` ingress rule to the
`odoo` (15) Service. The 15 stack and DB are untouched until the flip.

## To build (pending the delivery decision in the "open decision" section)
- `Dockerfile.nrs-import` (option A) — bakes `docs/seed/NRS_asset_seed/` +
  `scripts/` on a slim python image with `openpyxl`.
- `k8s/dev/70-nrs-location-export-job.yaml` — psql the staging DB → CSV on a PVC.
- `k8s/dev/71-nrs-import-job.yaml` — runs the two scripts against `odoo-19`.
- A `deploy-19`-style manual workflow to orchestrate the above.
