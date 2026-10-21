-- A launch of a cloud preset (design 0016 §7): the provider it reached (`endpoint`, empty for an engine's launch; a
-- cloud launch's `engine` is empty, so the GPU's learned memory never reads it), the route it gave the gateway (JSON,
-- never a key), and what its own requests cost, in US dollars (its health's tiny request, design 0016 §12).
ALTER TABLE launches ADD COLUMN endpoint TEXT NOT NULL DEFAULT '';
ALTER TABLE launches ADD COLUMN route TEXT;
ALTER TABLE launches ADD COLUMN cost_usd REAL;
