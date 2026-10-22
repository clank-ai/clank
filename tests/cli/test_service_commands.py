"""Design 0002 §2.15: `clank status` says whether the service runs and what waits for the user, and how to start it when
it does not; `clank stop` stops it; `clank serve --background` says when a service already runs and starts none, and a
start in the background that fails says only what its own service said (the owner's report, 2026-10-18: the error
quoted another service's log lines), and it runs from Clank's home, never the current folder."""

import socket
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from clank.cli.main import main
from clank.kernel.access import read_connection
from clank.kernel.home import Home
from clank.kernel.service import ServiceError, start_detached
from tests.support.served import served


def test_status_says_how_to_start_the_service_when_it_does_not_run(home: Home) -> None:
    result = CliRunner().invoke(main, ["status"], env={"CLANK_HOME": str(home.root)})
    assert result.exit_code == 1
    assert "not running" in result.output
    assert "clank serve" in result.output


def test_status_shows_the_running_service_and_stop_stops_it(home: Home) -> None:
    environment = {"CLANK_HOME": str(home.root)}
    with served(home) as (process, connection, _):
        status = CliRunner().invoke(main, ["status"], env=environment)
        assert status.exit_code == 0, status.output
        assert "running" in status.output
        assert connection.url in status.output
        as_json = CliRunner().invoke(main, ["status", "--json"], env=environment)
        assert f'"pid": {connection.pid}' in as_json.output
        stopped = CliRunner().invoke(main, ["stop"], env=environment)
        assert stopped.exit_code == 0, stopped.output
        assert process.wait(20) == 0
    assert read_connection(home) is None


def test_serve_in_the_background_says_when_a_service_already_runs_and_starts_no_second_one(home: Home) -> None:
    environment = {"CLANK_HOME": str(home.root)}
    with served(home) as (_, connection, _):
        result = CliRunner().invoke(main, ["serve", "--background"], env=environment)
        assert result.exit_code == 0, result.output
        assert result.output.strip() == (
            f"Clank service already runs on {connection.url} (process {connection.pid}); nothing was started"
        )
        running = read_connection(home)
        assert running is not None
        assert running.pid == connection.pid


def test_a_start_in_the_background_runs_from_clanks_home_never_the_current_folder(
    home: Home, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`python -m clank` reads the current folder first: a service started from a checkout of Clank ran that checkout's
    code, not the one installed (the owner's switch to the public version, 2026-10-22). It starts from Clank's home."""
    seen: dict[str, Any] = {}

    class Ended:
        def poll(self) -> int:
            return 1

    def popen(arguments: list[str], **options: Any) -> Ended:
        seen.update(options)
        return Ended()

    monkeypatch.setattr("clank.kernel.service.subprocess.Popen", popen)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ServiceError):
        start_detached(home, timeout=2)
    assert seen["cwd"] == str(home.root)


def test_a_start_in_the_background_that_fails_says_only_what_its_own_service_said(home: Home) -> None:
    home.ensure()
    earlier = "h11._util.LocalProtocolError: can't handle event type Response when role=SERVER and state=CLOSED\n"
    (home.logs / "service.log").write_text(earlier, encoding="utf-8")  # another service's line, from before
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        port = held.getsockname()[1]
        with pytest.raises(ServiceError) as raised:
            start_detached(home, port)
    message = str(raised.value)
    assert f"port {port} is in use" in message
    assert "LocalProtocolError" not in message
