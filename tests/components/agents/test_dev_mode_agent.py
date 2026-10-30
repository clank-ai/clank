"""Design 0024 §3 and §6 (decision 0152): dev mode, for the agent. OpenCode may fetch and search (`webfetch` and
`websearch` allowed in its configuration) once it starts in a folder while dev mode is on, and not otherwise; a window
already open keeps what it started with until it starts again. The agent's network instructions say, in dev mode,
that every public host answers at once, with no question and no wait, and that private addresses still never do; off,
they are the file as it is. They are one file, written at each start of the agent as dev mode says then, and written
again in every running workspace's container whenever dev mode is turned on or off, so none of dev mode's words is
left in a container once it is off, an agent starting while it is turned off included."""

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.adapters.program import AgentModel
from clank.components.agents.service import Agents
from clank.components.workspaces.sandbox import AGENT_CLANK, agent_files, image_folder, names
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents.test_agent_servers import CONFIG, kernel, opened, platform  # noqa: F401 (fixtures)
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
MODEL = AgentModel(url="http://edge:18210/v1", name="agent", title="daily 262K", context=262144, output=16384)
NETWORK = f"{AGENT_CLANK}/instructions/network.md"
NORMAL = (image_folder() / "instructions" / "network.md").read_text(encoding="utf-8")
DEV_WORDS = "Dev mode is on"


def says_dev(text: str) -> bool:
    return DEV_WORDS in text


def as_it_is(text: str) -> bool:
    return text == NORMAL


def written(fake: FakePlatform, name: str, wanted: Callable[[str], bool], seconds: float = 10) -> str:
    """The network instructions in a container once they are as wanted: a change heard writes them in a thread of its
    own."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = fake.files.get((name, NETWORK), "")
        if wanted(found):
            return found
        threading.Event().wait(0.02)
    raise AssertionError(f"never as wanted in {name}: {fake.files.get((name, NETWORK), '')[:300]!r}")


def dev(machine: Kernel, on: bool) -> None:
    """Dev mode turned on or off, as the console does."""
    machine.parts["runtime"].endpoints.set_dev(on, actor=YOU)


def webfetch(fake: FakePlatform, name: str) -> str:
    """What OpenCode's configuration in the container says of its `webfetch`."""
    return str(json.loads(fake.files[(name, CONFIG)])["permission"]["webfetch"])


def test_in_dev_mode_opencode_may_fetch_and_search_and_otherwise_not() -> None:
    told = json.loads(OpenCode().configuration(MODEL)[1])["permission"]
    assert (told["webfetch"], told["websearch"]) == ("deny", "deny")
    opened_up = json.loads(OpenCode().configuration(MODEL, web=True)[1])["permission"]
    assert opened_up == {"external_directory": "deny", "webfetch": "allow", "websearch": "allow", "edit": "ask"}, (
        "its web tools only: nothing outside the folder, and every change to a file still asked about"
    )


def test_in_dev_mode_the_instructions_say_every_public_host_answers_at_once_and_private_addresses_never() -> None:
    assert dict(agent_files())[NETWORK] == NORMAL, "off: the file as it is"
    told = dict(agent_files(dev_mode=True))[NETWORK]
    for needed in (DEV_WORDS, "every public host", "at once", "no question and no wait", "git clone https://",
                   "Private addresses", "still never", "`webfetch`"):  # fmt: skip
        assert needed in told, needed
    assert "holds your request while the owner is asked" not in told, "nothing waits for the owner in dev mode"
    assert told.count("# The internet") == 1
    literature = "## The literature, without a search engine"
    assert told.split(literature)[1] == NORMAL.split(literature)[1], "the literature's calls as they are"
    others = {path: text for path, text in agent_files(dev_mode=True) if path != NETWORK}
    assert others == {path: text for path, text in agent_files() if path != NETWORK}, "only the network's change"


def test_starting_the_agent_in_dev_mode_gives_it_the_web_and_says_so_and_turning_it_off_takes_the_words_back(
    kernel: Kernel,  # noqa: F811
    platform: FakePlatform,  # noqa: F811
    tmp_path: Path,
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    name = opened(kernel, platform, folder)
    agents: Agents = kernel.parts["agents"]
    agents.prepare("paper")
    assert webfetch(platform, name) == "deny"
    assert platform.files[(name, NETWORK)] == NORMAL
    dev(kernel, True)
    written(platform, name, says_dev)  # the running container told at once, its OpenCode not started again
    assert webfetch(platform, name) == "deny", "the window already open keeps what it started with"
    agents.prepare("paper")
    assert webfetch(platform, name) == "allow", "from its next start"
    assert json.loads(platform.files[(name, CONFIG)])["permission"]["websearch"] == "allow"
    assert says_dev(platform.files[(name, NETWORK)])
    dev(kernel, False)
    written(platform, name, as_it_is)  # none of dev mode's words left in the container, with no start of OpenCode
    agents.configure("paper")  # a window started without a terminal (a flow's box, the phone)
    assert webfetch(platform, name) == "deny"
    assert platform.files[(name, NETWORK)] == NORMAL


def test_a_change_of_dev_mode_writes_the_instructions_in_every_running_container_and_no_other(
    kernel: Kernel,  # noqa: F811
    platform: FakePlatform,  # noqa: F811
    tmp_path: Path,
) -> None:
    for each in ("paper", "notes", "idle"):
        (tmp_path / each).mkdir()
        kernel.settings.write("workspace", each, {"path": str(tmp_path / each)}, base=None, actor=YOU)
    found = names(kernel.home.id)
    for each in ("paper", "notes"):
        platform.containers.append(container(found.container(each), labels={"clank.home": kernel.home.id}))
    platform.containers.append(container(found.container("idle"), state="exited"))
    agents: Agents = kernel.parts["agents"]
    assert sorted(agents.tell_network()) == ["notes", "paper"], "the containers that run, as dev mode says: off"
    assert platform.files[(found.container("paper"), NETWORK)] == NORMAL
    dev(kernel, True)
    for each in ("paper", "notes"):
        written(platform, found.container(each), says_dev)
    assert (found.container("idle"), NETWORK) not in platform.files, "one that does not run: its agent's next start"


def test_dev_mode_turned_off_while_an_agent_starts_leaves_none_of_its_words(
    kernel: Kernel,  # noqa: F811
    platform: FakePlatform,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    name = opened(kernel, platform, folder)
    dev(kernel, True)
    written(platform, name, says_dev)
    put = platform.put_file

    def turned_off_meanwhile(where: str, path: str, text: str) -> None:
        if path == NETWORK and says_dev(text) and kernel.parts["runtime"].settings().dev_mode:
            dev(kernel, False)  # the owner turns dev mode off as the agent starts
            time.sleep(0.3)  # the change's own writing would land first, and the start's words after it
        put(where, path, text)

    monkeypatch.setattr(platform, "put_file", turned_off_meanwhile)
    kernel.parts["agents"].prepare("paper")
    written(platform, name, as_it_is)
    time.sleep(0.3)
    assert platform.files[(name, NETWORK)] == NORMAL, "and it stays so"
