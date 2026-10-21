"""One frame of the console as text (decision 0027; design 0001 §5.8).

`clank console --snapshot` prints it, for scripts, bug reports and a model that cannot see a screen, and the console's
tests compare it with the snapshots checked in. It renders the screen through Textual's compositor, as Textual's own
screenshots do, into a Rich console that records text instead of an SVG image.
"""

import io
from typing import Any

from rich.console import Console
from textual.app import App


def render_text(app: App[Any]) -> str:
    """The screen the app shows now, as plain text, one line per row."""
    width, height = app.size
    console = Console(
        width=width,
        height=height,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        record=True,
        legacy_windows=False,
        safe_box=False,
    )
    console.print(app.screen._compositor.render_update(full=True, screen_stack=app._background_screens))
    return console.export_text()
