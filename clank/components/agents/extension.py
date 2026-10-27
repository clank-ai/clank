"""Clank's VS Code extension in a release install (design 0028 §6): the one its release carries, checked and kept.

A clone builds its own extension (`tools.vsix`, found by `vscode.clank_vsix`). A release installed by the one-line
installer has no sources to build it from, so each release carries it, attached by CI with its SHA-256
(`tools/release.py`), and Clank's VS Code window takes it from there. `release_vsix` reads the release of Clank's own
version (`v` and its version) from GitHub's API, as `clank update` reads releases (`clank/updates.py`: its address,
its timeout), downloads the release's `clank-<version>.vsix` and its `SHA256SUMS`, and keeps the extension only when
its SHA-256 is the one SHA256SUMS gives, in `<cache>/<tag>/` beside that SHA256SUMS. The next time, the kept copy is
used without asking GitHub, once its SHA-256 is checked again. A file whose SHA-256 differs is refused and never kept.
No such release, a release without the extension or its sums, or no answer from GitHub raises `ReleaseError`, which
says why and what to do. Every call to GitHub goes through `fetch` and `download`, which the tests replace.
"""

import hashlib
import http.client
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clank import __version__, updates

TAG = f"v{__version__}"  # the release of Clank's own version
SUMS = "SHA256SUMS"
VSIX = re.compile(r"clank-(\d+\.\d+\.\d+)\.vsix")
LINE = re.compile(r"([0-9a-fA-F]{64}) [ *](.+)")  # a line of SHA256SUMS, as `sha256sum` writes it
AGENT = f"clank/{__version__} (VS Code extension)"
BUILD = "build it in a clone of Clank instead (getting started, step 2b)"
NEWER = f"a newer release carries it (`clank update --check` says whether one is out), or {BUILD}"
AGAIN = "it is tried again the next time, once this computer reaches github.com"
LATER = "it is tried again the next time"
UNCHECKED = f"Clank installs no extension it cannot check: {BUILD}"

Fetch = Callable[[str], Any]  # an address of GitHub's API; its JSON
Download = Callable[[str], bytes]  # the address of a file a release carries; its bytes


class ReleaseError(Exception):
    """Why the release's extension cannot be had (`why`), and what to do (`todo`)."""

    def __init__(self, why: str, todo: str) -> None:
        super().__init__(f"{why}; {todo}")
        self.why = why
        self.todo = todo


@dataclass(frozen=True)
class Kept:
    """The release's extension, checked, where it is kept; `downloaded` is False for a copy kept before."""

    path: Path
    downloaded: bool


def _open(url: str, accept: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": accept})
    return urllib.request.urlopen(request, timeout=updates.TIMEOUT)


def fetch(url: str) -> Any:
    """GitHub's API answer at `url`, read as JSON, as `clank update` reads it; `updates.TIMEOUT` seconds at most."""
    with _open(url, "application/vnd.github+json") as answer:
        return json.load(answer)


def download(url: str) -> bytes:
    """A file a release carries, at `url` (GitHub sends it from its storage, through a redirect); `updates.TIMEOUT`
    seconds at most for each read."""
    with _open(url, "application/octet-stream") as answer:
        data: bytes = answer.read()
    return data


def sha256(data: bytes) -> str:
    """The SHA-256 of `data`, in lowercase hexadecimal, as SHA256SUMS writes it."""
    return hashlib.sha256(data).hexdigest()


def listed(text: str) -> dict[str, str]:
    """Each file SHA256SUMS lists, by name, with its SHA-256."""
    found = (LINE.fullmatch(line.strip()) for line in text.splitlines())
    return {match.group(2).strip(): match.group(1).lower() for match in found if match is not None}


def kept(folder: Path) -> Path | None:
    """The extension kept in `folder`, when its SHA-256 is still the one its release's SHA256SUMS gave; else None."""
    try:
        sums = listed((folder / SUMS).read_bytes().decode("utf-8", errors="replace"))
        for name, digest in sums.items():
            path = folder / name
            if VSIX.fullmatch(name) and path.is_file() and sha256(path.read_bytes()) == digest:
                return path
    except OSError:
        pass
    return None


def release_vsix(cache: Path, tag: str = TAG, fetch: Fetch = fetch, download: Download = download) -> Kept:
    """The extension of the release `tag`, checked: the copy kept in `cache/<tag>`, else the release's, downloaded,
    checked against its SHA256SUMS and kept there. Raises `ReleaseError` saying why there is none."""
    folder = cache / tag
    found = kept(folder)
    if found is not None:
        return Kept(found, downloaded=False)
    assets = _assets(tag, fetch)
    name = next((each for each in assets if VSIX.fullmatch(each)), None)
    if name is None:
        raise ReleaseError(
            f"the release {tag} on GitHub carries no VS Code extension (it was made before releases carried one)", NEWER
        )
    if SUMS not in assets:
        raise ReleaseError(f"the release {tag} on GitHub has no SHA256SUMS to check {name} against", UNCHECKED)
    sums = _download(download, assets[SUMS], tag)
    expected = listed(sums.decode("utf-8", errors="replace")).get(name)
    if expected is None:
        raise ReleaseError(f"the release {tag}'s SHA256SUMS does not list {name}", UNCHECKED)
    data = _download(download, assets[name], tag)
    if (actual := sha256(data)) != expected:
        raise ReleaseError(
            f"{name} from the release {tag} is refused: its SHA-256 is {actual}, not the {expected} the release's "
            "SHA256SUMS gives, so it was neither kept nor installed",
            "it is downloaded again the next time, and if it is refused again, please report it (SECURITY.md)",
        )
    try:
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / f"{name}.part"
        part.write_bytes(data)
        os.replace(part, folder / name)
        (folder / SUMS).write_bytes(sums)
    except OSError as error:
        raise ReleaseError(f"{name} could not be kept in {folder} ({error})", LATER) from error
    return Kept(folder / name, downloaded=True)


def _assets(tag: str, fetch: Fetch) -> dict[str, str]:
    """The files the release `tag` carries, by name, with the HTTPS address each downloads from."""
    try:
        release = fetch(f"{updates.API}/releases/tags/{tag}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ReleaseError(f"GitHub has no release {tag} of Clank to take it from", NEWER) from error
        raise ReleaseError(
            f"GitHub's API answered {error.code} ({error.reason}) about the release {tag}", LATER
        ) from error
    except (OSError, http.client.HTTPException) as error:
        raise ReleaseError(f"GitHub did not answer ({error})", AGAIN) from error
    except ValueError as error:
        raise ReleaseError(f"GitHub's answer about the release {tag} could not be read ({error})", LATER) from error
    try:
        files = {str(each["name"]): str(each["browser_download_url"]) for each in release["assets"]}
    except (KeyError, TypeError) as error:
        raise ReleaseError(f"GitHub's answer about the release {tag} could not be read ({error})", LATER) from error
    return {name: url for name, url in files.items() if url.startswith("https://")}


def _download(download: Download, url: str, tag: str) -> bytes:
    """A file of the release `tag`, or `ReleaseError` saying why GitHub did not send it."""
    try:
        return download(url)
    except (OSError, http.client.HTTPException) as error:
        name = url.rsplit("/", 1)[-1]
        raise ReleaseError(f"GitHub did not send {name} of the release {tag} ({error})", AGAIN) from error
