"""Design 0025 §8 (decision 0157): the files the agents sent, as the phone's listener serves them. A raster image (PNG,
JPEG, GIF, WebP), a PDF or plain text is served to be seen in place, as its own type, never sniffed for another; any
other file (a page, a drawing, a script) is served only as a download, `application/octet-stream` with
`Content-Disposition: attachment`; and every answer under `/api/files` carries `Content-Security-Policy: sandbox`, so
nothing sent runs as the app. The list of files says each one's type as it is served, so the page shows a picture
only for an image and its links save the rest (`download`)."""

import json
import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.remote import tailnet
from clank.components.remote.app import COOKIE, create_phone_app
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

PAGE = Path(create_phone_app.__code__.co_filename).parent / "page" / "app.js"
OWNER = "owner@example.com"
YOU = Actor(kind="user", via="console")
THROUGH_TAILSCALE = {"Tailscale-User-Login": OWNER}
ACT = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}
SEEN = {  # a file sent, and the type it is seen in place as
    "plot.png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    "photo.jpg": (b"\xff\xd8\xff\xe0", "image/jpeg"),
    "steps.gif": (b"GIF89a", "image/gif"),
    "map.webp": (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
    "paper.pdf": (b"%PDF-1.7\n", "application/pdf"),
    "notes.txt": (b"tau = 1.2 s\n", "text/plain; charset=utf-8"),
}
SAVED = {  # a file sent that is offered only to save
    "report.html": b"<!doctype html><title>a report</title><p>a page</p>",
    "figure.svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>',
    "tool.js": b'console.log("a script");\n',
    "notes.xhtml": b'<html xmlns="http://www.w3.org/1999/xhtml"><body>a page</body></html>',
    "data.xml": b"<?xml version='1.0'?><data/>",
    "plot.png.html": b"<p>a page whose name ends otherwise</p>",
}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["remote"], "owner_login", lambda: OWNER)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", OWNER))
    yield kernel
    kernel.close()


@pytest.fixture
def phone(kernel: Kernel, tmp_path: Path) -> Iterator[TestClient]:
    """A paired phone, and a workspace whose agent sent every file above."""
    box = tmp_path / "paper" / ".clank" / "outbox"
    box.mkdir(parents=True)
    sent = {**{name: content for name, (content, _) in SEEN.items()}, **SAVED}
    for at, (name, content) in enumerate(sent.items()):
        (box / name).write_bytes(content)
        note = {"file": name, "caption": name, "from": f"out/{name}", "sent": 1792038183.0 + at}
        (box / f"{name}.json").write_text(json.dumps(note), encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path / "paper")}, base=None, actor=YOU)
    app = create_phone_app(kernel.parts["remote"])
    with TestClient(app, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50000)) as client:
        code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
        assert client.post("/api/pair", json={"code": code}, headers=ACT).status_code == 200
        assert COOKIE in client.cookies
        yield client


def policy(headers: Mapping[str, str]) -> list[str]:
    """An answer's content security policy, by its directives."""
    return [each.strip() for each in headers["content-security-policy"].split(";") if each.strip()]


def test_a_page_a_drawing_or_a_script_sent_comes_back_only_as_a_download_in_a_sandbox(phone: TestClient) -> None:
    for name, content in SAVED.items():
        answer = phone.get(f"/api/files/paper/{name}", headers=THROUGH_TAILSCALE)
        assert (answer.status_code, answer.content) == (200, content), name
        assert answer.headers["content-type"] == "application/octet-stream", f"{name}: never served as its own type"
        assert answer.headers["content-disposition"] == f'attachment; filename="{name}"', name
        assert answer.headers["x-content-type-options"] == "nosniff", name
        assert policy(answer.headers) == ["sandbox"], name
    missing = phone.get("/api/files/paper/gone.html", headers=THROUGH_TAILSCALE)
    assert missing.status_code == 404
    assert policy(missing.headers) == ["sandbox"], "a refusal under /api/files carries the sandbox too"


def test_an_image_a_pdf_or_plain_text_sent_is_served_to_be_seen_in_place_never_sniffed(phone: TestClient) -> None:
    for name, (content, kind) in SEEN.items():
        answer = phone.get(f"/api/files/paper/{name}", headers=THROUGH_TAILSCALE)
        assert (answer.status_code, answer.content) == (200, content), name
        assert answer.headers["content-type"] == kind, name
        assert answer.headers["content-disposition"] == f'inline; filename="{name}"', name
        assert answer.headers["x-content-type-options"] == "nosniff", name
        assert policy(answer.headers) == ["sandbox"], name
    page = phone.get("/", headers=THROUGH_TAILSCALE)
    assert "script-src 'self'" in page.headers["content-security-policy"], "the app's own pages keep their policy"


def test_the_list_says_each_files_type_as_it_is_served(phone: TestClient) -> None:
    listed = {file["file"]: file["mime"] for file in phone.get("/api/files", headers=THROUGH_TAILSCALE).json()["files"]}
    assert listed == {
        **{name: kind.partition(";")[0] for name, (_, kind) in SEEN.items()},
        **{name: "application/octet-stream" for name in SAVED},
    }
    overview = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
    assert {file["file"]: file["mime"] for file in overview["files"]} == listed
    script = PAGE.read_text(encoding="utf-8")
    for shown in ("function fileRow", "function fileTile"):
        assert "download: saved(file)" in script.split(shown, 1)[1].split("\n}\n", 1)[0], f"{shown} saves a download"
    assert '=== "application/octet-stream" ? file.file : null' in script, "a download is a file served as one"


def test_an_outbox_reached_through_a_link_is_neither_listed_nor_served(
    kernel: Kernel, phone: TestClient, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "secret.txt").write_bytes(b"the owner's own")
    note = {"file": "secret.txt", "caption": "a secret", "from": "secret.txt", "sent": 1792038999.0}
    (elsewhere / "secret.txt.json").write_text(json.dumps(note), encoding="utf-8")
    (tmp_path / "other" / ".clank").mkdir(parents=True)
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(elsewhere), str(tmp_path / "other" / ".clank" / "outbox"))
    else:
        os.symlink(elsewhere, tmp_path / "other" / ".clank" / "outbox", target_is_directory=True)
    kernel.settings.write("workspace", "other", {"path": str(tmp_path / "other")}, base=None, actor=YOU)
    listed = phone.get("/api/files", headers=THROUGH_TAILSCALE).json()["files"]
    assert "other" not in {file["workspace"] for file in listed}, "nothing listed through the link"
    assert phone.get("/api/files/other/secret.txt", headers=THROUGH_TAILSCALE).status_code == 404
    named = phone.get("/api/files/paper/..%2Fother%2Fsecret.txt", headers=THROUGH_TAILSCALE)
    assert named.status_code == 404, "a name with a folder in it is no sent file"
