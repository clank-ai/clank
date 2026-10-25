"""Design 0020 §11 and §12: comments the owner left on lines of LaTeX files go to the agent as one message, numbered,
each with its file, its lines and the text it covers, and the rule to change only what they ask and answer each by its
number (`POST /agents/latex/comments`, to the session most recently active; refused while no agent runs, or with no
comment). After a numbered message (comments, or marks on a PDF's page), once the agent's turn ends, its reply is read:
each number it did not answer is asked for once more, in one message, and never a second time."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.latex.answers import Answers, answered
from clank.components.agents.latex.comments import compose_comments
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from tests.components.agents.test_annotations import workspace
from tests.components.agents.test_sessions import OpenCode, kernel, opencode  # noqa: F401 (fixtures)

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
COMMENTS = [
    {
        "file": "paper/intro.tex",
        "start": 12,
        "end": 13,
        "text": "the rank grows exponentially in t",
        "body": "Say why.",
    },
    {"file": "paper/results.tex", "start": 4, "end": 4, "text": "E_0 = -1.27", "body": "Give the error bar."},
]


def test_comments_are_one_numbered_message_with_their_files_lines_and_text() -> None:
    text = compose_comments(COMMENTS, "Keep the tone formal.")
    assert text == (
        "My comments on the LaTeX source:\n"
        "- Comment 1 on paper/intro.tex lines 12-13, on 'the rank grows exponentially in t': Say why.\n"
        "- Comment 2 on paper/results.tex line 4, on 'E_0 = -1.27': Give the error bar.\n\n"
        "Change only what the comments ask, and answer each by its number: what you changed and on which lines, or "
        "why you did not.\n\nKeep the tone formal."
    )


def test_the_numbers_a_reply_answers_are_read_in_the_forms_models_write_them() -> None:
    reply = (
        "**Comment 1**: added a sentence on line 13.\n2. Done: the error bar is there.\n- Mark 4 — struck.\n"
        "I also fixed comment #5 along the way, and 1990 papers."
    )
    assert answered(reply, "comment") == {1, 2, 5}
    assert answered(reply, "mark") == {2, 4}, "a bare number answers whatever was asked"


def test_the_route_sends_the_comments_to_the_agent_and_refuses_with_no_agent_or_no_comment(
    kernel: Kernel,  # noqa: F811
    opencode: int,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    workspace(kernel, folder, opencode, monkeypatch)
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        empty = service.post(
            "/api/v1/agents/latex/comments", headers=AUTH, json={"folder": str(folder), "comments": []}
        )
        assert empty.status_code == 409
        assert empty.json()["error"]["message"] == "comment on a line of a .tex file first, then send"
        sent = service.post("/api/v1/agents/latex/comments", headers=AUTH,
                            json={"folder": str(folder), "comments": COMMENTS})  # fmt: skip
        assert sent.status_code == 200, sent.text
        assert (sent.json()["session"], sent.json()["count"]) == ("ses_1", 2)
    path, body = OpenCode.sent[-1]
    assert path == "/session/ses_1/prompt_async"
    assert body["parts"][0]["text"].startswith("My comments on the LaTeX source:\n- Comment 1 on paper/intro.tex")
    [event] = kernel.events.after(0, types=["agents.latex_commented"])
    assert (event.data["workspace"], event.data["comments"]) == ("paper", 2)


class Session:
    """The sessions as the answers' check uses them: the messages it reads, and what it sends."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.sent: list[str] = []
        self.listening: list[Any] = []

    def listen(self, heard: Any) -> None:
        self.listening.append(heard)

    def messages(self, workspace: str, port: int, session: str, limit: int = 40) -> dict[str, Any]:
        return {"messages": [
            {"role": "user", "parts": [{"type": "text", "text": "an older message"}]},
            {"role": "user", "parts": [{"type": "text", "text": "My comments on the LaTeX source:\n- Comment 1 ..."}]},
            {"role": "assistant",
             "parts": [{"type": "reasoning", "length": 900}, {"type": "text", "text": self.reply}]},
        ]}  # fmt: skip

    def send(self, workspace: str, port: int, session: str, text: str, *, actor: Any) -> None:
        self.sent.append(text)

    def line(self, status: str) -> None:
        for heard in self.listening:
            heard("paper", {"type": "status", "port": 4096, "session": "ses_1", "status": status})


def test_a_number_left_unanswered_is_asked_for_once_when_the_turn_ends() -> None:
    session = Session("Comment 1: done on line 13.")
    answers = Answers(session, wait=False)  # type: ignore[arg-type]
    answers.expect("paper", 4096, "ses_1", "comment", [1, 2, 3], "My comments on the LaTeX source:")
    session.line("busy")
    session.line("idle")
    assert session.sent == [
        "You did not answer comments 2 and 3 of my message: answer each by its number, what you changed and on which "
        "lines, or why you did not."
    ]
    session.line("busy")
    session.line("idle")
    assert len(session.sent) == 1, "asked once more, never a second time"


def test_a_reply_answering_every_number_asks_nothing() -> None:
    session = Session("1. Done.\n2. Not done: it is right as it is.")
    answers = Answers(session, wait=False)  # type: ignore[arg-type]
    answers.expect("paper", 4096, "ses_1", "comment", [1, 2], "My comments on the LaTeX source:")
    session.line("idle")
    assert session.sent == [], "an idle before the turn started is not its end"
    session.line("busy")
    session.line("idle")
    assert session.sent == []
    assert json.dumps(answers.waiting()) == "[]"
