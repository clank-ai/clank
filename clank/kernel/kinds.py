"""The kernel's own declarations: its kinds of record and its event types, collected for `clank.registry`.

Each part of the kernel declares what it owns in its own module; this module only lists those declarations, so that
the registry reads the kernel the way it reads a component.
"""

from clank.kernel import operations, questions, secrets, service_kinds, settings
from clank.kernel.console_kinds import ConsoleSettings, StyleSettings
from clank.kernel.events import Event, EventType
from clank.kernel.operations import Operation
from clank.kernel.questions import Question
from clank.kernel.records import Kind
from clank.kernel.service_kinds import ServiceSettings

KINDS: list[type[Kind]] = [ServiceSettings, ConsoleSettings, StyleSettings, Event, Operation, Question]
EVENT_TYPES: list[EventType] = [
    *service_kinds.EVENT_TYPES,
    *settings.EVENT_TYPES,
    *operations.EVENT_TYPES,
    *questions.EVENT_TYPES,
    *secrets.EVENT_TYPES,
]
