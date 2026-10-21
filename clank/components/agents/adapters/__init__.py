"""The agents component's kind of adapter, the agent program (decision 0011, design 0004 §4): the programs that work
in a workspace's container. OpenCode is the first. The interface is in `program.py`; each adapter is a module of its
own, listed here.
"""

from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.adapters.program import AgentProgram
from clank.kernel.adapters import AdapterKind

AGENT_PROGRAMS: AdapterKind[AgentProgram] = AdapterKind(
    "agent_program",
    "The programs that work in a workspace's container: OpenCode first.",
    AgentProgram,
    [OpenCode],
)
