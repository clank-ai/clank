"""Docker's memory limits, in words (design 0014 §4).

Every workspace's container has a memory limit (design 0002 §2.9, design 0004 §3). Where Docker cannot set one (a
Raspberry Pi's default kernel boots with the memory controller off, and `docker run --memory` then runs without it), an
agent's runaway process could take the computer's memory, and the out-of-memory killer may end Clank's own service
with it. So no workspace opens there unless the owner allows it (`allow_unlimited_memory` in `config/docker.json`).
These are the words the opening, Docker's view and the doctor share: Docker's own, and the fix, which the owner makes
(Clank never edits /boot/firmware).
"""

from collections.abc import Sequence

MEMORY_FIX = (
    "on a Raspberry Pi, add `cgroup_enable=memory` to the one line of /boot/firmware/cmdline.txt, then restart; "
    "elsewhere, turn on the kernel's memory controller. Clank changes neither"
)


def memory_said(words: Sequence[str]) -> str:
    """Docker's own words on why it cannot limit a container's memory."""
    return "; ".join(words) or "Docker says MemoryLimit is false"


def memory_refused(words: Sequence[str]) -> str:
    """Why no workspace opens where Docker cannot limit a container's memory, and what to do."""
    return (
        f"Docker cannot limit a container's memory ({memory_said(words)}), so no workspace opens: an agent's runaway "
        f"process could take this computer's memory. {MEMORY_FIX[0].upper()}{MEMORY_FIX[1:]}; or let workspaces open "
        'anyway with "allow_unlimited_memory": true in config/docker.json'
    )
