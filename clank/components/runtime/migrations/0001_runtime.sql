-- The runtime's state (design 0003 §3, §6): what each slot runs, each launch, each engine installed.

-- What a slot runs now: its state since when and why, the preset, the launch, and the process's identity on its host
-- (decision 0030: its id, start time and command line's SHA-256); and the configuration that last reached ready.
CREATE TABLE slots (
    name       TEXT PRIMARY KEY,
    status     TEXT NOT NULL CHECK (status IN ('stopped', 'starting', 'ready', 'stopping', 'failed')),
    since      TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    preset     TEXT,
    launch_id  INTEGER,
    host       TEXT,
    pid        INTEGER,
    started    TEXT,
    command    TEXT,
    port       INTEGER,
    last_good  TEXT
);

-- Each start of an engine: what was planned and estimated, and how it went (design 0001 §3.6: what the estimates learn
-- from; §4.2: how long a start took).
CREATE TABLE launches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slot            TEXT NOT NULL,
    preset          TEXT NOT NULL,
    options         TEXT NOT NULL,
    engine          TEXT NOT NULL,
    engine_version  TEXT NOT NULL,
    host            TEXT NOT NULL,
    command_line    TEXT NOT NULL,
    log             TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ready_at        TEXT,
    ended_at        TEXT,
    outcome         TEXT NOT NULL CHECK (outcome IN ('starting', 'ready', 'failed', 'stopped', 'crashed')),
    detail          TEXT NOT NULL DEFAULT '',
    estimate_mib    INTEGER,
    before_mib      INTEGER,
    measured_mib    INTEGER,
    seconds         REAL
);
CREATE INDEX launches_by_engine ON launches (engine, host, id);

-- Each engine installed on a host: the command that runs it, its folder and libraries, and how it came to be there.
CREATE TABLE installs (
    id            TEXT PRIMARY KEY,
    setup         TEXT NOT NULL,
    version       TEXT NOT NULL,
    host          TEXT NOT NULL,
    program       TEXT NOT NULL,
    folder        TEXT NOT NULL,
    library_path  TEXT NOT NULL DEFAULT '',
    how           TEXT NOT NULL CHECK (how IN ('adopted', 'recipe', 'test')),
    detail        TEXT NOT NULL DEFAULT '',
    installed     TEXT NOT NULL
);
