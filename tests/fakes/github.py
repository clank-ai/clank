"""A fake of GitHub, for Clank's calls to it about releases: its API's answer about a release by its tag (`fetch`) and
the files the release carries (`download`), from what a test gives it, never the network. It keeps every address
asked, in order. A tag it has no release of is answered 404, as GitHub answers; offline, every call fails as it fails on
a computer without a network."""

import email.message
import urllib.error
from typing import Any

from clank import updates


class FakeGitHub:
    """Releases by tag, each with its files by name; every address asked."""

    def __init__(self) -> None:
        self.releases: dict[str, dict[str, bytes]] = {}
        self.asked: list[str] = []
        self.offline = False

    @staticmethod
    def address(tag: str, name: str) -> str:
        """Where a file of a release downloads from, as the API names it (`browser_download_url`)."""
        return f"{updates.REPO}/releases/download/{tag}/{name}"

    def fetch(self, url: str) -> Any:
        """The API's answer about the release of a tag: its tag, its page and its files."""
        self._asked(url)
        prefix = f"{updates.API}/releases/tags/"
        tag = url.removeprefix(prefix)
        if not url.startswith(prefix) or tag not in self.releases:
            raise urllib.error.HTTPError(url, 404, "Not Found", email.message.Message(), None)
        assets = [
            {"name": name, "size": len(data), "browser_download_url": self.address(tag, name)}
            for name, data in self.releases[tag].items()
        ]
        return {"tag_name": tag, "html_url": f"{updates.REPO}/releases/tag/{tag}", "assets": assets}

    def download(self, url: str) -> bytes:
        """A file a release carries."""
        self._asked(url)
        for tag, files in self.releases.items():
            for name, data in files.items():
                if url == self.address(tag, name):
                    return data
        raise urllib.error.HTTPError(url, 404, "Not Found", email.message.Message(), None)

    def _asked(self, url: str) -> None:
        self.asked.append(url)
        if self.offline:
            raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))
