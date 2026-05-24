-- Phase 1 in-place DB cleanup (PATH B).
-- Only run AFTER:
--   1. ./docs/upgrade/phase-1-archive.sh has captured all retired-model data to CSV
--   2. A pg_dump snapshot has been taken (see phase-1-cleanup-options.md)
--   3. You've decided you cannot use Path A (drop volume + re-seed).
--
-- Wrap the whole thing in a transaction so a syntax error doesn't leave the DB half-cleaned.

BEGIN;

-- ──────────────────────────────────────────────────────────────────────
-- PART 1: Fully retired modules (myservice_osint, myservice_ai_patterns,
--         myservice_security_scc, myservice_security_soc, nrs_watchlist)
-- ──────────────────────────────────────────────────────────────────────

-- 1a. List the modules so we have IDs to work with.
--     We'll mark them uninstalled and let Odoo's own cleanup logic run on
--     next boot to drop residual ir_model_data — but we also pre-clean
--     the high-blast-radius rows explicitly here.

\set retired_modules '''myservice_osint'',''myservice_ai_patterns'',''myservice_security_scc'',''myservice_security_soc'',''nrs_watchlist'''

-- 1b. Drop ir.model.data referencing these modules.
--     This is the registry table that maps XML xmlids to DB rows.
DELETE FROM ir_model_data WHERE module IN (:retired_modules);

-- 1c. Drop the model entries from ir_model + ir_model_fields + ir_model_access + ir_model_constraint.
--     We identify retired models by their declared module column where possible,
--     and by an explicit name list as a belt-and-braces fallback.
WITH dead_models AS (
  SELECT id, model FROM ir_model WHERE model IN (
    'osint.feed.entry','osint.source.config',
    'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
    'nrs.watchlist.subject'
  )
)
DELETE FROM ir_model_access WHERE model_id IN (SELECT id FROM dead_models);

DELETE FROM ir_model_constraint WHERE model IN (
  SELECT id FROM ir_model WHERE model IN (
    'osint.feed.entry','osint.source.config',
    'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
    'nrs.watchlist.subject'
  )
);

DELETE FROM ir_model_fields WHERE model_id IN (
  SELECT id FROM ir_model WHERE model IN (
    'osint.feed.entry','osint.source.config',
    'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
    'nrs.watchlist.subject'
  )
);

DELETE FROM ir_model WHERE model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'nrs.watchlist.subject'
);

-- 1d. Drop the actual data tables. CASCADE to handle any straggling FKs.
DROP TABLE IF EXISTS osint_feed_entry        CASCADE;
DROP TABLE IF EXISTS osint_source_config     CASCADE;
DROP TABLE IF EXISTS ai_pattern_alert        CASCADE;
DROP TABLE IF EXISTS ai_daily_brief          CASCADE;
DROP TABLE IF EXISTS ai_brief_download_log   CASCADE;
DROP TABLE IF EXISTS nrs_watchlist_subject   CASCADE;

-- 1e. Mark the modules as uninstalled. Don't delete the row — Odoo wants
--     to track that the module was once present (avoids "unknown module" errors).
UPDATE ir_module_module
SET state = 'uninstalled', latest_version = NULL
WHERE name IN (
  'myservice_osint','myservice_ai_patterns',
  'myservice_security_scc','myservice_security_soc','nrs_watchlist'
);

-- ──────────────────────────────────────────────────────────────────────
-- PART 2: Partial retirement of myservice_security
--         Keep: security.incident, security.guard, security.duty.roster, security.access.log
--         Drop: security.watchlist, security.watchlist.alias, security.state.threat
-- ──────────────────────────────────────────────────────────────────────

-- 2a. Drop M2M relations from kept models to dropped models.
--     security.incident.watchlist_ids <-> security.watchlist
DROP TABLE IF EXISTS security_incident_watchlist_rel CASCADE;

-- 2b. Drop the watchlist_match_id column on security.access_log (was a M2O to security.watchlist).
--     We don't `DROP COLUMN` directly because Odoo's ORM will reconcile via its own
--     -u update path; instead null out and let the registry update on next boot.
--     But the column itself does need to go away to avoid FK violations once
--     security_watchlist table is dropped.
ALTER TABLE security_access_log DROP COLUMN IF EXISTS watchlist_match_id;

-- 2c. Same pattern for the dropped models in ir_model / ir_model_fields / etc.
DELETE FROM ir_model_access WHERE model_id IN (
  SELECT id FROM ir_model WHERE model IN (
    'security.watchlist','security.watchlist.alias','security.state.threat'
  )
);

DELETE FROM ir_model_constraint WHERE model IN (
  SELECT id FROM ir_model WHERE model IN (
    'security.watchlist','security.watchlist.alias','security.state.threat'
  )
);

DELETE FROM ir_model_fields WHERE model_id IN (
  SELECT id FROM ir_model WHERE model IN (
    'security.watchlist','security.watchlist.alias','security.state.threat'
  )
);

DELETE FROM ir_model WHERE model IN (
  'security.watchlist','security.watchlist.alias','security.state.threat'
);

-- 2d. Drop the dropped-model tables.
DROP TABLE IF EXISTS security_watchlist        CASCADE;
DROP TABLE IF EXISTS security_watchlist_alias  CASCADE;
DROP TABLE IF EXISTS security_state_threat     CASCADE;

-- 2e. Drop ir_model_data rows for the views / actions / menus / records
--     we removed from myservice_security in Phase 1. Identify by xmlid prefix.
DELETE FROM ir_model_data
WHERE module = 'myservice_security'
  AND name IN (
    'action_security_watchlist','action_security_state_threats',
    'action_security_command_center','action_osint_page',
    'action_ai_patterns_page','action_daily_brief_page',
    'menu_security_command_center','menu_security_osint_page',
    'menu_security_ai_page','menu_security_daily_brief',
    'menu_security_watchlist','menu_security_state_threats',
    'access_security_watchlist_manager','access_security_watchlist_admin',
    'access_security_watchlist_alias_manager',
    'access_security_state_threat_officer','access_security_state_threat_manager'
  );

-- ──────────────────────────────────────────────────────────────────────
-- PART 3: Generic cleanup of any other dangling references
-- ──────────────────────────────────────────────────────────────────────

-- 3a. mail.followers and mail.message on dropped models — Odoo polymorphs these via res_model.
DELETE FROM mail_followers WHERE res_model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
);
DELETE FROM mail_message WHERE model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
);
DELETE FROM mail_activity WHERE res_model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
);

-- 3b. ir.attachment polymorphic on res_model.
DELETE FROM ir_attachment WHERE res_model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
);

-- 3c. Scheduled actions (cron jobs) for dropped modules.
DELETE FROM ir_cron WHERE id IN (
  SELECT id FROM ir_cron c
  JOIN ir_model_data d ON d.res_id = c.id AND d.model = 'ir.cron'
  WHERE d.module IN (
    'myservice_osint','myservice_ai_patterns',
    'myservice_security_scc','myservice_security_soc','nrs_watchlist'
  )
);

-- 3d. ir_ui_view rows owned by the retired modules (xmlid-keyed).
DELETE FROM ir_ui_view WHERE id IN (
  SELECT res_id FROM ir_model_data
  WHERE model = 'ir.ui.view'
    AND module IN ('myservice_osint','myservice_ai_patterns',
                   'myservice_security_scc','myservice_security_soc','nrs_watchlist')
);

-- 3e. Window actions owned by retired modules.
DELETE FROM ir_act_window WHERE id IN (
  SELECT res_id FROM ir_model_data
  WHERE model = 'ir.actions.act_window'
    AND module IN ('myservice_osint','myservice_ai_patterns',
                   'myservice_security_scc','myservice_security_soc','nrs_watchlist')
);

-- 3f. Menus owned by retired modules.
DELETE FROM ir_ui_menu WHERE id IN (
  SELECT res_id FROM ir_model_data
  WHERE model = 'ir.ui.menu'
    AND module IN ('myservice_osint','myservice_ai_patterns',
                   'myservice_security_scc','myservice_security_soc','nrs_watchlist')
);

COMMIT;

-- Verification queries (run after COMMIT)
\echo
\echo '==> Verification: should each return 0 rows'
\echo
SELECT count(*) AS retired_models_remaining FROM ir_model WHERE model IN (
  'osint.feed.entry','osint.source.config',
  'ai.pattern.alert','ai.daily.brief','ai.brief.download.log',
  'security.watchlist','security.watchlist.alias','security.state.threat',
  'nrs.watchlist.subject'
);

SELECT count(*) AS orphan_ir_model_data FROM ir_model_data
WHERE module IN ('myservice_osint','myservice_ai_patterns',
                 'myservice_security_scc','myservice_security_soc','nrs_watchlist');

SELECT name, state FROM ir_module_module
WHERE name IN ('myservice_osint','myservice_ai_patterns',
               'myservice_security_scc','myservice_security_soc','nrs_watchlist')
ORDER BY name;
