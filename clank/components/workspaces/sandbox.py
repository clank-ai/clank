"""A workspace's container and the edge, as Clank wants them (design 0004 §3 and §6, design 0002 §2.9).

`ContainerSpec` says a container whole: its name, image, Clank's labels, the networks it joins (the first when it
starts, the others right after, each with the name the others call it), what it mounts, its user and working folder,
its limits, and its command. `run_arguments` turns it into the exact arguments of `docker run`, so what a container may
reach is checked by reading them, without Docker.

A workspace's container mounts its folder at `/workspace` and nothing else of the machine: its home is a volume of its
own (so OpenCode's sessions survive the container), it runs as the image's user `agent` (uid 1000) with no capability,
`no-new-privileges`, and `--init` (so no process is left a zombie), within its CPU, memory and process limits (and
every program in it told how many CPUs it has, which Docker's limit does not change: `thread_env`), and it
joins only an internal network of its own, where nothing answers but the edge: not the machine, not the internet, not
another workspace. The edge is on the network that reaches the host and joins each workspace's network (as `edge`)
when that workspace opens, and again whenever it is made or started (`edge.py`); it has a read-only root and small
limits, and runs one program: it forwards the gateway's port and the proxy's to the host, and nothing else.

A workspace's setup (design 0004 §10) runs in a container of its own, made for it and removed when it ends: mounted,
contained and limited as the workspace's container, but on Docker's default network, which reaches the internet, so
the folder's own software can be downloaded into the home without the workspace's container ever reaching out.

All of them run Clank's sandbox image, built from the Dockerfile in the `image` folder beside this module; its tag is
the checksum of that Dockerfile (`image_tag`), so a change to it builds a new image, and an image of that tag is the one
it made. Clank's own programs for the container (the edge's, the bridge, the MCP server, its `sitecustomize`) and its
instructions live in the same folder and are mounted read-only at `/opt/clank` in every container Clank runs
(`ContainerSpec.programs`, decision 0142), never copied into the image: a change to them rebuilds nothing, and each
container runs the version the service runs. A workspace whose record names image layers (design 0020 §3: `tex`) runs
an image built on it, a layer at a time in their order, each from its folder under `layers` with the image below as
the build argument `BASE` (`layer_chain`); its tag names the layers and is the checksum of the base's tag and the
layers' files (`layered_tag`).
"""

import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

USER = "1000:1000"
WORKSPACE = "/workspace"
AGENT_HOME = "/home/agent"
PROCESSES = 1024
EDGE_ALIAS = "edge"
PORTS_LABEL = "clank.ports"  # the ports the edge forwards, so a change makes it again (design 0024 §2)
PROXY_LABEL = "clank.proxy"  # the proxy's port a workspace's container was told, so one told none is made again
NO_PROXY = "edge,localhost,127.0.0.1"  # what a workspace's container reaches without the proxy
HOST = "host.docker.internal"
PROGRAMS = "/opt/clank"  # Clank's programs and instructions, mounted read-only from `image_folder()` (0142)
EDGE_PROGRAM = f"{PROGRAMS}/edge.py"
BRIDGE_PROGRAM = f"{PROGRAMS}/bridge.py"  # the session bridge to OpenCode's servers (design 0005 §2)
PHONE_PROGRAM = f"{PROGRAMS}/phone_mcp.py"  # Clank's own MCP server for the agent: send_to_phone (design 0005 §3)
AGENT_CLANK = f"{AGENT_HOME}/.clank"  # Clank's files for the agent, written at each start (design 0018 §7.5)
CURRENT_PHONE = f"{AGENT_CLANK}/mcp/phone_mcp.py"  # Clank's MCP server as this Clank has it
CURRENT_INSTRUCTIONS = f"{AGENT_CLANK}/instructions/*.md"  # Clank's instructions to every agent (design 0020 §13)
IMAGE = "clank-sandbox"
DEFAULT_NETWORK = "bridge"  # Docker's own, which reaches the internet: a workspace's setup only
LAYERS = ("tex",)  # the image layers Clank knows (design 0020 §3), in the order they are built
THREADS = ("OMP_NUM_THREADS", "NUMBA_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def thread_env(cpus: float) -> tuple[tuple[str, str], ...]:
    """How many threads numerical libraries start: a container's CPUs, at least one (Docker's limit does not change how
    many CPUs a program sees; design 0004 §10)."""
    count = str(max(1, int(cpus)))
    return tuple((name, count) for name in THREADS)


@dataclass(frozen=True)
class Names:
    """The names of one CLANK_HOME's networks, volumes and containers, so two homes never share one."""

    home: str

    def inner(self, workspace: str) -> str:
        """A workspace's internal network: no route out; its container and the edge."""
        return f"clank-{self.home}-{workspace}-net"

    @property
    def outer(self) -> str:
        """The network that reaches the host: the edge alone."""
        return f"clank-{self.home}-outer"

    @property
    def edge(self) -> str:
        """The edge's container."""
        return f"clank-{self.home}-edge"

    def container(self, workspace: str) -> str:
        """A workspace's container."""
        return f"clank-{self.home}-{workspace}"

    def volume(self, workspace: str) -> str:
        """A workspace's home: its agent's settings and sessions."""
        return f"clank-{self.home}-{workspace}-home"

    def setup(self, workspace: str) -> str:
        """The container that installs a workspace's software, while it does (design 0004 §10)."""
        return f"clank-{self.home}-{workspace}-setup"


def names(home: str) -> Names:
    """The names of a CLANK_HOME's networks, volumes and containers, by its id."""
    return Names(home)


@dataclass(frozen=True)
class ContainerSpec:
    """A container as Clank wants it."""

    name: str
    image: str
    labels: tuple[tuple[str, str], ...]
    networks: tuple[tuple[str, str], ...]
    command: tuple[str, ...]
    binds: tuple[tuple[str, str], ...] = ()
    volumes: tuple[tuple[str, str], ...] = ()
    user: str = USER
    workdir: str = ""
    cpus: float = 1.0
    memory_mib: int = 1024
    processes: int = PROCESSES
    read_only: bool = False
    hosts: tuple[str, ...] = ()
    once: bool = False  # run in the foreground and removed when it ends, rather than detached
    env: tuple[tuple[str, str], ...] = ()  # what every program in it runs with
    programs: str = ""  # the folder of Clank's programs, mounted read-only at `PROGRAMS` (decision 0142)


def workspace_spec(
    home: str, name: str, folder: str, image: str, *, cpus: float, memory_mib: int, proxy: str = ""
) -> ContainerSpec:
    """A workspace's container: its folder at `/workspace`, its home a volume of its own, the internal network only;
    told the proxy (design 0024 §2: its URL, with the workspace's token) when one is given, the edge and the loopback
    bypassing it."""
    found = names(home)
    env = thread_env(cpus)
    labels = _labels(home, name)
    if proxy:
        env += (("HTTP_PROXY", proxy), ("HTTPS_PROXY", proxy), ("ALL_PROXY", proxy), ("NO_PROXY", NO_PROXY))
        labels += ((PROXY_LABEL, proxy.rsplit(":", 1)[-1].rstrip("/")),)  # the port, never the token
    return ContainerSpec(
        name=found.container(name),
        image=image,
        labels=labels,
        networks=((found.inner(name), ""),),
        command=("sleep", "infinity"),
        binds=((folder, WORKSPACE),),
        volumes=((found.volume(name), AGENT_HOME),),
        workdir=WORKSPACE,
        cpus=cpus,
        memory_mib=memory_mib,
        env=env,
        programs=str(image_folder()),
    )


def setup_spec(
    home: str, name: str, folder: str, image: str, *, cpus: float, memory_mib: int, command: str
) -> ContainerSpec:
    """The container that installs a workspace's software (design 0004 §10): mounted, contained and limited as the
    workspace's own, on Docker's default network, which reaches the internet; it runs the command and is removed."""
    found = names(home)
    return ContainerSpec(
        name=found.setup(name),
        image=image,
        labels=_labels(home, name),
        networks=((DEFAULT_NETWORK, ""),),
        command=("bash", "-lc", command),
        binds=((folder, WORKSPACE),),
        volumes=((found.volume(name), AGENT_HOME),),
        workdir=WORKSPACE,
        cpus=cpus,
        memory_mib=memory_mib,
        once=True,
        env=thread_env(cpus),
        programs=str(image_folder()),
    )


def edge_ports(gateway_port: int, proxy_port: int) -> str:
    """The ports the edge forwards, as its label `clank.ports` says them: "18210,18211"."""
    return f"{gateway_port},{proxy_port}"


def edge_spec(home: str, image: str, *, gateway_port: int, proxy_port: int) -> ContainerSpec:
    """The edge: on the network that reaches the host (each workspace's own it joins as `edge`: `edge.py`); it
    forwards the gateway's port and the proxy's (design 0024 §2) to the host's and nothing else. Its label
    `clank.ports` names the ports, so an edge forwarding others is made again (`edge.py`)."""
    found = names(home)
    ports = (gateway_port, proxy_port)
    return ContainerSpec(
        name=found.edge,
        image=image,
        labels=(*_labels(home, "edge"), (PORTS_LABEL, edge_ports(gateway_port, proxy_port))),
        networks=((found.outer, ""),),
        command=("python3", EDGE_PROGRAM, *(part for port in ports for part in (str(port), HOST, str(port)))),
        cpus=0.5,
        memory_mib=128,
        processes=64,
        read_only=True,
        hosts=(f"{HOST}:host-gateway",),
        programs=str(image_folder()),
    )


def run_arguments(spec: ContainerSpec) -> list[str]:
    """The exact arguments of `docker run` for a spec; it joins its first network, and the others after it starts."""
    arguments = ["run", "--rm" if spec.once else "--detach", "--name", spec.name]
    for key, value in spec.labels:
        arguments += ["--label", f"{key}={value}"]
    network, alias = spec.networks[0]
    arguments += ["--network", network]
    if alias:
        arguments += ["--network-alias", alias]
    for source, target in spec.binds:
        arguments += ["--mount", _mount("bind", source, target)]
    if spec.programs:
        arguments += ["--mount", _mount("bind", spec.programs, PROGRAMS, readonly=True)]
    for source, target in spec.volumes:
        arguments += ["--mount", _mount("volume", source, target)]
    for host in spec.hosts:
        arguments += ["--add-host", host]
    arguments += ["--user", spec.user, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--init"]
    arguments += ["--cpus", f"{spec.cpus:g}", "--memory", f"{spec.memory_mib}m", "--pids-limit", str(spec.processes)]
    for key, value in spec.env:
        arguments += ["--env", f"{key}={value}"]
    if spec.read_only:
        arguments.append("--read-only")
    if spec.workdir:
        arguments += ["--workdir", spec.workdir]
    return [*arguments, spec.image, *spec.command]


def _labels(home: str, record: str) -> tuple[tuple[str, str], ...]:
    return (("clank.home", home), ("clank.component", "workspaces"), ("clank.record", record))


def _mount(kind: str, source: str, target: str, *, readonly: bool = False) -> str:
    """A `--mount` value: Docker reads it as one line of CSV, so a field with a comma or a quote is quoted."""
    out = io.StringIO()
    fields = [f"type={kind}", f"source={source}", f"target={target}", *(["readonly"] if readonly else [])]
    csv.writer(out, lineterminator="").writerow(fields)
    return out.getvalue()


def joined(spec: ContainerSpec) -> Sequence[tuple[str, str]]:
    """The networks a container joins after it starts, each with its alias."""
    return spec.networks[1:]


def image_folder() -> Path:
    """The folder Clank's sandbox image is built from (its Dockerfile), which also holds the programs and instructions
    mounted at `PROGRAMS` in every container (decision 0142)."""
    return Path(str(resources.files("clank.components.workspaces").joinpath("image")))


def agent_files() -> list[tuple[str, str]]:
    """Clank's files for the agent, as this Clank has them, each with its path in the container (design 0018 §7.5):
    its MCP server and the module it imports, and its instructions."""
    folder = image_folder()
    found = [(f"{AGENT_CLANK}/mcp/{name}", (folder / name).read_text(encoding="utf-8"))
             for name in ("phone_mcp.py", "find_figures.py")]  # fmt: skip
    found += [(f"{AGENT_CLANK}/instructions/{rules.name}", rules.read_text(encoding="utf-8"))
              for rules in sorted((folder / "instructions").glob("*.md"))]  # fmt: skip
    return found


def image_tag() -> str:
    """The sandbox image's tag: the checksum of its Dockerfile alone, since the folder's programs are mounted, not
    copied (decision 0142)."""
    digest = hashlib.sha256((image_folder() / "Dockerfile").read_bytes())
    return f"{IMAGE}:{digest.hexdigest()[:12]}"


def layer_folder(name: str) -> Path:
    """The folder an image layer is built from: its Dockerfile, and what it copies."""
    return Path(str(resources.files("clank.components.workspaces").joinpath("layers", name)))


@dataclass(frozen=True)
class LayerStep:
    """One layer built on the image below it: the layer, the tag it builds on, and the tag it gets."""

    layer: str
    base: str
    tag: str


def layer_chain(layers: Sequence[str]) -> list[LayerStep]:
    """The layers a workspace names, in Clank's order, each built on the image below it, the sandbox image first;
    empty for none. An unknown layer is a `ValueError` naming the layers there are."""
    unknown = sorted(set(layers) - set(LAYERS))
    if unknown:
        raise ValueError(f"there is no image layer {unknown[0]!r}: the layers are {', '.join(LAYERS)}")
    wanted = [name for name in LAYERS if name in set(layers)]
    steps: list[LayerStep] = []
    below = image_tag()
    for count in range(1, len(wanted) + 1):
        tag = _layered(wanted[:count])
        steps.append(LayerStep(wanted[count - 1], below, tag))
        below = tag
    return steps


def layered_tag(layers: Sequence[str]) -> str:
    """The tag of the image a workspace with these layers runs: the sandbox image's, with none."""
    chain = layer_chain(layers)
    return chain[-1].tag if chain else image_tag()


def _layered(layers: Sequence[str]) -> str:
    """The tag of the sandbox image with these layers on it: their names, and the checksum of the base's tag and their
    folders' files."""
    digest = hashlib.sha256(image_tag().encode("utf-8"))
    for name in layers:
        digest.update(name.encode("utf-8") + b"\0")
        _add_files(digest, layer_folder(name))
    return f"{IMAGE}-{'-'.join(layers)}:{digest.hexdigest()[:12]}"


def _add_files(digest: "hashlib._Hash", folder: Path) -> None:
    """Each file of the folder, by its path and its bytes (Python's caches left out)."""
    for path in sorted(folder.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
