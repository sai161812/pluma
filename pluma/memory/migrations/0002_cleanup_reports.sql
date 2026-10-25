-- Cleanup ownership must survive STOP before task-history insertion.
-- Deliberately independent of tasks: never fabricate a command/input mode.
CREATE TABLE IF NOT EXISTS cleanup_reports (
    task_id TEXT PRIMARY KEY NOT NULL,
    recorded_at TEXT NOT NULL,
    released_at TEXT,
    metadata_json TEXT NOT NULL
);
