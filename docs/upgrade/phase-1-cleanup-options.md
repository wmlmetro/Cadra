# Phase 1 DB Cleanup — Two Paths

Phase 1 deleted 5 module directories from the source tree and trimmed myservice_security. The Odoo registry in the local Postgres still has rows for these modules' models, fields, views, access rules, etc. That mismatch will cause boot errors on the next `odoo-bin -u all` because Odoo tries to resolve `ir.model.data` entries pointing at modules that no longer exist on disk.

You have two paths to reconcile. **Run [phase-1-archive.sh](phase-1-archive.sh) first** in either case — that captures all the row data to CSV under [archive/](archive/) so it can be reconstructed later if needed.

---

## Path A — Nuke & re-seed (recommended for local dev)

**When to use:** if your local NRS database contents came from re-runnable seed scripts (`load_offices.py`, `myservice_master_seed.py`, etc.) and you don't have hand-curated data you'd lose.

**Pros:** clean state, no SQL surgery, matches what a fresh Odoo 18 install will look like, no risk of orphan rows.
**Cons:** loses any data you entered manually; takes ~10–30 minutes to re-seed depending on which scripts you run.

```bash
# 1. Archive first (always — your only safety net)
./docs/upgrade/phase-1-archive.sh

# 2. Stop the stack
docker compose -f docker-compose.dev.yml down

# 3. Wipe the postgres volume
docker volume rm myservicenrs_cadra_pgdata
# (also myservicenrs_cadra_odoo_data if you want a fully clean filestore)

# 4. Bring it back up — Odoo will initialise a fresh DB
docker compose -f docker-compose.dev.yml up -d

# 5. Wait ~30s, then install the trimmed module set
docker exec myservicenrs-odoo-1 odoo \
    -c /etc/odoo/odoo.conf -d odoo \
    -i myservice_api,myservice_asset_register,myservice_barcode_station,\
myservice_dashboard,myservice_fleet_maintenance,myservice_fm_dashboard,\
myservice_identity,myservice_nrs_base,myservice_request_fields,\
myservice_security,myservice_staff_bus,myservice_theme_v5,\
myservice_website_theme,myservice_workflow \
    --stop-after-init

# 6. Re-seed (whichever scripts apply — see load_all.sh for the canonical sequence)
./load_all.sh
```

---

## Path B — In-place SQL surgery (preserves current DB)

**When to use:** if you have data in the current DB you cannot lose or re-generate.

**Pros:** preserves all kept-model data (locations, assets, fleet, requests, employees, incidents, guards, rosters, access logs).
**Cons:** more risk — you're modifying Odoo's internal registry directly. Test on a DB clone first.

### Step 1 — Archive (run [phase-1-archive.sh](phase-1-archive.sh))

### Step 2 — Snapshot the DB before surgery
```bash
docker exec myservicenrs-db-1 pg_dump -Fc -U odoo odoo \
    > docs/upgrade/archive/pre-cleanup-snapshot-$(date +%Y%m%d-%H%M%S).dump
```

### Step 3 — Apply [phase-1-cleanup.sql](phase-1-cleanup.sql)

```bash
docker exec -i myservicenrs-db-1 psql -U odoo -d odoo \
    < docs/upgrade/phase-1-cleanup.sql
```

This script:
- Marks the 5 retired modules as uninstalled in `ir_module_module`
- Removes their `ir_model_data`, `ir_ui_view`, `ir_act_window`, `ir_ui_menu` rows
- Drops the model tables themselves
- For myservice_security partial retirement: drops only the `security.watchlist`, `security.watchlist.alias`, `security.state.threat` model registry entries and their tables; drops the `security_incident_watchlist_rel` M2M and the `watchlist_match_id` column on `security_access_log`

### Step 4 — Restart and update
```bash
docker compose -f docker-compose.dev.yml restart odoo
# Trigger a registry refresh
docker exec myservicenrs-odoo-1 odoo \
    -c /etc/odoo/odoo.conf -d odoo \
    -u myservice_security,myservice_api \
    --stop-after-init
```

### Step 5 — Verify
```bash
# Should return 0 for each retired model
docker exec myservicenrs-db-1 psql -U odoo -d odoo -c "
SELECT model, count(*) FROM ir_model
WHERE model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
) GROUP BY model;"

# Should return 0 — no orphan ir_model_data pointing at removed modules
docker exec myservicenrs-db-1 psql -U odoo -d odoo -c "
SELECT module, count(*) FROM ir_model_data
WHERE module IN ('myservice_osint','myservice_ai_patterns',
                 'myservice_security_scc','myservice_security_soc','nrs_watchlist')
GROUP BY module;"
```

If either query returns rows, the cleanup is incomplete — check the snapshot, restore if needed, investigate.

### Rollback
```bash
docker exec myservicenrs-db-1 pg_restore -U odoo -d odoo --clean --if-exists \
    /var/lib/postgresql/data/pre-cleanup-snapshot-*.dump
# (copy the dump into the container first, or use docker cp)
```

---

## Which path should I pick?

Honest answer: **Path A unless you have a specific reason not to.** Your local data is presumably the output of seed scripts you already maintain (the `load_*.py` and `*_seed.py` files at the repo root). Re-running them is faster and safer than SQL surgery against Odoo's internal registry. Path B exists for when you've spent days curating data in the local DB that isn't reproducible from seeds.

If you go Path A, you can stop reading here.
