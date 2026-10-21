"""Refuse anything in the repository that looks like a key, a token, a home folder or a machine's identity (design
0001 §8.4; AGENTS.md: nothing personal or secret in the repository).

The patterns cover the common kinds of keys and tokens, paths into a user's home folder on Windows, macOS and Linux,
GPU identifiers and network hardware addresses, and the names of the user and the computer running the check. Those
names are skipped when they are generic (on a CI machine, or in a container, whose user is often an ordinary word such
as `node` or `agent`), and so are such users' home folders and those a placeholder names (`%USERNAME%`, `$USER`); a
mention of the repository's own home on GitHub (`<owner>/Clank`) is not personal. A name that identifies no one but is
reported anyway belongs in `GENERIC_NAMES`. A file that is not text is skipped. A finding
names its file, line and kind, never the value, so that a secret is not copied into a log.
"""

import getpass
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.files import read_text, repository_files

# Names that identify no one: the users and machines of CI services, containers (Clank's own sandboxes among them),
# services and editors. Many are also ordinary words in this repository, which would otherwise be reported everywhere.
GENERIC_NAMES = {
    "admin",
    "administrator",
    "agent",
    "app",
    "clank",
    "codespace",
    "dev",
    "docker",
    "github",
    "guest",
    "localhost",
    "node",
    "nobody",
    "opencode",
    "root",
    "runner",
    "runneradmin",
    "sandbox",
    "test",
    "ubuntu",
    "user",
    "vscode",
}
# A home folder named by a placeholder (`<you>`, `%USERNAME%`, `$USER`, `${USER}`, `$env:USERNAME`) or by a generic
# name is no one's.
_PLACEHOLDER = r"[<%$]"
_GENERIC = "|".join(sorted(GENERIC_NAMES))

PATTERNS = {
    "a private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "a GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})",
    "an API key (sk-...)": r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}",
    "an AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "a Google API key": r"\bAIza[0-9A-Za-z_-]{35}",
    "a Hugging Face token": r"\bhf_[A-Za-z0-9]{30,}",
    "a Slack token": r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    "a Windows home folder": rf"\b[A-Za-z]:[\\/]+Users[\\/]+(?!(?:Public|Default|{_GENERIC})\b|{_PLACEHOLDER})"
    r"[^\\/\s<>\"'`|*?]+",
    "a macOS home folder": rf"(?<![\w.~])/Users/(?!(?:Shared|{_GENERIC})\b|{_PLACEHOLDER})[A-Za-z0-9._-]+",
    "a Linux home folder": rf"(?<![\w.~])/home/(?!(?:{_GENERIC})\b|{_PLACEHOLDER})[a-z_][a-z0-9_-]*",
    "a GPU identifier": r"\bGPU-[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b",
    "a network hardware address": r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b",
}


@dataclass(frozen=True)
class Finding:
    """Something that looks secret or personal: where it is and what it looks like, never its value."""

    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: looks like {self.kind}"


def patterns(user: str | None, host: str | None, repository: str) -> dict[str, re.Pattern[str]]:
    """The patterns to look for, with the names of the user and the computer when they are not generic.

    A name followed by `/<repository>` is the repository's own home on GitHub, which is public, not personal.
    """
    compiled = {kind: re.compile(pattern) for kind, pattern in PATTERNS.items()}
    for kind, name in (("the user's name", user), ("this computer's name", host)):
        if name and len(name) >= 3 and name.lower() not in GENERIC_NAMES:
            home = re.escape("/" + repository)
            compiled[kind] = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])(?!{home}\b)")
    return compiled


def local_patterns(root: Path) -> dict[str, re.Pattern[str]]:
    """The patterns for the computer running the check, its user's name and its own name included."""
    try:
        user: str | None = getpass.getuser()
    except (OSError, KeyError, ImportError):
        user = None
    return patterns(user, socket.gethostname(), root.name)


def scan_text(path: str, text: str, compiled: dict[str, re.Pattern[str]]) -> list[Finding]:
    """The findings in one file's text."""
    return [
        Finding(path, number, kind)
        for number, line in enumerate(text.splitlines(), start=1)
        for kind, pattern in compiled.items()
        if pattern.search(line)
    ]


def scan(root: Path, files: list[Path], compiled: dict[str, re.Pattern[str]]) -> list[Finding]:
    """The findings in every text file of the list; files that are not text are skipped."""
    findings: list[Finding] = []
    for file in files:
        text = read_text(root / file)
        if text is not None:
            findings.extend(scan_text(file.as_posix(), text, compiled))
    return findings


def main() -> int:
    """Print every finding in the repository; returns 1 when there is any."""
    root = Path(__file__).resolve().parents[1]
    findings = scan(root, repository_files(root), local_patterns(root))
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
