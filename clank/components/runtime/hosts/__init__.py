"""The runtime component's hosts: where engines run (decision 0030, design 0003 §2).

A kind of host is added here: its module, its recordings under `tests/fixtures/<name>/<version>/` (unless its program
is the running system itself), and a line in the list below.
"""

from clank.components.runtime.hosts.host import EngineHost
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.hosts.wsl import WslHost
from clank.kernel.adapters import AdapterKind

HOSTS: AdapterKind[EngineHost] = AdapterKind(
    "host",
    "Where engines run: this machine, or a WSL distribution of it.",
    EngineHost,
    [LocalHost, WslHost],
)
