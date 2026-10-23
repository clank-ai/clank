"""The console's style (design 0011 §2-§3): read before the first frame, and loaded into a Textual theme.

The console reads `CLANK_HOME/config/console.json` for the style's name (`clank` when there is none), then that style's
file: the owner's `config/styles/<name>.json`, else Clank's own in `clank/defaults/styles/`. An element a style leaves
out is Clank's own (the kind's defaults are Clank's style). A style that is not found gives Clank's own style, and a
file that does not read leaves the style in force (Clank's own at start); `problem` says why, with the file, line and
field, for the message line: the console always starts. It reads the files itself (`read_record`, as the service reads
every settings file), so that it draws in its style before the service answers, and reads them again when the service
reports a change of either (`ClankConsole.restyle`).

`theme_of` makes the Textual theme: Textual's base colors from the style's roles, so Textual's own widgets (the command
palette, inputs, scroll bars) match, and every element as a variable the style sheet and the drawing helpers name:
`$clank-<role>` for the colors by role, `$clank-data-1` to `-6`, `$clank-part-<kind>`, `$clank-call-<kind>` and
`$clank-box-<kind>` for the kinds, `$clank-border-kind` for the panels' border, `$clank-title-align` for their titles,
and `$clank-panel-padding`, `$clank-page-padding`, `$clank-rows-between` and `$clank-columns-between` for the room
between things, in cells. `current()` is the style in force,
for the helpers that draw glyphs (`mark`).

`forget_theme` is the console's one migration (design 0011 §3): an earlier console kept a Textual theme in
`CLANK_HOME/state/console.json`, saved by itself as tokyo-night unless the owner picked another; the entry is removed
once, and a theme the owner had picked is returned, for the message line to name once.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from textual.theme import Theme

from clank.kernel.console_kinds import ConsoleSettings, StyleSettings
from clank.kernel.home import Home
from clank.kernel.records import Settings
from clank.kernel.settings import DEFAULTS, SettingsProblem, read_record

CLANK = "clank"
CLANKS_USED = "Clank's style is used"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # a style's file name: no folder, no dot


@dataclass(frozen=True)
class LoadedStyle:
    """The style in force: its name, its elements, and why it is Clank's own when another was asked for ("" else)."""

    name: str
    style: StyleSettings
    problem: str = ""


_current = StyleSettings()


def current() -> StyleSettings:
    """The style in force."""
    return _current


def use(loaded: LoadedStyle) -> None:
    """Make a loaded style the one in force, for the drawing helpers."""
    global _current
    _current = loaded.style


def mark(name: str) -> str:
    """A mark of the style in force, by its name (`on`, `done`, `failed`, ...)."""
    return str(getattr(_current.marks, name))


def console_settings(home: Home) -> ConsoleSettings:
    """The console's settings as its file says them; the defaults when there is none, or it does not read."""
    found = _read(ConsoleSettings, home.config / "console.json") if (home.config / "console.json").is_file() else None
    return found if isinstance(found, ConsoleSettings) else ConsoleSettings()


def load_style(home: Home, last: LoadedStyle | None = None) -> LoadedStyle:
    """The style the console's settings pick, read from its file. A file that does not read leaves `last` in force
    (Clank's own at start), a style that is not found gives Clank's own; `problem` says why."""
    kept = (last.name, last.style, "the style in force stays") if last else (CLANK, StyleSettings(), CLANKS_USED)
    console = home.config / "console.json"
    name = CLANK
    if console.is_file():
        found = _read(ConsoleSettings, console)
        if isinstance(found, str):
            return LoadedStyle(kept[0], kept[1], f"{found}; {kept[2]}")
        assert isinstance(found, ConsoleSettings)
        name = found.style
    if not NAME.match(name):
        return LoadedStyle(CLANK, StyleSettings(), f"the style {name!r} is not a file's name; {CLANKS_USED}")
    for folder in (home.config / StyleSettings.folder(), DEFAULTS / StyleSettings.folder()):
        path = folder / f"{name}.json"
        if path.is_file():
            style = _read(StyleSettings, path)
            if isinstance(style, str):
                return LoadedStyle(kept[0], kept[1], f"{style}; {kept[2]}")
            assert isinstance(style, StyleSettings)
            return LoadedStyle(name, style)
    where = home.config / StyleSettings.folder() / f"{name}.json"
    return LoadedStyle(CLANK, StyleSettings(), f"the style {name} was not found ({where}); {CLANKS_USED}")


def theme_of(loaded: LoadedStyle) -> Theme:
    """The Textual theme of a style: its base colors from the roles, and every element as a variable."""
    style = loaded.style
    colors = style.colors
    variables = {f"clank-{name.replace('_', '-')}": value for name, value in colors.model_dump().items()}
    variables |= {f"clank-data-{index}": value for index, value in enumerate(style.data, start=1)}
    for group, prefix in (("parts", "part"), ("calls", "call"), ("boxes", "box")):
        kinds = getattr(style.kinds, group).model_dump()
        variables |= {f"clank-{prefix}-{name}": value for name, value in kinds.items()}
    variables |= {
        "clank-border-kind": style.border,
        "clank-title-align": style.titles.align,
        "clank-panel-padding": str(style.spacing.panel_padding),
        "clank-page-padding": str(style.spacing.page_padding),
        "clank-rows-between": str(style.spacing.rows_between),
        "clank-columns-between": str(style.spacing.columns_between),
    }
    variables |= {
        "text-muted": colors.quiet,
        "foreground-muted": colors.quiet,
        "border": colors.border_focused,
        "border-blurred": colors.border,
        "block-cursor-background": colors.selection,
        "block-cursor-foreground": colors.selected_text,
        "block-cursor-blurred-background": colors.selection,
        "block-cursor-blurred-foreground": colors.text,
        "footer-background": colors.bars,
        "footer-key-foreground": colors.key,
        "footer-description-foreground": colors.quiet,
        "scrollbar": colors.scrollbar,
        "scrollbar-background": colors.scrollbar_track,
        "scrollbar-corner-color": colors.scrollbar_track,
    }
    return Theme(
        name=loaded.name,
        primary=colors.brand,
        secondary=colors.title,
        accent=colors.now,
        warning=colors.attention,
        error=colors.failed,
        success=colors.good,
        foreground=colors.text,
        background=colors.background,
        surface=colors.surface,
        panel=colors.bars,
        dark=style.dark,
        variables=variables,
    )


def forget_theme(home: Home) -> str | None:
    """Remove the theme an earlier console remembered (the file too, when nothing else is in it); returns it when the
    owner had picked it, None for tokyo-night, saved by the console itself, for none, or when the file cannot be read or
    written (so that it is never named twice)."""
    path = home.state / "console.json"
    try:
        remembered = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(remembered, dict) or "theme" not in remembered:
            return None
        theme = str(remembered.pop("theme"))
        if remembered:
            path.write_text(json.dumps(remembered) + "\n", encoding="utf-8", newline="\n")
        else:
            path.unlink()
    except (OSError, ValueError):
        return None
    return None if theme == "tokyo-night" else theme


def _read(kind: type[Settings], path: Path) -> "Settings | str":
    """A settings file's record, or what is wrong with it, in the settings files' own words."""
    found = read_record(kind, path)
    if isinstance(found, list):
        problem: SettingsProblem = found[0]
        return str(problem)
    return found[0]
