"""OpenCode's session titles, answered by the gateway itself (design 0001 §6.4, design 0004 §2).

OpenCode asks the model for a title in a small request of its own just before a new session's first prompt (its first
message is a system prompt starting "You are a title generator", and it offers no tools). An engine that keeps one
conversation cached would put this request in that conversation's place, so the session's first prompt (thousands of
tokens of instructions and tools) would be read again from the start: Clank's prototype measured 52 of 89 long
re-reads coming right after such a request, and the desktop froze during some. The title is the first line of the
user's message, its Markdown marks dropped, cut at its first clause when longer than `LONGEST` characters, then at a
word.
"""

import re
from typing import Any

PROMPT = "You are a title generator"
ASKING = "Generate a title for this conversation"
LONGEST = 50
CLAUSE = re.compile(r"[,;:]\s|[.!?]\s")
MARKS = re.compile(r'^[\s#>*`_=~|"-]+')


def local_title(body: Any) -> str | None:
    """The title for OpenCode's title request, or None for any other request."""
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or not messages or body.get("tools") or not isinstance(messages[0], dict):
        return None
    if messages[0].get("role") != "system" or not _text(messages[0].get("content")).startswith(PROMPT):
        return None
    said = [_text(m.get("content")) for m in messages[1:] if isinstance(m, dict) and m.get("role") == "user"]
    said = [text for text in said if not text.startswith(ASKING)]
    line = next((line for line in (said[-1] if said else "").splitlines() if line.strip()), "")
    line = re.sub(r"\s+", " ", MARKS.sub("", line)).strip().strip('`*_"')
    if len(line) > LONGEST:
        clause = CLAUSE.search(line)
        if clause and 12 <= clause.start() <= LONGEST:
            line = line[: clause.start() + (1 if line[clause.start()] in "?!" else 0)]
    if len(line) > LONGEST:
        cut = line.rfind(" ", 0, LONGEST + 1)
        line = line[:cut] if cut > 0 else line[:LONGEST]
    return line.rstrip(" .,;:-") or "New session"


def _text(content: Any) -> str:
    """A message's text, whether it is a string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""
