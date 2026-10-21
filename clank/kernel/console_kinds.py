"""The console's settings kinds: its style, and which style it uses (design 0011 §2-§3).

A **style** is a readable file of the console's named elements: its colors by role, its data colors and the colors of
the kinds the Monitor and flows draw, its border, its titles, its marks, its bar and spark glyphs, its tree's
connectors and its spacing. Each element's default is Clank's own style, the boards' (design 0011's tables), so a style
that names a few elements keeps every other of Clank's, and Clank's own file (`clank/defaults/styles/clank.json`) holds
nothing but its title. A color is written `#rrggbb`; a glyph is one cell wide. The **console** record names the style
the console draws in (`clank` until it is changed).

They live in the kernel, beside the service's own settings kind, because the service reads and writes every settings
record (the Records page, `clank records`) and the kernel imports no client (decision 0019); the console reads them too,
before the service answers, so that it draws in its style from its first frame.
"""

import unicodedata
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from clank.kernel.records import Settings

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


def _one_cell_each(text: str) -> str:
    """Glyphs of one cell each: no character a terminal draws two cells wide, none that joins the one before it."""
    for character in text:
        if unicodedata.east_asian_width(character) in ("W", "F") or unicodedata.combining(character):
            raise ValueError(f"{character!r} is not one cell wide in every terminal")
    return text


def _one_glyph(text: str) -> str:
    if len(text) != 1:
        raise ValueError("must be one character")
    return _one_cell_each(text)


Glyph = Annotated[str, AfterValidator(_one_glyph)]
Glyphs = Annotated[str, AfterValidator(_one_cell_each)]


class Element(BaseModel):
    """A group of a style's elements; a key it does not know is refused, so a misspelled one is found."""

    model_config = ConfigDict(extra="forbid")


def _color(default: str, title: str, what: str) -> Color:
    return Field(default, title=title, description=what)


class StyleColors(Element):
    """The colors by role: what each is for, never what it looks like."""

    background: Color = _color("#1a1b26", "Background", "The page, the panels and the windows.")
    bars: Color = _color("#16161e", "Bars", "The header and the keys bar.")
    inset: Color = _color("#16161e", "Inset", "A diff or a command shown inside a panel.")
    surface: Color = _color("#24283b", "Surface", "A button, a choice to pick.")
    border: Color = _color("#3b4261", "Border", "Every panel's border, the menu's edge, a divider.")
    border_focused: Color = _color("#7aa2f7", "Focused border", "The border of the panel that has the focus.")
    title: Color = _color("#7aa2f7", "Title", "A panel's title, set in its border.")
    key: Color = _color("#7aa2f7", "Key", "A key, in the keys bar, the menu and a sentence.")
    brand: Color = _color("#bb9af7", "Brand", "The header's ◆ CLANK.")
    name: Color = _color("#e0af68", "Name", "The folder's name in the header, a workspace's in a sentence.")
    text: Color = _color("#c0caf5", "Text", "Text.")
    quiet: Color = _color("#828bb8", "Quiet", "What explains: a time, a key's words, a panel's note.")
    dim: Color = _color("#565f89", "Dim", "The room kept for the answer, a list's rail, a waiting box's border.")
    selection: Color = _color("#283457", "Selection", "The highlighted row.")
    selected_text: Color = _color("#ffffff", "Selected text", "The highlighted row's text, in bold.")
    good: Color = _color("#9ece6a", "Good", "As wanted: running, ready, done.")
    attention: Color = _color("#e0af68", "Attention", "Waits for you; a warning.")
    now: Color = _color("#ff9e64", "Now", "What runs now; the spinner.")
    failed: Color = _color("#f7768e", "Failed", "What failed, or is not as it should be.")
    planned: Color = _color("#f7768e", "Planned", "A page a later milestone brings.")
    low: Color = _color("#9ece6a", "Low", "A bar below 60% of its whole.")
    busy: Color = _color("#e0af68", "Busy", "A bar from 60% to 85% of its whole.")
    full: Color = _color("#f7768e", "Full", "A bar above 85% of its whole.")
    diff_hunk: Color = _color("#bb9af7", "Diff hunk", "A diff's hunk line; added lines are good, removed failed.")
    scrollbar: Color = _color("#3b4261", "Scroll bar", "A scroll bar's thumb.")
    scrollbar_track: Color = _color("#1f2335", "Scroll bar's track", "A scroll bar's track.")


class ContextParts(Element):
    """The colors of the context's parts, as the Monitor draws them (design 0012 §4.2)."""

    system: Color = _color("#7aa2f7", "System prompt", "The agent program's instructions.")
    tools: Color = _color("#3d59a1", "Tool definitions", "The tools the agent may call.")
    yours: Color = _color("#e0af68", "Your messages", "What the owner wrote.")
    text: Color = _color("#c0caf5", "Model text", "What the model wrote as its answer.")
    thinking: Color = _color("#bb9af7", "Thinking", "The model's thinking sent back with the history.")
    calls: Color = _color("#73daca", "Tool calls", "The calls the model made.")
    results: Color = _color("#9ece6a", "Tool results", "What the calls gave back.")
    loop: Color = _color("#f7768e", "Loop text", "Text that repeats itself, kept in the context.")


class CallKinds(Element):
    """The colors of the kinds of tool call, as the Monitor's flow draws them (design 0012 §6.3)."""

    reading: Color = _color("#7aa2f7", "Reading", "A call that reads (read, glob, grep, list).")
    running: Color = _color("#e0af68", "Running", "A call that runs a command (bash).")
    editing: Color = _color("#73daca", "Editing", "A call that changes a file (edit, write, patch).")
    mcp: Color = _color("#9d7cd8", "MCP", "A call to an MCP server's tool.")


class FlowBoxes(Element):
    """The colors of a flow's kinds of box (design 0013 §12)."""

    you: Color = _color("#e0af68", "You", "A brief, or work the owner does by hand.")
    plan: Color = _color("#7aa2f7", "Plan", "A box that writes a plan.")
    verify: Color = _color("#bb9af7", "Verify", "A box that checks an earlier box's deliverable.")
    decompose: Color = _color("#7dcfff", "Decompose", "A box that breaks a plan into tasks.")
    task: Color = _color("#73daca", "Task", "A box that does one task.")
    integrate: Color = _color("#c0caf5", "Integrate", "A box that puts every deliverable together.")
    gate: Color = _color("#e0af68", "Gate", "The owner's checkpoint.")


class StyleKinds(Element):
    """The colors the Monitor and flows draw by kind, each by name, so a kind keeps its color."""

    parts: ContextParts = Field(default_factory=ContextParts, title="Parts", description="The context's parts.")
    calls: CallKinds = Field(default_factory=CallKinds, title="Calls", description="The kinds of tool call.")
    boxes: FlowBoxes = Field(default_factory=FlowBoxes, title="Boxes", description="A flow's kinds of box.")


class StyleTitles(Element):
    """How a panel's title is set in its border."""

    align: Literal["left", "center", "right"] = Field("left", title="Align", description="Where the title stands.")
    style: Literal["bold", "plain"] = Field("bold", title="Weight", description="Bold, or plain.")


class StyleMarks(Element):
    """The glyphs that say a state, and the others a page draws for a meaning."""

    brand: Glyph = Field("◆", title="Brand", description="The header's mark before CLANK.")
    on: Glyph = Field("●", title="On", description="Something that runs, or a state's dot.")
    off: Glyph = Field("○", title="Off", description="Something that waits or is off.")
    done: Glyph = Field("✓", title="Done", description="Something done, or as wanted.")
    failed: Glyph = Field("✗", title="Failed", description="Something that failed.")
    asks: Glyph = Field("?", title="Asks", description="A question waiting.")
    event: Glyph = Field("·", title="Event", description="A line of history.")
    cut: Glyph = Field("…", title="Cut", description="The end of text Clank cut to fit.")
    note: Glyph = Field("✎", title="Note", description="A note of the owner's.")
    held: Glyph = Field("⏸", title="Held", description="Something held: a model request, while its session is paused.")


class StyleBar(Element):
    """A bar's glyphs."""

    full: Glyph = Field("█", title="Full cell", description="A bar's full cell.")
    eighths: Glyphs = Field(
        " ▏▎▍▌▋▊▉", min_length=8, max_length=8, title="Eighths", description="A cell filled from none to seven eighths."
    )
    empty: Glyph = Field("░", title="Empty cell", description="A bar's empty cell.")
    kept: Glyph = Field("▒", title="Kept", description="The room a bar keeps for something (the answer, design 0012).")


class StyleTree(Element):
    """The connectors a branching flow is drawn with (design 0012 §6.3)."""

    down: Glyph = Field("│", title="Down", description="A line down.")
    branch: Glyph = Field("├", title="Branch", description="A branch off a line down.")
    last: Glyph = Field("└", title="Last", description="The last branch.")
    across: Glyph = Field("─", title="Across", description="A line across.")
    split: Glyph = Field("┬", title="Split", description="Where a line splits.")
    split_end: Glyph = Field("╮", title="Split's end", description="The last arm of a split.")
    join: Glyph = Field("┴", title="Join", description="Where lines join.")
    join_end: Glyph = Field("╯", title="Join's end", description="The last arm of a join.")
    arrow: Glyph = Field("▸", title="Arrow", description="Where a line leads.")
    not_yet: Glyph = Field("┄", title="Not yet", description="A path not taken yet.")
    dead_end: Glyph = Field("⊘", title="Dead end", description="Where a path ends.")


class StyleSpacing(Element):
    """The room between things, in cells."""

    panel_padding: int = Field(1, ge=0, le=4, title="Panel padding", description="Columns inside a panel's border.")
    page_padding: int = Field(1, ge=0, le=4, title="Page padding", description="Columns around a page.")
    rows_between: int = Field(1, ge=0, le=4, title="Rows between", description="Rows between panels stacked.")
    columns_between: int = Field(2, ge=0, le=8, title="Columns between", description="Columns between panels.")


class StyleSettings(Settings):
    """A style of the console: every element of its look, by name (design 0011 §2)."""

    KIND = "style"
    LABEL = "Style"
    HELP = (
        "A style of the console: its colors by role, the colors it draws kinds in, its border, its titles, its marks, "
        "its bar and tree glyphs and its spacing; an element a style leaves out is Clank's own (design 0011 §2)."
    )
    FOLDER = "styles"

    dark: bool = Field(True, title="Dark", description="Whether the style is dark, for the widgets Textual draws.")
    colors: StyleColors = Field(
        default_factory=StyleColors, title="Colors", description="The colors by role, what each is for."
    )
    data: list[Color] = Field(
        default_factory=lambda: ["#7aa2f7", "#3d59a1", "#bb9af7", "#7dcfff", "#73daca", "#9d7cd8"],
        min_length=6,
        max_length=6,
        title="Data colors",
        description="Six colors in order, for the series of a chart; a sparkline takes the first.",
    )
    kinds: StyleKinds = Field(
        default_factory=StyleKinds, title="Kinds", description="The colors the Monitor and flows draw kinds in."
    )
    border: Literal["solid", "round"] = Field(
        "solid", title="Border", description="A panel's border: square corners, or round."
    )
    titles: StyleTitles = Field(default_factory=StyleTitles, title="Titles", description="A panel's title.")
    marks: StyleMarks = Field(default_factory=StyleMarks, title="Marks", description="The glyphs that say a state.")
    spinner: Glyphs = Field(
        "⣾⣽⣻⢿⡿⣟⣯⣷", min_length=2, title="Spinner", description="The spinner's frames, while something runs."
    )
    bar: StyleBar = Field(default_factory=StyleBar, title="Bar", description="A bar's glyphs.")
    sparks: Glyphs = Field(
        "▁▂▃▄▅▆▇█", min_length=2, title="Sparks", description="A sparkline's steps, from none to the most."
    )
    tree: StyleTree = Field(default_factory=StyleTree, title="Tree", description="A branching flow's connectors.")
    spacing: StyleSpacing = Field(default_factory=StyleSpacing, title="Spacing", description="The room between things.")


class ConsoleSettings(Settings):
    """How the console looks (design 0011 §3)."""

    KIND = "console"
    LABEL = "Console"
    HELP = "How the console looks: the style it draws in (design 0011)."
    SINGLE = True

    style: str = Field("clank", title="Style", description="The style the console draws in, by its file's name.")
