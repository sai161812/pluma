-- Stable keyset browsing, including tasks with identical saved timestamps.
CREATE INDEX IF NOT EXISTS idx_tasks_history_order ON tasks(created_at DESC, task_id DESC);
