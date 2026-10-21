"""Design 0002 §2.8: a secret is a file of its own in `CLANK_HOME/secrets/`, readable only by the user; clients see its
name, when it was set and its last four characters, never its value; a component gets its value through the kernel,
which records who used it and why, without the value; setting and removing one are recorded the same way."""

import json
import os
import sys
from datetime import UTC, datetime

import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, EventLog, EventTypes
from clank.kernel.home import Home
from clank.kernel.kinds import EVENT_TYPES
from clank.kernel.secrets import Secrets, SecretsError
from clank.kernel.store import Store, kernel_migrations

YOU = Actor(kind="user", via="cli")
VALUE = "sk-test-0123456789abcd"


@pytest.fixture
def secrets(home: Home) -> Secrets:
    home.ensure()
    store = Store(home.database)
    store.migrate(kernel_migrations())
    clock = FakeClock(datetime(2026, 10, 13, 18, 0, tzinfo=UTC))
    return Secrets(home, EventLog(store, clock, EventTypes(EVENT_TYPES)), clock)


def written(home: Home) -> str:
    """Everything Clank wrote outside its secrets folder: the settings, the state database, the logs."""
    found = []
    for path in home.root.rglob("*"):
        if path.is_file() and home.secrets not in path.parents:
            found.append(path.read_bytes().decode("utf-8", errors="replace"))
    return "\n".join(found)


def test_a_secret_is_a_file_of_its_own_that_only_the_user_can_read(home: Home, secrets: Secrets) -> None:
    secrets.put("mcp-server/myproject", "env.API_KEY", VALUE, actor=YOU)
    [path] = [path for path in home.secrets.rglob("*") if path.is_file()]
    assert path.read_text(encoding="utf-8") == VALUE
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o077 == 0, "readable only by the user"
    assert secrets.value("mcp-server/myproject", "env.API_KEY", user="tools", why="a check") == VALUE


def test_clients_see_its_name_when_it_was_set_and_its_last_four_characters(secrets: Secrets) -> None:
    secrets.put("mcp-server/myproject", "env.API_KEY", VALUE, actor=YOU)
    [shown] = secrets.shown("mcp-server/myproject")
    assert (shown.name, shown.ends, shown.set) == ("env.API_KEY", "abcd", "2026-10-13T18:00:00.000Z")
    assert VALUE not in json.dumps(shown.__dict__)


def test_using_setting_and_removing_one_are_recorded_without_its_value(home: Home, secrets: Secrets) -> None:
    secrets.put("mcp-server/myproject", "env.API_KEY", VALUE, actor=YOU)
    secrets.value("mcp-server/myproject", "env.API_KEY", user="tools", why="a check")
    secrets.remove("mcp-server/myproject", actor=YOU)
    types = [event.type for event in secrets.events.latest(10)]
    assert {"secret.set", "secret.used", "secret.removed"} <= set(types)
    assert VALUE not in written(home)
    assert secrets.shown("mcp-server/myproject") == []
    with pytest.raises(SecretsError, match=r"no secret env\.API_KEY"):
        secrets.value("mcp-server/myproject", "env.API_KEY", user="tools", why="a check")


def test_a_name_that_could_leave_its_folder_is_refused(secrets: Secrets) -> None:
    for scope, name in (("mcp-server/../x", "a"), ("mcp-server/x", "../a"), ("mcp-server/x", "a/b")):
        with pytest.raises(SecretsError, match="cannot be"):
            secrets.put(scope, name, VALUE, actor=YOU)
    assert not any(part for part in os.listdir(secrets.folder) if part.startswith(".."))
