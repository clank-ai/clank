-- Each check and test of a provider someone else runs (design 0016 §6): when, whether it passed, its items (a check's)
-- or what it said (a test's), and what its own requests cost, in US dollars, which the cost totals count (§12).
CREATE TABLE endpoint_checks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint  TEXT NOT NULL,
    kind      TEXT NOT NULL CHECK (kind IN ('check', 'test')),
    time      TEXT NOT NULL,
    ok        INTEGER NOT NULL,
    items     TEXT NOT NULL,
    cost_usd  REAL NOT NULL DEFAULT 0
);
CREATE INDEX endpoint_checks_by_endpoint ON endpoint_checks (endpoint, kind, id);
