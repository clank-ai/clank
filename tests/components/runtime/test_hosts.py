"""Design 0003 §2-§3 and decision 0030: the runtime's hosts are this machine and each host record; a record naming a
WSL distribution gives a WSL host there; `clank host add` writes one only for a distribution WSL has, recorded as you
(cli); and `clank host list` and the API list them with their kind and Clank folder."""

import json
from collections.abc import Iterator

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.machine import service as machine_service
from clank.components.machine.kinds import MachineProfile
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.hosts.wsl import WslHost
from clank.components.runtime.service import HostNotFound, Runtime
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    monkeypatch.setattr(WslHost, "distributions", staticmethod(lambda run=None: ["Ubuntu-22.04", "Ubuntu"]))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=client))
        yield client


def runtime(kernel: Kernel) -> Runtime:
    part: Runtime = kernel.parts["runtime"]
    return part


def test_this_machine_is_a_host_and_a_record_naming_a_distribution_is_a_wsl_host(kernel: Kernel) -> None:
    assert isinstance(runtime(kernel).host("local"), LocalHost)
    runtime(kernel).add_host("ubuntu", "wsl", distro="Ubuntu", actor=YOU)
    found = runtime(kernel).host("ubuntu")
    assert isinstance(found, WslHost)
    assert (found.distro, found.name) == ("Ubuntu", "ubuntu")
    with pytest.raises(HostNotFound, match="there is no host named 'elsewhere'"):
        runtime(kernel).host("elsewhere")


def test_a_host_is_added_only_for_a_distribution_wsl_has(kernel: Kernel) -> None:
    with pytest.raises(ValueError, match=r"WSL has no distribution named Debian; it has Ubuntu-22.04, Ubuntu"):
        runtime(kernel).add_host("debian", "wsl", distro="Debian", actor=YOU)


def test_the_commands_add_and_list_hosts_and_the_api_lists_them(http: TestClient, kernel: Kernel) -> None:
    added = CliRunner().invoke(main, ["host", "add", "ubuntu-22.04", "--wsl", "Ubuntu-22.04"])
    assert added.exit_code == 0, added.output
    assert "Added the host ubuntu-22.04: WSL's Ubuntu-22.04, its Clank folder ~/.clank" in added.output
    record = kernel.settings.get("host", "ubuntu-22.04")
    assert record.record.model_dump()["distro"] == "Ubuntu-22.04"
    changed = [event for event in kernel.events.latest(5, types=["settings.changed"])]
    assert changed[0].actor.via == "cli"
    listed = CliRunner().invoke(main, ["host", "list"])
    assert "local         this machine       ~/.clank" in listed.output, "its columns line up"
    assert "ubuntu-22.04  WSL: Ubuntu-22.04  ~/.clank" in listed.output
    hosts = http.get("/api/v1/runtime/hosts", headers=AUTH).json()
    assert [(host["name"], host["adapter"]) for host in hosts] == [("local", "local"), ("ubuntu-22.04", "wsl")]
    refused = CliRunner().invoke(main, ["host", "add", "debian", "--wsl", "Debian"])
    assert refused.exit_code == 1
    assert "WSL has no distribution named Debian" in refused.output
    as_json = json.loads(CliRunner().invoke(main, ["host", "list", "--json"]).output)
    assert as_json[1]["distro"] == "Ubuntu-22.04"
