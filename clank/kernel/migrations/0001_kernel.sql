-- The kernel's state (design 0002 §2.2-2.5): the event log, operations with their steps and logs, and questions.
-- Applied once, in order; never edited once released: a change is the next migration (design 0002 §2.2).
-- Times are UTC text that sorts in time order (clank/kernel/clock.py); structured values are JSON text.

CREATE TABLE kernel_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    time         TEXT NOT NULL,
    type         TEXT NOT NULL,
    subject_kind TEXT,
    subject_id   TEXT,
    actor        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX events_by_time ON events (time);
CREATE INDEX events_by_type ON events (type, id);
CREATE INDEX events_by_subject ON events (subject_kind, subject_id, id);

CREATE TABLE operations (
    id            TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL
                  CHECK (status IN ('queued', 'running', 'waiting', 'done', 'failed', 'canceled', 'interrupted')),
    started_by    TEXT NOT NULL,
    created       TEXT NOT NULL,
    updated       TEXT NOT NULL,
    finished      TEXT,
    cancelable    INTEGER NOT NULL,
    params        TEXT NOT NULL DEFAULT '{}',
    result        TEXT,
    error         TEXT NOT NULL DEFAULT '',
    request_key   TEXT UNIQUE,
    locks         TEXT NOT NULL DEFAULT '[]',
    waiting_on    TEXT,
    planned_steps INTEGER NOT NULL,
    retry_of      TEXT
);
CREATE INDEX operations_by_status ON operations (status, created);

CREATE TABLE operation_steps (
    operation_id TEXT NOT NULL REFERENCES operations (id) ON DELETE CASCADE,
    number       INTEGER NOT NULL,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    repeatable   INTEGER NOT NULL,
    started      TEXT NOT NULL,
    finished     TEXT,
    detail       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (operation_id, number)
);

CREATE TABLE operation_log (
    operation_id TEXT NOT NULL REFERENCES operations (id) ON DELETE CASCADE,
    number       INTEGER NOT NULL,
    time         TEXT NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (operation_id, number)
);

CREATE TABLE questions (
    id             TEXT PRIMARY KEY,
    type           TEXT NOT NULL CHECK (type IN ('approval', 'choice', 'text')),
    status         TEXT NOT NULL CHECK (status IN ('waiting', 'answered', 'expired', 'withdrawn')),
    about_kind     TEXT,
    about_id       TEXT,
    asked_by       TEXT NOT NULL,
    title          TEXT NOT NULL,
    detail         TEXT NOT NULL DEFAULT '',
    options        TEXT NOT NULL DEFAULT '[]',
    default_option TEXT,
    expires        TEXT,
    urgency        TEXT NOT NULL CHECK (urgency IN ('normal', 'high')),
    asked          TEXT NOT NULL,
    answer         TEXT,
    reason         TEXT NOT NULL DEFAULT '',
    operation_id   TEXT REFERENCES operations (id)
);
CREATE INDEX questions_by_status ON questions (status, asked);
