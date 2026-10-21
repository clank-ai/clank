"""The questions page: every question waiting for the user (design 0002 §2.5).

Each shows its title, who asked it and when, its detail, and its options with their keys. The highlighted one is
answered with an option's key (Tab moves into the list; a digit there answers a numbered option instead of opening a
page), and `v` shows it whole. The answer is recorded as you (console); a question answered anywhere else leaves the
list as soon as the event stream says so. `question_lines` and `answer` are shared with the home page.
"""

from datetime import tzinfo
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListItem, ListView

from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.details import DetailsScreen
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import time_of
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.console.app import ClankConsole


def question_lines(question: dict[str, Any], zone: tzinfo | None) -> list[str]:
    """A question as the console shows it: its title and who asked it when, its detail, and its options' keys."""
    asked = f"asked {time_of(question['asked'], zone)} by {Actor.model_validate(question['asked_by']).describe()}"
    lines = [f"{question['id']}  {question['title']}   {asked}"]
    if question["detail"]:
        lines.append(question["detail"])
    options = [f"{option['key'] or option['id']} {option['label']}" for option in question["options"]]
    lines.append("   ".join([*options, "v details"]))
    return lines


def answer(console: "ClankConsole", question: dict[str, Any], key: str) -> bool:
    """Answer a question with the option this key chooses; False when no option has this key. An option that takes a
    typed answer (its `asks`: a number, its unit and its bounds, as the service says, design 0016 §11) asks for it in
    one field first, the answer's text holding it; the service checks it."""
    chosen = next((option for option in question["options"] if key and key in (option["key"], option["id"])), None)
    if chosen is None:
        return False
    if chosen.get("asks"):
        typed(console, question, chosen)
        return True
    client = console.client
    actions.call(
        console,
        lambda: client.post(f"questions/{question['id']}/answer", {"option": chosen["id"]}),
        done=f"answered {question['id']}: {chosen['label']}",
    )
    return True


def typed(console: "ClankConsole", question: dict[str, Any], option: dict[str, Any]) -> None:
    """An option's typed answer, in one field labeled with what the service says it takes, then the answer."""
    from clank.console.form import Field, FormScreen

    asks = option["asks"]
    bounds = f"{asks['min']:g} to {asks['max']:g}" if "min" in asks and "max" in asks else ""
    unit = ", ".join(part for part in (str(asks.get("unit") or ""), bounds) if part)
    label = f"{asks.get('said') or option['label']}" + (f" ({unit})" if unit else "")
    client = console.client

    def given(values: dict[str, str] | None) -> None:
        if values is None:
            return
        body = {"option": option["id"], "text": values["text"]}
        actions.call(
            console,
            lambda: client.post(f"questions/{question['id']}/answer", body),
            done=f"answered {question['id']}: {option['label']}, {values['text']}",
        )

    console.push_screen(FormScreen(question["title"], [Field("text", label, str(asks.get("min", "")))]), given)


def details(console: "ClankConsole", question: dict[str, Any]) -> None:
    """Show a question whole, over the console."""
    options = [
        f"{option['key'] or option['id']}  {option['label']}" + (f": {option['effect']}" if option["effect"] else "")
        for option in question["options"]
    ]
    default = f"If nobody answers in time: {question['default']}." if question.get("default") else ""
    lines = [*question_lines(question, console.zone)[1:-1], "", *options, *([default] if default else [])]
    # Opened once the key that asked for it is handled: the window's own keys (v closes it) must not take that key too.
    console.call_later(console.push_screen, DetailsScreen(question["title"], lines))


def waiting_badge(waiting: int) -> Content | None:
    """The questions waiting, as the menu shows them."""
    return Content.assemble((f"{mark('on')} {waiting}", "$clank-attention")) if waiting else None


WAITING = "Waiting for your answer"  # the list's title, with how many wait


class QuestionsPage(Page):
    """Every question waiting for the user."""

    ENTRY = MenuEntry(
        "questions",
        "Questions",
        "Every question waiting for your answer, with its options.",
        "design 0002 §2.5",
        key="2",
    )
    PANELS = ("questions-waiting",)
    KEYS = (
        PageKey("y n …", "answer", "answer it with an option's key", "answer the highlighted question with one of its "
                "options' keys (Right or Tab into the list first for numbered ones)"),
        PageKey("v", "question", "the question whole"),
    )  # fmt: skip

    def badge(self, frame: int) -> Content | None:
        """How many questions wait."""
        return waiting_badge(len(self.console.data.questions))

    def compose(self) -> ComposeResult:
        """A line when nothing waits, and the list of what does."""
        with Panel(title=WAITING, id="questions-waiting"):
            yield Label("No question waits for you.", id="questions-none")
            yield ListView(id="questions-list")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the list again when the questions changed, keeping the highlighted one."""
        if "all" not in changed and "questions" not in changed:
            return
        listed = self.query_one("#questions-list", ListView)
        kept = self._highlighted(data)
        listed.clear()
        for question in data.questions:
            lines = question_lines(question, self.console.zone)
            listed.append(ListItem(*(Label(line) for line in lines)))
        self.query_one("#questions-none", Label).display = not data.questions
        count = f" · {len(data.questions)}" if data.questions else ""
        self.query_one("#questions-waiting", Panel).title = WAITING + count
        ids = [question["id"] for question in data.questions]
        if kept in ids:
            listed.index = ids.index(kept)

    def press(self, key: str) -> bool:
        """Answer the highlighted question with an option's key, or show it whole (`v`)."""
        question = self._highlighted_question()
        if question is None:
            return False
        if key == "v":
            details(self.console, question)
            return True
        return answer(self.console, question, key)

    def explain(self) -> tuple[str, list[str]]:
        """Why the highlighted question is asked, and how it can be answered."""
        question = self._highlighted_question()
        if question is None:
            return super().explain()
        lines = question_lines(question, self.console.zone)[:-1]
        chosen = {option["id"]: option["label"] for option in question["options"]}
        if question.get("default"):
            lines.append(
                f"If nobody answers in time, Clank takes: {chosen.get(question['default'], question['default'])}."
            )
        if question["asked_by"].get("via") == "docker.stop":
            lines.append(
                "Clank stops only what it started: stopping Docker stops every container in it, so it asks first "
                "when containers it did not start run (design 0001 §4.6, design 0002 §3.2)."
            )
        lines.append(
            "Answer with an option's key here, in VS Code, or with `clank questions answer`; the first answer counts, "
            "and every client shows who gave it (design 0002 §2.5)."
        )
        return question["title"], lines

    def _highlighted_question(self) -> dict[str, Any] | None:
        questions = self.console.data.questions
        index = self.query_one("#questions-list", ListView).index
        if index is None or not 0 <= index < len(questions):
            return questions[0] if questions else None
        return questions[index]

    def _highlighted(self, data: ConsoleData) -> str | None:
        question = self._highlighted_question()
        return question["id"] if question else None
