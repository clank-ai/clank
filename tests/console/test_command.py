"""Design 0001 §5.8 and design 0002 §2.15: `clank console --snapshot` prints one frame of the console as text; when
the service is not running, `clank console` starts it in the background first, and with --no-start says how to start
it instead. Design 0013 §15: `--view` opens a page with views on one of them (the Monitor's Flow view)."""

from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from clank.cli import console as console_command
from clank.cli.main import main
from clank.client import Client
from clank.kernel.access import Connection, write_connection
from clank.kernel.home import Home


def test_snapshot_prints_one_frame_of_the_console(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_command, "connect", lambda home, start: client)
    shown = CliRunner().invoke(main, ["console", "--snapshot", "--page", "home", "--width", "100", "--height", "30"])
    assert shown.exit_code == 0, shown.output
    assert "CLANK" in shown.output
    assert "What runs" in shown.output
    assert len(shown.output.splitlines()[0]) <= 100


def test_without_a_service_the_console_starts_one_in_the_background_first(
    client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Home] = []

    def start_in_the_background(found: Home) -> Connection:
        started.append(found)
        (found.state / "local.token").write_text("t\n", encoding="utf-8")
        connection = Connection(client.url, 1, datetime.now(UTC), "0.0.0")
        write_connection(found, connection)
        return connection

    monkeypatch.setattr(console_command, "start_detached", start_in_the_background)
    shown = CliRunner().invoke(main, ["console", "--snapshot"], env={"CLANK_HOME": str(home.root)})
    assert shown.exit_code == 0, shown.output
    assert "starting it in the background" in shown.output
    assert [found.root for found in started] == [home.root]


def test_with_no_start_it_says_how_to_start_the_service_instead(home: Home) -> None:
    shown = CliRunner().invoke(main, ["console", "--no-start"], env={"CLANK_HOME": str(home.root)})
    assert shown.exit_code == 1
    assert "clank serve" in shown.output


def test_view_opens_the_monitor_on_its_flow_view_for_a_terminal_that_keeps_f10(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0013 §15: `clank console --page monitor --view flow` (or `--view flow` alone) opens the Monitor's Flow
    view, for a terminal over SSH that keeps F10 for itself."""
    monkeypatch.setattr(console_command, "connect", lambda home, start: client)
    shown = CliRunner().invoke(main, ["console", "--snapshot", "--page", "monitor", "--view", "flow"])
    assert shown.exit_code == 0, shown.output
    assert "No flow yet" in shown.output
    alone = CliRunner().invoke(main, ["console", "--snapshot", "--view", "flow"])
    assert "No flow yet" in alone.output
