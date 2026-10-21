"""The records page: every record of every kind, through the same routes (design 0002 §2.2).

Three lists, top to bottom: the kinds (settings, which the user decides, and state, which Clank keeps), the records of
the highlighted kind, and the highlighted record's values, each with its field's title. A record is read when it is
highlighted (once: highlighting what is already shown reads nothing), and again when an event says a record of its kind
changed, keeping what was highlighted. `?` on a value explains it: what it is, its
value, where it comes from, the file that holds it (or would), when a change applies (as its kind says: at once, or at
whose next start), and where its kind is defined (design 0001 §5.4). Settings change in their files, through `clank
records` or the API; a form to change them here comes with the first screen that needs one.
"""

import json
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Label, ListItem, ListView

from clank.console.data import ConsoleData
from clank.console.gauges import fit
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel

SOURCES = {
    "built-in": "Clank's built-in values: there is no file yet",
    "default": "Clank's own file of defaults, shipped with Clank",
    "user": "your file",
}


class RecordsPage(Page):
    """Every record of every kind."""

    ENTRY = MenuEntry(
        "records",
        "Records",
        "Every record of every kind, with what each value is and where it is kept; ? explains a value.",
        "design 0002 §2.2",
        key="7",
    )
    PANELS = ("records-kinds-panel", "records-records", "records-values")

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._kind: dict[str, Any] | None = None
        self._records: list[dict[str, Any]] = []
        self._record: dict[str, Any] | None = None
        self._wanted_kind: str | None = None
        self._wanted_record: str | None = None
        self._seen = 0

    def compose(self) -> ComposeResult:
        """The kinds, a kind's records, a record's values."""
        with Panel(title="Kinds", id="records-kinds-panel"):
            yield ListView(id="records-kinds")
        with Panel(title="Records", id="records-records"):
            yield ListView(id="records-list")
        with Panel(title="Values", id="records-values"):
            yield Label(id="records-record")
            yield ListView(id="records-fields")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """List the kinds; read the shown kind's records again when an event says one changed."""
        listed = self.query_one("#records-kinds", ListView)
        if "all" in changed and len(listed.children) != len(data.kinds):
            listed.clear()
            for kind in data.kinds:
                listed.append(ListItem(Label(f"{kind['kind']:<12} {kind['sort']:<9} {kind['help']}")))
        if "history" in changed and self._kind is not None:
            fresh = [event for event in data.history if event["id"] > self._seen]
            if any((event.get("subject") or {}).get("kind") == self._kind["kind"] for event in fresh):
                self._read_records(self._kind, again=True)
        self._seen = data.last_event

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Read the highlighted kind's records, or the highlighted record."""
        index = event.list_view.index
        if index is None:
            return
        if event.list_view.id == "records-kinds" and 0 <= index < len(self.console.data.kinds):
            self._read_records(self.console.data.kinds[index])
        elif event.list_view.id == "records-list" and 0 <= index < len(self._records):
            self._read_record(self._records[index])

    def explain(self) -> tuple[str, list[str]]:
        """The highlighted value, record or kind."""
        focused = self.console.focused
        fields = self.query_one("#records-fields", ListView)
        if focused is fields and self._kind is not None and self._record is not None and fields.index is not None:
            names = list(self._record["values"])
            if 0 <= fields.index < len(names):
                return self._explain_field(self._kind, self._record, names[fields.index])
        if self._kind is not None:
            kind = self._kind
            lines = [kind["help"], f"Sort: {kind['sort']}."]
            if kind["sort"] == "settings":
                lines.append(f"A change applies {kind['applies']}.")
            lines += [f"Defined in {kind['defined_in']}.", "Design 0002 §2.2 says what records are."]
            return f"{kind['label']} ({kind['kind']})", lines
        return super().explain()

    def _read_records(self, kind: dict[str, Any], again: bool = False) -> None:
        if kind["kind"] == self._wanted_kind and not again:
            return
        if kind["kind"] != self._wanted_kind:
            self._wanted_record = None
        self._kind, self._wanted_kind = kind, kind["kind"]
        client, name = self.console.client, kind["kind"]

        def work() -> None:
            try:
                records = client.get(f"records/{name}")
            except Exception:
                return
            self.console.call_from_thread(self._show_records, name, records, again)

        self.run_worker(work, thread=True, group="records", exit_on_error=False)

    def _show_records(self, name: str, records: list[dict[str, Any]], again: bool) -> None:
        if name != self._wanted_kind:
            return
        self._records = records
        listed = self.query_one("#records-list", ListView)
        listed.clear()
        for record in records:
            source = f"  ({record['source']})" if "source" in record else ""
            listed.append(ListItem(Label(f"{record['id']}  {record['title']}{source}")))
        if not records:
            self._record, self._wanted_record = None, None
            self.query_one("#records-record", Label).update(f"No {name} record yet.")
            self.query_one("#records-fields", ListView).clear()
            return
        ids = [record["id"] for record in records]
        index = ids.index(self._wanted_record) if self._wanted_record in ids else 0
        listed.index = index
        self._read_record(records[index], again=again)

    def _read_record(self, record: dict[str, Any], again: bool = False) -> None:
        if record["id"] == self._wanted_record and not again:
            return
        self._wanted_record = record["id"]
        client, name, id = self.console.client, record["kind"], record["id"]

        def work() -> None:
            try:
                found = client.get(f"records/{name}/{id}")
            except Exception:
                return
            self.console.call_from_thread(self._show_record, found)

        self.run_worker(work, thread=True, group="record", exit_on_error=False)

    def _show_record(self, record: dict[str, Any]) -> None:
        if self._kind is None or record["kind"] != self._wanted_kind or record["id"] != self._wanted_record:
            return
        fields = self.query_one("#records-fields", ListView)
        before = self._record
        kept = None
        if before is not None and before["id"] == record["id"] and fields.index is not None:
            names = list(before["values"])
            kept = names[fields.index] if 0 <= fields.index < len(names) else None
        self._record = record
        if "source" in record:
            where = record["file"] or f"no file yet; yours would be {self._shown_path(record['user_file'])}"
            head = f"{record['kind']} {record['id']} · {record['source']} · {where}"
        else:
            head = f"{record['kind']} {record['id']} · state, kept by the service"
        self.query_one("#records-record", Label).update(head)
        fields.clear()
        properties = self._kind["schema"].get("properties", {})
        for name, value in record["values"].items():
            shown = json.dumps(value)
            shown = fit(shown, 48)
            title = properties.get(name, {}).get("title", "")
            fields.append(ListItem(Label(f"{name:<18} {shown:<50} {title}")))
        names = list(record["values"])
        if kept in names:
            fields.index = names.index(kept)

    def _explain_field(self, kind: dict[str, Any], record: dict[str, Any], name: str) -> tuple[str, list[str]]:
        field = kind["schema"].get("properties", {}).get(name, {})
        lines = [field.get("description", ""), f"Value: {json.dumps(record['values'][name])}"]
        if "default" in field:
            lines.append(f"Default: {json.dumps(field['default'])}")
        if "source" in record:
            lines.append(f"From: {SOURCES.get(record['source'], record['source'])}.")
            if record["file"]:
                lines.append(f"Kept in: {self._shown_path(record['file'])}")
            else:
                lines.append(f"Kept in: nowhere yet; a file of yours, {self._shown_path(record['user_file'])}, would")
                lines.append("replace Clank's values (only the values that differ need to be in it).")
            lines.append(f"A change applies {kind['applies']}.")
            lines.append(f"Its schema: clank/schemas/{kind['kind']}.schema.json")
        else:
            lines.append("State: kept by the service in its database; it changes only through its own actions.")
        lines.append(f"Defined in: {kind['defined_in']}")
        lines.append("Design 0002 §2.2 (records); design 0001 §5.4 (explain).")
        return f"{kind['kind']} · {name}: {field.get('title', name)}", [line for line in lines if line]

    def _shown_path(self, path: str) -> str:
        root = str(self.console.home.root)
        return "CLANK_HOME" + path[len(root) :].replace("\\", "/") if path.startswith(root) else path
