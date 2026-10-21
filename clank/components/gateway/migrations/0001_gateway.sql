-- The gateway component's own state (design 0016 §9, §12).

-- Each workspace's key at the gateway (its SHA-256 only; the key is a secret, workspace/<name>/gateway-key), and the
-- farthest its requests may go: this-machine until the owner allows the cloud; when the owner last answered the cloud
-- question for it, and the question open for it now.
CREATE TABLE workspace_keys (
    workspace  TEXT PRIMARY KEY,
    key_hash   TEXT UNIQUE,
    models     TEXT NOT NULL DEFAULT 'this-machine' CHECK (models IN ('this-machine', 'my-servers', 'cloud')),
    answered   TEXT NOT NULL DEFAULT '',
    question   TEXT
);

-- Each cloud request that ended, taken from the gateway's spool (`state/cloud-spool.jsonl`) by its run and sequence:
-- when, of which session (and the session that started it), workspace, provider, preset and model, the provider's
-- generation, its tokens, what it cost in US dollars and how that is known (usage, generation, estimate), and its
-- refusal when it was refused (its status and Clank's code). `rev` only grows: a row taken or changed (an estimate
-- made exact) gets the next, so a client asks for what changed since the last it saw.
CREATE TABLE cloud_costs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run         TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    time        TEXT NOT NULL,
    request     TEXT NOT NULL,
    session     TEXT NOT NULL DEFAULT '',
    parent      TEXT NOT NULL DEFAULT '',
    workspace   TEXT NOT NULL DEFAULT '',
    endpoint    TEXT NOT NULL DEFAULT '',
    preset      TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    generation  TEXT NOT NULL DEFAULT '',
    tokens      TEXT NOT NULL DEFAULT '{}',
    usd         REAL NOT NULL DEFAULT 0,
    how         TEXT NOT NULL CHECK (how IN ('usage', 'generation', 'estimate')),
    status      INTEGER,
    code        TEXT NOT NULL DEFAULT '',
    rev         INTEGER NOT NULL,
    UNIQUE (run, seq)
);
CREATE INDEX cloud_costs_by_time ON cloud_costs (time);
CREATE INDEX cloud_costs_by_session ON cloud_costs (session, parent);
CREATE INDEX cloud_costs_by_rev ON cloud_costs (rev);
