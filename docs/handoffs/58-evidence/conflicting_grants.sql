-- Handoff 58 §5: people who ALREADY hold a pair the seeded exclusion table
-- forbids, measured BEFORE the seed. Effective membership (implications
-- followed), internal users only, API credentials' users left out (their
-- groups are derived from scopes, CLAUDE.md rule 7). Denominator printed.
WITH RECURSIVE x(name, gid) AS (
  SELECT d.module || '.' || d.name, d.res_id FROM ir_model_data d
  WHERE d.model = 'res.groups' AND (d.module, d.name) IN (
    ('myservice_asset_register','group_asset_officer'),
    ('myservice_asset_register','group_iad_vfm_officer'),
    ('myservice_asset_register','group_iad_vfm_approver'),
    ('myservice_asset_register','group_asset_controller'),
    ('myservice_asset_register','group_tag_issuing_unit'),
    ('myservice_asset_register','group_register_maker'),
    ('myservice_asset_register','group_register_checker'))
),
eff(uid, gid) AS (
  SELECT r.uid, r.gid FROM res_groups_users_rel r
  UNION
  SELECT e.uid, i.hid FROM eff e JOIN res_groups_implied_rel i ON i.gid = e.gid
),
pairs(a, b) AS (VALUES
  ('officer','iad_vfm_officer'),('officer','iad_vfm_approver'),
  ('officer','asset_controller'),('officer','tag_issuing_unit'),
  ('officer','register_maker'),('officer','register_checker'),
  ('register_maker','register_checker'),('iad_vfm_officer','iad_vfm_approver')),
named AS (SELECT replace(replace(name,'myservice_asset_register.group_',''),'asset_officer','officer') k, gid FROM x),
people AS (
  SELECT u.id, u.login, u.active FROM res_users u
  JOIN res_partner p ON p.id = u.partner_id
  WHERE NOT u.share AND u.id NOT IN (SELECT user_id FROM myservice_api_client WHERE user_id IS NOT NULL)
),
hits AS (
  SELECT pe.login, pe.active, pr.a || ' × ' || pr.b AS pair
  FROM people pe, pairs pr
  JOIN named na ON na.k = pr.a JOIN named nb ON nb.k = pr.b
  WHERE EXISTS (SELECT 1 FROM eff WHERE eff.uid = pe.id AND eff.gid = na.gid)
    AND EXISTS (SELECT 1 FROM eff WHERE eff.uid = pe.id AND eff.gid = nb.gid)
)
SELECT 'people (internal, not credentials): ' || (SELECT count(*) FROM people)
UNION ALL SELECT 'people holding a forbidden pair: ' || count(DISTINCT login) FROM hits
UNION ALL SELECT '  ' || login || (CASE WHEN active THEN '' ELSE ' (inactive)' END) || ' — ' || string_agg(pair, ', ') FROM hits GROUP BY login, active;
