-- Handoff 62: every asset.register_state.changed row for the drive's units,
-- oldest first, with its payload exactly as stored (= as sent) and Vendra's
-- answer. Run: psql -d test19 -f outbox.sql
SELECT l.name, l.asset_id, l.status, l.http_status, l.attempts,
       l.payload_sent::json->>'register_state' AS state,
       l.payload_sent AS payload,
       left(l.response_received, 400) AS vendra_answered,
       l.delivery_history
  FROM workflow_dispatch_log l
 WHERE l.event_type = 'asset.register_state.changed'
   AND l.asset_id BETWEEN 100041 AND 100052
 ORDER BY l.asset_id, l.id;
