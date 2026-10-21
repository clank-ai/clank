"""How a session's flow keeps text (design 0012 §6.3: nothing spills out of a node): on one line, cut with "…"; the
whole text is one read of the session's history away."""

from typing import Any

BRIEF = 300  # characters of a text a node keeps


def brief(text: Any, limit: int = BRIEF) -> str:
    """A text on one line, cut with "…" at `limit` characters."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
