"""Design 0024 §5 and §6 (decision 0141): the named sets of hosts (Python packages, papers, code, data and models,
documentation) live in `CLANK_HOME/config/network-sets.json`, written with the defaults when missing and read each
time, so the owner can change it; a set allowed writes its hosts into the workspace's record one by one, each marked
with the set, and taking it back removes those still marked (a host the owner also allowed by name stays); the route
and the command (`clank workspace allow FOLDER --set papers`, `clank workspace sets`); the agent's instructions
(`network.md`) name the proxy, the ask once in words, and the literature calls, every host of which the Papers set
allows. Design 0004 §10 (decision 0169): the set `setup` is what a workspace's setup reaches, the package indexes,
Clank's default while the owner's file names none (the file left as it is), the owner's to change, listed with the
others and never allowed to an agent."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.gateway.proxy import allowed_host
from clank.components.workspaces import network
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.folders import WorkspaceError
from clank.components.workspaces.sandbox import image_folder
from clank.components.workspaces.service import Workspaces
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

OWNER = Actor(kind="user", via="console")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7728), base_url="http://127.0.0.1:7728") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7728", "t", name="cli", http=client))
        yield client


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


def paper(kernel: Kernel, folder: Path) -> Workspaces:
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    found: Workspaces = kernel.parts["workspaces"]
    return found


def test_the_sets_file_is_written_with_the_defaults_and_read_back_when_the_owner_changes_it(home: Home) -> None:
    found = network.sets(home)
    assert list(found) == ["python", "papers", "code", "data", "docs", "setup"]
    assert found["papers"]["hosts"][:2] == ["arxiv.org", "export.arxiv.org"]
    assert "pypi.org" in found["python"]["hosts"]
    assert found["python"]["for"].startswith("pip install")
    file = home.config / "network-sets.json"
    assert file.is_file(), "a readable file the owner can change"
    written = json.loads(file.read_text(encoding="utf-8"))
    written["mine"] = {"hosts": ["example.test"], "for": "a test"}
    file.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
    assert network.sets(home)["mine"] == {"hosts": ["example.test"], "for": "a test"}, "read each time it is used"
    file.write_text("{ not json", encoding="utf-8")
    with pytest.raises(WorkspaceError) as refused:
        network.sets(home)
    assert "network-sets.json" in str(refused.value)


def test_a_set_allowed_writes_its_hosts_marked_with_it_and_taking_it_back_removes_only_those(
    kernel: Kernel, tmp_path: Path
) -> None:
    workspaces = paper(kernel, tmp_path)
    view = workspaces.allow_set("paper", "papers", True, actor=OWNER)
    hosts = view["hosts"]
    assert set(network.sets(kernel.home)["papers"]["hosts"]) <= set(hosts)
    assert all("(set papers)" in how for how in hosts.values())
    workspaces.allow_host("paper", "arxiv.org", True, actor=OWNER)  # also by name: the note is the owner's own
    assert "(set papers)" not in workspaces.records()[0]["hosts"]["arxiv.org"]
    after = workspaces.allow_set("paper", "papers", False, actor=OWNER)
    assert list(after["hosts"]) == ["arxiv.org"], "the set's hosts gone, the one allowed by name stays"
    with pytest.raises(WorkspaceError) as refused:
        workspaces.allow_set("paper", "nope", True, actor=OWNER)
    assert "papers" in str(refused.value), "the sets there are named"
    events = kernel.events.after(0, types=["workspaces.host_allowed"])
    assert sum(1 for event in events if event.data["allowed"]) == len(network.sets(kernel.home)["papers"]["hosts"]) + 1


def test_the_route_and_the_command_allow_a_set_and_list_the_sets(
    kernel: Kernel, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    assert run("workspace", "open", "--yes").exit_code == 0
    listed = http.get("/api/v1/workspaces/network-sets", headers={"Authorization": "Bearer t"}).json()
    assert "github.com" in listed["code"]["hosts"]
    allowed = http.post("/api/v1/workspaces/paper/sets", json={"set": "code", "allow": True},
                        headers={"Authorization": "Bearer t"})  # fmt: skip
    assert allowed.status_code == 200, allowed.text
    assert "github.com" in allowed.json()["hosts"]
    said = run("workspace", "allow", str(folder), "--set", "papers")
    assert said.exit_code == 0, said.output
    assert "paper: its agent may reach api.crossref.org, " in said.output
    taken = run("workspace", "allow", str(folder), "--no-set", "code", "--no-set", "papers")
    assert taken.exit_code == 0, taken.output
    assert "paper: its agent reaches no host" in taken.output
    sets = run("workspace", "sets")
    assert sets.exit_code == 0, sets.output
    assert "papers" in sets.output
    assert "export.arxiv.org" in sets.output
    assert "finding and reading papers" in sets.output
    assert "setup: pypi.org, files.pythonhosted.org" in sets.output, "what a setup reaches, shown as the others"
    assert run("workspace", "allow", str(folder), "--set", "nope").exit_code != 0
    assert run("workspace", "allow", str(folder), "--set", "setup").exit_code != 0, "a setup's, never the agent's"


def test_the_setup_set_names_the_package_indexes_a_setup_reaches_and_is_never_an_agents(
    kernel: Kernel, tmp_path: Path
) -> None:
    """Design 0004 §10 (decision 0169): the set `setup`, Clank's own default while the owner's file names none."""
    found = network.sets(kernel.home)["setup"]
    assert found["hosts"] == ["pypi.org", "files.pythonhosted.org"]
    assert "a workspace's setup" in found["for"]
    assert network.setup_hosts(kernel.home) == ["pypi.org", "files.pythonhosted.org"]
    file = kernel.home.config / "network-sets.json"
    older = json.loads(file.read_text(encoding="utf-8"))
    del older["setup"]  # a file written before the set
    file.write_text(json.dumps(older, indent=2) + "\n", encoding="utf-8")
    assert network.setup_hosts(kernel.home) == ["pypi.org", "files.pythonhosted.org"], "Clank's default"
    assert "a set named setup in config/network-sets.json changes it" in network.sets(kernel.home)["setup"]["for"]
    assert "setup" not in json.loads(file.read_text(encoding="utf-8")), "the owner's file is left as it is"
    older["setup"] = {"hosts": ["pypi.org", "files.pythonhosted.org", "download.pytorch.org"], "for": "mine"}
    file.write_text(json.dumps(older, indent=2) + "\n", encoding="utf-8")
    assert network.setup_hosts(kernel.home)[-1] == "download.pytorch.org", "the owner's to change"
    workspaces = paper(kernel, tmp_path)
    with pytest.raises(WorkspaceError) as refused:
        workspaces.allow_set("paper", "setup", True, actor=OWNER)
    assert "python" in str(refused.value), "the set for the agent's own pip install is named"
    assert workspaces.records()[0]["hosts"] == {}


def test_the_instructions_tell_the_agent_how_it_reaches_the_internet_and_the_literature_calls_fit_the_papers_set(
    home: Home,
) -> None:
    text = (image_folder() / "instructions" / "network.md").read_text(encoding="utf-8")
    assert "proxy" in text
    assert "ask" in text, "the agent may ask once, in words"
    assert "once" in text
    assert "curl" in text
    assert "requests" in text
    assert "Private addresses" in text or "private address" in text
    hosts = set(re.findall(r"https?://([a-z0-9.-]+)/", text))
    assert hosts >= {"export.arxiv.org", "api.semanticscholar.org", "api.crossref.org", "api.openalex.org"}
    papers = network.sets(home)["papers"]["hosts"]
    assert all(allowed_host(host, papers) for host in hosts), (
        f"a host the instructions name is not in the Papers set: {hosts}"
    )
