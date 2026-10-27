"""Design 0028 §6: Clank's VS Code window without building its extension. In a release install (no extension's sources
in Clank's folder), opening a folder takes the extension that the GitHub release of Clank's own version carries: it is
downloaded, its SHA-256 checked against the release's SHA256SUMS, kept under CLANK_HOME/vscode/cache and installed;
the next time, the kept copy is used without asking GitHub, once its SHA-256 is checked again. A file whose SHA-256 is
not the release's is refused, neither kept nor installed. No such release, a release without the extension or its
sums, or no answer from GitHub is said with what to do, and the folder opens all the same. A clone keeps its own build
and never asks GitHub. GitHub is the fake of `tests/fakes/github.py`, never the network."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank import registry, updates
from clank.components.agents import extension, vscode
from clank.components.agents.kinds import EXTENSIONS
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.github import FakeGitHub
from tests.fakes.platform import FakePlatform
from tests.support.vscode import asked, fake_vscode

YOU = Actor(kind="user", via="console")
TAG = "v0.3.0b3"
NAME = "clank-0.10.4.vsix"
VSIX = b"PK\x03\x04 Clank's extension, as tools.vsix packages it"
OTHER = b"PK\x03\x04 another file"


def sums(*files: tuple[str, bytes]) -> bytes:
    """SHA256SUMS as `sha256sum` writes it, and the release job (`tools/release.py`)."""
    return "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files).encode()


def released(github: FakeGitHub, tag: str, vsix: bytes = VSIX) -> None:
    """A release of `tag` carrying an extension (`vsix`), and SHA256SUMS giving the SHA-256 of the real one."""
    github.releases[tag] = {NAME: vsix, "SHA256SUMS": sums((NAME, VSIX))}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    """The fake GitHub, the one Clank's VS Code window asks; no release yet."""
    fake = FakeGitHub()
    monkeypatch.setattr(extension, "fetch", fake.fetch)
    monkeypatch.setattr(extension, "download", fake.download)
    return fake


@pytest.fixture
def release(kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake VS Code, in a release install: Clank's folder has no extension's sources, and none built; the file that
    keeps what the fake was asked."""
    state = fake_vscode(kernel, tmp_path, monkeypatch)
    monkeypatch.setattr(vscode, "clank_vsix", lambda: None)
    monkeypatch.setattr(vscode, "in_a_clone", lambda: False)
    return state


async def open_folder(kernel: Kernel, folder: Path) -> Operation:
    started = await kernel.operations.start("agents.vscode", {"folder": str(folder)}, actor=YOU)
    with anyio.fail_after(60):
        return await kernel.operations.wait(started.id)


def said(kernel: Kernel, done: Operation) -> list[str]:
    return [line.text for line in kernel.operations.log_lines(done.id)]


def test_a_releases_extension_is_downloaded_checked_kept_and_the_kept_copy_used_next_time(tmp_path: Path) -> None:
    github = FakeGitHub()
    released(github, TAG)
    cache = tmp_path / "cache"
    got = extension.release_vsix(cache, TAG, github.fetch, github.download)
    assert (got.path, got.downloaded) == (cache / TAG / NAME, True)
    assert got.path.read_bytes() == VSIX
    assert github.asked == [
        f"{updates.API}/releases/tags/{TAG}",
        FakeGitHub.address(TAG, "SHA256SUMS"),
        FakeGitHub.address(TAG, NAME),
    ]
    again = extension.release_vsix(cache, TAG, github.fetch, github.download)
    assert (again.path, again.downloaded) == (got.path, False)
    assert len(github.asked) == 3, "the kept copy is used: GitHub is not asked again"
    got.path.write_bytes(b"changed since it was kept")
    fresh = extension.release_vsix(cache, TAG, github.fetch, github.download)
    assert (fresh.downloaded, fresh.path.read_bytes()) == (True, VSIX), "a kept copy that no longer checks is not used"


def test_a_file_whose_sha256_is_not_the_releases_is_refused_and_not_kept(tmp_path: Path) -> None:
    github = FakeGitHub()
    released(github, TAG, vsix=OTHER)
    with pytest.raises(extension.ReleaseError) as refused:
        extension.release_vsix(tmp_path / "cache", TAG, github.fetch, github.download)
    assert f"{NAME} from the release {TAG} is refused" in refused.value.why
    assert hashlib.sha256(VSIX).hexdigest() in refused.value.why, "the SHA-256 the release gives"
    assert hashlib.sha256(OTHER).hexdigest() in refused.value.why, "and the file's"
    assert "SECURITY.md" in refused.value.todo
    assert not (tmp_path / "cache" / TAG / NAME).exists(), "never kept"


def test_no_release_one_without_the_extension_or_its_sums_and_no_network_each_say_why_and_what_to_do(
    tmp_path: Path,
) -> None:
    github = FakeGitHub()
    cache = tmp_path / "cache"

    def refused() -> extension.ReleaseError:
        with pytest.raises(extension.ReleaseError) as caught:
            extension.release_vsix(cache, TAG, github.fetch, github.download)
        return caught.value

    none = refused()
    assert f"GitHub has no release {TAG}" in none.why
    assert "clank update --check" in none.todo
    assert "step 2b" in none.todo
    github.releases[TAG] = {"SHA256SUMS": sums()}
    assert "carries no VS Code extension" in refused().why
    github.releases[TAG] = {NAME: VSIX}
    unchecked = refused()
    assert "no SHA256SUMS" in unchecked.why
    assert "cannot check" in unchecked.todo
    github.releases[TAG] = {NAME: VSIX, "SHA256SUMS": sums(("clank-0.10.3.vsix", VSIX))}
    assert f"does not list {NAME}" in refused().why
    released(github, TAG)
    github.offline = True
    offline = refused()
    assert "GitHub did not answer" in offline.why
    assert "getaddrinfo failed" in offline.why, "in the network's own words"
    assert "github.com" in offline.todo
    assert not cache.exists() or not any(cache.rglob("*.vsix")), "nothing kept"


@pytest.mark.anyio
async def test_in_a_release_install_the_releases_extension_is_installed_and_its_kept_copy_used_the_next_time(
    kernel: Kernel, release: Path, github: FakeGitHub, tmp_path: Path
) -> None:
    released(github, extension.TAG)
    folder = tmp_path / "paper"
    folder.mkdir()
    async with kernel.operations.running():
        done = await open_folder(kernel, folder)
        assert done.status == "done", done.error
        first = asked(release)
        again = await open_folder(kernel, folder)
        assert again.status == "done", again.error
        second = asked(release, 2)
    kept = kernel.home.root / "vscode" / "cache" / extension.TAG / NAME
    assert kept.read_bytes() == VSIX
    assert ["--install-extension", str(kept), "--force"] in [call[4:] for call in first["calls"]]
    assert first["installed"]["clank.clank"] == "0.10.4"
    assert done.result == {"folder": str(folder), "installed": ["clank.clank", *EXTENSIONS], "failed": []}
    lines = said(kernel, done)
    assert any(f"release {extension.TAG}" in line and "SHA256SUMS" in line for line in lines), lines
    assert len(github.asked) == 3, "the second time the kept copy is used, without asking GitHub"
    installs = [call for call in second["calls"] if "--install-extension" in call]
    assert len(installs) == 1 + len(EXTENSIONS), "the second time nothing is installed again"
    assert first["opened"] == [str(folder)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("situation", "why", "todo"),
    [
        ("refused", f"{NAME} from the release {extension.TAG} is refused", "SECURITY.md"),
        ("no release", f"GitHub has no release {extension.TAG}", "clank update --check"),
        ("offline", "GitHub did not answer", "github.com"),
    ],
)
async def test_a_refused_extension_no_release_or_no_network_is_said_and_the_folder_opens_all_the_same(
    kernel: Kernel, release: Path, github: FakeGitHub, tmp_path: Path, situation: str, why: str, todo: str
) -> None:
    if situation == "refused":
        released(github, extension.TAG, vsix=OTHER)
    elif situation == "offline":
        released(github, extension.TAG)
        github.offline = True
    async with kernel.operations.running():
        done = await open_folder(kernel, tmp_path)
    assert done.status == "done", done.error
    assert done.result is not None
    assert (done.result["installed"], done.result["failed"]) == (list(EXTENSIONS), ["clank.clank"])
    [line] = [line for line in said(kernel, done) if line.startswith("Clank's extension")]
    assert why in line, line
    assert todo in line, line
    assert "opens without the agent beside the files" in line, line
    state = asked(release)
    assert state["opened"] == [str(tmp_path)]
    assert "clank.clank" not in state["installed"]
    assert not any((kernel.home.root / "vscode" / "cache").rglob("*.vsix")), "nothing kept"


@pytest.mark.anyio
async def test_a_clone_uses_its_own_build_and_never_asks_github(
    kernel: Kernel, github: FakeGitHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = fake_vscode(kernel, tmp_path, monkeypatch)
    built = vscode.clank_vsix()
    assert built is not None
    released(github, extension.TAG)
    monkeypatch.setattr(vscode, "in_a_clone", lambda: True)
    monkeypatch.setattr(vscode, "clank_vsix", lambda: None)
    folder = tmp_path / "paper"
    folder.mkdir()
    async with kernel.operations.running():
        unbuilt = await open_folder(kernel, folder)
        assert unbuilt.status == "done", unbuilt.error
        asked(code)
        monkeypatch.setattr(vscode, "clank_vsix", lambda: built)
        done = await open_folder(kernel, folder)
        assert done.status == "done", done.error
        state = asked(code, 2)
    assert any("Clank's extension is not built" in line and "tools.vsix" in line for line in said(kernel, unbuilt))
    assert ["--install-extension", str(built), "--force"] in [call[4:] for call in state["calls"]]
    assert state["installed"]["clank.clank"] == "9.9.9", "the clone's own build"
    assert github.asked == [], "a clone never asks GitHub"
