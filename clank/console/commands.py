"""The command palette's commands (design 0001 §5.1: every action has a key and is in the palette, Ctrl+P): every page
by name, planned ones included; Docker's start and stop; the doctor; the console's style (design 0011 §3); and an
answer to each waiting question with each of its options. Typing narrows them down; Enter runs the highlighted one."""

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, cast

from textual.command import DiscoveryHit, Hit, Hits, Provider

from clank.console.pages.questions import answer

if TYPE_CHECKING:
    from clank.console.app import ClankConsole

Command = tuple[str, str, Callable[[], object]]


class ClankCommands(Provider):
    """Clank's commands, for the palette."""

    def commands(self) -> list[Command]:
        """Every command, with what it does."""
        console = cast("ClankConsole", self.app)
        found: list[Command] = []
        for entry in console.entries():
            coming = f" (coming in {entry.milestone})" if entry.planned else ""
            found.append((f"Open {entry.label}", entry.summary + coming, partial(console.show_page, entry.id)))
        found += [
            ("Start Docker", "Start Docker and wait until its engine answers.", partial(console.ask_docker, False)),
            (
                "Stop Docker",
                "Stop Docker and every container in it; asks first when containers Clank did not start run.",
                partial(console.ask_docker, True),
            ),
            ("Run the doctor", "Check this computer for what Clank needs; changes nothing.", console.run_doctor),
            (
                "Change style",
                "Pick the console's style: its colors and the marks that say a state.",
                console.pick_style,
            ),
        ]
        for question in console.data.questions:
            for option in question["options"]:
                key = option["key"] or option["id"]
                found.append(
                    (
                        f"Answer {question['title']} {option['label']}",
                        f"{question['id']}: {option['effect'] or option['label']}",
                        partial(answer, console, question, key),
                    )
                )
        return found

    async def discover(self) -> Hits:
        """Every command, before anything is typed."""
        for name, help, run in self.commands():
            yield DiscoveryHit(name, run, help=help)

    async def search(self, query: str) -> Hits:
        """The commands whose names match what is typed, best first."""
        matcher = self.matcher(query)
        for name, help, run in self.commands():
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), run, help=help)
