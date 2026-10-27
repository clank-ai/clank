"""The sessions that used local-only content (design 0016 §10, decision 0111): a session is marked the first time any of
its requests shows a call to a tool that never goes to the cloud (Clank's Notion tools, a server marked local), whatever
slot serves it; it and the subagents it starts are kept from the cloud from then on, even once a compaction folds the
call into a summary. The marks are kept in `state/local-only.json`, so a restart of the gateway forgets none; written
through the kernel's `files`, and a file another program holds for good is said in the gateway's log, the marks held
in memory all the same: a request never fails for it.
"""

import json
import logging
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from clank.kernel import files

log = logging.getLogger(__name__)


class LocalMarks:
    """The sessions marked local only, each with the first local-only tool it called."""

    def __init__(self, file: Path | None = None) -> None:
        self._file = file
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, str]] = {}
        if file is not None and file.is_file():
            try:
                found = json.loads(file.read_text(encoding="utf-8"))
                sessions = found.get("sessions") if isinstance(found, dict) else None
                if isinstance(sessions, dict):
                    self._sessions = {str(key): dict(value) for key, value in sessions.items()}
            except (OSError, ValueError, TypeError):
                self._sessions = {}

    def mark(self, session: str, tool: str) -> bool:
        """Mark a session for a local-only tool it called; whether it was not marked before."""
        if not session:
            return False
        with self._lock:
            if session in self._sessions:
                return False
            self._sessions[session] = {"tool": tool}
            self._save()
            return True

    def marked(self, *sessions: str) -> str:
        """The local-only tool the first of these sessions that is marked called; "" when none is."""
        with self._lock:
            for session in sessions:
                if session and session in self._sessions:
                    return self._sessions[session].get("tool", "")
        return ""

    def _save(self) -> None:
        if self._file is None:
            return
        try:
            files.replace(self._file, json.dumps({"sessions": self._sessions}, indent=1) + "\n", files.MOMENT)
        except OSError as error:
            log.warning("the sessions kept from the cloud could not be written to %s (%s): kept in memory",
                        self._file, error)  # fmt: skip


def local_calls(messages: Iterable[Any], prefixes: Sequence[str]) -> list[str]:
    """The tools a request's messages call that never go to the cloud, in order."""
    found = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        for call in message.get("tool_calls") or []:
            name = str(((call or {}).get("function") or {}).get("name") or "") if isinstance(call, Mapping) else ""
            if name and any(name.startswith(prefix) for prefix in prefixes):
                found.append(name)
    return found


def held_back(tools: Iterable[Any], prefixes: Sequence[str]) -> tuple[list[Any], list[str]]:
    """A request's tools without those that never go to the cloud, and the names of those taken out."""
    kept, removed = [], []
    for tool in tools:
        name = str(((tool or {}).get("function") or {}).get("name") or "") if isinstance(tool, Mapping) else ""
        if name and any(name.startswith(prefix) for prefix in prefixes):
            removed.append(name)
        else:
            kept.append(tool)
    return kept, removed


def whose(tool: str, prefixes: Sequence[str]) -> str:
    """What a local-only tool belongs to, in words: Notion, or the server it is a tool of, marked local."""
    if tool.startswith("clank_notion_"):
        return "Notion"
    prefix = next((each for each in prefixes if tool.startswith(each)), "")
    return f"{prefix.rstrip('_') or tool}, marked local"
