"""The state database: one SQLite file, written only by the Clank service (decision 0014, design 0002 §2.2).

Every write happens in a transaction that commits or rolls back whole; a transaction opened inside another one joins
it. Callbacks registered with `after_commit` run once the outermost transaction has committed, so a listener only hears
of a change that is there to be read, and they are dropped if it rolls back. Migrations are numbered per owner (the
kernel first, then each component), applied once and in order, and never edited once released: each one's checksum is
kept, and a migration whose text changed is refused. A migration's file must not open or close transactions itself.
One connection serves every thread, behind a lock: the service's writes are small and short.
"""

import hashlib
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from clank.kernel.clock import to_text

MIGRATION_FILE = re.compile(r"^(\d{4})_(\w+)\.sql$")
LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    owner    TEXT NOT NULL,
    number   INTEGER NOT NULL,
    name     TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied  TEXT NOT NULL,
    PRIMARY KEY (owner, number)
)
"""


@dataclass(frozen=True)
class Migration:
    """One numbered change to the database, owned by the kernel or by a component."""

    owner: str
    number: int
    name: str
    sql: str = field(repr=False)

    @property
    def label(self) -> str:
        """How the migration is named in messages: "kernel 0001 kernel"."""
        return f"{self.owner} {self.number:04d} {self.name}"


class MigrationError(Exception):
    """A migration that failed, or one that was edited after it was applied."""


class Store:
    """The state database, opened once by the service (or in memory, with `path=None`, for tests)."""

    def __init__(self, path: Path | None) -> None:
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(
            ":memory:" if path is None else str(path), check_same_thread=False, isolation_level=None
        )
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        self._after: list[Callable[[], None]] = []
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA busy_timeout = 5000")
        if path is not None:
            self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute(LEDGER)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """A transaction that commits when the block ends and rolls back if it raises; inner ones join it."""
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield self._db
                finally:
                    self._depth -= 1
                return
            self._db.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield self._db
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                self._after.clear()
                raise
            finally:
                self._depth = 0
            callbacks, self._after = self._after, []
        for callback in callbacks:
            callback()

    def after_commit(self, callback: Callable[[], None]) -> None:
        """Run `callback` once the open transaction has committed (never, if it rolls back)."""
        with self._lock:
            if not self._depth:
                raise RuntimeError("after_commit needs an open transaction")
            self._after.append(callback)

    def read(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """The rows a query returns."""
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def migrate(self, migrations: Sequence[Migration]) -> list[str]:
        """Apply each migration not applied yet, the kernel's first, in order; returns the labels of those applied."""
        applied: list[str] = []
        with self._lock:
            done = {
                (row["owner"], row["number"]): row["checksum"]
                for row in self._db.execute("SELECT owner, number, checksum FROM schema_migrations")
            }
            for migration in sorted(migrations, key=lambda m: (m.owner != "kernel", m.owner, m.number)):
                checksum = hashlib.sha256(migration.sql.encode("utf-8")).hexdigest()
                key = (migration.owner, migration.number)
                if key in done:
                    if done[key] != checksum:
                        raise MigrationError(
                            f"{migration.label} was edited after it was applied; a change must be a new migration"
                        )
                    continue
                self._apply(migration, checksum)
                applied.append(migration.label)
        return applied

    def _apply(self, migration: Migration, checksum: str) -> None:
        try:
            self._db.executescript("BEGIN IMMEDIATE;\n" + migration.sql)
            self._db.execute(
                "INSERT INTO schema_migrations (owner, number, name, checksum, applied) VALUES (?, ?, ?, ?, ?)",
                (migration.owner, migration.number, migration.name, checksum, to_text(datetime.now(UTC))),
            )
            self._db.execute("COMMIT")
        except sqlite3.Error as error:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise MigrationError(f"{migration.label} failed: {error}") from error

    def close(self) -> None:
        """Close the database."""
        with self._lock:
            self._db.close()


def migrations_in(package: str, owner: str) -> list[Migration]:
    """The migrations kept as `migrations/NNNN_name.sql` files in a package."""
    folder = resources.files(package).joinpath("migrations")
    found: list[Migration] = []
    for entry in folder.iterdir():
        match = MIGRATION_FILE.match(entry.name)
        if match:
            found.append(Migration(owner, int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8")))
    return sorted(found, key=lambda migration: migration.number)


def kernel_migrations() -> list[Migration]:
    """The kernel's own migrations."""
    return migrations_in("clank.kernel", "kernel")
