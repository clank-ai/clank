"""Design 0014 §2 (decision 0070): every container command Clank sends is Docker's own CLI, the same whichever program
runs the engine, so the container methods of the interface are one base's, `DockerCli`, which every adapter extends
without overriding any of them; and every command's arguments start in one place, where an adapter names the engine
its commands go to."""

from collections.abc import Callable, Sequence

from clank.components.workspaces.adapters import CONTAINER_PLATFORMS
from clank.components.workspaces.adapters.docker_cli import DockerCli
from clank.components.workspaces.adapters.platform import ContainerPlatform, PlatformStatus
from clank.components.workspaces.sandbox import ContainerSpec
from clank.kernel.adapters import Capability
from clank.kernel.processes import TIMEOUT_SECONDS, Answer


def container_methods() -> list[str]:
    """The interface's container methods, `limits` to `exec_argv`, in the order it declares them."""
    names = [name for name in vars(ContainerPlatform) if not name.startswith("_")]
    return names[names.index("limits") : names.index("exec_argv") + 1]


def test_every_container_command_is_the_plain_docker_cli_both_adapters_share() -> None:
    methods = container_methods()
    assert "run_container" in methods
    assert "put_files" in methods
    for name in methods:
        assert name in vars(DockerCli), f"DockerCli does not say {name} itself"
    for adapter in CONTAINER_PLATFORMS.all():
        assert issubclass(adapter, DockerCli), adapter.NAME
        overridden = [name for name in methods if name in vars(adapter)]
        assert overridden == [], f"{adapter.NAME} overrides {', '.join(overridden)}"
    assert set(DockerCli.__abstractmethods__) == {"capabilities", "find", "status", "request_start", "request_stop"}


class Named(DockerCli):
    """A platform whose commands go to an engine it names."""

    NAME = "named"
    LABEL = "Named"
    PLATFORMS = ("linux",)

    @classmethod
    def find(cls) -> str | None:
        return "docker"

    def capabilities(self) -> list[Capability]:
        return []

    def status(self) -> PlatformStatus:
        return PlatformStatus(adapter=self.NAME, label=self.LABEL, state="running")

    def request_start(self) -> None:
        pass

    def request_stop(self) -> None:
        pass

    def _target(self) -> list[str]:
        return ["--context", "elsewhere"]


def test_every_command_starts_with_the_engine_its_adapter_names() -> None:
    sent: list[list[str]] = []

    def answer(arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        sent.append(list(arguments))
        return Answer(0, "", "")

    def run(arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        sent.append(list(arguments))
        return ""

    def follow(arguments: Sequence[str], line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
        sent.append(list(arguments))
        return 0

    platform = Named(run, "/usr/bin/docker", platform="linux", answer=answer, follow=follow)
    spec = ContainerSpec(name="x", image="i", labels=(), networks=(("n", ""),), command=("true",), once=True)
    platform.limits()
    platform.containers()
    platform.image_exists("i")
    platform.build_image("i", "/f", {}, lambda text: None, lambda: False)
    platform.ensure_network("n", internal=True, labels={})
    platform.run_container(spec)
    platform.run_once(spec, lambda text: None, lambda: False)
    platform.put_files("x", [("/a", "1")])
    platform.run_in("x", ["ls"], workdir="/workspace")
    sent.append(platform.exec_argv("x", ["opencode"], workdir="/workspace"))
    assert len(sent) >= 10
    assert all(command[:3] == ["/usr/bin/docker", "--context", "elsewhere"] for command in sent), sent
