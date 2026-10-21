"""Design 0002 §2.2 and decision 0014: state lives in one SQLite database, written in transactions that commit or roll
back whole, with numbered migrations that are applied once and never edited."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from clank.kernel.store import Migration, MigrationError, Store, kernel_migrations

FIRST = Migration("test", 1, "first", "CREATE TABLE things (name TEXT PRIMARY KEY);")
SECOND = Migration("test", 2, "second", "ALTER TABLE things ADD COLUMN size INTEGER NOT NULL DEFAULT 0;")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    store = Store(tmp_path / "state" / "clank.db")
    yield store
    store.close()


def names(store: Store) -> list[str]:
    return [row["name"] for row in store.read("SELECT name FROM things ORDER BY name")]


def test_migrations_apply_once_and_in_order(store: Store) -> None:
    assert store.migrate([SECOND, FIRST]) == ["test 0001 first", "test 0002 second"]
    assert store.migrate([FIRST, SECOND]) == []
    with store.transaction() as db:
        db.execute("INSERT INTO things (name, size) VALUES ('a', 1)")
    assert names(store) == ["a"]


def test_an_applied_migration_that_was_edited_is_refused(store: Store) -> None:
    store.migrate([FIRST])
    edited = Migration("test", 1, "first", "CREATE TABLE things (name TEXT PRIMARY KEY, extra TEXT);")
    with pytest.raises(MigrationError, match="test 0001 first was edited"):
        store.migrate([edited])


def test_a_failing_migration_leaves_nothing_behind(store: Store) -> None:
    broken = Migration("test", 1, "broken", "CREATE TABLE half (x TEXT);\nTHIS IS NOT SQL;")
    with pytest.raises(MigrationError, match="test 0001 broken"):
        store.migrate([broken])
    assert store.read("SELECT name FROM sqlite_master WHERE name = 'half'") == []
    assert store.read("SELECT * FROM schema_migrations") == []


def fail_halfway(store: Store) -> None:
    with store.transaction() as db:
        db.execute("INSERT INTO things (name) VALUES ('a')")
        raise RuntimeError("halfway")


def fail_after_an_inner_transaction(store: Store) -> None:
    with store.transaction() as outer:
        outer.execute("INSERT INTO things (name) VALUES ('a')")
        with store.transaction() as inner:
            inner.execute("INSERT INTO things (name) VALUES ('b')")
        raise RuntimeError("after the inner one")


def fail_after_registering(store: Store, heard: list[str]) -> None:
    with store.transaction():
        store.after_commit(lambda: heard.append("rolled back"))
        raise RuntimeError("rolled back")


def test_a_transaction_that_fails_writes_nothing(store: Store) -> None:
    store.migrate([FIRST])
    with pytest.raises(RuntimeError, match="halfway"):
        fail_halfway(store)
    assert names(store) == []


def test_nested_transactions_commit_or_roll_back_together(store: Store) -> None:
    store.migrate([FIRST])
    with pytest.raises(RuntimeError, match="after"):
        fail_after_an_inner_transaction(store)
    assert names(store) == []


def test_callbacks_run_only_after_the_outermost_commit_and_never_after_a_rollback(store: Store) -> None:
    store.migrate([FIRST])
    heard: list[str] = []
    with store.transaction():
        store.after_commit(lambda: heard.append("outer"))
        with store.transaction():
            store.after_commit(lambda: heard.append("inner"))
        assert heard == []
    assert heard == ["outer", "inner"]
    with pytest.raises(RuntimeError, match="rolled back"):
        fail_after_registering(store, heard)
    assert heard == ["outer", "inner"]


def test_a_callback_needs_an_open_transaction(store: Store) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        store.after_commit(lambda: None)


def test_the_database_uses_write_ahead_logging(store: Store) -> None:
    assert store.read("PRAGMA journal_mode")[0][0] == "wal"


def test_the_kernels_migrations_create_its_tables(store: Store) -> None:
    assert store.migrate(kernel_migrations()) == [
        "kernel 0001 kernel",
        "kernel 0002 operation_log_step",
        "kernel 0003 canceled_steps",
    ]
    tables = {row["name"] for row in store.read("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"kernel_meta", "events", "operations", "operation_steps", "operation_log", "questions"} <= tables
    assert "step" in {row["name"] for row in store.read("PRAGMA table_info(operation_log)")}
