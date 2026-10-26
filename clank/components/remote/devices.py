"""Paired devices and the codes that pair them (design 0005 §4, after a pattern already proven on this PC).

A code is made on the computer only (the console, `clank remote pair`): eight characters without look-alikes, good for
`CODE_MINUTES` and once, kept as its SHA-256. The device types it on the phone page; Tailscale's verified login comes
with the request, and a device is paired only to the login of this computer's own Tailscale user. Wrong codes are
counted: after `TRIES` in `TRIES_MINUTES` minutes code entry rests until the window passes. A paired device gets a token
of its own (kept as its SHA-256), sent back with every request; it lasts `TTL_DAYS` from its last use, renewed on
each use (design 0025 §2: no ceiling from its pairing), and is revoked from the computer. An install claim
(`install_claim`, `claim`) carries a pairing from the Safari tab into the installed app, once, within `CLAIM_MINUTES`.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from clank.kernel.clock import from_text, to_text

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # no 0/O, 1/I/L or U: easy to read off a screen and type
CODE_LENGTH = 8
CODE_MINUTES = 15
TRIES = 8
TRIES_MINUTES = 15
TTL_DAYS = 30
CLAIM_MINUTES = 60  # how long an install claim may be traded for the token (design 0025 §2)
SEEN_MINUTES = 5  # a device's last use is written at most this often


class PairingError(Exception):
    """A code that does not pair, and why (said to the device without telling which part was wrong)."""


@dataclass(frozen=True)
class Device:
    """A paired device."""

    id: str
    name: str
    login: str
    paired: datetime
    last_seen: datetime
    revoked: datetime | None

    def view(self) -> dict[str, Any]:
        """As a client sees it."""
        return {
            "id": self.id,
            "name": self.name,
            "login": self.login,
            "paired": to_text(self.paired),
            "last_seen": to_text(self.last_seen),
            "revoked": to_text(self.revoked) if self.revoked else None,
        }


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def normalized(code: str) -> str:
    """A code as typed, its spaces and dashes left out, in capitals."""
    return "".join(character for character in code.upper() if character.isalnum())


class Devices:
    """The paired devices and the pairing codes, in the state database."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        self._store = kernel.store

    def new_code(self, name: str) -> tuple[str, datetime]:
        """A code to pair a device of this name, and until when it may be used; codes not used yet are replaced."""
        now = self.kernel.clock.now()
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        expires = now + timedelta(minutes=CODE_MINUTES)
        with self._store.transaction() as db:
            db.execute("DELETE FROM pairings WHERE used IS NULL")
            db.execute(
                "INSERT INTO pairings (code_hash, name, created, expires) VALUES (?, ?, ?, ?)",
                (_hash(normalized(code)), name.strip() or "phone", to_text(now), to_text(expires)),
            )
        return code, expires

    def waiting_code(self) -> dict[str, Any] | None:
        """The code not used yet, if one is still good: its device's name and when it expires (never the code)."""
        now = to_text(self.kernel.clock.now())
        rows = self._store.read(
            "SELECT name, expires FROM pairings WHERE used IS NULL AND expires > ? ORDER BY created DESC LIMIT 1",
            (now,),
        )
        return {"name": rows[0]["name"], "expires": rows[0]["expires"]} if rows else None

    def cancel_code(self) -> dict[str, Any] | None:
        """Cancel the code not used yet: it no longer pairs; what it was for (None when no code was waiting)."""
        waiting = self.waiting_code()
        with self._store.transaction() as db:
            db.execute("DELETE FROM pairings WHERE used IS NULL")
        return waiting

    def pair(self, code: str, login: str) -> tuple[Device, str]:
        """Pair the device that typed a code: the device and its token; `PairingError` when it does not pair."""
        now = self.kernel.clock.now()
        window = to_text(now - timedelta(minutes=TRIES_MINUTES))
        failures = self._store.read("SELECT COUNT(*) AS count FROM pair_failures WHERE time > ?", (window,))[0]["count"]
        if failures >= TRIES:
            raise PairingError(f"too many wrong codes: try again in {TRIES_MINUTES} minutes")
        found = self._store.read(
            "SELECT name, expires FROM pairings WHERE code_hash = ? AND used IS NULL", (_hash(normalized(code)),)
        )
        if not found or from_text(found[0]["expires"]) <= now:
            with self._store.transaction() as db:  # counted in a transaction of its own, which the refusal keeps
                db.execute("INSERT INTO pair_failures (time) VALUES (?)", (to_text(now),))
            raise PairingError("that code does not pair: make a new one on the computer (Phone, F9, p)")
        row = found[0]
        with self._store.transaction() as db:
            db.execute("UPDATE pairings SET used = ? WHERE code_hash = ?", (to_text(now), _hash(normalized(code))))
            token = secrets.token_urlsafe(32)
            device = Device(f"dev-{uuid.uuid4().hex[:8]}", str(row["name"]), login, now, now, None)
            db.execute(
                "INSERT INTO devices (id, name, token_hash, login, paired, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                (device.id, device.name, _hash(token), login, to_text(now), to_text(now)),
            )
        return device, token

    def device(self, token: str, login: str) -> Device | None:
        """The device this token belongs to, when it is still good and comes with the login it paired with."""
        if not token:
            return None
        rows = self._store.read("SELECT * FROM devices WHERE token_hash = ?", (_hash(token),))
        if not rows:
            return None
        device = _device(rows[0])
        now = self.kernel.clock.now()
        if device.revoked is not None or device.login != login:
            return None
        if now - device.last_seen > timedelta(days=TTL_DAYS):  # renewed on each use (design 0025 §2)
            return None
        if now - device.last_seen > timedelta(minutes=SEEN_MINUTES):
            with self._store.transaction() as db:
                db.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (to_text(now), device.id))
        return device

    def install_claim(self, device: str) -> str:
        """A one-time install claim for a device just paired (design 0025 §2): the icon's start link carries it, and
        the installed app's first launch trades it for the device's token within `CLAIM_MINUTES`."""
        now = self.kernel.clock.now()
        claim = secrets.token_urlsafe(24)
        with self._store.transaction() as db:
            db.execute(
                "INSERT INTO install_claims (claim_hash, device, created, expires) VALUES (?, ?, ?, ?)",
                (_hash(claim), device, to_text(now), to_text(now + timedelta(minutes=CLAIM_MINUTES))),
            )
        return claim

    def claim(self, claim: str, login: str) -> tuple[Device, str] | None:
        """Trade an install claim for a new token of its device, once: the pairing moves into the installed app (the
        old token stops); None for a claim spent, lapsed, unknown, or not the login's."""
        if not claim:
            return None
        now = self.kernel.clock.now()
        rows = self._store.read(
            "SELECT device, expires FROM install_claims WHERE claim_hash = ? AND used IS NULL", (_hash(claim),)
        )
        if not rows or from_text(rows[0]["expires"]) <= now:
            return None
        found = self._store.read("SELECT * FROM devices WHERE id = ?", (rows[0]["device"],))
        if not found:
            return None
        device = _device(found[0])
        if device.revoked is not None or device.login != login:
            return None
        token = secrets.token_urlsafe(32)
        with self._store.transaction() as db:
            db.execute("UPDATE install_claims SET used = ? WHERE claim_hash = ?", (to_text(now), _hash(claim)))
            db.execute(
                "UPDATE devices SET token_hash = ?, last_seen = ? WHERE id = ?", (_hash(token), to_text(now), device.id)
            )
        return _device(self._store.read("SELECT * FROM devices WHERE id = ?", (device.id,))[0]), token

    def all(self) -> list[Device]:
        """Every paired device, the newest first, revoked ones too."""
        return [_device(row) for row in self._store.read("SELECT * FROM devices ORDER BY paired DESC")]

    def revoke(self, id: str) -> Device:
        """Revoke a device: its token no longer works."""
        with self._store.transaction() as db:
            if db.execute("SELECT id FROM devices WHERE id = ?", (id,)).fetchone() is None:
                raise PairingError(f"there is no device {id!r}")
            now = to_text(self.kernel.clock.now())
            db.execute("UPDATE devices SET revoked = ? WHERE id = ? AND revoked IS NULL", (now, id))
        return next(device for device in self.all() if device.id == id)


def _device(row: Any) -> Device:
    revoked = row["revoked"]
    return Device(row["id"], row["name"], row["login"], from_text(row["paired"]), from_text(row["last_seen"]),
                  from_text(revoked) if revoked else None)  # fmt: skip
