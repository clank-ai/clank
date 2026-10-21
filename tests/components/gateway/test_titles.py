"""Design 0001 §6.4 and design 0004 §2: OpenCode asks for a session's title in a small request of its own just before
the session's first prompt; answered by the model, that request would take the place of the conversation the engine
keeps cached (measured with Clank's prototype: 52 of 89 long re-reads, the desktop freezing during some), so the
gateway answers it itself, from the first line of the user's message, cut at a clause, then at a word; a request with
tools, or with another first message, is not one."""

from typing import Any

from clank.components.gateway.titles import local_title

TITLE_SYSTEM = "You are a title generator. You output ONLY a thread title. Nothing else."


def asking(text: str, **extra: Any) -> dict[str, Any]:
    return {
        "model": "agent",
        "messages": [
            {"role": "system", "content": TITLE_SYSTEM},
            {"role": "user", "content": "Generate a title for this conversation:\n"},
            {"role": "user", "content": text},
        ],
        **extra,
    }


def test_opencodes_title_request_is_answered_from_the_first_line_of_the_users_message() -> None:
    assert local_title(asking("# Fix the parser\nIt fails on empty files.")) == "Fix the parser"
    assert local_title(asking('"Plot the decay rates"')) == "Plot the decay rates"
    assert local_title(asking("")) == "New session"


def test_a_long_first_line_is_cut_at_its_first_clause_then_at_a_word() -> None:
    long = "Rewrite the particle simulator's sampling loop, keeping the old one for comparison and timing both"
    assert local_title(asking(long)) == "Rewrite the particle simulator's sampling loop"
    words = "word " * 30
    title = local_title(asking(words))
    assert title is not None
    assert len(title) <= 50
    assert title.endswith("word")


def test_a_request_with_tools_or_another_first_message_is_not_a_title_request() -> None:
    assert local_title(asking("Fix it", tools=[{"type": "function"}])) is None
    assert local_title({"model": "agent", "messages": [{"role": "user", "content": "Fix the parser"}]}) is None
    assert local_title({"model": "agent", "messages": "not a list"}) is None
