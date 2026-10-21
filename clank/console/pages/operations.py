"""The operations page: what runs in the service, step by step (design 0002 §2.4).

The newest operations, with their status and progress; the highlighted one shows its steps and its log below the
list, read again as it writes. `c` asks the highlighted operation to stop at its next check; `r` starts an interrupted
or failed one again, when that is safe. Both are refused, in the service's own words, when they cannot be done.
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.gauges import spinner
from clank.console.keys import PageKey
from clank.console.lists import refill
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import painted, time_of
from clank.kernel.events import Actor


def progress(operation: dict[str, Any]) -> str:
    """How far it is: "2 of 3: stop"."""
    steps = operation["steps"]
    if not steps:
        return f"0 of {operation['planned_steps']}"
    return f"{steps[-1]['number']} of {operation['planned_steps']}: {steps[-1]['name']}"


class OperationsPage(Page):
    """What runs in the service, step by step."""

    ENTRY = MenuEntry(
        "operations",
        "Operations",
        "What runs in the service, step by step, with its log; c cancels, r retries.",
        "design 0002 §2.4",
        key="6",
    )
    PANELS = ("operations-newest", "operations-steps")
    KEYS = (
        PageKey("c", "cancel", "cancel", "cancel the highlighted operation"),
        PageKey("r", "retry", "retry", "run the highlighted operation again"),
    )

    def badge(self, frame: int) -> Content | None:
        """A spinner while an operation runs, a question mark while one waits for an answer."""
        statuses = {operation["status"] for operation in self.console.data.operations}
        if "running" in statuses:
            return Content.assemble((spinner(frame), "$clank-now"))
        return Content.assemble((mark("asks"), "$clank-attention")) if "waiting" in statuses else None

    def compose(self) -> ComposeResult:
        """The newest operations, then the highlighted one's steps and log."""
        with Panel(title="The newest operations", id="operations-newest"):
            yield ListView(id="operations-list")
        with Panel(title="Steps and log", id="operations-steps"):
            yield Label(id="operation-detail")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the list again when the operations changed; read the highlighted one's log again as it writes."""
        if changed & {"all", "operations"}:
            listed = self.query_one("#operations-list", ListView)
            kept = self._selected()
            lines = [painted(self._line(operation), operation["status"]) for operation in data.operations]
            refill(listed, lines, [operation["id"] for operation in data.operations], kept["id"] if kept else None)
            self._read_log()
        elif "log" in changed and data.last_log is not None:
            selected = self._selected()
            if selected is not None and (data.last_log.get("subject") or {}).get("id") == selected["id"]:
                self._read_log()

    def press(self, key: str) -> bool:
        """`c` cancels the highlighted operation; `r` retries it."""
        selected = self._selected()
        if selected is None or key not in ("c", "r"):
            return False
        client, id = self.console.client, selected["id"]
        if key == "c":
            actions.call(self.console, lambda: client.post(f"operations/{id}/cancel"), done=f"asked {id} to stop")
        else:
            actions.call(self.console, lambda: client.post(f"operations/{id}/retry"), done=f"started {id} again")
        return True

    def explain(self) -> tuple[str, list[str]]:
        """What the highlighted operation is, and what can be done with it."""
        selected = self._selected()
        if selected is None:
            return super().explain()
        return f"{selected['title']} ({selected['id']})", [
            f"Its kind: {selected['type']}; {selected['status']}, {progress(selected)}.",
            "Operations run in the service, never in a client: closing the console stops nothing, and every client "
            "sees the same progress.",
            "c asks it to stop at its next check; r runs an interrupted or failed one again when its steps are safe to "
            "repeat (design 0002 §2.4).",
        ]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted operation's steps and log."""
        if event.list_view.id == "operations-list":
            self._read_log()

    def _line(self, operation: dict[str, Any]) -> str:
        who = Actor.model_validate(operation["started_by"]).describe()
        created = time_of(operation["created"], self.console.zone)
        return (
            f"{operation['id']}  {operation['title']:<18}  {operation['status']:<11}  {progress(operation):<18}  "
            f"{created} by {who}"
        )

    def _selected(self) -> dict[str, Any] | None:
        operations = self.console.data.operations
        index = self.query_one("#operations-list", ListView).index
        if index is None or not 0 <= index < len(operations):
            return operations[0] if operations else None
        return operations[index]

    def _read_log(self) -> None:
        selected = self._selected()
        if selected is None:
            self.query_one("#operation-detail", Label).update("No operation yet.")
            return
        id, client = selected["id"], self.console.client

        def work() -> None:
            try:
                lines = client.get(f"operations/{id}/log")
            except Exception:
                return
            self.console.call_from_thread(self._show, id, lines)

        self.run_worker(work, thread=True, group="operation-log", exit_on_error=False)

    def _show(self, id: str, lines: list[dict[str, Any]]) -> None:
        selected = self._selected()
        if selected is None or selected["id"] != id:
            return
        shown: list[str | Content] = [
            f"{selected['title']} ({id}): {selected['status']}"
            + (f": {selected['error']}" if selected["error"] else "")
        ]
        by_step: dict[int | None, list[str]] = {}
        for line in lines:
            by_step.setdefault(line["step"], []).append(line["text"])
        shown += [f"    {text}" for text in by_step.get(None, [])]
        for step in selected["steps"]:
            told = f"  {step['number']} of {selected['planned_steps']}: {step['name']}  {step['status']}"
            shown.append(painted(told, f"  {step['status']}"[2:]))
            shown += [f"    {text}" for text in by_step.get(step["number"], [])]
        first = shown[0] if isinstance(shown[0], Content) else painted(shown[0], selected["status"])
        drawn = [first, *(each if isinstance(each, Content) else Content(each) for each in shown[1:])]
        self.query_one("#operation-detail", Label).update(Content("\n").join(drawn))
