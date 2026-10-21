"""The workspaces component's kind of adapter, the container platform (design 0002 §2.9, §2.10): where Clank's
containers run. Docker Desktop is the first; Docker Engine on Linux comes later. The interface is in `platform.py`;
each adapter is a module of its own, listed here, with its recordings in `tests/fixtures/<adapter>/`.
"""

from clank.components.workspaces.adapters.docker_desktop import DockerDesktop
from clank.components.workspaces.adapters.platform import ContainerPlatform
from clank.kernel.adapters import AdapterKind

CONTAINER_PLATFORMS: AdapterKind[ContainerPlatform] = AdapterKind(
    "container_platform",
    "Where containers run: Docker Desktop first, Docker Engine on Linux later.",
    ContainerPlatform,
    [DockerDesktop],
)
