"""The Monitor's live text (design 0012 §2, §7; §11 step 7): the followed session's model request as it is written,
from the gateway's live view of that session (`GET /gateway/live?session=`), its own requests only (a subagent's show
in its own flow). OpenCode keeps a part's text only at its start and at its end, so the gateway is the only source of
text as it is written, and of a step for a viewer who joins in the middle.

The page shows it under the Flow's row with `l` on the Session view, and reads it only while it is shown and the page is
on screen: on every tick while the session works, once a second while it does not. `LiveView.take` keeps the text read
so far and its length, so each reading asks only for what came after it (`after`), as the Requests page's live view
does; a reading of another request than the one held starts that one from its start, and once the request held ended
and a newer one began, the newer one is followed. Its first line says whether the request is being written or ended,
its tokens and what was asked, cut to the panel's width; the text shows its end (`LIVE_SHOWN` characters), its thinking
dimmed, its answer as it is, its calls' arguments in the calls' color (`live_text`, the Requests page's), and stays at
its end while it is there. What did not change is not drawn again.
"""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Label

from clank.console.lists import relabel
from clank.console.style import current, mark
from clank.console.text import live_text

WIDTH = 100  # the width drawn for before the panel is laid out


def head(found: dict[str, Any] | None, width: int) -> Content:
    """The first line: being written or ended, its tokens and speed, and what was asked, cut to `width`."""
    meta = (found or {}).get("meta")
    if not meta:
        why = (found or {}).get("problem") or "the session's next model request shows here as it is written"
        return _cut(Content.styled(f"no request of this session yet: {why}", "$clank-quiet"), width)
    speed = f" · {meta['per_second']:.0f} tok/s" if meta.get("per_second") else ""
    if found and found.get("flying"):
        state = Content.assemble((f"{mark('on')} ", "$clank-now"), ("being written", "bold"))
    else:
        state = Content.assemble((f"{mark('off')} ", "$clank-quiet"), ("ended", "bold"))
    asked = " ".join(str((found or {}).get("asked") or "").split())
    said = Content.assemble(
        state,
        f" · {int(meta.get('tokens') or 0):,} tokens{speed}",
        (f" · asked: {asked}" if asked else "", "$clank-quiet"),
    )
    return _cut(said, width)


def _cut(line: Content, width: int) -> Content:
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


class LiveView(Vertical):
    """The live text's content: its first line, and the text in a scroll kept at its end."""

    can_focus = True

    DEFAULT_CSS = """
    LiveView {
        height: auto;
    }
    LiveView #monitor-live-head {
        text-wrap: nowrap;
    }
    LiveView #monitor-live-scroll {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.request = ""  # the request followed
        self.parts: list[list[str]] = []  # its text so far, by kind
        self.length = 0  # its characters so far: the next reading asks for those after
        self.text = Content("")
        self.found: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        """The first line, then the text in a scroll."""
        yield Label(head(None, WIDTH), id="monitor-live-head")
        with VerticalScroll(id="monitor-live-scroll"):
            yield Label(id="monitor-live-text")

    def take(self, found: dict[str, Any], asked: str) -> None:
        """A reading of the live view, asked for the request `asked` from `self.length` on: what is new, or another
        request from its start."""
        if found.get("id") != asked:  # another request: read it from its start
            self.request, self.parts, self.length = str(found.get("id") or ""), [], 0
            if asked:  # what came was from the offset of the one held: the new one is read next, whole
                self.found = found
                self._draw()
                return
        for kind, text in found.get("parts") or []:
            if self.parts and self.parts[-1][0] == kind:
                self.parts[-1][1] += text
            else:
                self.parts.append([kind, text])
        self.length = int(found.get("length") or 0)
        if not found.get("flying") and found.get("newest") and found["newest"] != self.request:
            self.request, self.parts, self.length = str(found["newest"]), [], 0  # the next began
        self.found = found
        self._draw()

    def forget(self) -> None:
        """Another session is followed: nothing of the last is held."""
        self.request, self.parts, self.length, self.found = "", [], 0, None
        self._draw()

    def _draw(self) -> None:
        width = self.content_size.width or WIDTH
        relabel(self.query_one("#monitor-live-head", Label), head(self.found, width))
        scroll = self.query_one("#monitor-live-scroll", VerticalScroll)
        at_end = scroll.scroll_y >= scroll.max_scroll_y - 1
        self.text = live_text(self.parts)
        relabel(self.query_one("#monitor-live-text", Label), self.text)
        if at_end:
            scroll.call_after_refresh(scroll.scroll_end, animate=False)
