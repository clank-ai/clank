"""Design 0021 §11: Clank's service, and Docker Desktop through it, start when the owner signs in to Windows, so the PC
is ready for remote work after a restart. `clank autostart on` writes the entry Windows runs at sign-in (the current
user's Run key, `Clank`): Python's windowless program running `clank autostart run`, with CLANK_HOME when it is set;
`off` removes it; `status` says whether it is there and what it runs. `run` starts the service in the background when
it does not run, then asks it to start Docker, writing what it did to logs/autostart.log. On another system, `on` says
it is not supported there yet."""

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from clank.cli import autostart, common, follow
from clank.cli.main import main
from clank.client import NotRunning
from clank.kernel.home import Home


class Run:
    """The current user's Run key, as the tests see it."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}


@pytest.fixture
def run_key(monkeypatch: pytest.MonkeyPatch) -> Run:
    key = Run()
    monkeypatch.setattr(autostart, "WINDOWS", True)
    monkeypatch.setattr(autostart, "read_entry", lambda: key.values.get(autostart.ENTRY))
    monkeypatch.setattr(autostart, "write_entry", lambda command: key.values.__setitem__(autostart.ENTRY, command))
    monkeypatch.setattr(autostart, "delete_entry", lambda: key.values.pop(autostart.ENTRY, None))
    monkeypatch.setattr(autostart, "windowless", lambda: "D:/tools/clank/Scripts/pythonw.exe")
    return key


def clank(*arguments: str) -> Result:
    return CliRunner().invoke(main, ["autostart", *arguments])


def test_on_writes_the_sign_in_entry_off_removes_it_and_status_says_which(
    run_key: Run, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLANK_HOME", raising=False)
    assert "is off" in clank("status").output
    done = clank("on")
    assert done.exit_code == 0, done.output
    assert run_key.values["Clank"] == '"D:/tools/clank/Scripts/pythonw.exe" -P -m clank autostart run'
    assert "starts Clank's service and Docker when you sign in" in done.output
    assert "Task Manager" in done.output
    assert "is on" in clank("status").output
    monkeypatch.setenv("CLANK_HOME", "D:/clank-home")
    clank("on")
    assert run_key.values["Clank"].endswith('autostart run --home "D:/clank-home"'), "a home of its own goes with it"
    assert clank("off").exit_code == 0
    assert "Clank" not in run_key.values
    assert "is off" in clank("status").output


def test_on_another_system_it_says_it_is_not_supported_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "WINDOWS", False)
    done = clank("on")
    assert done.exit_code == 1
    assert "Windows only for now" in done.output


def test_run_starts_the_service_when_it_does_not_run_then_asks_it_to_start_docker(
    home: Home, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLANK_HOME", str(home.root))
    started: list[Path] = []
    posted: list[str] = []

    class Client:
        def post(self, path: str, body: Any = None) -> dict[str, Any]:
            posted.append(path)
            return {"id": "op-1", "status": "running"}

    def connect() -> Client:
        if not started:
            raise NotRunning("the service does not run")
        return Client()

    monkeypatch.setattr(common, "connect", connect)
    monkeypatch.setattr(autostart, "start_detached", lambda found: started.append(found.root))
    monkeypatch.setattr(follow, "follow", lambda client, operation: {"status": "done"})
    done = clank("run")
    assert done.exit_code == 0, done.output
    assert started == [home.root]
    assert posted == ["docker/start"]
    written = (home.logs / "autostart.log").read_text(encoding="utf-8")
    assert "started Clank's service" in written
    assert "Docker: done" in written
