"""Docker as `clank setup` reads it (design 0028 §4, §5): what the setup's checklist needs of the workspaces, read in
one go from the container platform's adapter, by the service or by `clank setup` itself when the service does not run.

`setup_reading` asks the platform its status, how it is set up on this computer (`PlatformSetup`: whether it starts with
the computer, whether this account is in its group, and the commands its owner runs to put it right), and while it runs,
whether it can limit a container's memory and whether Clank's sandbox image is built for this Clank (its tag is the
checksum of the image's Dockerfile, so an image built by an earlier Clank is not this one). For a folder, it says why
the folder may not be a workspace (`checked_folder`'s refusal: a drive's root, the home folder, Clank's own folder), or
why the agent could not write it as the platform mounts it (Docker Engine shows the host's own owners, design 0014 §4).
It changes nothing: every question is one the platform answers without starting anything, and a platform that is not
installed, or not supported, is asked nothing more.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from clank.components.workspaces.adapters.platform import (
    ContainerPlatform,
    PlatformError,
    PlatformSetup,
    PlatformStatus,
)
from clank.components.workspaces.sandbox import image_tag

Memory = tuple[bool | None, list[str]]


@dataclass(frozen=True)
class SetupReading:
    """Docker as `clank setup` reads it: the platform's status, whether Clank starts it, how it is set up on this
    computer; while it runs, whether it limits a container's memory (and whether the owner allows a workspace without
    that), and whether the sandbox image of `image`'s tag is built (None: Docker cannot be asked now); for the folder
    named (none: not asked), why it may not be a workspace, or why the agent could not write it."""

    status: PlatformStatus
    starts: bool = False
    setup: PlatformSetup = field(default_factory=PlatformSetup)
    memory: Memory = (None, [])
    allow_unlimited_memory: bool = False
    image: str = ""
    image_built: bool | None = None
    folder: str = ""
    folder_problem: str = ""
    folder_access: str = ""


def setup_reading(
    platform: ContainerPlatform,
    *,
    starts: Callable[[], bool],
    allow_unlimited_memory: bool,
    clank_home: Path,
    folder: str = "",
    socket_folder: Path | None = None,
    memory: Callable[[], Memory] | None = None,
    status: PlatformStatus | None = None,
) -> SetupReading:
    """Docker as `clank setup` reads it, from this platform: `starts` says whether Clank starts it, `memory` reads its
    memory limits (the platform's own question unless the caller keeps a reading), `status` is its status when the
    caller has just read it (else it is asked)."""
    from clank.components.workspaces.folders import WorkspaceError, checked_folder

    status = status or platform.status()
    tag = image_tag()
    if status.state in ("not installed", "unsupported"):
        return SetupReading(status, image=tag, folder=folder, allow_unlimited_memory=allow_unlimited_memory)
    setup = platform.setup_state()
    found: Memory = (None, [])
    built: bool | None = None
    if status.running:
        try:
            found = (memory or platform.memory_limits)()
            built = platform.image_exists(tag)
        except PlatformError:
            built = None
    problem = access = ""
    if folder:
        try:
            path = checked_folder(folder, clank_home, socket_folder)
        except WorkspaceError as error:
            problem = str(error)
        else:
            access = platform.agent_access(path)
    return SetupReading(
        status=status,
        starts=starts(),
        setup=setup,
        memory=found,
        allow_unlimited_memory=allow_unlimited_memory,
        image=tag,
        image_built=built,
        folder=folder,
        folder_problem=problem,
        folder_access=access,
    )
