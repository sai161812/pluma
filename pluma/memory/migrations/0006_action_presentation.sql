-- Dedicated redacted executor presentation; historical rows remain unavailable.
ALTER TABLE actions ADD COLUMN presentation_json TEXT;
DROP TRIGGER ui_actions_update;
CREATE TRIGGER ui_actions_update AFTER UPDATE ON actions
WHEN OLD.ended_at IS NOT NEW.ended_at OR OLD.verified IS NOT NEW.verified
 OR OLD.result_json IS NOT NEW.result_json OR OLD.verification_json IS NOT NEW.verification_json
 OR OLD.error_json IS NOT NEW.error_json OR OLD.presentation_json IS NOT NEW.presentation_json
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('action_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id,
        (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NEW.id);
END;
