"""A workspace's software (design 0004 §10): what installs the folder's own programs where its agent finds them.

The sandbox image holds the common tools, not a folder's own software (its packages, its command line, its MCP
server), and a workspace's container cannot download anything. So a workspace has a setup command, run by Clank in a
container of its own that reaches the internet (`sandbox.setup_spec`), which installs the software into a Python
virtual environment in the workspace's home (`VENV`, first on the image's `PATH`). `proposed_setup` reads the folder's
files for the usual one: a `pyproject.toml` is installed editable (`pip install -e`, so the agent's changes to the code
are what runs), with its `dev` extra when it has one (tests, linters and the like); a `requirements.txt` is installed as
it is; a folder with neither needs nothing. The user may give another command; the workspace's record keeps it.
"""

import tomllib
from pathlib import Path

VENV = "~/.venv"
EXTRA = "dev"


def proposed_setup(folder: str) -> str | None:
    """The command that installs the folder's software, from its files; None when it has nothing to install."""
    root = Path(folder)
    make = f"python3 -m venv {VENV} && {VENV}/bin/python -m pip install"
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        return f"{make} -e '.[{EXTRA}]'" if EXTRA in _extras(pyproject) else f"{make} -e ."
    if (root / "requirements.txt").is_file():
        return f"{make} -r requirements.txt"
    return None


def _extras(pyproject: Path) -> set[str]:
    """The optional dependencies' names a `pyproject.toml` declares; none when it cannot be read."""
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return set()
    extras = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    return set(extras) if isinstance(extras, dict) else set()
