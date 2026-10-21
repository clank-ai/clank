"""The components of the Clank service (design 0002 §1), in the order the service builds them.

Each is one package of the same shape (`clank/kernel/components.py` says which files); this list is the one place
they are named, and `clank.registry` reads it. A test fails when a component's folder is not listed here.
"""

from clank.components.agents.component import COMPONENT as AGENTS
from clank.components.flows.component import COMPONENT as FLOWS
from clank.components.gateway.component import COMPONENT as GATEWAY
from clank.components.machine.component import COMPONENT as MACHINE
from clank.components.notion.component import COMPONENT as NOTION
from clank.components.remote.component import COMPONENT as REMOTE
from clank.components.runtime.component import COMPONENT as RUNTIME
from clank.components.tools.component import COMPONENT as TOOLS
from clank.components.workspaces.component import COMPONENT as WORKSPACES
from clank.kernel.components import Component

COMPONENTS: tuple[Component, ...] = (MACHINE, WORKSPACES, RUNTIME, GATEWAY, TOOLS, AGENTS, REMOTE, NOTION, FLOWS)
