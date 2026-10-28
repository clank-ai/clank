"""The workspaces component's kind of adapter, the container platform (design 0002 §2.9, §2.10): where Clank's
containers run. Docker Desktop is the first; Docker Engine on Linux, the system's service, the second (design 0014 §2,
decision 0070). The interface is in `platform.py`; the container commands, Docker's own CLI whatever program runs the
engine, are one base's, `DockerCli` in `docker_cli.py`; each adapter is a module of its own that extends it, listed
here, with its recordings in `tests/fixtures/<adapter>/`.
"""

from clank.components.workspaces.adapters.docker_desktop import DockerDesktop
from clank.components.workspaces.adapters.docker_engine import DockerEngine
from clank.components.workspaces.adapters.platform import ContainerPlatform
from clank.kernel.adapters import AdapterKind

CONTAINER_PLATFORMS: AdapterKind[ContainerPlatform] = AdapterKind(
    "container_platform",
    "Where containers run: Docker Desktop, and Docker Engine on Linux.",
    ContainerPlatform,
    [DockerDesktop, DockerEngine],
)
