"""Annotations (design 0008 §5): a figure the owner marked up, kept in the folder and sent to the workspace's agent.

`send` takes what the annotator sends: the figure (a file in a workspace's folder), the marks, the message, and the
marked-up copy as a PNG. The marks are said in words (`figures.describe`), with the figure's geometry when Matplotlib
saved it in the workspace (`.clank/figures/`, only while its checksum is the figure's). The marked-up copy and a record
of the annotation (the marks, the message, the words, where it went) are kept in `.clank/annotations/`, which a
`.gitignore` keeps out of git. The message goes to the session most recently active among the agents running in the
workspace's container, with the marked-up copy as an image when the agent's model reads images (`reads_images`);
else, unless vision is off, with what the vision model read in it (`read_image`, design 0008 §7). Nothing is sent
while no agent runs. Each annotation sent is an event (`agents.annotated`). A page of a PDF Clank rendered (design 0020
§10, `latex/pages.py`) is said as a page: each mark with its source file and line and the words under it.
"""

import base64
import hashlib
import json
import ntpath
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.agents.figures import describe, image_size
from clank.components.agents.latex.pages import PageMarks, page_image
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.sessions import Sessions
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

KEPT = (".clank", "annotations")
READING = (
    "This scientific figure has numbered marks a user drew on it (shapes or arrows, each with its number in a filled "
    "circle; a note is a white bubble of text tied by a thin line to its numbered pin, and marks the pin's place). For "
    "each mark, in one line: its number, what it marks (which curves, points or element), and roughly where in the "
    "plot's own data coordinates (read the axes)."
)
PNG = b"\x89PNG\r\n\x1a\n"
EVENT_TYPES = [
    EventType(
        "agents.annotated",
        "You marked up a figure and sent it to the workspace's agent (design 0008).",
        {
            "workspace": "The workspace.", "figure": "The figure, in its folder.",
            "annotation": "The marked-up copy, in the folder.", "marks": "How many marks.",
            "attached": "Whether the marked-up copy went to the model as an image.",
        },
    )
]  # fmt: skip


class AnnotationError(Exception):
    """An annotation that cannot be sent, and why."""


class Annotations:
    """The figures marked up in the workspaces' folders."""

    def __init__(
        self,
        kernel: "Kernel",
        sessions: "Sessions",
        reads_images: Callable[[], bool],
        read_image: Callable[[bytes, str], str] | None = None,
    ) -> None:
        self.kernel = kernel
        self.sessions = sessions
        self.reads_images = reads_images
        self.read_image = read_image or (lambda image, question: "")
        self.pages: PageMarks | None = None  # a PDF's pages (design 0020 §10), set by the agents' part
        self._lock = threading.Lock()

    def send(
        self, folder: str, figure: str, marks: list[dict[str, Any]], message: str, image: str, *, actor: Actor
    ) -> dict[str, Any]:
        """Keep the annotation, then send it to the agent; where it went, what was said, and whether the marked-up copy
        went as an image."""
        workspace, root = self._workspace(folder)
        path = Path(figure)
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as error:
            raise AnnotationError(f"{figure} is not in the folder of {workspace} ({root})") from error
        data = path.read_bytes()
        size = image_size(data)
        if size is None:
            raise AnnotationError(f"{relative} is not a PNG or a JPEG")
        marked = _decoded(image)
        if not marks and not message.strip():
            raise AnnotationError("mark something on the figure or write what to do, then send")
        page = page_image(root, relative) if self.pages is not None else None
        geometry = None if page else self._geometry(root, relative, data)
        if page is not None and self.pages is not None:
            sentences = self.pages.describe(workspace, root, relative, marks) if marks else []
            about = f"page {page[1]} of `{page[0]['pdf']}`"
        else:
            sentences = describe(marks, geometry, size)
            about = f"the figure `{relative}`"
        target = self._target(workspace)
        attached = self.reads_images()
        with self._lock:
            kept = root.joinpath(*KEPT)
            kept.mkdir(parents=True, exist_ok=True)
            ignore = kept / ".gitignore"
            if not ignore.exists():
                ignore.write_text("*\n", encoding="utf-8")
            stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(relative).stem) or "figure"
            number = 1
            while (kept / f"{stem}-{number}.png").exists():
                number += 1
            copy = kept / f"{stem}-{number}.png"
            copy.write_bytes(marked)
        shown = "/".join([*KEPT, copy.name])
        seen = "" if attached or not marks else self.read_image(marked, READING)
        text = compose(
            relative, shown, sentences, message, attached, geometry is not None or page is not None, seen, about=about
        )
        files = [{"url": f"file:///workspace/{shown}", "mime": "image/png", "filename": copy.name}] if attached else []
        record = {
            "figure": relative, "copy": shown, "marks": marks, "message": message, "said": sentences,
            "geometry": geometry is not None, "attached": attached, "seen": seen, "workspace": workspace,
            "port": target["port"], "session": target["session"], "time": to_text(self.kernel.clock.now()),
        }  # fmt: skip
        copy.with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        self.sessions.send(workspace, target["port"], target["session"], text, actor=actor, files=files)
        self.kernel.events.record(
            "agents.annotated",
            summary=f"{actor.describe()} sent {relative} with {len(marks)} marks to {workspace}'s agent",
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={
                "workspace": workspace,
                "figure": relative,
                "annotation": shown,
                "marks": len(marks),
                "attached": attached,
            },
        )
        return {**target, "workspace": workspace, "annotation": shown, "text": text, "attached": attached}

    def workspace_of(self, folder: str) -> tuple[str, Path]:
        """The workspace of a folder and its folder; `AnnotationError` when it has none."""
        return self._workspace(folder)

    def _workspace(self, folder: str) -> tuple[str, Path]:
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        wanted = ntpath.normcase(str(Path(folder)))
        for record in workspaces.records():
            if ntpath.normcase(str(Path(record["path"]))) == wanted:
                return record["name"], Path(record["path"])
        raise AnnotationError(f"{folder} has no Clank workspace: run `clank` in it first")

    def _target(self, workspace: str) -> dict[str, Any]:
        """The session most recently active among the agents running in the workspace's container."""
        found: list[tuple[int, int, str]] = []
        for server in self.sessions.servers(workspace):
            for session in server["sessions"]:
                found.append(
                    (int(session.get("updated") or session.get("created") or 0), server["port"], session["id"])
                )
        if not found:
            raise AnnotationError(
                f"no agent runs in {workspace}: start it (the console's This folder page, a or c), then send again"
            )
        _, port, session = max(found)
        return {"port": port, "session": session}

    @staticmethod
    def _geometry(root: Path, relative: str, data: bytes) -> dict[str, Any] | None:
        """The figure's geometry, when Matplotlib saved it in the workspace and it is still this figure's."""
        kept = root.joinpath(".clank", "figures", *f"{relative}.json".split("/"))
        try:
            geometry: dict[str, Any] = json.loads(kept.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return geometry if geometry.get("sha256") == hashlib.sha256(data).hexdigest() else None


def compose(
    figure: str,
    copy: str,
    sentences: list[str],
    message: str,
    attached: bool,
    measured: bool,
    seen: str = "",
    *,
    about: str = "",
) -> str:
    """The message the agent receives: the figure (or a PDF's page, `about`) and its marked-up copy, each mark in words
    (and what the vision model saw in the copy, when the agent's model cannot see it), then the owner's words."""
    subject = about or f"the figure `{figure}`"
    lines = [f"About {subject}: my marked-up copy is `{copy}`" + (" (attached)." if attached else ".")]
    if sentences:
        lines += ["", "My marks:", *(f"- {sentence}" for sentence in sentences)]
        if not measured:
            lines.append(
                "(The figure's geometry is not known, so the marks are placed by where they are in the image.)"
            )
    if seen:
        lines += ["", "What the vision model sees at my marks:", seen]
    if message.strip():
        lines += ["", message.strip()]
    return "\n".join(lines)


def _decoded(image: str) -> bytes:
    """The marked-up copy, from a data URL or base64: a PNG."""
    raw = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        data = base64.b64decode(raw, validate=True)
    except ValueError as error:
        raise AnnotationError("the marked-up copy is not readable") from error
    if not data.startswith(PNG):
        raise AnnotationError("the marked-up copy is not a PNG")
    return data
