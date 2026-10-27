"""Design 0026 §1 and §2 (decision 0145): what is installed, read from uv's record of the tool (a release from GitHub at
a tag, a clone installed editable, another way); what is newer (the latest release, or the commits a clone's branch is
behind, with whether its tree has changes of its own); and what updating does: a clone with changes of its own is
refused, a clone whose pull touches no dependency pulls and starts the service again, a release (or a clone whose
dependencies changed) is installed by a helper that runs after `clank update` ended, written where the owner can read
it; a dry run says each step and changes nothing; no answer from GitHub is said, never taken for "up to date"."""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from clank import updates
from clank.cli.update import update


def receipt(folder: Path, requirement: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "uv-receipt.toml").write_text(f"[tool]\nrequirements = [{requirement}]\n", encoding="utf-8")
    return folder


class Git:
    """A clone's git as `updates` asks it: each command's answer, by its first words; every command kept."""

    def __init__(self, answers: dict[str, tuple[int, str]]) -> None:
        self.answers = answers
        self.ran: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str) -> tuple[int, str]:
        self.ran.append(argv)
        line = " ".join(argv)
        for start, answer in self.answers.items():
            if line.startswith(start):
                return answer
        return 0, ""


BEHIND = {
    "git rev-parse --abbrev-ref --symbolic-full-name @{u}": (0, "origin/main\n"),
    "git rev-parse --abbrev-ref HEAD": (0, "main\n"),
    "git rev-list --count HEAD..@{u}": (0, "2\n"),
    "git log": (0, "a1b2c3d agents: a fix\nd4e5f6a docs: a page\n"),
    "git diff --name-only HEAD @{u}": (0, "clank/agents.py\ndocs/x.md\n"),
    "git status --porcelain": (0, ""),
    "git remote get-url origin": (0, "https://github.com/clank-ai/clank.git\n"),
}


def test_how_clank_was_installed_is_read_from_uvs_record_of_the_tool(tmp_path: Path) -> None:
    clone = receipt(tmp_path / "a", '{ name = "clank", editable = "C:/LocalAI/clank-public" }')
    found = updates.installed(prefix=clone, run=Git({}))
    assert (found.kind, found.where) == ("clone", "C:/LocalAI/clank-public")
    release = receipt(tmp_path / "b", '{ name = "clank", git = "https://github.com/clank-ai/clank?tag=v0.3.0b1" }')
    assert updates.installed(prefix=release, run=Git({})).kind == "release"
    other = receipt(tmp_path / "c", '{ name = "clank", directory = "D:/somewhere" }')
    assert updates.installed(prefix=other, run=Git({})).kind == "other"
    none = updates.installed(
        prefix=tmp_path / "none", run=Git({"git rev-parse --show-toplevel": (0, "C:/src/clank\n")})
    )
    assert (none.kind, none.where) == ("clone", "C:/src/clank"), "run from a working copy (uv run), no receipt"


def test_a_releases_newer_version_comes_from_githubs_latest_release_and_no_answer_is_said() -> None:
    install = updates.Install("release", "0.3.0b1", "v0.3.0b1", "")

    def fetch(url: str) -> Any:
        assert url == f"{updates.API}/releases/latest"
        return {"tag_name": "v0.3.1"}

    found = updates.newer(install, run=Git({}), fetch=fetch)
    assert (found["latest"], found["newer"]) == ("v0.3.1", True)
    assert "api.github.com" in found["contacted"]

    def silent(url: str) -> Any:
        raise TimeoutError("timed out")

    quiet = updates.newer(install, run=Git({}), fetch=silent)
    assert quiet["newer"] is None
    assert "did not answer" in quiet["error"]
    assert (
        updates.newer(updates.Install("release", "0.3.1", "", ""), Git({}), lambda url: {"tag_name": "v0.3.1"})["newer"]
        is False
    )
    assert updates.later("0.3.0", "0.3.0b1"), "a final version after its pre-releases"
    assert updates.later("0.10.0", "0.9.9"), "by number, not by text"
    assert not updates.later("0.3.0b1", "0.3.0")


def test_a_clone_says_how_far_its_branch_is_behind_and_whether_its_tree_has_changes_of_its_own() -> None:
    install = updates.Install("clone", "0.3.0b1", "C:/LocalAI/clank-public", "")
    git = Git(BEHIND)
    found = updates.newer(install, run=git, fetch=lambda url: {})
    assert ["git", "fetch", "--quiet"] in git.ran, "the clone's remote is asked first"
    assert (found["behind"], found["newer"], found["dirty"]) == (2, True, False)
    assert found["titles"] == ["a1b2c3d agents: a fix", "d4e5f6a docs: a page"]
    assert (found["dependencies"], found["extension"]) == (False, False)
    assert "github.com/clank-ai/clank" in found["contacted"]


def test_updating_a_clone_with_changes_of_its_own_is_refused_and_one_without_pulls_and_restarts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install = updates.Install("clone", "0.3.0b1", "C:/LocalAI/clank-public", "")
    dirty = Git({**BEHIND, "git status --porcelain": (0, " M clank/x.py\n")})
    monkeypatch.setattr(updates, "installed", lambda **_: install)
    monkeypatch.setattr(updates, "run", dirty)
    refused = CliRunner().invoke(update, [])
    assert refused.exit_code == 1
    assert "changes of its own" in refused.output
    assert ["git", "pull", "--ff-only"] not in dirty.ran
    clean = Git(BEHIND)
    restarted: list[str] = []
    monkeypatch.setattr(updates, "run", clean)

    def restart() -> bool:
        restarted.append("restarted")
        return True

    monkeypatch.setattr(updates, "restart_service", restart)
    done = CliRunner().invoke(update, [])
    assert done.exit_code == 0, done.output
    assert ["git", "pull", "--ff-only"] in clean.ran
    assert restarted == ["restarted"]
    assert "a1b2c3d agents: a fix" in done.output


def test_a_release_is_installed_by_a_helper_after_clank_update_ends_and_a_dry_run_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install = updates.Install("release", "0.3.0b1", "v0.3.0b1", "")
    monkeypatch.setattr(updates, "installed", lambda **_: install)
    monkeypatch.setattr(updates, "fetch", lambda url: {"tag_name": "v0.3.1"})
    monkeypatch.setenv("CLANK_HOME", str(tmp_path / "home"))
    started: list[Path] = []
    stopped: list[str] = []
    monkeypatch.setattr(updates, "stop_running", lambda: stopped.append("stopped"))
    monkeypatch.setattr(updates, "start_helper", lambda script: started.append(script))
    dry = CliRunner().invoke(update, ["--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "git+https://github.com/clank-ai/clank@v0.3.1" in dry.output
    assert (started, stopped) == ([], []), "a dry run changes nothing"
    done = CliRunner().invoke(update, [])
    assert done.exit_code == 0, done.output
    assert stopped == ["stopped"], "the service and the gateway stopped first: their files are the tool's"
    [script] = started
    text = script.read_text(encoding="utf-8")
    assert (
        "uv tool install --force --reinstall-package clank --python 3.12 git+https://github.com/clank-ai/clank@v0.3.1"
        in text
    )
    assert "core.longpaths" in text
    assert "serve --background" in text
    assert "update.log" in done.output


def test_check_says_what_is_installed_what_is_newer_and_what_it_contacted(monkeypatch: pytest.MonkeyPatch) -> None:
    install = updates.Install("release", "0.3.0b1", "v0.3.0b1", "")
    monkeypatch.setattr(updates, "installed", lambda **_: install)
    monkeypatch.setattr(updates, "fetch", lambda url: {"tag_name": "v0.3.1"})
    said = CliRunner().invoke(update, ["--check"])
    assert said.exit_code == 0, said.output
    assert "0.3.0b1" in said.output
    assert "v0.3.1" in said.output
    assert "api.github.com" in said.output
    as_json = json.loads(CliRunner().invoke(update, ["--check", "--json"]).output)
    assert as_json["install"]["kind"] == "release"
    assert as_json["newer"]["latest"] == "v0.3.1"
