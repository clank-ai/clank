"""Updating Clank (design 0026, decision 0145): what is installed, what is newer, and what updating does.

`installed` reads how Clank was installed from uv's record of the tool (`uv-receipt.toml` beside the tool's Python): a
release (a Git requirement: the installer's `git+https://github.com/clank-ai/clank@<tag>`), a clone (an editable
requirement, or Clank run from a working copy with no record), or another way. `newer` finds what is newer: GitHub's
latest release (its newest tag while there is no release) for a release; the commits a clone's branch is behind its
upstream, after a fetch, with whether its tree has changes of its own and whether those commits touch Clank's
dependencies or its VS Code extension, for a clone. `helper_script` writes what finishes an update that installs the
tool again once `clank update` has ended (decision 0145: Windows keeps a running program's files). Every outside call
goes through `run` and `fetch`, and the service through `restart_service`, `stop_running` and `start_helper`, which the
tests replace.
"""

import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from clank import __version__
from clank.kernel.processes import background_flags

REPO = "https://github.com/clank-ai/clank"
API = "https://api.github.com/repos/clank-ai/clank"
TIMEOUT = 10.0  # seconds GitHub has to answer
PACKAGE = Path(__file__).resolve().parent
DEPENDENCIES = ("pyproject.toml", "uv.lock")  # a pull that changes one installs the tool again
TITLES = 10  # the newest commits a clone is behind, named
VERSION = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:\.?(a|b|rc)(\d+))?")
STAGES = {"a": 0, "b": 1, "rc": 2}  # a final version comes after its pre-releases

Run = Callable[[list[str], str], tuple[int, str]]  # a command and its folder; its status and what it said
Fetch = Callable[[str], Any]  # a URL; its JSON


@dataclass(frozen=True)
class Install:
    """How Clank was installed: `release`, `clone` or `other`; its version; where (a clone's folder, a release's
    source, or how another install was found); uv's record of it ("" when none)."""

    kind: str
    version: str
    where: str
    receipt: str

    def view(self) -> dict[str, str]:
        """As the command's JSON says it."""
        return asdict(self)


def run(argv: list[str], cwd: str) -> tuple[int, str]:
    """A command's status and what it said (its errors too when it failed)."""
    try:
        done = subprocess.run(
            argv, cwd=cwd or None, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            check=False, creationflags=background_flags(),
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return done.returncode, (done.stdout or "") + ((done.stderr or "") if done.returncode else "")


def fetch(url: str) -> Any:
    """GitHub's API answer at `url`, read as JSON; `TIMEOUT` seconds at most."""
    headers = {"User-Agent": f"clank/{__version__} (update check)", "Accept": "application/vnd.github+json"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as answer:
        return json.load(answer)


def installed(*, prefix: Path | None = None, run: Run = run) -> Install:
    """How this Clank was installed (the module docstring)."""
    receipt = (prefix or Path(sys.prefix)) / "uv-receipt.toml"
    if receipt.is_file():
        try:
            tool = tomllib.loads(receipt.read_text(encoding="utf-8")).get("tool", {})
        except (OSError, tomllib.TOMLDecodeError):
            tool = {}
        for requirement in tool.get("requirements", []):
            if not isinstance(requirement, dict) or requirement.get("name") != "clank":
                continue
            if requirement.get("editable"):
                return Install("clone", __version__, str(requirement["editable"]), str(receipt))
            if requirement.get("git"):
                return Install("release", __version__, str(requirement["git"]), str(receipt))
            said = ", ".join(f"{key} {value}" for key, value in requirement.items() if key != "name")
            return Install("other", __version__, said or "no source named", str(receipt))
    status, output = run(["git", "rev-parse", "--show-toplevel"], str(PACKAGE))
    if status == 0 and output.strip():
        return Install("clone", __version__, output.strip(), "")
    return Install("other", __version__, f"no uv record of the tool beside {sys.executable}", "")


def later(newer: str, older: str) -> bool:
    """Whether the version `newer` comes after `older` (`v0.3.1` after `0.3.0b1`); False when either cannot be read."""
    first, second = _key(newer), _key(older)
    return first is not None and second is not None and first > second


def _key(text: str) -> tuple[int, int, int, int, int] | None:
    found = VERSION.match(text.strip())
    if found is None:
        return None
    major, minor, patch, stage, number = found.groups()
    return int(major), int(minor), int(patch or 0), STAGES.get(stage or "", 3), int(number or 0)


def newer(install: Install, run: Run = run, fetch: Fetch = fetch) -> dict[str, Any]:
    """What is newer than what is installed, and what was contacted to know it; `newer` None when it cannot be known
    (then `error` says why: never taken for up to date)."""
    if install.kind == "release":
        return _release(install, fetch)
    if install.kind == "clone":
        return _clone(install, run)
    return {"newer": None, "contacted": "nothing", "error": (
        f"Clank was installed another way ({install.where}): update it the way it was installed, or install it with "
        "the installer (getting-started)"
    )}  # fmt: skip


def _release(install: Install, fetch: Fetch) -> dict[str, Any]:
    contacted = "GitHub's API (api.github.com), for the latest release"
    try:
        try:
            latest = str(fetch(f"{API}/releases/latest")["tag_name"])
        except urllib.error.HTTPError as error:
            error.close()  # its answer's body, unread, is let go of here
            if error.code != 404:
                raise
            tags = fetch(f"{API}/tags")  # no release yet: its newest tag
            latest = str(tags[0]["name"]) if tags else ""
    except OSError as error:
        return {"newer": None, "latest": "", "contacted": contacted, "error": f"GitHub did not answer: {error}"}
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return {
            "newer": None,
            "latest": "",
            "contacted": contacted,
            "error": f"GitHub's answer could not be read: {error}",
        }
    return {"newer": later(latest, install.version), "latest": latest, "contacted": contacted, "error": ""}


def _clone(install: Install, run: Run) -> dict[str, Any]:
    where = install.where
    remote = run(["git", "remote", "get-url", "origin"], where)[1].strip()
    contacted = f"the clone's remote ({remote or 'origin'}), with git fetch"
    found: dict[str, Any] = {"newer": None, "contacted": contacted, "error": "", "behind": 0, "titles": [],
                             "dirty": False, "dependencies": False, "extension": False}  # fmt: skip
    status, said = run(["git", "fetch", "--quiet"], where)
    if status != 0:
        return {**found, "error": f"git fetch did not succeed: {said.strip() or 'it said nothing'}"}
    found["branch"] = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], where)[1].strip()
    status, upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], where)
    if status != 0 or not upstream.strip():
        return {**found, "error": f"its branch {found['branch']} has no upstream to update from"}
    found["upstream"] = upstream.strip()
    count = run(["git", "rev-list", "--count", "HEAD..@{u}"], where)[1].strip()
    found["behind"] = int(count) if count.isdigit() else 0
    log = run(["git", "log", "--format=%h %s", "-n", str(TITLES), "HEAD..@{u}"], where)[1]
    found["titles"] = [line.strip() for line in log.splitlines() if line.strip()]
    changed = [line.strip() for line in run(["git", "diff", "--name-only", "HEAD", "@{u}"], where)[1].splitlines()]
    found["dependencies"] = any(name in DEPENDENCIES for name in changed)
    found["extension"] = any(name.startswith("vscode/") for name in changed)
    found["dirty"] = bool(run(["git", "status", "--porcelain", "--untracked-files=no"], where)[1].strip())
    found["newer"] = found["behind"] > 0
    return found


def install_command(install: Install, found: dict[str, Any]) -> list[str]:
    """uv's command that installs the tool again: the latest release as the installer installs it, or the clone."""
    if install.kind == "release":
        return ["uv", "tool", "install", "--force", "--reinstall-package", "clank", "--python", "3.12",
                f"git+{REPO}@{found['latest']}"]  # fmt: skip
    return ["uv", "tool", "install", "--force", "--editable", install.where, "--python", "3.12"]


def helper_script(command: list[str], log: Path, waits_for: int, windows: bool) -> str:
    """The script that finishes an update after `clank update` (process `waits_for`) ended: it installs with `command`
    (Git allowed long paths for that one download, as the installer does), starts the service again, and writes each
    step to `log` (decision 0145)."""
    shown = " ".join(command)
    if windows:
        quoted = " ".join(f"'{part}'" for part in command[1:])
        return "\n".join([
            "# Clank's update, finishing after `clank update` ended (decision 0145). Each step goes to the log below.",
            f"$log = '{log}'",
            "function Say($text) {",
            "  Add-Content -Path $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $text)",
            "}",
            f"Say 'waiting for clank update (process {waits_for}) to end'",
            f"while (Get-Process -Id {waits_for} -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 300 }}",
            "$env:GIT_CONFIG_COUNT = '1'; $env:GIT_CONFIG_KEY_0 = 'core.longpaths'; $env:GIT_CONFIG_VALUE_0 = 'true'",
            f"Say '> {shown}'",
            f"& {command[0]} {quoted} *>> $log",
            "if ($LASTEXITCODE -ne 0) { Say \"uv could not install Clank (exit $LASTEXITCODE): it is as it was; "
            "start it with: clank serve --background\"; exit 1 }",
            "Say 'installed: starting the service again (clank serve --background)'",
            "& clank serve --background *>> $log",
            "Say 'done: clank status says what runs'",
            "",
        ])  # fmt: skip
    quoted = " ".join(f"'{part}'" for part in command)
    return "\n".join([
        "#!/bin/sh",
        "# Clank's update, finishing after `clank update` ended (decision 0145). Each step goes to the log below.",
        f"log='{log}'",
        'say() { echo "$(date "+%Y-%m-%d %H:%M:%S") $1" >> "$log"; }',
        f"say 'waiting for clank update (process {waits_for}) to end'",
        f"while kill -0 {waits_for} 2>/dev/null; do sleep 0.3; done",
        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.longpaths GIT_CONFIG_VALUE_0=true",
        f"say '> {shown}'",
        f'if ! {quoted} >> "$log" 2>&1; then say "uv could not install Clank: it is as it was; start it with: '
        'clank serve --background"; exit 1; fi',
        "say 'installed: starting the service again (clank serve --background)'",
        'clank serve --background >> "$log" 2>&1',
        "say 'done: clank status says what runs'",
        "",
    ])  # fmt: skip


def restart_service() -> bool:
    """Start the service again on the new code, when it runs; whether it ran."""
    status, _ = run([sys.executable, "-m", "clank", "status"], "")
    if status != 0:
        return False
    run([sys.executable, "-m", "clank", "stop"], "")
    run([sys.executable, "-m", "clank", "serve", "--background"], "")
    return True


def stop_running() -> None:
    """Stop the service and the gateway, whose files are the tool's (decision 0145)."""
    run([sys.executable, "-m", "clank", "stop"], "")
    run([sys.executable, "-m", "clank", "gateway", "stop"], "")


def start_helper(script: Path) -> None:
    """Start the helper detached, so it outlives `clank update`."""
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        subprocess.Popen(argv, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(["sh", str(script)], start_new_session=True, close_fds=True)
