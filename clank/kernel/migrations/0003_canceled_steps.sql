-- A step cut short by a cancel is recorded as canceled, not failed. SQLite cannot change a CHECK constraint in
-- place, so the table is rebuilt with its rows.
CREATE TABLE operation_steps_new (
    operation_id TEXT NOT NULL REFERENCES operations (id) ON DELETE CASCADE,
    number       INTEGER NOT NULL,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'done', 'failed', 'canceled')),
    repeatable   INTEGER NOT NULL,
    started      TEXT NOT NULL,
    finished     TEXT,
    detail       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (operation_id, number)
);
INSERT INTO operation_steps_new SELECT operation_id, number, name, status, repeatable, started, finished, detail
    FROM operation_steps;
DROP TABLE operation_steps;
ALTER TABLE operation_steps_new RENAME TO operation_steps;
