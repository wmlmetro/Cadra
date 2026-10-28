BEGIN READ ONLY;
\pset footer off
SELECT count(*) AS captures_all_time, min(create_date) AS first, max(create_date) AS last FROM nrs_audit_capture;
WITH rev AS (
  SELECT r.campaign_id, count(*) FILTER (WHERE u.active) AS reviewers_named
  FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id = r.user_id GROUP BY 1)
SELECT c.id, left(c.capture_uuid,8) AS uuid8, c.campaign_id AS camp, k.state AS camp_state,
       c.location_id AS loc, c.state, c.outcome, c.duplicate_of_id AS dup_of,
       c.operator_id AS op, c.device_id AS dev, to_char(c.captured_at,'MM-DD HH24:MI') AS captured,
       to_char(c.received_at,'MM-DD HH24:MI') AS received,
       coalesce(rev.reviewers_named,0) AS reviewers_named,
       row_number() OVER (PARTITION BY c.campaign_id, c.state ORDER BY c.id) AS rank_in_review_list
FROM nrs_audit_capture c JOIN nrs_audit_campaign k ON k.id = c.campaign_id
LEFT JOIN rev ON rev.campaign_id = c.campaign_id
WHERE c.received_at > now() - interval '14 days'
ORDER BY c.id;
WITH rev AS (
  SELECT r.campaign_id, count(*) FILTER (WHERE u.active) AS n
  FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id = r.user_id GROUP BY 1)
SELECT k.id AS campaign, k.state, count(c.id) AS captured,
  count(c.id) FILTER (WHERE c.state='pending_review') AS pending_review,
  count(c.id) FILTER (WHERE c.state='accepted') AS accepted,
  count(c.id) FILTER (WHERE c.state='returned') AS returned,
  coalesce(rev.n,0) AS reviewers_named,
  (SELECT count(*) FROM nrs_audit_campaign_capturer_rel x WHERE x.campaign_id=k.id) AS capturers_named
FROM nrs_audit_campaign k LEFT JOIN nrs_audit_capture c ON c.campaign_id = k.id
LEFT JOIN rev ON rev.campaign_id = k.id GROUP BY k.id, k.state, rev.n ORDER BY k.id;
SELECT d.id, d.active, d.user_id AS bound_to, to_char(d.registered_at,'MM-DD HH24:MI') reg,
  (SELECT count(*) FROM nrs_audit_capture c WHERE c.device_id=d.id) AS captures
FROM nrs_audit_device d ORDER BY d.id;
ROLLBACK;
BEGIN READ ONLY;
\pset footer off
SELECT r.campaign_id, r.user_id, u.active, u.share FROM nrs_audit_campaign_reviewer_rel r JOIN res_users u ON u.id=r.user_id ORDER BY 1,2;
SELECT r.campaign_id, r.user_id FROM nrs_audit_campaign_capturer_rel r ORDER BY 1,2;
SELECT k.id, k.state, k.create_date::date, k.created_by_id, (SELECT count(*) FROM nrs_audit_campaign_scope s WHERE s.campaign_id=k.id) scopes FROM nrs_audit_campaign k ORDER BY k.id;
-- who holds the reviewer group / audit:review
SELECT g.id, g.name->>'en_US' AS grp, array_agg(gu.uid ORDER BY gu.uid) AS uids
FROM res_groups g JOIN res_groups_users_rel gu ON gu.gid=g.id
WHERE g.name->>'en_US' ILIKE '%audit%' GROUP BY 1,2 ORDER BY 1;
ROLLBACK;
BEGIN READ ONLY;
\pset footer off
SELECT c.id, c.campaign_id camp, string_agg(DISTINCT p.source, ',') AS photo_source, count(p.id) photos, c.ai_suggestion_id IS NOT NULL AS used_ai, c.code IS NOT NULL AS has_code FROM nrs_audit_capture c LEFT JOIN nrs_audit_capture_photo_rel r ON r.capture_id=c.id LEFT JOIN nrs_audit_photo p ON p.id=r.photo_id GROUP BY c.id ORDER BY c.id;
SELECT source, count(*), count(*) FILTER (WHERE id NOT IN (SELECT photo_id FROM nrs_audit_capture_photo_rel)) AS unattached FROM nrs_audit_photo GROUP BY 1;
ROLLBACK;
BEGIN READ ONLY;
\pset footer off
SELECT p.id AS photo, p.source, p.uploaded_by_id AS by, to_char(p.uploaded_at,'MM-DD HH24:MI:SS') AS uploaded,
  (SELECT string_agg(s.id||':'||s.result||' '||to_char(s.requested_at,'MM-DD HH24:MI'), '; ') FROM nrs_ai_suggestion s WHERE s.audit_photo_id=p.id) AS ai,
  (SELECT string_agg(r.capture_id::text, ',') FROM nrs_audit_capture_photo_rel r WHERE r.photo_id=p.id) AS capture
FROM nrs_audit_photo p ORDER BY p.id;
SELECT s.id, s.actor_id, to_char(s.requested_at,'MM-DD HH24:MI:SS') req, s.result, s.audit_photo_id, s.photo_id, s.pending_photo_id,
 (SELECT c.id FROM nrs_audit_capture c WHERE c.ai_suggestion_id=s.id) AS used_by_capture
FROM nrs_ai_suggestion s WHERE s.requested_at > '2026-10-19' ORDER BY s.id;
ROLLBACK;
