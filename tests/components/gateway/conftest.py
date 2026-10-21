"""The gateway's tests use the runtime's rig: its kernel, the fake engines installed for both serving setups, and a
preset for each; and the fake OpenRouter (`openrouter`), the adapter's URL pointed at it."""

from tests.components.runtime.conftest import openrouter, rig  # noqa: F401  (fixtures, found by their names)
