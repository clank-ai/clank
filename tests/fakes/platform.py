"""A container platform that does as it is told, for the tests of what uses one (the workspaces component, the
commands, the console): its state, its containers, and how many checks a start takes; from M4, its images, networks,
volumes and the containers it runs from specs, all in memory (a build says the lines it is given and ends as told).

Its networks behave as Docker's where Clank depends on it (design 0004 §3, revised 2026-10-26): each container says
the networks it is on, a removed container leaves every network with it (so an edge made again is on its first network
only), and a network made again is another network, which a container that was on the old one cannot start without
(`NetworkGone`), as Docker keeps a network's id, not its name."""

from collections.abc import Callable, Mapping, Sequence

from clank.components.workspaces.adapters.platform import (
    Container,
    ContainerPlatform,
    NetworkGone,
    PlatformError,
    PlatformStatus,
)
from clank.components.workspaces.sandbox import ContainerSpec
from clank.kernel.adapters import Capability
from clank.kernel.processes import Answer


def container(
    name: str, *, state: str = "running", labels: dict[str, str] | None = None, networks: Sequence[str] = ()
) -> Container:
    """A container with a name, a state, labels and the networks it is on."""
    found = labels or {}
    return Container(
        id=name.encode().hex()[:12].ljust(64, "0"),
        name=name,
        image=f"{name}:latest",
        state=state,
        status="Up 5 minutes" if state == "running" else "Exited (0) 1 hour ago",
        clank={key: value for key, value in found.items() if key.startswith("clank.")},
        label_keys=sorted(found),
        networks=list(networks),
    )


def with_edge(platform: "FakePlatform", home: str, workspace: str, ports: str = "18210,18211") -> None:
    """The edge as an opening leaves it (design 0004 §3): running, made from Clank's sandbox image, forwarding the
    gateway's and the proxy's ports, on the network that reaches the host and on `workspace`'s; joined to that network
    when the edge is there already."""
    from clank.components.workspaces.sandbox import image_tag, names

    found = names(home)
    for index, each in enumerate(platform.containers):
        if each.name == found.edge:
            if found.inner(workspace) not in each.networks:
                joined = [*each.networks, found.inner(workspace)]
                platform.containers[index] = each.model_copy(update={"networks": joined})
            return
    labels = {"clank.home": home, "clank.component": "workspaces", "clank.record": "edge", "clank.ports": ports}
    made = container(found.edge, labels=labels, networks=[found.outer, found.inner(workspace)])
    platform.containers.append(made.model_copy(update={"image": image_tag()}))


class FakePlatform(ContainerPlatform):
    """A container platform that does as it is told: its state, its containers, and how many checks a start takes
    (None: it never comes up)."""

    NAME = "fake"
    LABEL = "Fake Docker"
    PLATFORMS = ("win32", "linux", "darwin")

    def __init__(
        self,
        state: str = "running",
        containers: Sequence[Container] = (),
        starts_after: int | None = 1,
    ) -> None:
        super().__init__(lambda arguments, timeout=0.0: None, None if state == "not installed" else "fake")
        self.state = state
        self.containers = list(containers)
        self.starts_after = starts_after
        self.calls: list[str] = []
        self.on_check: Callable[[], None] | None = None
        self._checks = 0
        self.cpus_memory: tuple[int, int] | None = (16, 32768)
        self.images: set[str] = set()
        self.build_args: dict[str, dict[str, str]] = {}  # each image built: its build arguments
        self.build_folders: dict[str, str] = {}  # and the folder it was built from
        self.networks: dict[str, bool] = {}
        self.made: dict[str, int] = {}  # each network: how many times it was made, which stands for its id
        self.attached: dict[str, dict[str, int]] = {}  # each container: the networks it joined, as made then
        self.joined: set[tuple[str, str]] = set()
        self.files: dict[tuple[str, str], str] = {}
        self.volumes: set[str] = set()
        self.specs: dict[str, ContainerSpec] = {}
        self.build_lines = ["#1 [internal] load build definition from Dockerfile", "#12 naming to clank-sandbox done"]
        self.build_status: int | None = 0
        self.setup_lines = ["Collecting numpy", "Successfully installed paper-1.0"]
        self.setup_status: int | None = 0
        self.inside: Callable[[list[str], bytes | None], Answer] | None = None

    @classmethod
    def find(cls) -> str | None:
        return "fake"

    def capabilities(self) -> list[Capability]:
        return [Capability(name, self.command is not None, "as told") for name in ("status", "start", "stop")]

    def status(self) -> PlatformStatus:
        if self.on_check is not None:
            self.on_check()
        if self.state == "starting":
            self._checks += 1
            if self.starts_after is not None and self._checks >= self.starts_after:
                self.state = "running"
        running = self.state == "running"
        return PlatformStatus(
            adapter=self.NAME,
            label=self.LABEL,
            state=self.state,
            version="4.85.0" if running else "",
            engine="29.6.2" if running else "",
            containers=self.containers if running else [],
            detail="install it" if self.state == "not installed" else "",
        )

    def request_start(self) -> None:
        if self.command is None:
            raise PlatformError("Fake Docker is not installed")
        self.calls.append("start")
        self.state = "starting"
        self._checks = 0

    def request_stop(self) -> None:
        if self.command is None:
            raise PlatformError("Fake Docker is not installed")
        self.calls.append("stop")
        self.state = "stopped"

    def after_start(self, log: Callable[[str], None]) -> None:
        self.calls.append("after start")
        log("nothing to put back")

    def limits(self) -> tuple[int, int] | None:
        return self.cpus_memory

    def image_exists(self, tag: str) -> bool:
        return tag in self.images

    def build_image(
        self,
        tag: str,
        folder: str,
        labels: Mapping[str, str],
        line: Callable[[str], None],
        canceled: Callable[[], bool],
        args: Mapping[str, str] | None = None,
    ) -> int | None:
        self.calls.append(f"build {tag}")
        self.build_args[tag] = dict(args or {})
        self.build_folders[tag] = folder
        for text in self.build_lines:
            if canceled():
                return None
            line(text)
        if self.build_status == 0:
            self.images.add(tag)
        return self.build_status

    def ensure_network(self, name: str, *, internal: bool, labels: Mapping[str, str]) -> None:
        if name not in self.networks:
            self.calls.append(f"network {name}")
            self.networks[name] = internal
            self.made[name] = self.made.get(name, 0) + 1

    def join_network(self, network: str, container: str, alias: str) -> bool:
        found = self._find(container)
        if found is None:
            raise PlatformError(f"{container} could not join {network}: No such container: {container}")
        if network in found.networks:
            return False
        self.calls.append(f"join {container} {network}")
        self.joined.add((network, container))
        self._networks(container, [*found.networks, network])
        self.attached.setdefault(container, {})[network] = self.made.get(network, 0)
        return True

    def leave_network(self, network: str, container: str) -> None:
        self.joined.discard((network, container))
        found = self._find(container)
        if found is not None:
            self._networks(container, [each for each in found.networks if each != network])
            self.attached.get(container, {}).pop(network, None)

    def remove_network(self, name: str) -> None:
        self.calls.append(f"remove network {name}")
        self.networks.pop(name, None)

    def container(self, name: str) -> Container | None:
        return self._find(name)

    def run_container(self, spec: ContainerSpec) -> None:
        if self._find(spec.name) is not None:
            raise PlatformError(f"{spec.name} could not start: Conflict. The name is in use.")
        self.calls.append(f"run {spec.name}")
        self.specs[spec.name] = spec
        self.volumes.update(volume for volume, _ in spec.volumes)
        on = [network for network, _ in spec.networks]
        made = container(spec.name, labels=dict(spec.labels), networks=on)
        self.containers.append(made.model_copy(update={"image": spec.image}))
        self.attached[spec.name] = {network: self.made.get(network, 0) for network in on}

    def run_once(self, spec: ContainerSpec, line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
        self.calls.append(f"setup {spec.name}")
        self.specs[spec.name] = spec
        for text in self.setup_lines:
            if canceled():
                return None
            line(text)
        return self.setup_status

    def start_container(self, name: str) -> None:
        """Started, unless a network it joined (one this platform made) is gone or was made again since."""
        self.calls.append(f"start {name}")
        for network, made in self.attached.get(name, {}).items():
            if made and (network not in self.networks or self.made.get(network) != made):
                raise NetworkGone(f"{name} could not start: Error response from daemon: network {network} not found")
        self._set(name, "running")

    def stop_container(self, name: str, seconds: int) -> None:
        self.calls.append(f"stop {name}")
        if self._find(name) is not None:
            self._set(name, "exited")

    def remove_container(self, name: str) -> None:
        """Removed, and off every network with it, as Docker does."""
        self.calls.append(f"remove {name}")
        self.containers = [found for found in self.containers if found.name != name]
        self.joined = {(network, joined) for network, joined in self.joined if joined != name}
        self.attached.pop(name, None)

    def remove_volume(self, name: str) -> None:
        self.calls.append(f"remove volume {name}")
        self.volumes.discard(name)

    def put_file(self, name: str, path: str, text: str) -> None:
        found = self._find(name)
        if found is None or found.state != "running":
            raise PlatformError(f"{path} could not be written in {name}: it does not run")
        self.files[(name, path)] = text

    def run_in(
        self, name: str, argv: Sequence[str], *, workdir: str, input: bytes | None = None, timeout: float = 30.0
    ) -> Answer:
        """What `inside` answers (a test runs the bridge on this machine with it), else that it cannot."""
        found = self._find(name)
        if found is None or found.state != "running":
            return Answer(1, "", f"Error response from daemon: container {name} is not running")
        if self.inside is None:
            return Answer(1, "", "the fake platform runs nothing in a container")
        self.calls.append(f"in {name}: {' '.join(argv[:3])}")
        return self.inside(list(argv), input)

    def exec_argv(
        self,
        name: str,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None = None,
        terminal: bool = True,
    ) -> list[str]:
        given = [part for key, value in (env or {}).items() for part in ("--env", f"{key}={value}")]
        tty = ["--tty"] if terminal else []
        return ["docker", "exec", "--interactive", *tty, *given, "--workdir", workdir, name, *argv]

    def _find(self, name: str) -> Container | None:
        """The container of this name (what `container` answers, without counting as a call of it)."""
        return next((found for found in self.containers if found.name == name), None)

    def _networks(self, name: str, networks: list[str]) -> None:
        found = self._find(name)
        if found is not None:
            self.containers[self.containers.index(found)] = found.model_copy(update={"networks": networks})

    def _set(self, name: str, state: str) -> None:
        found = self._find(name)
        if found is None:
            raise PlatformError(f"{name} could not start: No such container")
        status = "Up 1 second" if state == "running" else "Exited (0) 1 second ago"
        self.containers[self.containers.index(found)] = found.model_copy(update={"state": state, "status": status})
