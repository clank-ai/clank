-- The remote component's state (design 0005 §4): the paired devices and the codes that pair them.

-- A device that may reach the phone page: its name, the hash of its token (never the token), the Tailscale login it
-- paired with, when it was paired and last used, and when it was revoked.
CREATE TABLE devices (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    login      TEXT NOT NULL,
    paired     TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    revoked    TEXT
);

-- A code made on the computer to pair one device: the hash of the code, the device's name, until when it may be used,
-- and when it was used.
CREATE TABLE pairings (
    code_hash  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created    TEXT NOT NULL,
    expires    TEXT NOT NULL,
    used       TEXT
);

-- Each wrong code typed, so code entry rests after too many.
CREATE TABLE pair_failures (
    time       TEXT NOT NULL
);
