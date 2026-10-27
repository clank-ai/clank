"""Design 0014 §4: on Docker Engine a mounted folder shows the host's own owners, and the agent works as user 1000 in
its container, so a folder that user may not read, write and enter is refused when its workspace opens, saying why:
that the agent works as user 1000 in its container, whose folder it is, and how to let it write (an access control
list for user 1000, or the folder opened to every user). The folder's owner bits, its group's (user 1000's group is
1000), the others' and a POSIX access control list all count, as Linux counts them. Docker Desktop's file sharing maps
the folder's owner, so it says nothing."""

import os
import struct
import sys
from pathlib import Path

import pytest

from clank.components.workspaces.adapters.docker_desktop import DockerDesktop
from clank.components.workspaces.adapters.docker_engine import DockerEngine, granted, refusal
from clank.kernel.processes import Answer

READ, WRITE, ENTER = 4, 2, 1
EVERYTHING = READ | WRITE | ENTER
USER_OBJ, USER, GROUP_OBJ, GROUP, MASK, OTHER = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20


def acl(*entries: tuple[int, int, int]) -> bytes:
    """A POSIX access control list as Linux stores it (`system.posix_acl_access`): version 2, then each entry's tag,
    permissions and id."""
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, perms, id) for tag, perms, id in entries)


def test_what_user_1000_may_do_comes_from_the_owner_the_group_the_others_and_the_acl() -> None:
    assert granted(0o40755, 1000, 1000, None) == EVERYTHING, "user 1000's own folder"
    assert granted(0o40755, 1001, 1001, None) == READ | ENTER, "another user's, as the others may"
    assert granted(0o40775, 1001, 1000, None) == EVERYTHING, "its group is user 1000's"
    assert granted(0o40777, 1001, 1001, None) == EVERYTHING, "open to every user"
    assert granted(0o40700, 1001, 1001, None) == 0, "a private folder"
    listed = acl((USER_OBJ, 7, 0), (USER, 7, 1000), (GROUP_OBJ, 5, 0), (MASK, 7, 0), (OTHER, 0, 0))
    assert granted(0o40770, 1001, 1001, listed) == EVERYTHING, "an access control list names user 1000"
    masked = acl((USER_OBJ, 7, 0), (USER, 7, 1000), (GROUP_OBJ, 5, 0), (MASK, 5, 0), (OTHER, 0, 0))
    assert granted(0o40750, 1001, 1001, masked) == READ | ENTER, "its mask limits what the list gives"
    grouped = acl((USER_OBJ, 7, 0), (GROUP_OBJ, 0, 0), (GROUP, 7, 1000), (MASK, 7, 0), (OTHER, 0, 0))
    assert granted(0o40770, 1001, 1001, grouped) == EVERYTHING, "or user 1000's group"


def test_the_refusal_says_the_agent_is_user_1000_whose_folder_it_is_and_how_to_let_it_write() -> None:
    said = refusal("/srv/work/paper", 0o40755, 1001, 1001, None, "owner")
    assert said.startswith("the agent works as user 1000 in its container")
    assert "/srv/work/paper is owner's (user 1001" in said
    assert "may not write it" in said
    assert "`setfacl -R -m u:1000:rwX,d:u:1000:rwX /srv/work/paper`" in said
    assert "`chmod -R a+rwX /srv/work/paper`" in said
    assert refusal("/srv/work/paper", 0o40755, 1000, 1000, None, "agent") == "", "user 1000's own: no refusal"
    private = refusal("/srv/work/my notes", 0o40700, 1001, 1001, None, "owner")
    assert "may not read, write or enter it" in private
    assert "'/srv/work/my notes'" in private, "a folder's name with a space is quoted for the shell"


def test_docker_desktops_file_sharing_says_nothing() -> None:
    def answer(arguments: object, timeout: float = 15.0, input: bytes | None = None) -> Answer:
        raise AssertionError("nothing is asked")

    desktop = DockerDesktop(lambda arguments, timeout=0.0: None, "docker", platform="linux", answer=answer)
    assert desktop.agent_access("/srv/work/paper") == ""


def test_on_linux_a_folder_of_another_user_that_user_1000_may_not_write_is_refused(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("a folder's owners and modes are Linux's: CI's Linux jobs run this")
    folder = tmp_path / "private"
    folder.mkdir()
    folder.chmod(0o700)
    engine = DockerEngine(lambda arguments, timeout=0.0: None, "/usr/bin/docker", platform="linux")
    said = engine.agent_access(str(folder))
    if os.getuid() == 1000:
        assert said == "", "the folder is user 1000's own"
    else:
        assert "may not read, write or enter it" in said
    folder.chmod(0o777)
    assert engine.agent_access(str(folder)) == ""
