"""Design 0011 §2 (the style: a file of named elements) and §3 (the console's setting that picks it): Clank's own style
holds the boards' values; an owner's style that names a few elements keeps every other element of Clank's; a color that
is not #rrggbb, a glyph two cells wide, and a bar's eighths that are not eight glyphs, are refused, naming the field;
the console's setting picks `clank` until it is changed."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from clank.kernel.console_kinds import ConsoleSettings, StyleSettings
from clank.kernel.settings import DEFAULTS


def clanks() -> StyleSettings:
    """Clank's own style, as its file holds it (its schema line set apart, as the settings files do)."""
    data: dict[str, Any] = json.loads((DEFAULTS / "styles" / "clank.json").read_text(encoding="utf-8"))
    assert data.pop("schema") == "style/1"
    return StyleSettings.model_validate(data)


def test_clanks_own_style_holds_the_boards_values() -> None:
    style = clanks()
    assert style.title == "Clank"
    assert (style.colors.background, style.colors.bars, style.colors.border) == ("#1a1b26", "#16161e", "#3b4261")
    assert (style.colors.title, style.colors.text, style.colors.quiet) == ("#7aa2f7", "#c0caf5", "#828bb8")
    assert (style.colors.selection, style.colors.good, style.colors.failed) == ("#283457", "#9ece6a", "#f7768e")
    assert (style.colors.planned, style.colors.border_focused, style.colors.now) == ("#f7768e", "#7aa2f7", "#ff9e64")
    assert style.data == ["#7aa2f7", "#3d59a1", "#bb9af7", "#7dcfff", "#73daca", "#9d7cd8"]
    assert (style.kinds.boxes.verify, style.kinds.parts.results, style.kinds.calls.mcp) == (
        "#bb9af7",
        "#9ece6a",
        "#9d7cd8",
    )
    assert (style.marks.on, style.marks.done, style.marks.failed, style.marks.note) == ("●", "✓", "✗", "✎")
    assert (style.border, style.titles.align, style.titles.style) == ("solid", "left", "bold")
    assert (style.bar.full, style.bar.empty, style.bar.kept) == ("█", "░", "▒")
    assert (style.tree.branch, style.tree.last, style.tree.dead_end) == ("├", "└", "⊘")
    assert style.spacing.panel_padding == 1


def test_an_owners_style_naming_a_few_elements_keeps_every_other_of_clanks() -> None:
    owners = StyleSettings.model_validate({"title": "Mine", "colors": {"quiet": "#999999", "good": "#00aa00"}})
    assert (owners.colors.quiet, owners.colors.good) == ("#999999", "#00aa00")
    assert owners.colors.border == clanks().colors.border
    assert owners.marks == clanks().marks


def test_a_color_that_is_not_rrggbb_is_refused_naming_its_field() -> None:
    with pytest.raises(ValidationError) as refused:
        StyleSettings.model_validate({"colors": {"good": "#12345"}})
    assert refused.value.errors()[0]["loc"] == ("colors", "good")


def test_a_glyph_two_cells_wide_is_refused_naming_its_field() -> None:
    with pytest.raises(ValidationError) as refused:
        StyleSettings.model_validate({"marks": {"on": "全"}})
    assert refused.value.errors()[0]["loc"] == ("marks", "on")


def test_a_bars_eighths_that_are_not_eight_glyphs_are_refused_naming_their_field() -> None:
    with pytest.raises(ValidationError) as refused:
        StyleSettings.model_validate({"bar": {"eighths": " ▎▌▊"}})
    assert refused.value.errors()[0]["loc"] == ("bar", "eighths")


def test_the_consoles_setting_picks_clank_until_it_is_changed() -> None:
    assert ConsoleSettings().style == "clank"
    assert ConsoleSettings.model_validate({"style": "mine"}).style == "mine"
