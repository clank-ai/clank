"""A workspace's software (design 0004 §10): what installs the folder's own programs where its agent finds them.

The sandbox image holds the common tools, not a folder's own software (its packages, its command line, its MCP
server), and a workspace's container reaches only the hosts the owner allowed. So a workspace has a setup command, run
by Clank in a container of its own (`sandbox.setup_spec`), which installs the software into a Python virtual
environment in the workspace's home (`VENV`, first on the image's `PATH`), which sees the image's scientific Python
(decision 0138) and takes the folder's own versions over it. `proposed_setup` reads the folder's files for the usual
one: a `pyproject.toml` is installed editable (`pip install -e`, so the agent's changes to the code are what runs), with
its `dev` extra when it has one (tests, linters and the like); a `requirements.txt` is installed as it is; a folder with
neither needs nothing. The user may give another command; the workspace's record keeps it.

The setup goes out only through Clank's proxy, to the package indexes (decision 0169), and runs nothing of the
workspace's home but what it makes itself (`setup_script`, run with `/bin/bash -c`, never a login shell, which would
read the home's profile): its `HOME` is a clean folder of the container's own (`SETUP_HOME`), pip reads no configuration
file (`PIP_CONFIG`), its `PATH` is the image's without `~/.venv/bin` (`SETUP_PATH`), and Clank makes `~/.venv` afresh
with the image's own Python, each program of its steps named by its full path, before it puts `~/.venv/bin` first on
the `PATH` again and the command runs, so whatever was written into the home since (by the agent too) changes nothing
of what runs. `~/.venv` in the command is still the workspace's environment (`VENV_PATH`), so a command kept from before
installs where the agent finds it.
"""

import re
import tomllib
from pathlib import Path

VENV = "~/.venv"
VENV_PATH = "/home/agent/.venv"  # where `VENV` is, whatever a setup's HOME says (`sandbox.AGENT_HOME`'s `.venv`)
EXTRA = "dev"
SETUP_HOME = "/tmp/clank-setup-home"  # a setup's HOME: made empty in the container's own files, removed with it
SETUP_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"  # the image's PATH without `VENV_PATH`
PIP_CONFIG = "/dev/null"  # PIP_CONFIG_FILE: pip then reads no configuration file at all, Clank's settings alone
SHELL = "/bin/bash"  # the image's own shell, which runs `setup_script` (`bash -c`)
PYTHON = "/usr/bin/python3"  # the image's own Python, which makes `~/.venv` afresh
TILDE_VENV = re.compile(r"(^|[\s;&|(=])~/\.venv(?=$|[\s/;&|)])")  # `~/.venv` as the shell would expand it


def proposed_setup(folder: str) -> str | None:
    """The command that installs the folder's software, from its files; None when it has nothing to install."""
    root = Path(folder)
    make = f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install"
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        return f"{make} -e '.[{EXTRA}]'" if EXTRA in _extras(pyproject) else f"{make} -e ."
    if (root / "requirements.txt").is_file():
        return f"{make} -r requirements.txt"
    return None


def setup_env() -> tuple[tuple[str, str], ...]:
    """What a setup runs with besides its threads and the proxy: a clean HOME, a PATH outside the workspace's home
    (the image's without `~/.venv/bin`, which `setup_script` puts first once it made it afresh), and pip set up by
    Clank alone."""
    return (("HOME", SETUP_HOME), ("PATH", SETUP_PATH), ("PIP_CONFIG_FILE", PIP_CONFIG))


def setup_script(command: str) -> str:
    """What the setup container runs with `bash -c`: its clean HOME made, `~/.venv` removed (a link as a link) and made
    afresh by the image's own Python in isolated mode, each program named by its full path, ending the setup when any
    of that fails; then `~/.venv/bin` first on the PATH, as in the workspace's container, and the command on a line of
    its own, its `~/.venv` the workspace's, so its exit is the setup's."""
    made = f"{PYTHON} -I -m venv --system-site-packages {VENV_PATH}"
    prepare = f'/bin/mkdir -p "$HOME" && /bin/rm -rf {VENV_PATH} && {made} && export PATH={VENV_PATH}/bin:{SETUP_PATH}'
    return prepare + " || exit\n" + TILDE_VENV.sub(lambda found: found.group(1) + VENV_PATH, command)


def _extras(pyproject: Path) -> set[str]:
    """The optional dependencies' names a `pyproject.toml` declares; none when it cannot be read."""
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return set()
    extras = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    return set(extras) if isinstance(extras, dict) else set()
