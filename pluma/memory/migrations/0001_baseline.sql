-- PLUMA SQLite baseline schema — migration 0001
-- Spec §20.1
--
-- All tables are created with IF NOT EXISTS so this migration is idempotent.
-- Run order: this file is the first and only baseline migration.
-- WAL mode and foreign-key enforcement are set at connection time (see db.py).

-- Preferences: typed key/value store for user-configurable settings.
CREATE TABLE IF NOT EXISTS preferences (
    key         TEXT PRIMARY KEY NOT NULL,
    value_json  TEXT NOT NULL,           -- JSON-encoded value
    updated_at  TEXT NOT NULL            -- ISO-8601 UTC timestamp
);

-- Aliases: user-defined shorthand names for paths, apps, or routines.
CREATE TABLE IF NOT EXISTS aliases (
    alias       TEXT PRIMARY KEY NOT NULL,
    target_json TEXT NOT NULL,           -- JSON-encoded target descriptor
    updated_at  TEXT NOT NULL
);

-- Routines: saved multi-step command sequences.
CREATE TABLE IF NOT EXISTS routines (
    id              TEXT PRIMARY KEY NOT NULL,  -- UUID
    name            TEXT NOT NULL UNIQUE,
    definition_json TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Tasks: one row per PlumaRequest/TaskCapsule.
CREATE TABLE IF NOT EXISTS tasks (
    task_id          TEXT PRIMARY KEY NOT NULL,
    request_id       TEXT NOT NULL,
    input_mode       TEXT NOT NULL CHECK (input_mode IN ('text', 'voice')),
    command_text     TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    completed_at     TEXT,
    final_state      TEXT,               -- TaskState enum value
    route            TEXT,               -- RouteMode enum value
    active_process   TEXT,
    active_window    TEXT,
    stop_reason      TEXT,
    error_code       TEXT
);

-- Actions: one row per tool-call step within a task.
CREATE TABLE IF NOT EXISTS actions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id              TEXT NOT NULL REFERENCES tasks(task_id),
    step_index           INTEGER NOT NULL,
    tool                 TEXT NOT NULL,
    adapter              TEXT,
    args_json_sanitized  TEXT NOT NULL,  -- Sensitive values redacted before storage.
    risk                 TEXT NOT NULL,
    approval_state       TEXT,           -- 'auto_allowed', 'user_confirmed', 'elevated', 'denied'
    started_at           TEXT NOT NULL,
    ended_at             TEXT,
    duration_ms          REAL,
    result_json          TEXT,           -- Sanitised ToolResult.data
    verified             INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    verification_json    TEXT,           -- VerifyResult JSON
    error_json           TEXT            -- Factual error detail
);

-- Undo records: pre-state captured before reversible actions.
CREATE TABLE IF NOT EXISTS undo_records (
    action_id            INTEGER PRIMARY KEY REFERENCES actions(id),
    undo_json            TEXT NOT NULL,  -- Tool-specific rollback recipe
    available            INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
    rollback_attempted   INTEGER NOT NULL DEFAULT 0 CHECK (rollback_attempted IN (0, 1)),
    rollback_ok          INTEGER,        -- NULL until attempted; then 0/1
    rollback_result_json TEXT
);

-- Resources: task-owned processes, temp files, browser tabs, etc.
CREATE TABLE IF NOT EXISTS resources (
    id           TEXT PRIMARY KEY NOT NULL,   -- UUID
    task_id      TEXT NOT NULL REFERENCES tasks(task_id),
    resource_type TEXT NOT NULL,              -- 'temp_dir', 'subprocess', 'browser_tab', ...
    ownership    TEXT NOT NULL CHECK (ownership IN ('PREEXISTING', 'PLUMA_CREATED')),
    external_id  TEXT,                        -- PID, path, handle, etc.
    created_at   TEXT NOT NULL,
    released_at  TEXT,
    metadata_json TEXT
);

-- Screen events: minimal metadata about UIA/OCR targets used during tasks.
-- Screenshots are NOT stored (spec §8.2, §16.3).
CREATE TABLE IF NOT EXISTS screen_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id                 TEXT NOT NULL REFERENCES tasks(task_id),
    snapshot_id             TEXT NOT NULL,
    source                  TEXT NOT NULL CHECK (source IN ('UIA', 'OCR')),
    target_label            TEXT,
    control_type            TEXT,
    bounds_json             TEXT,           -- BoundingBox as JSON
    confidence              REAL,
    active_window_signature TEXT,           -- "process|title" at capture time
    created_at              TEXT NOT NULL
);

-- Indexes for common query patterns.
CREATE INDEX IF NOT EXISTS idx_actions_task_id    ON actions(task_id);
CREATE INDEX IF NOT EXISTS idx_resources_task_id  ON resources(task_id);
CREATE INDEX IF NOT EXISTS idx_screen_events_task ON screen_events(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at   ON tasks(created_at DESC);
