"""Design 0025 §3 and §4 (decision 0143): the installed app's shell. The page has the five tabs (Now, Flows, Work,
Files, More) and loads the app as a module on the live stream; every file the service worker caches for the app's
launch is served from the package with its media type (the app fetches nothing from elsewhere); the Home Screen icon
is a PNG drawn by Clank, 180 pixels square; the manifest names the icons and keeps the app to its own scope."""

import json
import re
import struct
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.remote import tailnet
from clank.components.remote.app import STATIC, create_phone_app
from clank.components.remote.icon import icon_png
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

OWNER = "owner@example.com"
THROUGH_TAILSCALE = {"Tailscale-User-Login": OWNER}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["remote"], "owner_login", lambda: OWNER)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", OWNER))
    yield kernel
    kernel.close()


@pytest.fixture
def phone(kernel: Kernel) -> Iterator[TestClient]:
    app = create_phone_app(kernel.parts["remote"])
    with TestClient(app, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50000)) as client:
        yield client


def test_the_page_has_the_five_tabs_and_loads_the_app_as_a_module(phone: TestClient) -> None:
    page = phone.get("/", headers=THROUGH_TAILSCALE).text
    tabs = re.findall(r'data-tab="([a-z]+)"', page)
    assert tabs == ["now", "flows", "work", "files", "more"]
    assert '<script type="module" src="app.js">' in page, "the app is a module: it imports model.mjs"
    assert 'rel="apple-touch-icon" href="icon-180.png"' in page
    assert 'rel="manifest" href="manifest.webmanifest"' in page
    assert 'id="attention"' in page, "the line an event asking for attention shows under the header"


def test_every_file_the_service_worker_caches_is_served_with_its_media_type(phone: TestClient) -> None:
    worker = phone.get("/sw.js", headers=THROUGH_TAILSCALE)
    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("text/javascript")
    listed = re.search(r"FILES\s*=\s*(\[[^\]]*\])", worker.text)
    assert listed is not None, "the worker lists the files of the app's launch"
    files = json.loads(listed.group(1))
    assert {"./", "app.js", "model.mjs", "style.css", "icon-180.png", "manifest.webmanifest"} <= set(files)
    assert "index.html" not in files, "the page is served at the root only: caching it by name would miss"
    for name in files:
        answer = phone.get(f"/{name}" if name != "./" else "/", headers=THROUGH_TAILSCALE)
        assert answer.status_code == 200, name
    assert phone.get("/model.mjs", headers=THROUGH_TAILSCALE).headers["content-type"].startswith("text/javascript")
    assert phone.get("/icon.svg", headers=THROUGH_TAILSCALE).headers["content-type"].startswith("image/svg+xml")
    assert "install.html" not in STATIC, "the install page is served filled in, at /pair, never raw"


def test_the_home_screen_icon_is_a_png_drawn_here_180_pixels_square(phone: TestClient) -> None:
    answer = phone.get("/icon-180.png", headers=THROUGH_TAILSCALE)
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"
    assert answer.content == icon_png(180)
    assert answer.content[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", answer.content[16:24])
    assert (width, height) == (180, 180)
    assert phone.get("/icon-180.png").status_code == 403, "like every file: only through Tailscale"


def test_the_manifest_names_the_icons_and_keeps_the_app_to_its_scope(phone: TestClient) -> None:
    manifest = phone.get("/manifest.webmanifest", headers=THROUGH_TAILSCALE).json()
    assert manifest["scope"] == "./"
    assert manifest["display"] == "standalone"
    assert {icon["src"] for icon in manifest["icons"]} == {"icon-180.png", "icon.svg"}
    assert manifest["background_color"] == manifest["theme_color"] == "#16161e"
