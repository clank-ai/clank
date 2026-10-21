"""Design 0003 §7.2, design 0001 §7.5 and the M1.4 plan's review focus 1-2: a download says the file's size and the
host's free disk and asks first; it is fetched by the host into `<file>.part` in the host's models folder, resumes
from what the `.part` has after an interruption, and becomes the file only once its SHA-256 is the catalog's; a file
whose checksum differs is kept aside as `<file>.bad` and refused. A file the user already has is adopted where it is
once its size and SHA-256 are the catalog's (a `model-file` record), and refused when either differs."""

import hashlib
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.runtime.catalog import ModelEntry, ModelFacts, ModelFileEntry
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
DATA = os.urandom(600_000)
REVISION = "0123456789abcdef0123456789abcdef01234567"


@dataclass
class Hub:
    """Hugging Face as a test sets it: one file's bytes, an answer cut off after `cut` bytes (once), and the Range
    header of each request."""

    data: bytes = DATA
    cut: int | None = None
    ranges: list[str | None] = field(default_factory=list)


def small(revision: str = REVISION) -> ModelEntry:
    return ModelEntry(
        id="small",
        name="Small",
        facts=ModelFacts(
            architecture="a test's", parameters="0", context=8192, attention_layers=2, kv_width=64, abilities=[]
        ),
        files=[
            ModelFileEntry(
                format="gguf", role="weights", repository="tests/small", revision=revision, path="small.gguf",
                size=len(DATA), sha256=hashlib.sha256(DATA).hexdigest(),
            )
        ],
    )  # fmt: skip


@pytest.fixture
def hub(bench: Rig) -> Iterator[Hub]:
    """A local server for the model's file, and the runtime pointed at it."""
    found = Hub()

    class Answer(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked = self.headers.get("Range")
            found.ranges.append(asked)
            start = int(asked.removeprefix("bytes=").rstrip("-")) if asked else 0
            body = found.data[start:]
            self.send_response(206 if asked else 200)
            self.send_header("Content-Length", str(len(body)))
            if asked:
                self.send_header("Content-Range", f"bytes {start}-{len(found.data) - 1}/{len(found.data)}")
            self.end_headers()
            if found.cut is not None:
                body, found.cut = body[: found.cut], None
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    bench.runtime.models = {**(bench.runtime.models or {}), "small": small()}
    bench.runtime.model_url = f"http://127.0.0.1:{server.server_port}/{{repository}}/resolve/{{revision}}/{{path}}"
    yield found
    server.shutdown()
    server.server_close()


def target(tmp_path: Path) -> Path:
    return tmp_path / "bench-clank" / "models" / "tests" / "small" / REVISION[:12] / "small.gguf"


async def run(rig: Rig, kind: str, **params: object) -> Operation:
    wanted = {"model": "small", "format": "gguf", "host": "bench", **params}
    started = await rig.kernel.operations.start(kind, wanted, actor=YOU)
    with anyio.fail_after(60):
        while True:
            current = rig.kernel.operations.get(started.id)
            if current.status == "waiting" and current.waiting_on:
                return current
            if current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.05)


async def test_a_download_says_the_size_and_free_disk_and_no_fetches_nothing(
    bench: Rig, hub: Hub, tmp_path: Path
) -> None:
    async with bench.kernel.operations.running():
        waiting = await run(bench, "runtime.download")
        question = bench.kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Download small.gguf (600 KB) to bench?"
        assert "free on bench" in question.detail
        bench.kernel.questions.answer(question.id, by=YOU, option="cancel")
        with anyio.fail_after(60):
            done = await bench.kernel.operations.wait(waiting.id)
    assert done.status == "canceled"
    assert hub.ranges == []
    assert not target(tmp_path).parent.exists()


async def test_a_download_cut_off_resumes_from_its_part_and_is_kept_once_verified(
    bench: Rig, hub: Hub, tmp_path: Path
) -> None:
    hub.cut = 200_000
    async with bench.kernel.operations.running():
        stopped = await run(bench, "runtime.download", yes=True)
        assert stopped.status == "failed"
        assert "stopped at" in stopped.error
        assert "downloading it again goes on from what it has" in stopped.error
        part = Path(f"{target(tmp_path)}.part")
        have = part.stat().st_size
        assert 0 < have <= 200_000
        done = await run(bench, "runtime.download", yes=True)
    assert done.status == "done", done.error
    assert hub.ranges == [None, f"bytes={have}-"]
    assert target(tmp_path).read_bytes() == DATA
    assert not part.exists()
    log = [line.text for line in bench.kernel.operations.log_lines(done.id)]
    assert any(line.startswith("verified: small.gguf is the catalog's") for line in log)


async def test_a_download_whose_checksum_differs_is_kept_aside_and_refused(
    bench: Rig, hub: Hub, tmp_path: Path
) -> None:
    hub.data = bytes(len(DATA))
    async with bench.kernel.operations.running():
        failed = await run(bench, "runtime.download", yes=True)
    assert failed.status == "failed"
    assert "SHA-256" in failed.error
    assert "kept aside as small.gguf.bad" in failed.error
    assert not target(tmp_path).exists()
    assert Path(f"{target(tmp_path)}.bad").read_bytes() == bytes(len(DATA))


async def test_a_file_already_there_is_not_fetched_again(bench: Rig, hub: Hub, tmp_path: Path) -> None:
    target(tmp_path).parent.mkdir(parents=True)
    target(tmp_path).write_bytes(DATA)
    async with bench.kernel.operations.running():
        done = await run(bench, "runtime.download", yes=True)
    assert done.status == "done", done.error
    assert hub.ranges == []


async def test_a_file_whose_revision_is_no_longer_known_is_not_downloaded(bench: Rig, hub: Hub) -> None:
    bench.runtime.models = {**(bench.runtime.models or {}), "small": small(revision="")}
    async with bench.kernel.operations.running():
        refused = await run(bench, "runtime.download", yes=True)
    assert refused.status == "failed"
    assert "its revision is no longer known" in refused.error
    assert "clank model adopt" in refused.error


async def test_a_file_the_user_has_is_adopted_where_it_is_once_verified(bench: Rig, hub: Hub, tmp_path: Path) -> None:
    mine = tmp_path / "elsewhere" / "small.gguf"
    mine.parent.mkdir()
    mine.write_bytes(DATA)
    async with bench.kernel.operations.running():
        done = await run(bench, "runtime.verify", path=str(mine))
    assert done.status == "done", done.error
    record = bench.kernel.settings.get("model-file", "small-gguf-weights-bench").record.model_dump()
    assert {key: record[key] for key in ("model", "file", "host", "path")} == {
        "model": "small", "file": "small.gguf", "host": "bench", "path": str(mine)
    }  # fmt: skip


def test_the_model_commands_download_a_file_and_adopt_one(
    bench: Rig, hub: Hub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(bench.kernel, token="t", port=7724), base_url="http://127.0.0.1:7724") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7724", "t", name="cli", http=http))
        fetched = CliRunner().invoke(
            main, ["model", "download", "small", "--format", "gguf", "--host", "bench", "--yes", "--limit", "50"]
        )
        assert fetched.exit_code == 0, fetched.output
        assert f"small.gguf is on bench at {target(tmp_path)}" in fetched.output
        mine = tmp_path / "mine.gguf"
        mine.write_bytes(DATA)
        adopted = CliRunner().invoke(
            main, ["model", "adopt", "small", "--format", "gguf", "--host", "bench", "--path", str(mine)]
        )
        assert adopted.exit_code == 0, adopted.output
        assert f"small.gguf is adopted on bench at {mine}" in adopted.output
        missing = CliRunner().invoke(main, ["model", "download", "small", "--format", "gguf", "--host", "nowhere"])
        assert missing.exit_code == 1
        assert "there is no host named 'nowhere'" in missing.output


async def test_a_file_the_user_has_that_differs_is_refused(bench: Rig, hub: Hub, tmp_path: Path) -> None:
    mine = tmp_path / "small.gguf"
    mine.write_bytes(DATA[:-1])
    async with bench.kernel.operations.running():
        shorter = await run(bench, "runtime.verify", path=str(mine))
        mine.write_bytes(bytes(len(DATA)))
        other = await run(bench, "runtime.verify", path=str(mine))
    assert shorter.status == "failed"
    assert "has 599,999 bytes, not the 600,000 of small.gguf" in shorter.error
    assert other.status == "failed"
    assert "SHA-256" in other.error
