"""Make the GitHub release of a version tag, with Clank's VS Code extension attached (design 0028 §6).

CI's release job (`.github/workflows/checks.yml`) runs `uv run python -m tools.release <tag>` when a tag `v*` is pushed
and every check passed on it, once `tools.extension` has compiled and tested the extension and `tools.vsix` packaged it.
The tag must be Clank's own version (`v` and `clank.__version__`): `clank code`, in a release install, reads the release
of that tag (`clank/components/agents/extension.py`). The release carries the extension as `tools.vsix` wrote it
(`clank-<the extension's version>.vsix`) and `SHA256SUMS`, its SHA-256 as `sha256sum` writes it, which `clank code`
checks a download against. A tag with a, b or rc (`v0.3.0b3`) makes a pre-release. The release's title and notes are the
version's section of CHANGELOG.md, its heading and its text, each link into the repository made to point at the file at
the tag (a release's page is not in the repository's tree, so a relative link would lead nowhere) and each paragraph
and list item on one line (GitHub shows a release's line breaks as written), or a link to CHANGELOG.md when it has no
such section. The two files are written to `dist/release/`, then GitHub's command line makes
the release (`gh release create`, with the job's token; `--verify-tag` refuses a tag that is not on GitHub).
`--dry-run` writes the files and prints the command and the notes, and runs nothing.
"""

import hashlib
import io
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from clank import __version__
from clank.updates import REPO, VERSION

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("dist") / "release"
SUMS = "SHA256SUMS"
INSIDE = re.compile(r"\]\((?![a-zA-Z][a-zA-Z0-9+.-]*:|#)/?([^)\s]+)\)")  # a link's target in the repository
BLOCK = re.compile(r"\s*(?:[-*+] |\d+[.)] |#|>|\|)")  # a line that begins a block: an item, a heading, a quote, a row
Runner = Callable[[Sequence[str]], int]


def run(command: Sequence[str]) -> int:
    """Run one command, its output going straight to the job's log; its exit status."""
    return subprocess.run(list(command), check=False).returncode


def prerelease(tag: str) -> bool:
    """Whether a tag is a pre-release's: an alpha, a beta or a release candidate (`v0.3.0b3`), read as `clank update`
    reads versions."""
    found = VERSION.fullmatch(tag)
    return found is not None and found.group(4) is not None


def notes(changelog: str, tag: str) -> tuple[str, str]:
    """The release's title and notes: the version's section of the changelog, else a link to the changelog."""
    version = tag.removeprefix("v")
    heading = re.compile(rf"## {re.escape(version)}(?=:|\s|$)")
    lines = changelog.splitlines()
    for start, line in enumerate(lines):
        if heading.match(line):
            end = next((n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
            text = "\n".join(lines[start + 1 : end]).strip()
            text = unwrapped(INSIDE.sub(lambda link: f"]({REPO}/blob/{tag}/{link.group(1)})", text))
            return f"Clank {line.removeprefix('## ').strip()}", text + "\n"
    return f"Clank {version}", f"What {tag} brings is in [CHANGELOG.md]({REPO}/blob/{tag}/CHANGELOG.md).\n"


def unwrapped(text: str) -> str:
    """The text with each paragraph and each list item on one line, since GitHub shows a release's line breaks as they
    are written (the changelog is wrapped at 120 columns); code between fences, headings and tables stay as written."""
    lines: list[str] = []
    continued = False  # whether the line before is a paragraph's or a list item's, which the next line may continue
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            lines.append(line)
            continued = False
        elif fenced or not line.strip():
            lines.append(line)
            continued = False
        elif continued and not BLOCK.match(line):
            lines[-1] = f"{lines[-1]} {line.strip()}"
        else:
            lines.append(line)
            continued = not line.lstrip().startswith(("#", "|", ">"))
    return "\n".join(lines)


def sums(files: Sequence[Path]) -> str:
    """SHA256SUMS: each file's SHA-256 and its name, as `sha256sum` writes them."""
    return "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)


def main(
    argv: Sequence[str] | None = None, *, root: Path = ROOT, version: str = __version__, runner: Runner = run
) -> int:
    """Make the release of the tag named (with `--dry-run`, say it); 1 when it cannot be made."""
    args = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in args
    tags = [arg for arg in args if not arg.startswith("--")]
    if len(tags) != 1:
        print("usage: python -m tools.release TAG [--dry-run]", file=sys.stderr)
        return 1
    tag = tags[0]
    if tag != f"v{version}":
        print(
            f"{tag} is not Clank's version (v{version}, set in clank/__init__.py), whose release `clank code` reads: "
            f"set the version, or tag v{version}",
            file=sys.stderr,
        )
        return 1
    package = json.loads((root / "vscode" / "package.json").read_text(encoding="utf-8"))
    vsix = root / "vscode" / f"{package['name']}-{package['version']}.vsix"
    if not vsix.is_file():
        print(f"vscode/{vsix.name} is not packaged: run `uv run python -m tools.vsix` first", file=sys.stderr)
        return 1
    title, text = notes((root / "CHANGELOG.md").read_text(encoding="utf-8"), tag)
    out = root / OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    (out / SUMS).write_text(sums([vsix]), encoding="utf-8", newline="\n")
    (out / "notes.md").write_text(text, encoding="utf-8", newline="\n")
    command = ["gh", "release", "create", tag, str(vsix), str(out / SUMS), "--title", title,
               "--notes-file", str(out / "notes.md"), "--verify-tag"]  # fmt: skip
    if prerelease(tag):
        command.append("--prerelease")
    if dry:
        print(
            f"Would run: {shlex.join(command)}\n\n{SUMS}:\n{(out / SUMS).read_text(encoding='utf-8')}\nNotes:\n{text}"
        )
        return 0
    return 1 if runner(command) != 0 else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")  # the notes' marks (●) in a console that cannot show them
    sys.exit(main())
