# NRS 15 → 19 cutover runbook (data re-provision)

The Odoo 19 rebuild is a greenfield re-platform, not an in-place upgrade — 19
cannot open a 15 database. Live tenants are re-provisioned onto fresh 19 DBs
from sources we already have. A read-only audit of the live cluster (the
`audit-tenant` workflow) confirmed there is **no real transactional data** to
migrate anywhere (0 user-authored requests, 0 operational attachments, ~0
custody transfers, 1–4 logins per tenant). So the cutover reproduces
**reference/master data only** — no transactional ETL.

## Per-tenant paths

- **gtb / jaiz / lasg** — fully regenerable from the seed scripts. Provision a
  fresh 19 DB and run `CADRA_SEED_PROFILE=<tenant> … odoo shell < scripts/bootstrap.py`.
  Validated end-to-end on `gtb19` (122 branches, 60 employees, 150 assets, 30 fleet).

- **NRS** — real master data (≈11.4k employees, ≈11.9k assets, ≈850 locations,
  ≈1.6k fleet) reproduced from source files in the repo. Validated on `nrs19`.

## NRS provisioning sequence (validated on Odoo 19)

1. **Install** the module set on a fresh DB (`-i myservice_*,web_responsive,cadra_brand_nrs`).

2. **Bootstrap groups + secrets** — run `scripts/bootstrap.py` (sets `jwt_secret`,
   adds admin to the operational groups). REQUIRED before the asset load, or
   `nrs.asset` creates are denied ("allowed for group: Asset Manager"). If you
   grant groups out-of-band, restart the server so the group cache refreshes.

3. **Locations** — the NRS asset CSVs reference locations by Odoo export IDs
   `__export__.generic_location_<N>_<hash>` where `<N>` is the SOURCE (staging)
   `generic_location.id`. Bridge them:
   a. Export the staging location tree to `nrs_locations_export.csv`:
      ```
      psql -d staging -tAc "COPY ( SELECT 'nrs_loc_'||id AS \"id\", name,
        CASE WHEN parent_id IS NOT NULL THEN 'nrs_loc_'||parent_id ELSE '' END AS \"parent_id/id\",
        COALESCE(location_type,''), COALESCE(zone_code,''),
        COALESCE(longitude::text,''), COALESCE(latitude::text,''),
        (CASE WHEN active THEN '1' ELSE '0' END)
        FROM generic_location ORDER BY parent_path ) TO STDOUT WITH CSV HEADER" > nrs_locations_export.csv
      ```
   b. Import + rebuild the `__export__` aliases (≈5s):
      ```
      python scripts/migrate_nrs_locations.py --url <odoo> --db nrs19 \
        --user admin --password <pw> \
        --locations-csv nrs_locations_export.csv --asset-pack docs/seed/NRS_asset_seed
      ```
   Result: 847 locations imported (hierarchy + coords preserved), 300/307
   asset-ref external IDs resolved. **7 source ids (~2%) are absent from the
   staging export** → those assets land without a location (residual cleanup;
   pick a mapping or accept). Categories/sub-categories are also matched by
   name and must exist (2 categories + 7 sub-categories for the NRS pack).

4. **Employees + assets** — run the existing loader (XML-RPC `load()`,
   idempotent, `--ensure-fields` creates the `x_*` custom fields):
   ```
   python scripts/seed_nrs_assets.py --url <odoo> --db nrs19 \
     --user admin --password <pw> --ensure-fields
   ```
   Validated result on 19: **11,386 employees + 11,878 assets** (10,259 ICT +
   1,619 fleet) — 100% of the CSV pack, zero loader code changes.

## Cutover mechanics

19 goes to NEW databases ALONGSIDE the live 15 (never in-place). Re-provision →
validate (counts + spot-check + client sign-off on a staging URL) → flip DNS →
keep 15 running as instant rollback. The `NRS_asset_seed` CSV pack is gitignored
(local/secure only); the staging location export is produced at cutover time.
