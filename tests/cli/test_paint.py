"""Design 0028 §4: color in the terminal, for the commands that print for people. Each kind of word has its color and
the words never depend on it: a checklist in color is, its color taken away, the checklist without; commands are bold,
even across a line's end; `NO_COLOR` drops every color."""

import click
import pytest

from clank.cli.paint import commands, paint
from clank.components.agents.setupcli import render

FOUND = {
    "items": [
        {"id": "docker_installed", "title": "Docker installed", "state": "done", "required": True,
         "said": "Docker Engine 28.0.4", "fix": None},
        {"id": "service", "title": "Clank's service", "state": "to do", "required": True, "said": "not running",
         "fix": {"said": "start it: `clank serve --background`", "does": "service"}},
        {"id": "vscode", "title": "Clank's VS Code window", "state": "to do", "required": False,
         "said": "VS Code is not installed", "fix": {"said": "install VS Code", "does": ""}},
    ],
    "ready": False,
    "said": "Not ready: 1 thing is left to do.",
}  # fmt: skip


def test_a_checklist_in_color_is_the_checklist_without_its_color_taken_away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    colored = render(FOUND, 120, colored=True)
    assert [click.unstyle(line) for line in colored] == render(FOUND, 120)
    assert click.style("✓ done      ", fg="green", bold=True) in colored[2]
    assert click.style("• to do     ", fg="yellow", bold=True) in colored[3]
    assert click.style("`clank serve --background`", bold=True) in "".join(colored)
    assert click.style("○ optional  ", fg="blue", bold=True) in "".join(colored)


def test_commands_are_bold_even_across_a_lines_end_and_no_color_drops_every_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    lines = commands(["run `sudo systemctl", "start docker` then"])
    assert lines == [
        "run " + click.style("`sudo systemctl", bold=True),
        click.style("start docker`", bold=True) + " then",
    ]
    monkeypatch.setenv("NO_COLOR", "1")
    assert paint("done", "good") == "done"
    assert commands(["run `it`"]) == ["run `it`"]
