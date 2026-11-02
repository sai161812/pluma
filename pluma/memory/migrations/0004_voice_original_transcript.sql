-- Preserve the source voice transcript separately from normalized command text.
ALTER TABLE tasks ADD COLUMN original_transcript TEXT;
