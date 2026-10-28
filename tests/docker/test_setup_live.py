"""Design 0028 §4 and §5, on this machine's Docker when asked (`-m docker`): `clank setup --check` reads this computer
as it is, through the platform the settings choose and without the service, as on a new computer right after the
installer: Docker installed, running and usable by this account are done, Clank's service is to start, the model and
the folder are not known yet; on Docker Engine, whether systemd starts it with the computer is said, and every command
it offers its owner is one a client runs. Reading it changes nothing: no container, network, volume or image is made
or removed."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from clank.cli.main import main
from clank.components.agents import checklist, setupfacts
from clank.kernel.home import Home
from tests.docker.conftest import docker

pytestmark = pytest.mark.docker


def made() -> list[str]:
    """Every container, network, volume and image this machine's Docker has, by id."""
    found = []
    for what in (("ps", "--all", "--quiet"), ("network", "ls", "--quiet"), ("volume", "ls", "--quiet"),
                 ("image", "ls", "--all", "--quiet")):  # fmt: skip
        found += sorted(docker(*what).stdout.split())
    return found


def test_clank_setup_check_reads_this_computers_docker_as_it_is_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("Docker does not run: start it with `clank docker start`")
    home = Home(tmp_path / "clank-home")
    home.ensure()
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    before = made()
    shown = CliRunner().invoke(main, ["setup", "--check"], env={"CLANK_HOME": str(home.root), "COLUMNS": "160"})
    assert made() == before, "nothing made or removed"
    assert shown.exit_code == 1, "not ready: no service runs for this home"
    assert "Nothing was changed." in shown.output
    found = checklist.view(setupfacts.offline(home, str(folder)))
    states = {item["id"]: item["state"] for item in found["items"]}
    assert states["docker_installed"] == "done", shown.output
    assert states["docker_running"] == "done", shown.output
    assert states["docker_access"] == "done", shown.output
    assert states["service"] == "to do"
    assert (states["model"], states["folder"]) == ("unknown", "unknown")
    reading = setupfacts.offline(home, str(folder)).docker
    if reading.status.adapter != "docker-engine":
        return
    assert "docker_boot" in states, "systemd says whether it starts with the computer"
    offered = [command for command in (reading.setup.start, reading.setup.boot, reading.setup.join) if command]
    assert offered, "the owner's commands"
    for command in offered:
        assert checklist.runnable(command), command
    account = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
    assert reading.setup.join[-1] == account, "the docker group's command names this account"
