"""Design 0002 §2.7: local clients prove they are the user on this machine by reading the local token, find the
service through its connection file, and what they do is recorded as the user, through that client."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank.kernel.access import (
    Connection,
    client_actor,
    local_token,
    read_connection,
    remove_connection,
    write_connection,
)
from clank.kernel.events import Actor
from clank.kernel.home import Home


def test_the_token_is_created_once_and_then_kept(home: Home) -> None:
    first = local_token(home)
    assert local_token(home) == first
    assert (home.state / "local.token").read_text(encoding="utf-8").strip() == first


def test_the_token_is_long_and_random(tmp_path: Path) -> None:
    one, two = local_token(Home(tmp_path / "a")), local_token(Home(tmp_path / "b"))
    assert len(one) >= 40
    assert one != two


@pytest.mark.skipif(sys.platform == "win32", reason="Windows keeps a user's own folders private by its own rules")
def test_the_token_file_is_readable_only_by_the_user(home: Home) -> None:
    local_token(home)
    assert os.stat(home.state / "local.token").st_mode & 0o077 == 0


def test_the_connection_file_round_trips_and_is_removed_on_stop(home: Home) -> None:
    assert read_connection(home) is None
    connection = Connection(
        url="http://127.0.0.1:7720", pid=4242, started=datetime(2026, 10, 11, 12, 0, tzinfo=UTC), version="0.1.0.dev0"
    )
    write_connection(home, connection)
    assert read_connection(home) == connection
    remove_connection(home)
    assert read_connection(home) is None


def test_a_clients_name_becomes_the_actor_of_what_it_does() -> None:
    assert client_actor("console") == Actor(kind="user", via="console")
    assert client_actor(None) == Actor(kind="user", via="api")
    assert client_actor("<script>vs code</script>") == Actor(kind="user", via="scriptvscodescript")
