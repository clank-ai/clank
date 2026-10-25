"""Every number answered (design 0020 §12): after a numbered message to the agent (comments on the LaTeX source, marks
on a PDF's page), Clank reads the agent's reply once its turn ends and asks once more for each number it left
unanswered, in one message; never a second time.

`answered` reads the numbers a reply answers, in the forms models write them: a line that starts with a number ("2.",
"**3**:", "- 4)"), which answers whatever was asked, or a number named with its kind anywhere ("Comment 1", "mark #4").
`Answers` follows the sessions' lines (`Sessions.listen`): a session waiting for answers whose status goes busy and
then idle has ended its turn; its messages are read (the agent's after the owner's message, found by its first line),
and the missing numbers asked for.
"""

import re
import threading
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.agents.sessions import Sessions

ASKER = Actor(kind="clank", via="every number answered")
LEADING = re.compile(r"^\s*(?:[-*>]\s*)?(?:\*\*)?(\d{1,3})(?:\*\*)?\s*[.:)\-\u2013\u2014]", re.M)  # - and dashes
NAMED = re.compile(r"\b(mark|comment)s?\s*#?(\d{1,3})\b", re.I)


@dataclass
class Expected:
    """A numbered message waiting for its answers: where it went, what its numbers are, how it begins."""

    workspace: str
    port: int
    session: str
    kind: str  # mark or comment
    numbers: list[int]
    head: str  # its first line, to find it among the session's messages
    busy: bool = False  # the agent's turn began
    asked_again: bool = False
    missing: list[int] = field(default_factory=list)


def answered(reply: str, kind: str) -> set[int]:
    """The numbers a reply answers, for a message of marks or comments."""
    found = {int(match.group(1)) for match in LEADING.finditer(reply)}
    found |= {int(match.group(2)) for match in NAMED.finditer(reply) if match.group(1).lower() == kind}
    return found


def reminder(kind: str, missing: list[int]) -> str:
    """What the agent is told of the numbers it left unanswered."""
    named = f"{kind}s" if len(missing) > 1 else kind
    listed = ", ".join(str(each) for each in missing[:-1]) + (" and " if len(missing) > 1 else "") + str(missing[-1])
    return (
        f"You did not answer {named} {listed} of my message: answer each by its number, what you changed and on which "
        "lines, or why you did not."
    )


class Answers:
    """The numbered messages waiting for their answers, checked when the agent's turn ends."""

    def __init__(self, sessions: "Sessions", *, wait: bool = True) -> None:
        self.sessions = sessions
        self.wait = wait  # check off the watcher's thread (False: at once, for the tests)
        self._waiting: dict[tuple[str, str], Expected] = {}
        self._lock = threading.Lock()
        sessions.listen(self.heard)

    def expect(self, workspace: str, port: int, session: str, kind: str, numbers: list[int], head: str) -> None:
        """A numbered message just sent: its answers are checked when the agent's turn ends."""
        if numbers:
            with self._lock:
                self._waiting[(workspace, session)] = Expected(workspace, port, session, kind, sorted(numbers), head)

    def waiting(self) -> list[dict[str, Any]]:
        """The messages waiting for their answers."""
        with self._lock:
            return [asdict(each) for each in self._waiting.values()]

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A watcher's line: a waiting session's turn began, or ended."""
        if line.get("type") != "status":
            return
        key = (workspace, str(line.get("session") or ""))
        with self._lock:
            expected = self._waiting.get(key)
            if expected is None:
                return
            if line.get("status") != "idle":
                expected.busy = True
                return
            if not expected.busy:
                return  # an idle before the turn began
            if expected.asked_again:
                self._waiting.pop(key, None)
                return
            expected.busy = False
        if self.wait:
            threading.Thread(target=self._check, args=(key, expected), name="answers", daemon=True).start()
        else:
            self._check(key, expected)

    def _check(self, key: tuple[str, str], expected: Expected) -> None:
        try:
            found = self.sessions.messages(expected.workspace, expected.port, expected.session, 20)["messages"]
        except Exception:  # noqa: BLE001: a session that cannot be read is not asked again
            with self._lock:
                self._waiting.pop(key, None)
            return
        start = max((index for index, message in enumerate(found) if message.get("role") == "user"
                     and _text(message).startswith(expected.head)), default=-1)  # fmt: skip
        reply = "\n".join(_text(message) for message in found[start + 1 :] if message.get("role") == "assistant")
        missing = [number for number in expected.numbers if number not in answered(reply, expected.kind)]
        with self._lock:
            if not missing:
                self._waiting.pop(key, None)
                return
            expected.asked_again, expected.missing = True, missing
        self.sessions.send(expected.workspace, expected.port, expected.session, reminder(expected.kind, missing),
                           actor=ASKER)  # fmt: skip


def _text(message: dict[str, Any]) -> str:
    return "\n".join(str(part.get("text") or "") for part in message.get("parts") or [] if part.get("type") == "text")
