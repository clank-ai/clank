"""Design 0014 §2 (decision 0070): the container platform adapter is chosen by platform and by what answers, asking no
engine. `auto`, the setting's default, is Docker Desktop on Windows and macOS. On Linux it is the adapter of the engine
the docker command would use: Docker Desktop when the command's current context is Docker Desktop's (desktop-linux);
else Docker Engine when systemd knows Docker's service; else Docker Desktop when its own command answers (a stopped
Docker Desktop, with no Docker Engine beside it); else Docker Engine, which asks the engine directly, says that Docker
from the snap and rootless Docker are unsupported, or says how to install Docker when there is no docker command. A name
set in the settings wins. Each choice says why, and the platform made keeps it. Docker Desktop on Linux names its own
context on every command; elsewhere its commands do not change. The workspaces say which adapter is in use, and
Docker's view says which, why, and whether Clank starts it."""

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.adapters.choose import choose_platform
from clank.components.workspaces.adapters.docker_desktop import DockerDesktop
from clank.components.workspaces.adapters.docker_engine import SYSTEMD, DockerEngine
from clank.components.workspaces.service import Workspaces, make_platform
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import open_kernel
from clank.kernel.home import Home
from clank.kernel.processes import TIMEOUT_SECONDS, Answer
from tests.fakes.platform import FakePlatform

CONTEXT = "docker context show"
SYSTEMD_ASKED = " ".join(SYSTEMD)
DESKTOP = "docker desktop version --format json"
ASKS_NO_ENGINE = {CONTEXT, SYSTEMD_ASKED, DESKTOP}


class Computer:
    """What answers on a computer: each command's answer by the program's name and its arguments (none: it does not
    answer); every command asked kept."""

    def __init__(self, answers: Mapping[str, Answer]) -> None:
        self.answers = dict(answers)
        self.asked: list[str] = []

    def __call__(
        self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None
    ) -> Answer:
        asked = " ".join([Path(arguments[0]).name, *arguments[1:]])
        self.asked.append(asked)
        return self.answers.get(asked, Answer(1, "", f"{arguments[0]}: no answer"))

    def run(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        found = self(arguments, timeout)
        return found.output if found.ok else None


def systemd(load: str, active: str = "inactive") -> Answer:
    return Answer(0, f"LoadState={load}\nActiveState={active}\n", "")


def choose(computer: Computer, platform: str = "linux", docker: str | None = "/usr/bin/docker") -> tuple[str, str]:
    return choose_platform("auto", platform=platform, answer=computer, which=lambda name: docker, environ={})


def test_docker_engine_is_used_where_docker_desktop_is_not() -> None:
    computer = Computer({CONTEXT: Answer(0, "default\n", ""), SYSTEMD_ASKED: systemd("loaded", "inactive")})
    chosen, why = choose(computer)
    assert chosen == "docker-engine"
    assert why == "Docker Engine: this is Linux, and systemd knows Docker's service"


def test_docker_desktop_is_used_on_windows_and_macos_and_where_its_context_is_current_on_linux() -> None:
    for system, said in (("win32", "Windows"), ("darwin", "macOS")):
        computer = Computer({})
        chosen, why = choose(computer, platform=system)
        assert (chosen, computer.asked) == ("docker-desktop", [])
        assert said in why
    current = Computer({CONTEXT: Answer(0, "desktop-linux\n", ""), SYSTEMD_ASKED: systemd("loaded", "active")})
    chosen, why = choose(current)
    assert chosen == "docker-desktop", "Docker Desktop runs: the docker command's context is its own"
    assert "desktop-linux" in why


def test_a_stopped_docker_desktop_is_still_chosen_where_no_docker_engine_is_installed() -> None:
    computer = Computer(
        {
            CONTEXT: Answer(0, "default\n", ""),
            SYSTEMD_ASKED: systemd("not-found"),
            DESKTOP: Answer(0, '{"version":"v0.4.3"}\n', ""),
        }
    )
    chosen, why = choose(computer)
    assert chosen == "docker-desktop"
    assert "its own command answers" in why


def test_a_docker_command_without_dockers_system_service_asks_the_engine_directly() -> None:
    for answers in ({CONTEXT: Answer(0, "default\n", ""), SYSTEMD_ASKED: systemd("not-found")}, {}):
        chosen, why = choose(Computer(answers))
        assert chosen == "docker-engine"
        assert "no Docker Desktop answers" in why


def test_the_snap_and_rootless_docker_go_to_docker_engine_which_says_they_are_unsupported() -> None:
    computer = Computer({CONTEXT: Answer(0, "default\n", ""), SYSTEMD_ASKED: systemd("not-found")})
    chosen, _ = choose(computer, docker="/snap/bin/docker")
    assert chosen == "docker-engine"
    snap = DockerEngine(computer.run, "/snap/bin/docker", platform="linux", answer=computer, environ={}).status()
    assert (snap.state, "docs.docker.com/engine/install" in snap.detail) == ("unsupported", True)
    rootless = Computer({CONTEXT: Answer(0, "rootless\n", ""), SYSTEMD_ASKED: systemd("not-found")})
    assert choose(rootless)[0] == "docker-engine"
    status = DockerEngine(rootless.run, "/usr/bin/docker", platform="linux", answer=rootless, environ={}).status()
    assert (status.state, "rootless" in status.detail) == ("unsupported", True)


def test_without_a_docker_command_docker_engine_says_how_to_install_it() -> None:
    computer = Computer({})
    chosen, why = choose(computer, docker=None)
    assert chosen == "docker-engine"
    assert "no docker command" in why
    status = DockerEngine(computer.run, None, platform="linux", answer=computer).status()
    assert status.state == "not installed"
    assert "docs.docker.com/engine/install" in status.detail


def test_an_adapter_named_in_the_settings_is_used_as_named() -> None:
    computer = Computer({CONTEXT: Answer(0, "desktop-linux\n", "")})
    for named, system in (("docker-engine", "linux"), ("docker-desktop", "linux"), ("docker-engine", "win32")):
        chosen, why = choose_platform(named, platform=system, answer=computer, which=lambda name: "docker", environ={})
        assert (chosen, why) == (named, "named in config/docker.json")
    assert computer.asked == [], "a name set there is used without asking anything"


def test_choosing_an_adapter_asks_no_engine() -> None:
    answers = [
        {CONTEXT: Answer(0, "default\n", ""), SYSTEMD_ASKED: systemd("loaded", "active")},
        {CONTEXT: Answer(0, "default\n", ""), SYSTEMD_ASKED: systemd("not-found")},
        {SYSTEMD_ASKED: systemd("not-found"), DESKTOP: Answer(0, "{}\n", "")},
        {CONTEXT: Answer(0, "desktop-linux\n", "")},
        {},
    ]
    for each in answers:
        computer = Computer(each)
        choose(computer)
        assert set(computer.asked) <= ASKS_NO_ENGINE, computer.asked


def test_docker_desktop_on_linux_names_its_own_context_and_elsewhere_changes_nothing() -> None:
    sent: list[list[str]] = []

    def answer(arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        sent.append(list(arguments))
        return Answer(0, "", "")

    for system, prefix in (("linux", ["docker", "--context", "desktop-linux"]), ("win32", ["docker"])):
        sent.clear()
        desktop = DockerDesktop(lambda arguments, timeout=0.0: None, "docker", platform=system, answer=answer)
        desktop.image_exists("clank-sandbox:abc")
        handed = desktop.exec_argv("clank-abc-x", ["opencode"], workdir="/workspace")
        assert sent[0][: len(prefix)] == prefix
        assert sent[0][len(prefix)] == "image"
        assert handed[: len(prefix) + 1] == [*prefix, "exec"]


def test_the_platform_made_from_the_settings_keeps_why_it_was_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspaces_service, "choose_platform", lambda setting: ("docker-engine", "a test's reason"))
    monkeypatch.setattr(DockerEngine, "find", classmethod(lambda cls: "/usr/bin/docker"))
    made = make_platform("auto")
    assert isinstance(made, DockerEngine)
    assert (made.command, made.chosen) == ("/usr/bin/docker", "a test's reason")


@pytest.fixture
def http(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Workspaces]]:
    platform = FakePlatform(state="stopped", starts=False, detail="start it with `sudo systemctl start docker`")
    platform.chosen = "Docker Engine: this is Linux, and systemd knows Docker's service"
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 27, 12, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as client:
        yield client, kernel.parts["workspaces"]
    kernel.close()


def test_dockers_view_says_which_adapter_was_chosen_why_and_whether_clank_starts_it(
    http: tuple[TestClient, Workspaces],
) -> None:
    client, workspaces = http
    view = client.get("/api/v1/docker", headers={"Authorization": "Bearer t"}).json()
    assert (view["adapter"], view["chosen"], view["starts"]) == (
        "fake",
        "Docker Engine: this is Linux, and systemd knows Docker's service",
        False,
    )
    assert view["said"] == "Fake Docker is stopped: start it with `sudo systemctl start docker`"
    assert workspaces.platform_adapter() == "fake", "the edge's way to the gateway depends on it (design 0014 §3)"
