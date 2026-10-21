"""Plans (design 0009 §4): a plan is a Markdown file whose header says `kind: plan`, wherever the folder keeps it.

The header is the file's front matter: its first line is `---`, and it ends at the next line that is `---` (spaces
after either are allowed, and Windows line endings). Only a line `kind: plan` inside it makes the file a plan; a file
that mentions it anywhere else is not one. Review mode lets the implementer change a plan without asking (§5), so
no file is a plan that is not Markdown, lies outside the folder, sits in a folder agents and assistants load their
settings from (`SETTINGS`), or instructs them (`INSTRUCTIONS`): a header in such a file must not let a change past the
owner. The planner may not write those files either (`adapters/opencode.py`).
"""

import posixpath
import re
from pathlib import PureWindowsPath

KIND = re.compile(r"^kind:\s*plan\s*$")
SETTINGS = (".opencode", ".claude", ".git", ".github", ".vscode")
INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md")


def plan_path(relative: str) -> bool:
    """Whether a file, by its path in the folder (`/` between its parts), may be a plan."""
    if not relative or relative.startswith("/") or PureWindowsPath(relative).drive:  # a drive: another place
        return False
    if not relative.lower().endswith(".md"):
        return False
    parts = posixpath.normpath(relative).split("/")
    if parts[0] == "..":
        return False
    names = {name.lower() for name in INSTRUCTIONS}
    return not any(part in SETTINGS for part in parts) and parts[-1].lower() not in names


def is_plan(text: str | None) -> bool:
    """Whether a file's text (None: no such file) is a plan's."""
    if not text:
        return False
    lines = text.splitlines()
    if lines[0].rstrip() != "---":
        return False
    header: list[str] = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            return any(KIND.match(each) for each in header)
        header.append(line)
    return False  # a header that never closes is not one
