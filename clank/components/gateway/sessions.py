"""Which session a model request belongs to (design 0012 §3, decision 0048): OpenCode sends its session's id with
every model request (`X-Session-Id`) and, for a subagent's request, the session that started it
(`x-parent-session-id`), as its `session/llm/request.ts` reads in OpenCode 1.19.0. The gateway keeps every header with
each record (`records.py`, its credentials' values left out), so the session is read from them: in the activity, for
each request in flight and the last that ended, and in the records' summary, so records kept before this was read show
their sessions too. One edge container serves every workspace, so a request's address names neither a workspace nor a
session: the session's id is all that joins a request to it. A request that names none (completion in VS Code, a
script) is no session's."""

from collections.abc import Mapping
from typing import Any

SESSION = "x-session-id"
PARENT = "x-parent-session-id"


def session_of(headers: Mapping[str, Any] | None) -> tuple[str, str]:
    """The session a request named and its parent, from its headers (their names in any case); "" for either it did
    not name."""
    found = {str(name).lower(): str(value).strip() for name, value in (headers or {}).items()}
    return found.get(SESSION, ""), found.get(PARENT, "")
