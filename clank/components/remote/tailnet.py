"""Tailscale, through its command (design 0005 §4): this machine's name on the tailnet and its user's login, and
publishing the phone's listener on the tailnet only (`tailscale serve --https=PORT`), or taking it down.

Clank refuses to publish when Tailscale Funnel is on for that port: Funnel would face the internet. The phone's checkup
(design 0025 §2) reads Tailscale's whole status (`status`: the peers, MagicDNS, the certificates) and what it serves
(`serve_config`: where each port goes, where Funnel is on). Every command runs without a window (`run_answer`) and
within a short time; a Tailscale that is not installed, not running or not signed in is said, not raised.
"""

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clank.kernel.processes import Answer, run_answer

WINDOWS_PROGRAM = Path("C:/Program Files/Tailscale/tailscale.exe")
SECONDS = 20.0
Run = Callable[[Sequence[str]], Answer]


@dataclass(frozen=True)
class Tailnet:
    """This machine on the tailnet: its name (`desktop.tail1234.ts.net`) and its user's login; or why not."""

    host: str
    login: str
    problem: str = ""


def program() -> str | None:
    """Tailscale's command on this machine, or None."""
    found = shutil.which("tailscale")
    if found:
        return found
    return str(WINDOWS_PROGRAM) if WINDOWS_PROGRAM.is_file() else None


def _run(argv: Sequence[str]) -> Answer:
    command = program()
    if command is None:
        return Answer(None, "", "Tailscale is not installed (https://tailscale.com/download)")
    return run_answer([command, *argv], timeout=SECONDS)


def _json(answer: Answer) -> dict[str, Any]:
    try:
        found = json.loads(answer.output) if answer.ok else None
    except ValueError:
        found = None
    return found if isinstance(found, dict) else {}


def status(run: Run | None = None) -> tuple[dict[str, Any], str]:
    """`tailscale status --json` as Tailscale wrote it; when it did not answer, {} and why."""
    answer = (run or _run)(["status", "--json"])
    found = _json(answer)
    if not found:
        return {}, (answer.errors or answer.output).strip()[:200] or "Tailscale did not answer"
    return found, ""


def serve_config(run: Run | None = None) -> dict[str, Any]:
    """`tailscale serve status --json`: where each port of this machine goes on the tailnet, and where Funnel is on;
    {} when nothing is served or Tailscale did not answer."""
    return _json((run or _run)(["serve", "status", "--json"]))


def read(run: Run | None = None) -> Tailnet:
    """This machine's name on the tailnet and its user's login; a problem when Tailscale cannot say."""
    found, problem = status(run)
    if not found:
        return Tailnet("", "", problem)
    if found.get("BackendState") != "Running":
        return Tailnet("", "", f"Tailscale is {found.get('BackendState') or 'not running'}: sign in (tailscale up)")
    me = found.get("Self") or {}
    user = (found.get("User") or {}).get(str(me.get("UserID", ""))) or {}
    host = str(me.get("DNSName") or "").rstrip(".")
    login = str(user.get("LoginName") or "").lower()
    if not host or not login:
        return Tailnet(host, login, "Tailscale did not say this machine's name or its user")
    return Tailnet(host, login)


def funnel_on(host: str, port: int, run: Run | None = None) -> bool:
    """Whether Tailscale Funnel publishes this port to the internet."""
    return bool((serve_config(run).get("AllowFunnel") or {}).get(f"{host}:{port}"))


def publish(local_port: int, tailnet_port: int, run: Run = _run) -> str:
    """Publish the local port on the tailnet only, over HTTPS on `tailnet_port`; "" when done, else why not."""
    answer = run(["serve", "--bg", f"--https={tailnet_port}", f"http://127.0.0.1:{local_port}"])
    return "" if answer.ok else (answer.errors or answer.output).strip()[:300] or "tailscale serve refused"


def unpublish(tailnet_port: int, run: Run = _run) -> str:
    """Stop publishing the tailnet port; "" when done (or it was not), else why not."""
    answer = run(["serve", f"--https={tailnet_port}", "off"])
    said = (answer.errors or answer.output).strip()
    if answer.ok or "not found" in said.lower() or "does not exist" in said.lower():
        return ""
    return said[:300] or "tailscale serve refused"
