"""Record Docker Engine as Clank's `docker-engine` adapter asks it (design 0014 §2, plan s9 L0), for
`tests/fixtures/docker-engine/<version>/program.json`, which the container platform's contract runs over.

    python3 tools/capture_docker_engine.py --state running --examples --out running.json
    python3 tools/capture_docker_engine.py --state stopped --out stopped.json
    python3 tools/capture_docker_engine.py --state "no access" --out no-access.json
    python3 tools/capture_docker_engine.py --merge running.json stopped.json no-access.json --where WHERE --out FILE

It runs the commands the adapter sends, as `commands` lists them: systemd's view of Docker's service, then the system
engine, named by its socket: its version, its containers and the names of their labels, its CPUs and memory, whether it
can limit a container's memory (with its warnings), and its containers' use. It keeps each one's exit status, output,
seconds and errors. If the adapter ever asks something else, the contract test fails, since a recording answers only
what was recorded, and the engine is recorded again.

It uses the standard library only, so a user outside the docker group can run it with the system's `python3`. It changes
nothing itself, and never runs `sudo`: whoever records stops the engine (both of its units, `docker.socket` and
`docker.service`, so the tool's commands wake nothing), or works as a user outside the docker group, before each state.
`--examples` makes four containers of a tiny public image before the running state is captured, one of each sort the
contract checks (`tests/fixtures/README.md`), and removes them after. Of `docker info` it asks only the fields Clank
reads, never the whole, which holds the host's name. Nothing personal is kept: the containers' ids are replaced by
made-up ones of the same form, and the computer's name, the user's name and the user's home folder, wherever they
appear, by made-up ones. A capture whose engine was not in the state it names is refused, saying so (`problems`). The
merge writes the recording and prints it between two marker lines, which the hand-run job
`.github/workflows/record-docker-engine.yml` leaves in its log for an agent to read and commit.
"""

import argparse
import getpass
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import cycle, islice
from pathlib import Path, PurePosixPath
from typing import Any

# What the adapter sends (clank/components/workspaces/adapters/docker_engine.py); a test holds the two lists alike.
SOCKET = "unix:///var/run/docker.sock"
TARGET = ("-H", SOCKET)
SYSTEMD = ("systemctl", "show", "docker.service", "--property=LoadState", "--property=ActiveState")
VERSION = "{{.Server.Version}}"
TEMPLATE = (
    '{"id":{{json .ID}},"name":{{json .Names}},"image":{{json .Image}},"state":{{json .State}},'
    '"status":{{json .Status}},"clank.home":{{json (.Label "clank.home")}},'
    '"clank.component":{{json (.Label "clank.component")}},"clank.record":{{json (.Label "clank.record")}},'
    '"clank.ports":{{json (.Label "clank.ports")}},"clank.proxy":{{json (.Label "clank.proxy")}},'
    '"networks":{{json .Networks}}}'
)
INSPECT = '{"id":{{json .Id}},"labels":{{json .Config.Labels}}}'
LIMITS = "{{.NCPU}} {{.MemTotal}}"
MEMORY = '{"limit":{{json .MemoryLimit}},"warnings":{{json .Warnings}}}'
STATS = "{{json .}}"

STATES = ("running", "stopped", "no access")
TIMEOUT_SECONDS = 120.0
IMAGE = "busybox:1.37.0"  # tiny and public: the example containers run it
HOME_ID = "0123456789ab"  # the made-up CLANK_HOME id of the example of Clank's own container
EXAMPLES: tuple[tuple[str, dict[str, str], str, tuple[str, ...], tuple[str, ...]], ...] = (
    # each example: its name, its labels, its first network, the networks it joins after, and its command (`true`
    # ends at once, so that one is not running)
    (
        f"clank-{HOME_ID}-demo",
        {"clank.home": HOME_ID, "clank.component": "workspaces", "clank.record": "demo"},
        f"clank-{HOME_ID}-demo-net",
        (),
        ("sleep", "3600"),
    ),
    (
        "toolbox-sandbox-017",
        {"toolbox.mode": "auto", "toolbox.project": "017", "toolbox.sandbox": "1"},
        "toolbox-017-net",
        ("toolbox-outer",),
        ("sleep", "3600"),
    ),
    (
        "web-dev",
        {"com.docker.compose.project": "dev", "com.docker.compose.service": "web"},
        "dev_default",
        (),
        ("sleep", "3600"),
    ),
    ("toolbox-docs-build", {"toolbox.project": "lean", "toolbox.role": "run"}, "bridge", (), ("true",)),
)
NETWORKS = (f"clank-{HOME_ID}-demo-net", "toolbox-017-net", "toolbox-outer", "dev_default")
BEGINS = "===== program.json begins ====="
ENDS = "===== program.json ends ====="
MADE_UP_HOST = "made-up-host"
MADE_UP_USER = "user"
MADE_UP_HOME = "/home/user"
GENERIC = frozenset({"admin", "docker", "localhost", "root", "runner", "ubuntu", "user"})  # names that say no one's
ID = re.compile(r"[0-9a-f]{64}")

Reply = tuple[int | None, str, str]  # a command's exit status (None: it did not run, or did not answer), output, errors
Runner = Callable[[Sequence[str]], Reply]


@dataclass(frozen=True)
class Personal:
    """What would say whose computer a recording came from: its name, and its user's name and home folder."""

    host: str
    user: str
    home: str

    @classmethod
    def here(cls) -> "Personal":
        """This computer's."""
        try:
            user = getpass.getuser()
        except (OSError, KeyError):
            user = ""
        return cls(socket.gethostname(), user, str(Path.home()))


def run_command(argv: Sequence[str]) -> Reply:
    """A command's exit status (None when it could not run, or gave no answer in time), its output and its errors."""
    try:
        done = subprocess.run(
            list(argv), capture_output=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS, check=False
        )
    except OSError as error:
        return None, "", f"could not run {argv[0]}: {error}"
    except subprocess.TimeoutExpired:
        return None, "", f"no answer within {TIMEOUT_SECONDS:g} seconds"
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def engine(docker: str, *arguments: str) -> list[str]:
    """A command to the system engine, named by its socket, as the adapter sends it."""
    return [docker, *TARGET, *arguments]


def commands(ids: Sequence[str], docker: str = "docker") -> list[list[str]]:
    """The commands the adapter sends, in its order: systemd's view of Docker's service; the engine's version; its
    containers, and the names of their labels when there are any (`ids`, as `docker ps` listed them); its CPUs and
    memory; whether it can limit a container's memory, with its warnings; its containers' use."""
    asked = [
        list(SYSTEMD),
        engine(docker, "version", "--format", VERSION),
        engine(docker, "ps", "--all", "--no-trunc", "--format", TEMPLATE),
    ]
    if ids:
        asked.append(engine(docker, "container", "inspect", "--format", INSPECT, *ids))
    return [
        *asked,
        engine(docker, "info", "--format", LIMITS),
        engine(docker, "info", "--format", MEMORY),
        engine(docker, "stats", "--no-stream", "--format", STATS),
    ]


def example_commands(docker: str = "docker") -> list[list[str]]:
    """What `--examples` runs before the running state is captured: the examples' networks, then each example, joined
    to its other networks once it runs."""
    made = [engine(docker, "network", "create", network) for network in NETWORKS]
    for name, labels, network, others, command in EXAMPLES:
        marks = [part for key, value in labels.items() for part in ("--label", f"{key}={value}")]
        detach = ["--detach"] if command != ("true",) else []
        made.append(engine(docker, "run", *detach, "--name", name, *marks, "--network", network, IMAGE, *command))
        made += [engine(docker, "network", "connect", other, name) for other in others]
    return made


def example_cleanup(docker: str = "docker") -> list[list[str]]:
    """What `--examples` runs after the capture: the examples and their networks removed."""
    names = [name for name, *_ in EXAMPLES]
    return [engine(docker, "rm", "--force", *names), engine(docker, "network", "rm", *NETWORKS)]


def made_up_id(index: int) -> str:
    """The made-up id of the index-th container listed: a1a1..., b2b2..., as in Docker Desktop's recording."""
    pairs = [letter + digit for letter, digit in islice(zip(cycle("abcdef"), cycle("123456789"), strict=False), 18)]
    return pairs[index] * 32 if index < len(pairs) else f"{index:064x}"


class Scrubber:
    """What a capture replaces, alike everywhere it appears: each container's id (and its short form) by a made-up one
    of the same form, the computer's name, the user's home folder and the user's name (a name that says no one's is
    kept); `replaced` says which of them appeared."""

    def __init__(self, personal: Personal) -> None:
        self.personal = personal
        self.ids: dict[str, str] = {}
        self.replaced: set[str] = set()

    def learn(self, listed: str) -> None:
        """The ids `docker ps` listed, each given its made-up one, in the order listed."""
        for line in listed.splitlines():
            try:
                found = json.loads(line)
            except ValueError:
                continue
            id = str(found.get("id", "")) if isinstance(found, dict) else ""
            if ID.fullmatch(id) and id not in self.ids:
                self.ids[id] = made_up_id(len(self.ids))

    def __call__(self, text: str) -> str:
        """The text with every personal value replaced."""
        for real, made in self.ids.items():
            if real[:12] in text:
                self.replaced.add("the containers' ids")
                text = text.replace(real, made).replace(real[:12], made[:12])
        home = self.personal.home.rstrip("/")
        if len(home) > 1 and home != MADE_UP_HOME and home in text:
            self.replaced.add("the user's home folder")
            text = text.replace(home, MADE_UP_HOME)
        for what, real, made in (
            ("the computer's name", self.personal.host, MADE_UP_HOST),
            ("the user's name", self.personal.user, MADE_UP_USER),
        ):
            if len(real) >= 3 and real.lower() not in GENERIC:
                word = re.compile(rf"(?<![\w-]){re.escape(real)}(?![\w-])")
                if word.search(text):
                    self.replaced.add(what)
                    text = word.sub(made, text)
        return text


def capture(
    state: str,
    run: Runner = run_command,
    *,
    docker: str | None = None,
    clock: Callable[[], float] = time.monotonic,
    personal: Personal | None = None,
    examples: bool = False,
) -> dict[str, Any]:
    """One state's capture: each command the adapter sends, keyed as the recording keys it (the program by its name),
    with its [exit status, output, seconds, errors], everything personal replaced; the engine's version when it
    answered; where its command is; and what was replaced. With `examples`, the example containers are made first and
    removed after, whatever happened; their commands are not recorded."""
    if state not in STATES:
        raise ValueError(f"{state!r} is not a state the recording holds: {', '.join(STATES)}")
    command = docker or shutil.which("docker") or "docker"
    scrub = Scrubber(personal or Personal.here())
    answers: dict[str, list[Any]] = {}

    def ask(argv: list[str], *, listing: bool = False) -> Reply:
        began = clock()
        status, output, errors = run(argv)
        seconds = round(clock() - began, 2)
        if listing and status == 0:
            scrub.learn(output)
        answers[scrub(" ".join([PurePosixPath(argv[0]).name, *argv[1:]]))] = [
            status,
            scrub(output),
            seconds,
            scrub(errors),
        ]
        return status, output, errors

    version = ""
    try:
        if examples:
            for argv in example_commands(command):
                status, output, errors = run(argv)
                if status != 0:
                    said = " ".join((errors or output).split()) or f"exit {status}"
                    raise RuntimeError(f"the example `{' '.join(argv[3:])}` could not be made: {said}")
        asked = commands([], command)
        ask(asked[0])
        status, output, _ = ask(asked[1])
        version = output.strip() if status == 0 else ""
        ask(asked[2], listing=True)
        for argv in commands(list(scrub.ids), command)[3:]:
            ask(argv)
    finally:
        if examples:
            for argv in example_cleanup(command):
                run(argv)
    return {
        "state": state,
        "version": version,
        "command": scrub(command),
        "answers": answers,
        "replaced": sorted(scrub.replaced),
    }


def problems(captured: dict[str, Any]) -> list[str]:
    """Why a capture is not of the state it names: running, its engine answered; stopped, systemd says Docker's service
    is not active and the engine does not answer; no access, Docker refused with "permission denied"."""
    state = captured.get("state")
    answers: dict[str, list[Any]] = captured.get("answers") or {}
    systemd = answers.get(" ".join(SYSTEMD)) or [None, "", 0.0, ""]
    version = answers.get(" ".join(["docker", *TARGET, "version", "--format", VERSION])) or [None, "", 0.0, ""]
    active = re.search(r"^ActiveState=(\S+)", str(systemd[1]), re.MULTILINE)
    said = " ".join(str(version[3] or version[1]).split()) or f"exit {version[0]}"
    if state not in STATES:
        return [f"{state!r} is not a state the recording holds: {', '.join(STATES)}"]
    if state == "running" and version[0] != 0:
        return [f"running: its engine did not answer `docker version` ({said})"]
    if state == "stopped" and active is not None and active.group(1) == "active":
        return ["stopped: systemd says Docker's service is active; stop both units first"]
    if state == "stopped" and version[0] == 0:
        return ["stopped: its engine answered `docker version`"]
    if state == "no access" and (version[0] == 0 or "permission denied" not in str(version[3]).lower()):
        return [f"no access: Docker did not refuse with permission denied ({said}); record as a user outside the group"]
    return []


def merge(captures: Sequence[dict[str, Any]], *, where: str, recorded: str) -> dict[str, Any]:
    """The recording of the three captures (`program.json`), whose `how` says where it was made, which version, and
    what was replaced; `ValueError` when a capture is not of its state, or a state is missing or given twice."""
    found = [problem for each in captures for problem in problems(each)]
    if found:
        raise ValueError("; ".join(found))
    by_state = {each["state"]: each for each in captures}
    if len(captures) != len(STATES) or set(by_state) != set(STATES):
        given = ", ".join(str(each.get("state")) for each in captures) or "none"
        raise ValueError(f"the recording needs one capture of each state ({', '.join(STATES)}); given: {given}")
    version = str(by_state["running"]["version"])
    replaced = sorted({item for each in captures for item in each.get("replaced") or []})
    how = (
        f"Recorded by tools/capture_docker_engine.py on {where}, from Docker Engine {version} as Docker's own "
        f"packages install it. Running: with four example containers of {IMAGE}, made by the tool for the recording "
        "and removed after (one of Clank's, one of another tool's, one of another program's, and one that is not "
        "running). Stopped: after `sudo systemctl stop docker.socket docker.service`, so its commands woke nothing. "
        "No access: as a user outside the docker group. Each answer is its exit status, its output, its seconds and "
        "its errors. Replaced by made-up values of the same form: "
        f"{', '.join(replaced) if replaced else 'nothing, since nothing personal appeared'}. The commands are those "
        "the tool lists, which are the adapter's; when they differ, the contract test fails, and the engine is "
        "recorded again."
    )
    return {
        "program": "Docker Engine",
        "version": version,
        "recorded": recorded,
        "how": how,
        "platform": "linux",
        "command": by_state["running"]["command"],
        "initial": "running",
        "states": {state: by_state[state]["answers"] for state in STATES},
        "transitions": {},
    }


def _write(path: Path, value: dict[str, Any]) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return text


def main(argv: Sequence[str] | None = None) -> int:
    """Capture one state, or merge three captures into the recording; returns the exit status."""
    parser = argparse.ArgumentParser(prog="capture_docker_engine", description=(__doc__ or "").split("\n\n", 1)[0])
    chosen = parser.add_mutually_exclusive_group(required=True)
    chosen.add_argument("--state", choices=STATES, help="The state the engine is in now, to capture.")
    chosen.add_argument("--merge", nargs="+", metavar="CAPTURE", help="The three captures to merge.")
    parser.add_argument("--examples", action="store_true", help="Make the example containers first (running).")
    parser.add_argument("--where", default="this computer", help="Where it was recorded, for the recording's how.")
    parser.add_argument("--out", required=True, help="The file to write.")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    out = Path(args.out)
    if args.state:
        try:
            captured = capture(args.state, examples=args.examples)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        _write(out, captured)
        print(f"captured {args.state}: {len(captured['answers'])} commands, Docker Engine {captured['version'] or '-'}")
        found = problems(captured)
        for problem in found:
            print(problem, file=sys.stderr)
        return 1 if found else 0
    captures = [json.loads(Path(name).read_text(encoding="utf-8")) for name in args.merge]
    try:
        recording = merge(captures, where=args.where, recorded=date.today().isoformat())
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    text = _write(out, recording)
    print(BEGINS)
    print(text, end="")
    print(ENDS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
