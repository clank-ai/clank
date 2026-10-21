"""The runtime component's kinds of adapter: engines, one per serving setup (design 0003 §4, decision 0010); and
endpoints, one per provider someone else runs, reached at its URL (design 0016 §6, decision 0102).

A serving setup is added here: its module, its recordings under `tests/fixtures/<name>/<version>/`, and a line in the
list below; nothing else in Clank changes. So is a provider: its module, its HTTP recordings
(`tests/fixtures/<name>/<date>/http.json`) and a line in `ENDPOINTS`.
"""

from clank.components.runtime.adapters.endpoint import EndpointAdapter
from clank.components.runtime.adapters.engine import EngineAdapter
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.adapters.llamacpp import LlamaCpp
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.adapters import AdapterKind

ENGINES: AdapterKind[EngineAdapter] = AdapterKind(
    "engine",
    "The programs that serve a model on this machine, one adapter per serving setup.",
    EngineAdapter,
    [KvmemLlamacpp, LlamaCpp],
)
ENDPOINTS: AdapterKind[EndpointAdapter] = AdapterKind(
    "endpoint",
    "The providers someone else runs, reached at their URL with the owner's key, one adapter per provider.",
    EndpointAdapter,
    [OpenRouter],
)
