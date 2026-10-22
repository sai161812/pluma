-- A durable claim precedes an inverse. Interrupted claims remain visible and
-- cannot be retried automatically after an uncertain external effect.
CREATE TABLE IF NOT EXISTS undo_claims (
    action_id INTEGER PRIMARY KEY REFERENCES undo_records(action_id),
    operation_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('claimed', 'verified', 'unverified')),
    created_at TEXT NOT NULL
);
