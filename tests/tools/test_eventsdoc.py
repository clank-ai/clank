"""Design 0002 §2.3: the events page lists every declared event type, grouped by the part that declares it, with what
it means, its data, and whether it is kept."""

from clank.kernel.events import EventType, EventTypes
from tools.eventsdoc import render


def test_the_page_lists_every_type_with_its_meaning_and_data() -> None:
    text = render(
        EventTypes(
            [
                EventType("thing.happened", "A thing happened.", {"size": "How big it was.", "who": "Who did it."}),
                EventType("thing.ticked", "A live tick.", live=True, owner="docker"),
            ]
        )
    )
    assert "## kernel" in text
    assert "## docker" in text
    assert "| `thing.happened` | kept | A thing happened. | `size`: How big it was.; `who`: Who did it. |" in text
    assert "| `thing.ticked` | live only | A live tick. | none |" in text
