"""The mirror (design 0023 §2, decision 0139): the conversations the service holds for the sessions clients follow,
so a read never reaches the container.

`Mirror.heard` takes the watchers' lines, as `Sessions.listen` hands them on: a `session` line names a session of the
workspace (its title, parent and times, the port of the server that runs it), a `status` line its status, and for a
followed session a `message` line a message's info, a `part` line a part whole (the watch says them whole for followed
sessions), a `delta` line text appended to a part as it is written, a `removed` line a message or a part taken back;
`asked`, `replied`, `question` and `answered` keep the permissions and questions open. A session is followed from
`follow` until `forget` drops it (no client read it for `FORGET_MINUTES`); its history before the mirror began comes
from OpenCode once, a page at a time, through `merge`.

`conversation` answers from memory, in the agent panel's shape: the newest `limit` messages (or those before a message
named), each with its parts in order, the cursor of the message to read before (`next`) and, when what comes before is
not held, OpenCode's own cursor for it (`from_opencode`), so the route reads that page once and merges it; whether the
session works, its title, its port, the waits open, and a version that moves with every change (the stream of design
0023 §3 is built on it). `sessions` lists the sessions a workspace's watcher saw, newest first, as the bridge's
`servers` lists them, so the route needs no process to find the newest one.

Bounded: past `FULL_BYTES` of text in one session, the oldest parts' text falls back to the Monitor's brief (cut at
`TEXT`, its length kept, `whole` false); the bridge's `part` action gives it whole again on demand.
"""

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

FORGET_MINUTES = 30  # a session no client read for this long is forgotten
FULL_BYTES = 4_000_000  # of a session's text and outputs held whole, at most
TEXT = 6000  # the brief a part's text falls back to (the bridge's TEXT)
CHANGES = 2000  # changes kept with their versions for the stream (design 0023 §3); a client behind them gets a snapshot
AT_WORK = ("busy", "retry")  # a session's status while it works (as `sessions.py` says it)
WAITS = ("asked", "replied", "question", "answered")
Subscriber = Callable[[int], None]


def _cut(text: str, limit: int) -> str:
    """A text cut at `limit` characters, saying how long it was (as the bridge cuts)."""
    return text if len(text) <= limit else text[:limit] + f" … [{len(text):,} characters]"


@dataclass
class Conversation:
    """One followed session as the mirror holds it."""

    workspace: str
    session: str
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)  # by id: the message's info
    parts: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)  # by message id, then part id
    complete: bool = False  # its history read since it was followed
    history_next: str = ""  # OpenCode's cursor for what comes before the oldest message held ("" at the first)
    version: int = 0
    read_at: float = 0.0  # when a client last read it (the clock's seconds)
    changes: deque[tuple[int, dict[str, Any]]] = field(default_factory=lambda: deque(maxlen=CHANGES))
    log_from: int = 1  # the version of the oldest change the log could hold (older ones were dropped)

    def changed(self, event: dict[str, Any]) -> int:
        """One more change, kept with its new version; the version."""
        self.version += 1
        if self.changes.maxlen is not None and len(self.changes) == self.changes.maxlen:
            self.log_from = self.changes[1][0]
        self.changes.append((self.version, event))
        return self.version

    def ordered(self) -> list[dict[str, Any]]:
        """The messages in time order, each with its parts."""
        infos = sorted(self.messages.values(), key=lambda info: (info.get("created") or 0, str(info.get("id"))))
        listed = []
        for info in infos:
            parts = self.parts.get(str(info["id"]), {})
            listed.append({"info": info, "parts": [parts[key] for key in sorted(parts)]})
        return listed

    def bytes_held(self) -> int:
        """The text and outputs held, in characters."""
        return sum(
            len(str(part.get("text") or "")) + len(str(part.get("output") or ""))
            for parts in self.parts.values()
            for part in parts.values()
        )


class Mirror:
    """The conversations held for the sessions clients follow, and the sessions each watcher saw."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._known: dict[str, dict[str, dict[str, Any]]] = {}  # by workspace, then session id
        self._held: dict[tuple[str, str], Conversation] = {}
        self._permissions: dict[str, dict[str, dict[str, Any]]] = {}  # by workspace, then request id
        self._questions: dict[str, dict[str, dict[str, Any]]] = {}
        self._subscribers: dict[tuple[str, str], list[Subscriber]] = {}
        self._told: list[tuple[Subscriber, int]] = []  # versions to tell once the lock is released

    # -- following

    def follow(self, workspace: str, session: str) -> None:
        """Hold the session's conversation from now on; its history comes through `merge`."""
        with self._lock:
            held = self._held.get((workspace, session))
            if held is None:
                held = self._held[(workspace, session)] = Conversation(workspace, session)
            held.read_at = self._clock()

    def followed(self, workspace: str) -> list[str]:
        """The sessions of the workspace held now, to tell its watch."""
        with self._lock:
            return sorted(session for (ws, session) in self._held if ws == workspace)

    def complete(self, workspace: str, session: str) -> bool:
        """Whether the session is held with its history read."""
        with self._lock:
            held = self._held.get((workspace, session))
            return held is not None and held.complete

    def forget(self) -> list[tuple[str, str]]:
        """Drop the sessions no client read for `FORGET_MINUTES`; which."""
        with self._lock:
            now = self._clock()
            gone = [key for key, held in self._held.items() if now - held.read_at > FORGET_MINUTES * 60]
            for key in gone:
                del self._held[key]
            return gone

    def knows(self, workspace: str, session: str) -> bool:
        """Whether a watcher's line, or a listing learned, named the session."""
        with self._lock:
            return session in self._known.get(workspace, {})

    def learn(self, workspace: str, running: list[dict[str, Any]]) -> None:
        """What the bridge's `servers` listed, once, before the watcher said the sessions (the service just started):
        each server's sessions with their status and its port, and the permissions and questions waiting."""
        with self._lock:
            known = self._known.setdefault(workspace, {})
            for server in running:
                port = server.get("port")
                for listed in [*(server.get("sessions") or []), *(server.get("children") or [])]:
                    id = str(listed.get("id") or "")
                    if not id:
                        continue
                    record = known.setdefault(id, {"id": id, "status": "idle", "port": None})
                    record.update({
                        "title": str(listed.get("title") or ""), "parent": listed.get("parent"),
                        "created": listed.get("created"), "updated": listed.get("updated"),
                        "status": str(listed.get("status") or "idle"),
                    })  # fmt: skip
                    if record.get("port") is None:
                        record["port"] = port
                for permission in server.get("permissions") or []:
                    self._permissions.setdefault(workspace, {})[str(permission.get("id"))] = dict(permission)
                for question in server.get("questions") or []:
                    self._questions.setdefault(workspace, {})[str(question.get("id"))] = dict(question)

    def version(self, workspace: str, session: str) -> int:
        """The conversation's version: it moves with every change (0 for a session not held)."""
        with self._lock:
            held = self._held.get((workspace, session))
            return held.version if held is not None else 0

    # -- the stream's part (design 0023 §3)

    def subscribe(self, workspace: str, session: str, told: Subscriber) -> Callable[[], None]:
        """Hear each new version of the conversation (told outside the mirror's lock); what unsubscribes."""
        key = (workspace, session)
        with self._lock:
            self._subscribers.setdefault(key, []).append(told)

        def stop() -> None:
            with self._lock:
                listeners = self._subscribers.get(key, [])
                if told in listeners:
                    listeners.remove(told)

        return stop

    def changes_since(self, workspace: str, session: str, version: int) -> list[tuple[int, dict[str, Any]]] | None:
        """The changes after `version`, each with its own; None when the log no longer reaches back that far, or the
        session is not held: a snapshot is due then."""
        with self._lock:
            held = self._held.get((workspace, session))
            if held is None or version + 1 < held.log_from:
                return None
            return [(each, event) for each, event in held.changes if each > version]

    def _changed(self, held: Conversation, event: dict[str, Any]) -> None:
        """A change of a held conversation: kept, and its subscribers told once the lock is released."""
        version = held.changed(event)
        for told in self._subscribers.get((held.workspace, held.session), []):
            self._told.append((told, version))

    def _tell(self) -> None:
        """Tell the subscribers what `_changed` gathered; outside the lock, so a subscriber may read the mirror."""
        while True:
            with self._lock:
                if not self._told:
                    return
                told, version = self._told.pop(0)
            told(version)

    # -- what the watchers say

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A watcher's line, as `Sessions.listen` hands it on (the module's docstring says what each changes)."""
        kind = line.get("type")
        with self._lock:
            if kind == "session":
                self._session(workspace, line)
            elif kind == "status":
                self._status(workspace, line)
            elif kind in WAITS:
                self._wait(workspace, kind, line)
            elif kind in ("synced", "gone", "disposed"):
                self._servers_left(workspace, line)
            elif kind in ("message", "part", "delta", "removed"):
                held = self._held.get((workspace, str(line.get("session") or "")))
                if held is not None:
                    event = getattr(self, f"_{kind}")(held, line)
                    if event is not None:
                        self._changed(held, event)
                    if kind in ("part", "delta") and self._bound(held):
                        self._changed(held, {"type": "snapshot"})
        self._tell()

    def _session(self, workspace: str, line: dict[str, Any]) -> None:
        info = line.get("session") or {}
        id = str(info.get("id") or "")
        known = self._known.setdefault(workspace, {})
        if line.get("deleted"):
            known.pop(id, None)
            self._held.pop((workspace, id), None)
            return
        record = known.setdefault(id, {"id": id, "status": "idle", "port": None})
        record.update({
            "title": str(info.get("title") or ""), "parent": info.get("parent"), "created": info.get("created"),
            "updated": info.get("updated"), "port": line.get("port", record.get("port")),
        })  # fmt: skip

    def _status(self, workspace: str, line: dict[str, Any]) -> None:
        id = str(line.get("session") or "")
        record = self._known.setdefault(workspace, {}).setdefault(
            id, {"id": id, "title": "", "parent": None, "created": None, "updated": None, "port": None}
        )
        record["status"] = str(line.get("status") or "idle")
        if line.get("port") is not None:
            record["port"] = line["port"]
        held = self._held.get((workspace, id))
        if held is not None:
            self._changed(held, {"type": "status", "busy": record["status"] in AT_WORK, "status": record["status"]})

    def _servers_left(self, workspace: str, line: dict[str, Any]) -> None:
        """A watch synced (the ports it follows now), or a server gone or its instance ended: the sessions of a server
        no longer followed keep their place in the list but have no port and are idle."""
        kept = {int(port) for port in line.get("ports") or []} if line.get("type") == "synced" else None
        left = None if kept is not None else line.get("port")
        for record in self._known.get(workspace, {}).values():
            port = record.get("port")
            if port is None:
                continue
            if (kept is not None and int(port) not in kept) or (left is not None and port == left):
                record["port"], record["status"] = None, "idle"

    def _wait(self, workspace: str, kind: str, line: dict[str, Any]) -> None:
        request = line.get("request")
        if kind == "asked" and isinstance(request, dict):
            self._permissions.setdefault(workspace, {})[str(request.get("id"))] = {
                "id": request.get("id"), "session": request.get("sessionID") or request.get("session"),
                "permission": request.get("permission"), "patterns": request.get("patterns") or [],
                "metadata": dict(request.get("metadata") or {}),
            }  # fmt: skip
        elif kind == "question" and isinstance(request, dict):
            self._questions.setdefault(workspace, {})[str(request.get("id"))] = {
                "id": request.get("id"), "session": request.get("session") or request.get("sessionID"),
                "questions": request.get("questions") or [],
            }  # fmt: skip
        elif kind == "replied":
            self._permissions.get(workspace, {}).pop(str(request), None)
        elif kind == "answered":
            self._questions.get(workspace, {}).pop(str(request), None)
        session = str(line.get("session") or "")
        if kind in ("asked", "question") and isinstance(request, dict):
            session = str(request.get("sessionID") or request.get("session") or session)
        held = self._held.get((workspace, session))
        if held is not None:
            self._changed(held, {"type": "waiting", "waiting": self.waiting(workspace, session)})

    def _message(self, held: Conversation, line: dict[str, Any]) -> dict[str, Any] | None:
        info = line.get("message") or {}
        if not info.get("id"):
            return None
        held.messages[str(info["id"])] = {**held.messages.get(str(info["id"]), {}), **info}
        return {"type": "message", "message": held.messages[str(info["id"])]}

    def _part(self, held: Conversation, line: dict[str, Any]) -> dict[str, Any] | None:
        part = line.get("part") or {}
        if not part.get("id") or not part.get("message"):
            return None
        held.parts.setdefault(str(part["message"]), {})[str(part["id"])] = dict(part)
        return {"type": "part", "message": str(part["message"]), "part": dict(part)}

    def _delta(self, held: Conversation, line: dict[str, Any]) -> dict[str, Any] | None:
        message, part_id, field_name = str(line.get("message") or ""), str(line.get("part") or ""), line.get("field")
        if not message or not part_id or field_name != "text":
            return None
        parts = held.parts.setdefault(message, {})
        part = parts.setdefault(part_id, {"id": part_id, "message": message, "type": "text", "text": "", "whole": True})
        text = str(line.get("text") or "")
        part["text"] = str(part.get("text") or "") + text
        part["length"] = len(part["text"])
        return {"type": "delta", "message": message, "part": part_id, "text": text}

    def _removed(self, held: Conversation, line: dict[str, Any]) -> dict[str, Any] | None:
        message = str(line.get("message") or "")
        if line.get("part"):
            held.parts.get(message, {}).pop(str(line["part"]), None)
            return {"type": "removed", "message": message, "part": str(line["part"])}
        held.messages.pop(message, None)
        held.parts.pop(message, None)
        return {"type": "removed", "message": message}

    def _bound(self, held: Conversation) -> bool:
        """Past `FULL_BYTES`, the oldest parts' text falls back to its brief; whether anything fell back."""
        total = held.bytes_held()
        if total <= FULL_BYTES:
            return False
        for message in held.ordered():
            for part in message["parts"]:
                text = str(part.get("text") or "")
                if part.get("whole") and len(text) > TEXT:
                    part["text"], part["whole"] = _cut(text, TEXT), False
                    total -= len(text) - len(part["text"])
                    if total <= FULL_BYTES:
                        return True
        return True

    # -- history

    def merge(self, workspace: str, session: str, page: dict[str, Any]) -> None:
        """A page of the session's history from OpenCode (the bridge's `page --whole`), merged: the mirror is complete
        from the first; the page's cursor is kept when the page reaches further back than what is held."""
        with self._lock:
            held = self._held.get((workspace, session))
            if held is None:
                return
            oldest_held = min(
                ((info.get("created") or 0, str(info.get("id"))) for info in held.messages.values()), default=None
            )
            for message in page.get("messages") or []:
                info = dict(message.get("info") or {})
                if not info.get("id"):
                    continue
                id = str(info["id"])
                held.messages[id] = {**held.messages.get(id, {}), **info}
                held.parts[id] = {str(part["id"]): dict(part) for part in message.get("parts") or [] if part.get("id")}
            page_oldest = min(
                (((m.get("info") or {}).get("created") or 0, str((m.get("info") or {}).get("id")))
                 for m in page.get("messages") or [] if (m.get("info") or {}).get("id")),
                default=None,
            )  # fmt: skip
            if not held.complete or oldest_held is None or (page_oldest is not None and page_oldest <= oldest_held):
                held.history_next = str(page.get("next") or "")
            held.complete = True
            self._changed(held, {"type": "snapshot"})
            self._bound(held)
        self._tell()

    # -- what clients read

    def conversation(self, workspace: str, session: str, limit: int, before: str = "") -> dict[str, Any] | None:
        """The conversation from memory; None when the session is not followed or its history not read yet."""
        with self._lock:
            held = self._held.get((workspace, session))
            if held is None or not held.complete:
                return None
            held.read_at = self._clock()
            ordered = held.ordered()
            end = len(ordered)
            if before:
                end = next((index for index, message in enumerate(ordered) if str(message["info"]["id"]) == before), 0)
            start = max(0, end - max(1, limit))
            page = ordered[start:end]
            more_held = start > 0
            from_opencode = "" if more_held or not page or start > 0 else held.history_next
            if not page and not more_held:
                from_opencode = held.history_next
            next_cursor = str(page[0]["info"]["id"]) if page and (more_held or held.history_next) else ""
            record = self._known.get(workspace, {}).get(session, {})
            return {
                "messages": page,
                "next": next_cursor,
                "from_opencode": from_opencode,
                "busy": str(record.get("status") or "idle") in AT_WORK,
                "title": str(record.get("title") or ""),
                "port": record.get("port"),
                "waiting": self.waiting(workspace, session),
                "version": held.version,
            }

    def waiting(self, workspace: str, session: str) -> dict[str, list[dict[str, Any]]]:
        """The permissions and questions open in the session."""
        with self._lock:
            return {
                "permissions": [
                    p for p in self._permissions.get(workspace, {}).values() if p.get("session") == session
                ],
                "questions": [q for q in self._questions.get(workspace, {}).values() if q.get("session") == session],
            }

    def sessions(self, workspace: str) -> list[dict[str, Any]]:
        """The workspace's root sessions as its watcher saw them, newest first (as `servers` lists them)."""
        with self._lock:
            roots = [dict(record) for record in self._known.get(workspace, {}).values() if not record.get("parent")]
            return sorted(roots, key=lambda record: record.get("updated") or 0, reverse=True)

    def port(self, workspace: str, session: str) -> int | None:
        """The port of the server that runs the session, as its watcher said."""
        with self._lock:
            found = self._known.get(workspace, {}).get(session, {}).get("port")
            return int(found) if found is not None else None
