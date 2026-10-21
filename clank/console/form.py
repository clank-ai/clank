"""A form over the console: a title, fields to fill in, each with its label and an example, and a note (design 0001
§5.1). Tab and Enter move to the next field; Enter in the last one, or Ctrl+S anywhere, gives the values to the page
that asked; Esc gives nothing. The page checks the values and acts on them; the form only collects them. It is one
panel (design 0011 §7), its title in its border.

A secret field (`Field.secret`, a `SecretField`) takes a key typed or pasted (design 0016 §4, §14): it keeps what it is
given to itself and draws only dots, then `…` and the last four characters once there are enough of them (`hidden`), so
no frame, snapshot or log ever holds the key; it posts no message that carries it, copies nothing to the clipboard, and
every key typed into it stays in it (`q` is a letter of the key there, not quit). Esc clears it; taking its value to
send it (`take`) clears it too, so the page that sends it holds it only for the call.
"""

from dataclasses import dataclass
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Label

from clank.console.panel import WindowPanel

DOTS = 24  # the most dots a secret draws, so a long key never draws wider than its field
SHOWN_FROM = 8  # the least characters before the last four show: a short value shows as dots alone


def hidden(value: str) -> str:
    """A secret as its field draws it: a dot for each character, then `…` and its last four once it is long enough."""
    if len(value) < SHOWN_FROM:
        return "•" * len(value)
    return "•" * min(len(value) - 4, DOTS) + "…" + value[-4:]


class SecretField(Widget, can_focus=True):
    """A key, typed or pasted, never drawn: dots, then its last four (design 0016 §4)."""

    DEFAULT_CSS = """
    SecretField {
        height: 3;
        width: 1fr;
        border: tall $clank-border;
        padding: 0 1;
    }
    SecretField:focus {
        border: tall $clank-border-focused;
    }
    """

    class Submitted(Message):
        """Enter in the field: its value is ready to take (the message carries none of it)."""

        def __init__(self, field: "SecretField") -> None:
            super().__init__()
            self.field = field

    def __init__(self, placeholder: str = "", *, id: str | None = None, classes: str = "") -> None:
        super().__init__(id=id, classes=classes)
        self.placeholder = placeholder
        self._value = ""

    @property
    def filled(self) -> bool:
        """Whether it holds anything."""
        return bool(self._value)

    @property
    def ends(self) -> str:
        """Its last four characters, as it draws them; nothing while it is too short to show them."""
        return self._value[-4:] if len(self._value) >= SHOWN_FROM else ""

    def take(self) -> str:
        """Its value, to send; the field is cleared."""
        value, self._value = self._value, ""
        self.refresh()
        return value

    def clear(self) -> None:
        """Forget what it holds."""
        self._value = ""
        self.refresh()

    def render(self) -> Content:
        """Dots and the last four, or the placeholder while it is empty."""
        if not self._value:
            return Content.assemble((self.placeholder, "$clank-quiet"))
        return Content(hidden(self._value))

    async def on_event(self, event: events.Event) -> None:
        """A key typed or a paste is taken here, before Textual's handling, which logs each event it handles (with
        TEXTUAL_LOG, to a file): what the field takes is never logged. Every character typed is the key's; Enter says
        it is ready; Esc clears it and goes on to the window; Tab, the arrows and the F-keys are the console's."""
        if isinstance(event, events.Paste):
            self._value += "".join(event.text.split())  # a key has no whitespace; a paste may end with a new line
        elif not isinstance(event, events.Key) or not self._takes(event):
            await super().on_event(event)
            return
        event.stop()
        event.prevent_default()
        self.refresh()

    def _takes(self, event: events.Key) -> bool:
        """Act on a key the field takes; False for one it leaves to the console (Esc, once it cleared the field)."""
        if event.key == "escape":
            self.clear()
            return False
        if event.key == "enter":
            self.post_message(self.Submitted(self))
        elif event.key == "backspace":
            self._value = self._value[:-1]
        elif event.is_printable and event.character and not event.character.isspace():
            self._value += event.character
        elif not event.key.startswith("ctrl+"):  # Ctrl and a key: nothing copies, cuts or selects it
            return False
        return True


@dataclass(frozen=True)
class Field:
    """One field: its key in the values given back, its label, an example, and what it holds at first."""

    key: str
    label: str
    example: str = ""
    value: str = ""
    secret: bool = False  # a key: typed into a `SecretField`, never drawn


class FormScreen(ModalScreen[dict[str, str] | None]):
    """A title, its fields, and a note on what happens with them."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "close"),
        Binding("ctrl+s", "submit", "done"),
    ]

    def __init__(self, title: str, fields: list[Field], note: str = "") -> None:
        super().__init__()
        self.heading = title
        self.fields = fields
        self.note = note

    def compose(self) -> ComposeResult:
        """Each field under its label in a panel titled with the title, and the note."""
        fields: list[Widget] = []
        for field in self.fields:
            entry: Widget = (
                SecretField(field.example, id=f"form-{field.key}")
                if field.secret
                else Input(value=field.value, placeholder=field.example, id=f"form-{field.key}")
            )
            fields += [Label(field.label, classes="form-label"), entry]
        note = Label(self.note or "Enter in the last field, or Ctrl+S, is done; Esc closes this.", classes="hint")
        yield WindowPanel(*fields, note, title=self.heading, id="form")

    def on_mount(self) -> None:
        """The first field has the focus."""
        self.query_one(f"#form-{self.fields[0].key}").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter: the next field, or done in the last one."""
        self._next(event.input.id or "")

    def on_secret_field_submitted(self, event: SecretField.Submitted) -> None:
        """Enter in a secret field: the next field, or done in the last one."""
        self._next(event.field.id or "")

    def _next(self, id: str) -> None:
        keys = [f"form-{field.key}" for field in self.fields]
        position = keys.index(id)
        if position + 1 < len(keys):
            self.query_one(f"#{keys[position + 1]}").focus()
        else:
            self.action_submit()

    def action_submit(self) -> None:
        """Give the values back; a secret field's is taken, and the field cleared."""
        values = {}
        for field in self.fields:
            entry = self.query_one(f"#form-{field.key}")
            values[field.key] = entry.take() if isinstance(entry, SecretField) else entry_value(entry)
        self.dismiss(values)

    def action_cancel(self) -> None:
        """Esc: nothing; a secret field is cleared."""
        for entry in self.query(SecretField):
            entry.clear()
        self.dismiss(None)


def entry_value(entry: Widget) -> str:
    """What an input of the form holds, its ends' spaces removed."""
    return entry.value.strip() if isinstance(entry, Input) else ""
