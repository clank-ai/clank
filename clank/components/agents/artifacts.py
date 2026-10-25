"""Artifacts (design 0021 §5): pages the agent makes for the owner (an interactive plot of results, a parameter
explorer, an explainer, a report, a diagram), kept as versions in the folder and shown in VS Code, the owner's comments
sent back to the agent. Nothing leaves the PC: a page may use the libraries Clank keeps (decision 0135), named
`clank-lib/<file>`, and the files of its own version, never the network.

**Its files are its state.** `.clank/artifacts/<name>/artifact.json` keeps its title, its kind and every version (when
it was made, its entry page, its files, the agent's note, the session that made it); `v<n>/` holds that version's
files, copied from the folder when the agent made it, keeping their layout from their common folder, so a page's
relative paths (`../results/sweep.json`) still work. A Markdown artifact gets Clank's page beside it (`index.html`,
`MARKDOWN`: its text rendered by marked, its math by KaTeX), and so does an SVG one (`SVG`); an HTML one is its own
page.

Refused, saying why: a name that is not lowercase letters, digits and dashes; a kind other than html, markdown or svg;
no file, a file that is not the folder's (or is Clank's own, under `.clank/`), more than `MOST_FILES` files or more than
`MOST_BYTES` in all; a first file that is not a page of its kind; and an entry page that names the network (a source, a
link, a style or a fetch at `http://`, `https://` or `//`).
"""

import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from clank.kernel.clock import to_text
from clank.kernel.events import CLANK, Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.sessions import Sessions
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

FOLDER = ".clank/artifacts"
CONTAINER = "/workspace/"
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
KINDS = {"html": (".html", ".htm"), "markdown": (".md", ".markdown"), "svg": (".svg",)}
MOST_FILES = 50
MOST_BYTES = 20 * 1024 * 1024
NETWORK = re.compile(
    r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*(?:https?:)?//)"""
    r"""|(?:url\(\s*["']?\s*(?:https?:)?//)|(?:@import\s+["'](?:https?:)?//)"""
    r"""|(?:\b(?:fetch|open|WebSocket|EventSource)\s*\(\s*["'`](?:https?|wss?):)""",
    re.IGNORECASE,
)
EVENT_TYPES = [
    EventType(
        "agents.artifact_made",
        "The agent made an artifact, or a new version of one (design 0021 §5).",
        {
            "workspace": "The workspace.", "folder": "Its folder, on this machine.", "name": "The artifact's name.",
            "title": "Its title.", "kind": "html, markdown or svg.", "version": "The version made.",
            "entry": "Its page, from the folder.",
        },
    ),
    EventType(
        "agents.artifact_commented",
        "The owner commented on a version of an artifact, sent to the session that made it (design 0021 §5).",
        {"workspace": "The workspace.", "name": "The artifact's name.", "version": "The version commented on."},
    ),
]  # fmt: skip
MARKDOWN = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="clank-lib/katex.min.css">
<script src="clank-lib/marked.min.js"></script>
<script src="clank-lib/katex.min.js"></script>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.55; }}
pre {{ overflow: auto; padding: .6rem; background: rgba(127, 127, 127, .12); }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid rgba(127, 127, 127, .4); padding: .2rem .5rem; }}
</style>
</head>
<body>
<main id="page"></main>
<script>
// Clank's page for a Markdown artifact (design 0021 §5): math is set aside before marked reads the text (so its
// underscores stay math), then drawn by KaTeX in its place.
const source = {source};
const math = [];
const MATH = /\\$\\$([\\s\\S]+?)\\$\\$|\\\\\\[([\\s\\S]+?)\\\\\\]|\\$([^$\\n]+?)\\$|\\\\\\(([\\s\\S]+?)\\\\\\)/g;
const kept = source.replace(MATH, (whole, display, bracket, inline, paren) => {{
  const shown = display !== undefined || bracket !== undefined;
  math.push({{ text: display ?? bracket ?? inline ?? paren, display: shown }});
  return `@@MATH${{math.length - 1}}@@`;
}});
const page = document.getElementById("page");
page.innerHTML = marked.parse(kept).replace(/@@MATH(\\d+)@@/g, (whole, index) => {{
  const each = math[Number(index)];
  return katex.renderToString(each.text, {{ displayMode: each.display, throwOnError: false }});
}});
</script>
</body>
</html>
"""
SVG = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title>
<style>body {{ margin: 0; display: flex; justify-content: center; }} img {{ max-width: 100%; }}</style></head>
<body><img src="{svg}" alt="{title}"></body>
</html>
"""


class ArtifactError(Exception):
    """An artifact that cannot be made, found or commented on, and why."""


class Artifacts:
    """The artifacts the agents make, in their workspaces' folders."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions") -> None:
        self.kernel = kernel
        self.sessions = sessions

    def make(
        self, workspace: str, name: str, title: str, kind: str, files: list[str], *, note: str = "",
        session: str = "",
    ) -> dict[str, Any]:  # fmt: skip
        """Make an artifact's next version from files of the folder (module docstring); its version, its entry page
        (from the folder) and the words for the model."""
        if not NAME.fullmatch(name):
            raise ArtifactError("a name is lowercase letters, digits and dashes, at most 48 (as in sweep-results)")
        if kind not in KINDS:
            raise ArtifactError("a kind is html, markdown or svg")
        title = " ".join(title.split()) or name
        folder = self._folder(workspace)
        paths = [self._file(folder, each) for each in files]
        if not paths:
            raise ArtifactError("the artifact names no file: name its page first, then the files it reads")
        if len(paths) > MOST_FILES or sum(path.stat().st_size for path in paths) > MOST_BYTES:
            raise ArtifactError(f"an artifact holds at most {MOST_FILES} files and {MOST_BYTES >> 20} MB in all")
        if paths[0].suffix.lower() not in KINDS[kind]:
            raise ArtifactError(f"its first file is its page: a {kind} file ({', '.join(KINDS[kind])})")
        if NETWORK.search(paths[0].read_text(encoding="utf-8", errors="replace")):
            raise ArtifactError(
                f"{paths[0].name} names the network: an artifact uses only its own files and Clank's libraries "
                "(clank-lib/plotly.min.js, katex.min.js, katex.min.css, marked.min.js, mermaid.min.js)"
            )
        home = folder / FOLDER / name
        kept = self._kept(home) or {"name": name, "title": title, "kind": kind, "versions": []}
        number = len(kept["versions"]) + 1
        target = home / f"v{number}"
        root = Path(os.path.commonpath([str(path.parent) for path in paths]))
        for path in paths:
            copied = target / path.relative_to(root)
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, copied)
        entry = paths[0].relative_to(root).as_posix()
        if kind != "html":
            page = MARKDOWN if kind == "markdown" else SVG
            text = paths[0].read_text(encoding="utf-8", errors="replace")
            source = json.dumps(text).replace("</", "<\\/")
            (target / "index.html").write_text(
                page.format(title=_escaped(title), source=source, svg=_escaped(entry)), encoding="utf-8"
            )
            entry = "index.html"
        kept.update(title=title, kind=kind)
        kept["versions"].append({"version": number, "made": to_text(self.kernel.clock.now()), "entry": entry,
                                 "files": [path.relative_to(root).as_posix() for path in paths], "note": note.strip(),
                                 "session": session})  # fmt: skip
        home.mkdir(parents=True, exist_ok=True)
        (home / "artifact.json").write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
        shown = f"{FOLDER}/{name}/v{number}/{entry}"
        self.kernel.events.record(
            "agents.artifact_made", summary=f"{workspace}: the artifact {title} ({name}), version {number}",
            actor=CLANK, subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "folder": str(folder), "name": name, "title": title, "kind": kind,
                  "version": number, "entry": shown},
        )  # fmt: skip
        said = (
            f"Artifact {title} ({name}), version {number}, made: it opens in the owner's VS Code window, beside you. "
            "The owner may comment on it; a comment comes to you naming its version. To change it, write its files "
            f"again and call make_artifact with the name {name}: that makes version {number + 1}."
        )
        return {"name": name, "version": number, "entry": shown, "said": said}

    def list(self, workspace: str) -> list[dict[str, Any]]:
        """The workspace's artifacts, the newest made first: each one's name, title, kind and versions."""
        root = self._folder(workspace) / FOLDER
        found = [kept for each in sorted(root.glob("*")) if (kept := self._kept(each)) is not None]
        brief = [
            {"name": kept["name"], "title": kept["title"], "kind": kept["kind"], "versions": len(kept["versions"]),
             "made": kept["versions"][-1]["made"]}
            for kept in found
        ]  # fmt: skip
        return sorted(brief, key=lambda each: str(each["made"]), reverse=True)

    def one(self, workspace: str, name: str) -> dict[str, Any]:
        """An artifact whole: its title, kind and every version, with the folder it is in."""
        folder = self._folder(workspace)
        kept = self._kept(folder / FOLDER / name) if NAME.fullmatch(name) else None
        if kept is None:
            raise ArtifactError(f"{workspace} has no artifact {name!r}")
        return {**kept, "workspace": workspace, "folder": str(folder), "home": f"{FOLDER}/{name}"}

    def comment(self, workspace: str, name: str, version: int, text: str, *, actor: Actor) -> dict[str, Any]:
        """Send the owner's comment on a version to the session that made it, in one message."""
        kept = self.one(workspace, name)
        made = next((each for each in kept["versions"] if each["version"] == version), None)
        if made is None:
            raise ArtifactError(f"the artifact {name} has no version {version}")
        session = str(made.get("session") or "")
        port = self.sessions.runs(workspace, session) if session else None
        if port is None:
            raise ArtifactError(
                f"no session of the agent's that made {name} version {version} runs now: start the agent, then send "
                "the comment again"
            )
        where = f"{CONTAINER}{FOLDER}/{name}/v{version}/"
        message = (
            f"The owner commented on the artifact {kept['title']} ({name}, version {version}):\n\n{text.strip()}\n\n"
            f"Its files are in {where}. To answer, change its files and call make_artifact with the name {name}: "
            f"that makes version {len(kept['versions']) + 1}."
        )
        self.sessions.send(workspace, port, session, message, actor=actor)
        self.kernel.events.record(
            "agents.artifact_commented", summary=f"{workspace}: a comment on {kept['title']} ({name}), version "
            f"{version}", actor=actor, subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "name": name, "version": version},
        )  # fmt: skip
        return {"said": f"Your comment on {name} version {version} was sent to the session that made it."}

    def _folder(self, workspace: str) -> Path:
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        try:
            return Path(workspaces.folder_of(workspace))
        except Exception as error:  # the workspaces' own refusal: no such workspace
            raise ArtifactError(f"there is no workspace {workspace!r}") from error

    @staticmethod
    def _file(folder: Path, named: str) -> Path:
        """A file of the folder, named from it or under `/workspace/`; `ArtifactError` for any other."""
        relative = named[len(CONTAINER) :] if named.startswith(CONTAINER) else named
        parts = PurePosixPath(relative.replace("\\", "/")).parts
        path = folder.joinpath(*parts)
        inside = path.resolve().is_relative_to(folder.resolve()) and ".." not in parts and parts[:1] != (".clank",)
        if not parts or not inside or not path.is_file():
            raise ArtifactError(f"{named} is not a file of the folder")
        return path

    @staticmethod
    def _kept(home: Path) -> dict[str, Any] | None:
        try:
            found: dict[str, Any] = json.loads((home / "artifact.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return found


def _escaped(text: str) -> str:
    """Text for an HTML page."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
