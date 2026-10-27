"""Design 0028 §6: each version tag's GitHub release carries Clank's VS Code extension. CI's release job makes it with
`tools.release` once the checks passed on the tag: it attaches the extension as `tools.vsix` packaged it and
SHA256SUMS, its SHA-256 as `sha256sum` writes it; a tag with a, b or rc makes a pre-release; the release's title and
notes are the version's section of CHANGELOG.md, its links into the repository pointing at the files at the tag, or a
link to CHANGELOG.md when there is no such section. A tag that is not Clank's own version, or an extension not
packaged, makes no release; a dry run says the command and runs nothing. GitHub's command line is replaced by a runner
that keeps what it was asked."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from tools import release

EXTENSION = b"PK\x03\x04 the extension, as tools.vsix packages it"
CHANGELOG = """# Changelog

Every version of Clank, newest first.

## Unreleased: since 0.3.0b3

- Something after it.

## 0.3.0b3: the extension in each release (2026-10-28)

The third public beta.

### Added

- **Clank's VS Code window without Node**: see [getting started](docs/getting-started.md#2b-clanks-vs-code-extension),
  [the issues](/docs/ISSUES.md) and [the home page](https://clank-ai.github.io/), or [above](#changelog).

## 0.3.0b2: the installer (2026-10-27)

- Older.
"""


class Gh:
    """GitHub's command line, as the tool runs it: every command kept, each answered with `status`."""

    def __init__(self, status: int = 0) -> None:
        self.status = status
        self.ran: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> int:
        self.ran.append(list(command))
        return self.status


def repository(tmp_path: Path) -> Path:
    """Clank's folder once `tools.vsix` packaged the extension (version 0.10.4), with its changelog."""
    root = tmp_path / "clank"
    (root / "vscode").mkdir(parents=True)
    (root / "vscode" / "package.json").write_text(json.dumps({"name": "clank", "version": "0.10.4"}), encoding="utf-8")
    (root / "vscode" / "clank-0.10.4.vsix").write_bytes(EXTENSION)
    (root / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    return root


def test_a_beta_tags_release_carries_the_extension_and_its_sha256_and_is_a_prerelease(tmp_path: Path) -> None:
    root = repository(tmp_path)
    gh = Gh()
    assert release.main(["v0.3.0b3"], root=root, version="0.3.0b3", runner=gh) == 0
    out = root / "dist" / "release"
    assert gh.ran == [
        ["gh", "release", "create", "v0.3.0b3", str(root / "vscode" / "clank-0.10.4.vsix"), str(out / "SHA256SUMS"),
         "--title", "Clank 0.3.0b3: the extension in each release (2026-10-28)", "--notes-file", str(out / "notes.md"),
         "--verify-tag", "--prerelease"],
    ]  # fmt: skip
    digest = hashlib.sha256(EXTENSION).hexdigest()
    assert (out / "SHA256SUMS").read_bytes() == f"{digest}  clank-0.10.4.vsix\n".encode(), "as sha256sum writes it"
    notes = (out / "notes.md").read_text(encoding="utf-8")
    assert notes.startswith("The third public beta.\n\n### Added\n")
    assert "Something after it" not in notes, "the tag's own section only"
    assert "Older" not in notes, "the tag's own section only"
    at = "https://github.com/clank-ai/clank/blob/v0.3.0b3"
    assert f"[getting started]({at}/docs/getting-started.md#2b-clanks-vs-code-extension)" in notes
    assert f"[the issues]({at}/docs/ISSUES.md)" in notes
    assert "[the home page](https://clank-ai.github.io/)" in notes, "a link outside the repository is kept"
    assert "[above](#changelog)" in notes
    assert "- **Clank's VS Code window without Node**: see [getting started]" in notes
    assert "#2b-clanks-vs-code-extension), [the issues]" in notes, "a list item on one line: GitHub shows line breaks"
    assert release.main(["v0.3.0b3"], root=root, version="0.3.0b3", runner=Gh(status=1)) == 1, "gh's failure is said"


WRAPPED = """## 0.4.0

A paragraph
wrapped in two.

- An item
  wrapped.
- Another.

```
clank code
clank work
```

| a | b |
| --- | --- |
"""


def test_the_notes_keep_each_paragraph_and_list_item_on_one_line_and_code_as_written() -> None:
    assert release.notes(WRAPPED, "v0.4.0")[1] == (
        "A paragraph wrapped in two.\n\n- An item wrapped.\n- Another.\n\n```\nclank code\nclank work\n```\n\n"
        "| a | b |\n| --- | --- |\n"
    )


@pytest.mark.parametrize(
    ("tag", "pre"),
    [("v0.3.0b3", True), ("v0.4.0a1", True), ("v0.4.0rc2", True), ("v0.4.0", False), ("v1.0", False)],
)
def test_a_tag_with_a_b_or_rc_is_a_prerelease(tag: str, pre: bool) -> None:
    assert release.prerelease(tag) is pre


def test_a_final_versions_release_is_not_a_prerelease_and_without_its_section_the_notes_link_to_the_changelog(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    gh = Gh()
    assert release.main(["v0.4.0"], root=root, version="0.4.0", runner=gh) == 0
    [command] = gh.ran
    assert "--prerelease" not in command
    assert command[command.index("--title") + 1] == "Clank 0.4.0"
    notes = (root / "dist" / "release" / "notes.md").read_text(encoding="utf-8")
    assert "(https://github.com/clank-ai/clank/blob/v0.4.0/CHANGELOG.md)" in notes


def test_a_tag_that_is_not_clanks_version_or_an_extension_not_packaged_makes_no_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    gh = Gh()
    assert release.main(["v0.3.0b4"], root=root, version="0.3.0b3", runner=gh) == 1
    assert "not Clank's version (v0.3.0b3" in capsys.readouterr().err
    (root / "vscode" / "clank-0.10.4.vsix").unlink()
    assert release.main(["v0.3.0b3"], root=root, version="0.3.0b3", runner=gh) == 1
    assert "tools.vsix" in capsys.readouterr().err
    assert gh.ran == []


def test_a_dry_run_says_the_command_and_the_notes_and_runs_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    gh = Gh()
    assert release.main(["v0.3.0b3", "--dry-run"], root=root, version="0.3.0b3", runner=gh) == 0
    assert gh.ran == []
    said = capsys.readouterr().out
    assert "gh release create v0.3.0b3" in said
    assert "--prerelease" in said
    assert "The third public beta." in said
