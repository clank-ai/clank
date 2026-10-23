"""A fake OpenCode server, as Clank's bridge uses one (design 0005 §2, design 0007 §4, design 0012 §3, §6.1 and §9):
OpenCode 1.19's routes and event stream, served on this machine for the bridge's tests.

Several fakes can share one `Store`, as OpenCode's servers in one container share their sessions (their storage is the
container's home), while each has its own run state (`status`), its own asks and questions waiting (and those
answered elsewhere meanwhile, `settled`), its own event stream and its own record of what was sent to it (`sent`) and
of what was read from it (`read`). A store starts from a synthetic session written in OpenCode's shapes
(`tests/fixtures/opencode/1.19.0/session.json`); `feed` and `replay` write events on the stream in one burst, as
OpenCode's come while the model writes, a stream sending every event fed once it said it is connected (its thread can be
made to wait just then, `connected_pause`, as a busy machine's does); `restart` ends the streams while the server still
listens; `dispose` ends its instance as OpenCode 1.19's does (measured 2026-10-22): the streams open then say so, stay
open and carry nothing more, and only a stream opened after hears what follows.

What it does as OpenCode does, as far as the bridge can tell (read in OpenCode 1.18.31's program, 2026-10-19): a message
that names no agent goes to `build`; messages page newest first by `limit` and `before`, an opaque cursor in
`X-Next-Cursor` while older ones are left, `before` without `limit` refused; rejecting an ask rejects every other ask of
its session; `summarize` answers only when the test lets it (`release`), as OpenCode's answers only once the run ends;
a part is updated only whole, its ids those of its path; an unknown session is not found. A revert (design 0012 §9.5)
cuts as OpenCode's `session/revert.ts` decides: at the part named only when a text or a tool part comes before it in its
message, else from the owner's last message, and its answer carries OpenCode's snapshot and text diff; a busy session is
neither reverted nor unreverted; the owner's next message makes a pending revert final, the messages after the cut
removed and the cut message's parts from the cut part on, each removal said on the stream. These were read by text
search in OpenCode 1.18.31's program, not yet confirmed against 1.19.0.
"""

import base64
import copy
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

from tests.support.served import free_port

FIXTURE = Path(__file__).parents[1] / "fixtures" / "opencode" / "1.19.0" / "session.json"
DEFAULT_MODEL = {"providerID": "clank", "modelID": "agent"}
BUILD = "build"
BUSY = ("busy", "retry")  # a session's run states that refuse a revert and an unrevert


def recorded() -> dict[str, Any]:
    """The synthetic session, its subagent, another session, and their bursts of events."""
    found: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return found


class Store:
    """What OpenCode keeps on disk, shared by every server in one container: the sessions and their messages."""

    def __init__(self, given: dict[str, Any] | None = None) -> None:
        given = given if given is not None else recorded()
        self.lock = threading.RLock()
        self.sessions: dict[str, dict[str, Any]] = {each["id"]: copy.deepcopy(each) for each in given["sessions"]}
        self.messages: dict[str, list[dict[str, Any]]] = copy.deepcopy(given["messages"])
        self.bursts: dict[str, list[dict[str, Any]]] = given["bursts"]
        self.made = 0

    def new_id(self, prefix: str) -> str:
        with self.lock:
            self.made += 1
            return f"{prefix}_new{self.made:02d}"


class FakeOpenCode:
    """One OpenCode server on a port of this machine."""

    def __init__(self, store: Store | None = None, port: int | None = None) -> None:
        self.store = store or Store()
        self.status: dict[str, dict[str, Any]] = {}  # the sessions this server runs: busy or retry
        self.asks: list[dict[str, Any]] = []  # permissions waiting on this server
        self.questions: list[dict[str, Any]] = []
        self.sent: list[tuple[str, str, Any]] = []  # (method, path, body) of every request that changes something
        self.read: list[str] = []  # the path of every request that reads (its query left out)
        self.settled: set[str] = set()  # asks and questions answered elsewhere meanwhile: listed, not found
        self.answered: list[str] = []  # the sessions whose compaction was answered, the answer delivered
        self.release = threading.Event()  # lets `summarize` answer
        self.closing = threading.Event()
        self.connected_pause = 0.0  # seconds each stream's thread waits once it said it is connected: a busy machine
        self._bursts: list[tuple[int, list[dict[str, Any]]]] = []  # each burst with the instance it was fed to
        self._restarts = 0
        self._instance = 0  # the instance a stream opened now hears
        self._fed = threading.Condition()
        handler = type("Handler", (_Handler,), {"fake": self})
        self.server = ThreadingHTTPServer(("127.0.0.1", port or free_port()), handler)
        self.server.daemon_threads = True
        self.port: int = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @classmethod
    def several(cls, count: int, store: Store | None = None) -> list["FakeOpenCode"]:
        """`count` servers on neighboring ports (the bridge's range), sharing one store."""
        store = store or Store()
        while True:
            first = free_port()
            made: list[FakeOpenCode] = []
            try:
                for offset in range(count):
                    made.append(cls(store, first + offset))
                return made
            except OSError:
                for each in made:
                    each.close()

    def close(self) -> None:
        self.closing.set()
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> "FakeOpenCode":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def feed(self, *events: dict[str, Any]) -> None:
        """Events on the stream, written at once: one burst."""
        with self._fed:
            self._bursts.append((self._instance, list(events)))
            self._fed.notify_all()

    def replay(self, name: str) -> None:
        """A burst of the synthetic session's events."""
        self.feed(*self.store.bursts[name])

    def restart(self) -> None:
        """End the event streams open now while the server still listens, as OpenCode's instance starting again does."""
        with self._fed:
            self._restarts += 1
            self._fed.notify_all()

    def dispose(self) -> None:
        """Its instance ended and a new one began, as OpenCode 1.19's does when its configuration changes: the streams
        open now say `server.instance.disposed`, then stay open and carry nothing more; a stream opened after hears
        the new instance."""
        with self._fed:
            self._bursts.append((self._instance, list(self.store.bursts["disposed"])))
            self._instance += 1
            self._fed.notify_all()

    def sent_to(self, path: str) -> list[Any]:
        """The bodies sent to a path (its query left out)."""
        return [body for _, each, body in self.sent if each == path]


def cursor(message: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"id": message}).encode()).decode()


class _Handler(BaseHTTPRequestHandler):
    fake: ClassVar[FakeOpenCode]

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(each) for each in url.path.strip("/").split("/")]
        query = dict(urllib.parse.parse_qsl(url.query))
        fake, store = self.fake, self.fake.store
        fake.read.append(url.path)
        if url.path == "/event":
            self._stream()
            return
        with store.lock:
            if url.path == "/session":
                self._json(list(store.sessions.values()))
            elif url.path == "/session/status":
                self._json(fake.status)
            elif url.path == "/permission":
                self._json(fake.asks)
            elif url.path == "/question":
                self._json(fake.questions)
            elif parts[0] == "session" and parts[1] not in store.sessions:
                self._missing(parts[1])
            elif len(parts) == 3 and parts[2] == "children":
                self._json([each for each in store.sessions.values() if each.get("parentID") == parts[1]])
            elif len(parts) == 3 and parts[2] == "message":
                self._messages(parts[1], query)
            elif len(parts) == 4 and parts[2] == "message":
                found = next(
                    (each for each in store.messages.get(parts[1], []) if each["info"]["id"] == parts[3]), None
                )
                self._json(found) if found is not None else self._missing(parts[3])
            else:
                self._json({"name": "NotFoundError", "data": {"message": f"no route {url.path}"}}, 404)

    def _messages(self, session: str, query: dict[str, str]) -> None:
        listed = self.fake.store.messages.get(session, [])
        if "before" in query and "limit" not in query:
            self._json({"name": "BadRequest", "data": {}}, 400)
            return
        limit = int(query.get("limit") or 0)
        if not limit:
            self._json(listed)
            return
        end = len(listed)
        if "before" in query:
            try:
                id = json.loads(base64.urlsafe_b64decode(query["before"]))["id"]
                end = next(index for index, each in enumerate(listed) if each["info"]["id"] == id)
            except (ValueError, KeyError, StopIteration):
                self._json({"name": "BadRequest", "data": {}}, 400)
                return
        page = listed[max(end - limit, 0) : end]
        more = {"X-Next-Cursor": cursor(page[0]["info"]["id"])} if end - limit > 0 and page else {}
        self._json(page, headers=more)

    def do_POST(self) -> None:
        self._change("POST")

    def do_PATCH(self) -> None:
        self._change("PATCH")

    def _change(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(each) for each in url.path.strip("/").split("/")]
        fake, store = self.fake, self.fake.store
        fake.sent.append((method, url.path, body))
        if url.path == "/session":
            with store.lock:
                id = store.new_id("ses")
                made = {"id": id, "title": (body or {}).get("title") or "New session",
                        "time": {"created": 1, "updated": 1}}  # fmt: skip
                store.sessions[id] = made
            self._json(made)
        elif parts[0] == "permission":
            self._permission(parts[1], (body or {}).get("reply", ""))
        elif parts[0] == "question":
            self._question(parts[1])
        elif parts[0] == "session" and parts[1] not in store.sessions:
            self._missing(parts[1])
        elif parts[-1] == "summarize":
            self._summarize(parts[1])
        elif method == "PATCH" and len(parts) == 6 and parts[4] == "part":
            self._part(parts[1], parts[3], parts[5], body)
        else:
            self._session(parts[1], parts[2], body or {})

    def _session(self, session: str, action: str, body: dict[str, Any]) -> None:
        store = self.fake.store
        with store.lock:
            info = store.sessions[session]
            if action == "prompt_async":
                self._cleanup(session, info)
                id = store.new_id("msg")
                model = dict(body.get("model") or DEFAULT_MODEL)
                if body.get("variant"):
                    model["variant"] = body["variant"]
                user = {"id": id, "sessionID": session, "role": "user", "time": {"created": 2},
                        "agent": body.get("agent") or BUILD, "model": model}  # fmt: skip
                parts = [{**each, "id": f"prt_{id}_{index}", "sessionID": session, "messageID": id}
                         for index, each in enumerate(body.get("parts") or [])]  # fmt: skip
                store.messages.setdefault(session, []).append({"info": user, "parts": parts})
                self._empty()
            elif action == "abort":
                self._json(True)
            elif action in ("revert", "unrevert") and (self.fake.status.get(session) or {}).get("type") in BUSY:
                self._json({"name": "BusyError", "data": {"message": f"Session {session} is busy"}}, 400)
            elif action == "revert":
                revert = self._revert(session, str(body.get("messageID") or ""), str(body.get("partID") or ""))
                if revert is not None:
                    info["revert"] = {**revert, "snapshot": "4b825dc6",
                                      "diff": "--- a/plot.py\n+++ b/plot.py\n" + "+x\n" * 2_000}  # fmt: skip
                self._json(info)
            elif action == "unrevert":
                info.pop("revert", None)
                self._json(info)
            else:
                self._json({"name": "NotFoundError", "data": {"message": f"no route {action}"}}, 404)

    def _revert(self, session: str, message: str, part: str) -> dict[str, str] | None:
        """Where a revert cuts, as OpenCode's `session/revert.ts` decides: at the part named only when a text or a tool
        part comes before it in its message, else from the owner's last message, the whole turn; None when nothing
        named is found."""
        last_user = ""
        for each in self.fake.store.messages.get(session, []):
            info = each["info"]
            if info.get("role") == "user":
                last_user = info["id"]
            before: list[dict[str, Any]] = []
            for kept in each["parts"]:
                if (info["id"] == message and not part) or kept["id"] == part:
                    named = part if any(one.get("type") in ("text", "tool") for one in before) else ""
                    return {"messageID": info["id"] if named or not last_user else last_user,
                            **({"partID": named} if named else {})}  # fmt: skip
                before.append(kept)
        return None

    def _cleanup(self, session: str, info: dict[str, Any]) -> None:
        """The owner's next message makes a pending revert final, as OpenCode's `SessionRevert.cleanup` does: the
        messages after the cut removed, and the cut message's parts from the cut part on (a revert by message alone
        removes that message too); each removal said on the stream."""
        revert = info.pop("revert", None)
        if not revert:
            return
        stored = self.fake.store.messages.get(session, [])
        ids = [each["info"]["id"] for each in stored]
        if revert["messageID"] not in ids:
            return
        at = ids.index(revert["messageID"])
        cut = revert.get("partID") or ""
        gone = stored[at + 1 :] if cut else stored[at:]
        events = [{"type": "message.removed", "properties": {"sessionID": session, "messageID": each["info"]["id"]}}
                  for each in gone]  # fmt: skip
        if cut:
            parts = [each["id"] for each in stored[at]["parts"]]
            keep = parts.index(cut) if cut in parts else len(parts)
            events += [{"type": "message.part.removed",
                        "properties": {"sessionID": session, "messageID": revert["messageID"], "partID": id}}
                       for id in parts[keep:]]  # fmt: skip
            stored[at]["parts"] = stored[at]["parts"][:keep]
        self.fake.store.messages[session] = stored[: at + 1] if cut else stored[:at]
        self.fake.feed(*events, {"type": "session.updated", "properties": {"sessionID": session, "info": info}})

    def _summarize(self, session: str) -> None:
        self.fake.release.wait(60)
        try:
            self._json(True)
            self.wfile.flush()
            self.fake.answered.append(session)
        except OSError:
            pass  # the client left before the answer

    def _part(self, session: str, message: str, part: str, body: Any) -> None:
        if not isinstance(body, dict) or (body.get("id"), body.get("messageID"), body.get("sessionID")) != (
            part,
            message,
            session,
        ):
            self._json({"name": "BadRequest", "data": {}}, 400)
            return
        with self.fake.store.lock:
            for each in self.fake.store.messages.get(session, []):
                if each["info"]["id"] == message:
                    each["parts"] = [copy.deepcopy(body) if kept["id"] == part else kept for kept in each["parts"]]
        self._json(body)

    def _permission(self, id: str, reply: str) -> None:
        fake = self.fake
        asked = next((each for each in fake.asks if each["id"] == id), None)
        if asked is None or id in fake.settled:
            self._missing(id)
            return
        if reply == "reject":  # OpenCode rejects every other ask of the session with it
            fake.asks = [each for each in fake.asks if each.get("sessionID") != asked.get("sessionID")]
        else:
            fake.asks = [each for each in fake.asks if each["id"] != id]
        self._json(True)

    def _question(self, id: str) -> None:
        fake = self.fake
        if id in fake.settled or not any(each["id"] == id for each in fake.questions):
            self._missing(id)
            return
        fake.questions = [each for each in fake.questions if each["id"] != id]
        self._json(True)

    def _stream(self) -> None:
        fake = self.fake
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        with fake._fed:  # what is fed from here on is sent, as OpenCode's stream sends every event once connected
            seen, begun, instance = len(fake._bursts), fake._restarts, fake._instance
        self.wfile.write(b'data: {"type":"server.connected","properties":{}}\n\n')
        self.wfile.flush()
        time.sleep(fake.connected_pause)
        try:
            while not fake.closing.is_set() and fake._restarts == begun:
                with fake._fed:
                    fake._fed.wait(0.1)
                    fresh, seen = fake._bursts[seen:], len(fake._bursts)
                for fed_to, burst in fresh:  # a burst in one write, to the streams of its instance only
                    if fed_to != instance:
                        continue
                    self.wfile.write(b"".join(f"data: {json.dumps(event)}\n\n".encode() for event in burst))
                    self.wfile.flush()
        except OSError:
            pass

    def _missing(self, id: str) -> None:
        self._json({"name": "NotFoundError", "data": {"message": f"{id} not found"}}, 404)

    def _empty(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _json(self, value: Any, status: int = 200, headers: dict[str, str] | None = None) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for name, said in (headers or {}).items():
            self.send_header(name, said)
        self.end_headers()
        self.wfile.write(data)
