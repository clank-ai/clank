"""The WSL host: processes in a WSL distribution, reached from Windows through `wsl.exe` (decision 0030).

Every question is one `bash -c` script run inside the distribution (`wsl.exe -d <distro> -e bash -c <script> clank
<arguments>`: `-e` passes the arguments as they are), and every script answers with one line and ends well, so what
the distribution says about a failure reaches the user in its own words (`error ...`). A script's first line names it
(`# clank: spawn`), which is also how a recording or a test tells them apart.

A start translates the log's Windows path with `wslpath`, enters the folder, and starts the engine with `setsid nohup
env ... <argv>`, its input from nowhere and its output appended to the log, so it outlives `wsl.exe` and the service.
For a moment its command line is still `setsid` or `nohup`; the script waits until `/proc/<pid>/cmdline` is the
engine's (by its SHA-256), then answers with the process id and its start time (field 22 of `/proc/<pid>/stat`, read
after the command's name, which may hold spaces). Every signal is sent by a script that checks the start time and the
command line first (`same`).

A step of an install is the one script that is followed line by line (`stream`): it runs the command in a process
group of its own, says the group first (`clank-group <id> <start time>`, kept from the lines the caller sees), and ends
with the command's exit status. Its PATH leaves out the Windows folders WSL adds (`/mnt/c/...`): a build searches its
PATH often, and each search through Windows' drives takes seconds. A canceled step ends `wsl.exe`, then the group in
the distribution (`end`), once its first process is seen to be the one the step started.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePath

from clank.components.runtime.hosts.host import EngineHost, HostError, ProcessIdentity, Stopped, command_hash
from clank.kernel.processes import run_command, stream_command

Runner = Callable[..., str | None]
Streamer = Callable[..., int | None]
# Whether the process $1 still has the start time $2 and the command line whose SHA-256 is $3 (a zombie has ended).
SAME = (
    'same() { s=$(cat /proc/"$1"/stat 2> /dev/null) || return 1; rest=${s##*") "}; read -ra f <<< "$rest"; '
    '[ "${f[0]}" != Z ] && [ "${f[19]}" = "$2" ] || return 1; '
    '[ "$(sha256sum < /proc/"$1"/cmdline 2> /dev/null | cut -c1-64)" = "$3" ]; }'
)
SCRIPTS = {
    "spawn": "\n".join(
        [
            "# clank: spawn",
            'cwd=$1; windows=$2; log=$(wslpath -u "$2"); shift 2; envs=()',
            'while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift',
            'command -v "$1" > /dev/null 2>&1 || { echo "error cannot start $1: no such program"; exit 0; }',
            'cd "$cwd" 2> /dev/null || { echo "error cannot enter $cwd"; exit 0; }',
            'mkdir -p "$(dirname "$log")" || { echo "error cannot write the log $windows"; exit 0; }',
            'setsid nohup env "${envs[@]}" "$@" >> "$log" 2>&1 < /dev/null &',
            'pid=$!; want=$(printf "%s\\0" "$@" | sha256sum | cut -c1-64)',
            "for i in $(seq 1 200); do",
            '  [ -d /proc/$pid ] || { echo "error $1 ended as soon as it started; its log: $windows"; exit 0; }',
            '  if [ "$(sha256sum < /proc/$pid/cmdline 2> /dev/null | cut -c1-64)" = "$want" ]; then',
            '    s=$(cat /proc/$pid/stat); rest=${s##*") "}; read -ra f <<< "$rest"; echo "ok $pid ${f[19]} $want"',
            "    exit 0",
            "  fi",
            "  sleep 0.05",
            "done",
            'echo "error $1 did not become itself within 10 seconds"',
        ]
    ),
    "alive": "\n".join(["# clank: alive", SAME, 'same "$1" "$2" "$3" && echo alive || echo gone']),
    "stop": "\n".join(
        [
            "# clank: stop",
            SAME,
            'same "$1" "$2" "$3" || { echo gone; exit 0; }',
            'kill -TERM "$1" 2> /dev/null',
            "end=$(( $(date +%s) + $4 ))",
            'while [ "$(date +%s)" -lt "$end" ]; do same "$1" "$2" "$3" || { echo stopped; exit 0; }; sleep 0.1; done',
            'same "$1" "$2" "$3" || { echo stopped; exit 0; }',
            'kill -KILL "$1" 2> /dev/null',
            'for i in $(seq 1 100); do same "$1" "$2" "$3" || { echo killed; exit 0; }; sleep 0.1; done',
            "echo killed",
        ]
    ),
    "size": "\n".join(["# clank: size", 'f="${1/#\\~/$HOME}"; [ -f "$f" ] && stat -c %s "$f" || echo none']),
    "sha256": "\n".join(
        ["# clank: sha256", 'f="${1/#\\~/$HOME}"; [ -f "$f" ] && sha256sum "$f" | cut -c1-64 || echo none']
    ),
    "home": "\n".join(["# clank: home", 'echo "$HOME"']),
    "output": "\n".join(["# clank: output", '"$@" 2>&1 < /dev/null; true']),
    "listener": "\n".join(["# clank: listener", 'ss -ltnpH "sport = :$1" 2> /dev/null | head -1']),
    "step": "\n".join(
        [
            "# clank: step",
            "cwd=$1; shift; envs=()",
            'while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift',
            'PATH=$(printf %s "$PATH" | tr : "\\n" | grep -v "^/mnt/[a-z]/" | paste -sd: -)',
            'mkdir -p "$cwd" 2> /dev/null && cd "$cwd" || { echo "cannot enter $cwd"; exit 126; }',
            'setsid env "${envs[@]}" "$@" < /dev/null 2>&1 &',
            'pid=$!; s=$(cat /proc/$pid/stat 2> /dev/null); rest=${s##*") "}; read -ra f <<< "$rest"',
            'echo "clank-group $pid ${f[19]:--}"',
            "wait $pid",
        ]
    ),
    "end": "\n".join(
        [
            "# clank: end",
            's=$(cat /proc/"$1"/stat 2> /dev/null) || { echo gone; exit 0; }; rest=${s##*") "}; read -ra f <<< "$rest"',
            '[ "${f[19]}" = "$2" ] || { echo gone; exit 0; }',
            'kill -TERM -- -"$1" 2> /dev/null',
            'for i in $(seq 1 50); do kill -0 -- -"$1" 2> /dev/null || { echo stopped; exit 0; }; sleep 0.1; done',
            'kill -KILL -- -"$1" 2> /dev/null; echo killed',
        ]
    ),
}
ANSWER_SECONDS = 60.0
SHA256_SECONDS = 1800.0


class WslHost(EngineHost):
    """A WSL distribution."""

    NAME = "wsl"
    LABEL = "A WSL distribution"
    PLATFORMS = ("win32",)

    def __init__(
        self, run: Runner = run_command, distro: str = "", name: str = "", stream: Streamer = stream_command
    ) -> None:
        super().__init__(name or f"wsl:{distro}")
        self.run = run
        self.stream = stream
        self.distro = distro
        self._home: str | None = None

    @staticmethod
    def distributions(run: Runner = run_command) -> list[str]:
        """The distributions WSL has, by name."""
        listed = run(["wsl.exe", "--list", "--quiet"]) or ""
        return [line.strip() for line in listed.splitlines() if line.strip()]

    def spawn(self, argv: Sequence[str], env: Mapping[str, str], cwd: str, log: PurePath) -> ProcessIdentity:
        """Start it in the distribution, its output appended to the log (a path of the service's machine)."""
        assignments = [f"{name}={value}" for name, value in env.items()]
        answer = self._ask("spawn", cwd, str(log), *assignments, "--", *argv)
        if answer.startswith("error "):
            raise HostError(answer.removeprefix("error "))
        _, pid, started, command = answer.split()
        if command != command_hash(argv):
            raise HostError(f"{argv[0]} started with another command line than the one asked for")
        return ProcessIdentity(self.name, int(pid), started, command)

    def alive(self, identity: ProcessIdentity) -> bool | None:
        """It still runs, with the same start time and command line; None when the distribution does not answer."""
        if identity.host != self.name:
            return False
        answer = self._try("alive", str(identity.pid), identity.started, identity.command)
        return True if answer == "alive" else False if answer == "gone" else None

    def stop(self, identity: ProcessIdentity, seconds: float) -> Stopped:
        """SIGTERM, then SIGKILL when the time is up; nothing when it is gone or another process."""
        if identity.host != self.name:
            return "gone"
        arguments = (str(identity.pid), identity.started, identity.command, str(round(seconds)))
        answer = self._try("stop", *arguments, timeout=seconds + ANSWER_SECONDS)
        if answer in ("stopped", "killed", "gone"):
            return answer  # type: ignore[return-value]  # one of Stopped's words, as the script says them
        raise HostError(
            f"WSL did not answer for {self.distro} while process {identity.pid} was being stopped: it may still run"
        )

    def output(self, argv: Sequence[str]) -> str | None:
        """What it prints in the distribution."""
        return self.run(self._command("output", argv), timeout=ANSWER_SECONDS)

    def exists(self, path: str) -> bool:
        """Whether the file is there."""
        return self.size(path) is not None

    def size(self, path: str) -> int | None:
        """Its size, or None."""
        answer = self._try("size", path)
        return int(answer) if answer.isdigit() else None

    def sha256(self, path: str) -> str | None:
        """Its SHA-256 (a model's takes a minute or two), or None."""
        answer = self._try("sha256", path, timeout=SHA256_SECONDS)
        return answer if len(answer) == 64 else None

    def expand(self, path: str) -> str:
        """`~` is the distribution's home folder for its default user."""
        if not path.startswith("~"):
            return path
        if self._home is None:
            self._home = self._ask("home")
        return self._home + path[1:]

    def listener(self, port: int) -> str | None:
        """The program listening on the port in the distribution, by name and process id."""
        answer = self._try("listener", str(port))
        if 'users:(("' not in answer:
            return None
        name = answer.split('users:(("', 1)[1].split('"', 1)[0]
        pid = answer.split("pid=", 1)[1].split(",", 1)[0] if "pid=" in answer else ""
        return f"{name} (process {pid})" if pid else name

    def run_step(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        cwd: str,
        line: Callable[[str], None],
        canceled: Callable[[], bool],
    ) -> int | None:
        """Run it in the distribution, in a process group of its own; canceled, the group is ended there."""
        group: list[str] = []

        def heard(text: str) -> None:
            if not group and text.startswith("clank-group "):
                group.extend(text.split()[1:3])
            else:
                line(text)

        assignments = [f"{name}={value}" for name, value in env.items()]
        status = self.stream(self._command("step", [cwd, *assignments, "--", *argv]), heard, canceled=canceled)
        if status is not None:
            return status
        if not canceled():
            raise HostError(
                f"WSL did not run the step in the distribution {self.distro}: is it installed (`wsl --list`)?"
            )
        if len(group) == 2:
            self._try("end", *group)
        return None

    def _command(self, script: str, arguments: Sequence[str]) -> list[str]:
        return ["wsl.exe", "-d", self.distro, "-e", "bash", "-c", SCRIPTS[script], "clank", *arguments]

    def _try(self, script: str, *arguments: str, timeout: float = ANSWER_SECONDS) -> str:
        return (self.run(self._command(script, arguments), timeout=timeout) or "").strip()

    def _ask(self, script: str, *arguments: str) -> str:
        answer = self.run(self._command(script, arguments), timeout=ANSWER_SECONDS)
        if answer is None:
            raise HostError(f"WSL did not answer for the distribution {self.distro}: is it installed (`wsl --list`)?")
        return answer.strip()
