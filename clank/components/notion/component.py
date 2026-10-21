"""The notion component's declaration (design 0010): Clank's connection to the owner's Notion, with their
integration's secret; the agent reads the shared databases through it, and every change the agent wants is staged for
the owner's review before the service writes it."""

from typing import Any

from clank.components.notion.kinds import NotionSettings
from clank.components.notion.service import EVENT_TYPES, Notion
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank notion`."""
    from clank.components.notion.cli import notion

    return [notion]


COMPONENT = Component(
    name="notion",
    summary="The owner's Notion: read by the agent through the service, changed only after the owner's review.",
    kinds=(NotionSettings,),
    event_types=tuple(EVENT_TYPES),
    build=Notion,
    commands=commands,
    uses=("agents",),  # a batch sent back goes to the workspace's agent (design 0010 §7)
)
