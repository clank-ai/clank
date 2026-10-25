"""Comments on the LaTeX source (design 0020 §11): the owner comments on lines of `.tex` files in VS Code (comment
threads), and sends them to the agent as one message, numbered, each with its file, its lines and the text it covers,
then the rule: change only what the comments ask, and answer each by its number. The message goes to the session most
recently active in the workspace's container, as a marked-up figure does (`annotations.py`); its answers are checked
when the agent's turn ends (`answers.py`). Each send is an event (`agents.latex_commented`).
"""

from typing import TYPE_CHECKING, Any

from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.annotations import Annotations
    from clank.components.agents.latex.answers import Answers
    from clank.components.agents.sessions import Sessions
    from clank.kernel.core import Kernel

HEAD = "My comments on the LaTeX source:"
RULE = (
    "Change only what the comments ask, and answer each by its number: what you changed and on which lines, or why "
    "you did not."
)
QUOTED = 200
EVENT_TYPES = [
    EventType(
        "agents.latex_commented",
        "You sent your comments on LaTeX files to the workspace's agent (design 0020 §11).",
        {"workspace": "The workspace.", "comments": "How many.", "files": "The files commented on."},
    )
]  # fmt: skip


class CommentError(Exception):
    """Comments that cannot be sent, and why."""


def compose_comments(comments: list[dict[str, Any]], message: str = "") -> str:
    """The message the agent receives: each comment numbered with its place and text, the rule, the owner's words."""
    lines = [HEAD]
    for number, comment in enumerate(comments, start=1):
        start, end = int(comment.get("start") or 0), int(comment.get("end") or comment.get("start") or 0)
        where = f"lines {start}-{end}" if end > start else f"line {start}"
        text = " ".join(str(comment.get("text") or "").split())
        quoted = f", on '{text if len(text) <= QUOTED else text[:QUOTED] + '…'}'" if text else ""
        lines.append(f"- Comment {number} on {comment.get('file')} {where}{quoted}: {str(comment.get('body')).strip()}")
    said = "\n".join(lines) + "\n\n" + RULE
    return said + (f"\n\n{message.strip()}" if message.strip() else "")


class Comments:
    """The owner's comments on LaTeX files, sent to the agent."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions", annotations: "Annotations", answers: "Answers") -> None:
        self.kernel = kernel
        self.sessions = sessions
        self.annotations = annotations
        self.answers = answers

    def send(self, folder: str, comments: list[dict[str, Any]], message: str, *, actor: Actor) -> dict[str, Any]:
        """Send the comments to the agent; where they went and what was said."""
        kept = [each for each in comments if str(each.get("body") or "").strip()]
        if not kept:
            raise CommentError("comment on a line of a .tex file first, then send")
        workspace, _ = self.annotations.workspace_of(folder)
        target = self.annotations.target_of(workspace)
        text = compose_comments(kept, message)
        self.sessions.send(workspace, target["port"], target["session"], text, actor=actor)
        numbers = list(range(1, len(kept) + 1))
        self.answers.expect(workspace, target["port"], target["session"], "comment", numbers, HEAD)
        files = sorted({str(each.get("file")) for each in kept})
        self.kernel.events.record(
            "agents.latex_commented",
            summary=f"{actor.describe()} sent {len(kept)} comments on {', '.join(files)} to {workspace}'s agent",
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "comments": len(kept), "files": files},
        )
        return {**target, "workspace": workspace, "count": len(kept), "text": text}
