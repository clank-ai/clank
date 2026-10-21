"""Design 0003 §7.1 and §8.4: `clank engine install` follows the install, asks at the terminal unless told `--yes`, and
prints where the engine went (exit 1 when it was not installed); `clank engine list` prints each serving setup's
versions, where each is installed and how, and which Clank has a recipe for; `clank engine adopt` follows the check
and says why it refused; the API starts an install as an operation."""

from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.kernel.api import create_app
from tests.components.runtime.conftest import Rig

INSTALL = ("engine", "install", "kvmem-llamacpp", "--version", "v0.16.0-rc1", "--host", "bench")


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


def test_engine_install_asks_follows_and_says_where_the_engine_went(
    bench: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(bench.kernel, token="t", port=7721), base_url="http://127.0.0.1:7721") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7721", "t", name="cli", http=http))
        monkeypatch.setattr(follow, "ask", lambda text, default: "n")
        declined = run(*INSTALL)
        assert declined.exit_code == 1, declined.output
        assert "Install KVMem/llama.cpp v0.16.0-rc1 on bench?" in declined.output
        assert "not installed" in declined.output
        installed = run(*INSTALL, "--yes")
        assert installed.exit_code == 0, installed.output
        assert "== fetch" in installed.output
        assert "KVMem/llama.cpp v0.16.0-rc1 is installed on bench, in " in installed.output
        listed = run("engine", "list")
        assert listed.exit_code == 0, listed.output
        assert "kvmem-llamacpp  v0.16.0-rc1  on bench (recipe), local (test); Clank has its recipe" in listed.output


def test_the_api_starts_an_install_as_an_operation(bench: Rig) -> None:
    with TestClient(create_app(bench.kernel, token="t", port=7722), base_url="http://127.0.0.1:7722") as http:
        headers = {"Authorization": "Bearer t", "X-Clank-Client": "test"}
        body = {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "host": "bench", "yes": True}
        started = http.post("/api/v1/runtime/installs", json=body, headers=headers)
        assert started.status_code == 200, started.text
        assert started.json()["type"] == "runtime.install"
        missing = http.post("/api/v1/runtime/installs", json={**body, "host": "elsewhere"}, headers=headers)
        assert missing.status_code == 404
        assert "there is no host named 'elsewhere'" in missing.json()["error"]["message"]


def test_engine_adopt_follows_the_check_and_says_why_it_refused(
    bench: Rig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with TestClient(create_app(bench.kernel, token="t", port=7723), base_url="http://127.0.0.1:7723") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7723", "t", name="cli", http=http))
        program = tmp_path / "build" / "bin" / "llama-kvmem-server"
        refused = run(
            "engine", "adopt", "kvmem-llamacpp", "--version", "v0.16.0-rc1", "--host", "bench",
            "--program", str(program), "--folder", str(tmp_path),
        )  # fmt: skip
        assert refused.exit_code == 1, refused.output
        assert "  1 of 2: check" in refused.output
        assert f"Adopt an engine already built: {program} is not on bench" in refused.output
