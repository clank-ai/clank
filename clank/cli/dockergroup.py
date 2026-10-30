"""On Linux, the docker group taken at once (decision 0150).

An account added to the docker group has the group only in programs started after its next login: a process keeps the
groups it started with. Until then, every `clank` command runs itself again through `sg docker`, the system's own
command (shadow-utils) that gives a program a group its account is in, asking nothing. So the command, and Clank's
service when it starts one, may use Docker at once, with no log out and in. Programs the person starts outside Clank
get the group at their next login, as always.

It runs again only where the system lists the account in the docker group and this process lacks it, `sg` is
installed, and the command was not run again already: the run again carries `CLANK_DOCKER_GROUP`, so it never loops.
"""

import os
import shlex
import shutil
import sys
from collections.abc import Sequence

from clank.components.workspaces.adapters.docker_engine import docker_group

GUARD = "CLANK_DOCKER_GROUP"  # set in a command run again through sg, which is never run again
WINDOWS = sys.platform == "win32"


def command(argv: Sequence[str]) -> list[str]:
    """The command line that runs this `clank` command again with the docker group: through `sg docker`, which hands
    the command to /bin/sh as one line."""
    return ["sg", "docker", "-c", shlex.join([sys.executable, "-m", "clank", *argv])]


def pending() -> bool:
    """Whether this process lacks the docker group the system lists its account in, and can take it now."""
    if WINDOWS or os.environ.get(GUARD) == "1" or shutil.which("sg") is None:
        return False
    listed, process = docker_group()
    return listed and not process


def take(argv: Sequence[str]) -> None:
    """Run this `clank` command again with the docker group when it is pending; returns only when it is not."""
    if pending():
        sys.stdout.flush()
        sys.stderr.flush()
        os.execvpe("sg", command(argv), {**os.environ, GUARD: "1"})
