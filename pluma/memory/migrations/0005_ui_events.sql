-- P15: committed identity-only event projections. No command, arguments,
-- transcript, clipboard, image, undo recipe or model text is copied here.
CREATE TABLE IF NOT EXISTS ui_event_stream (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), stream_id TEXT NOT NULL
);
INSERT OR IGNORE INTO ui_event_stream VALUES (1,
    lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' ||
    lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6))));
CREATE TABLE IF NOT EXISTS ui_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL, occurred_at TEXT NOT NULL,
    task_id TEXT NOT NULL, request_id TEXT, record_id INTEGER
);
CREATE TRIGGER IF NOT EXISTS ui_events_bound AFTER INSERT ON ui_events BEGIN
    DELETE FROM ui_events WHERE sequence <= NEW.sequence - 512;
END;
CREATE TRIGGER IF NOT EXISTS ui_tasks_insert AFTER INSERT ON tasks
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('task_recorded', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, NEW.request_id, NULL);
END;
CREATE TRIGGER IF NOT EXISTS ui_tasks_update AFTER UPDATE ON tasks
WHEN OLD.started_at IS NOT NEW.started_at OR OLD.completed_at IS NOT NEW.completed_at OR OLD.final_state IS NOT NEW.final_state OR OLD.route IS NOT NEW.route OR OLD.stop_reason IS NOT NEW.stop_reason OR OLD.error_code IS NOT NEW.error_code
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('task_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, NEW.request_id, NULL);
END;
CREATE TRIGGER IF NOT EXISTS ui_actions_insert AFTER INSERT ON actions
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('action_recorded', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS ui_actions_update AFTER UPDATE ON actions
WHEN OLD.ended_at IS NOT NEW.ended_at OR OLD.verified IS NOT NEW.verified OR OLD.result_json IS NOT NEW.result_json OR OLD.verification_json IS NOT NEW.verification_json OR OLD.error_json IS NOT NEW.error_json
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('action_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS ui_undo_records_insert AFTER INSERT ON undo_records
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('rollback_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), (SELECT task_id FROM actions WHERE id=NEW.action_id), (SELECT t.request_id FROM tasks t JOIN actions a ON a.task_id=t.task_id WHERE a.id=NEW.action_id), NEW.action_id);
END;
CREATE TRIGGER IF NOT EXISTS ui_undo_records_update AFTER UPDATE ON undo_records
WHEN OLD.available IS NOT NEW.available OR OLD.rollback_attempted IS NOT NEW.rollback_attempted OR OLD.rollback_ok IS NOT NEW.rollback_ok
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('rollback_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), (SELECT task_id FROM actions WHERE id=NEW.action_id), (SELECT t.request_id FROM tasks t JOIN actions a ON a.task_id=t.task_id WHERE a.id=NEW.action_id), NEW.action_id);
END;
CREATE TRIGGER IF NOT EXISTS ui_cleanup_reports_insert AFTER INSERT ON cleanup_reports
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('cleanup_recorded', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NULL);
END;
CREATE TRIGGER IF NOT EXISTS ui_resources_insert AFTER INSERT ON resources
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('resource_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NULL);
END;
CREATE TRIGGER IF NOT EXISTS ui_resources_update AFTER UPDATE ON resources
WHEN OLD.released_at IS NOT NEW.released_at
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('resource_changed', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NULL);
END;
CREATE TRIGGER IF NOT EXISTS ui_screen_events_insert AFTER INSERT ON screen_events
BEGIN
    INSERT INTO ui_events(kind, occurred_at, task_id, request_id, record_id)
    VALUES ('screen_recorded', strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.task_id, (SELECT request_id FROM tasks WHERE task_id=NEW.task_id), NEW.id);
END;
