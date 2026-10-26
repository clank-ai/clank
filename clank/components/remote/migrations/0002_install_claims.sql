-- Design 0025 §2: a one-time install claim carries a device's pairing from the Safari tab into the installed app (iOS
-- keeps a Home Screen app's storage apart from Safari's): the hash of the claim, the device it is for, until when it
-- may be used (an hour), and when it was used.
CREATE TABLE install_claims (
    claim_hash TEXT PRIMARY KEY,
    device     TEXT NOT NULL,
    created    TEXT NOT NULL,
    expires    TEXT NOT NULL,
    used       TEXT
);
