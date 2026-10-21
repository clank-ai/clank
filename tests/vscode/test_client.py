"""Design 0002 §2.5 and §2.7: the VS Code extension's client, run by Node against a real Clank service, lists the
question waiting and answers it; the service records the answer as you (vscode), as it would one from the console."""

import os
import shutil
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.fakes.platform import FakePlatform
from tests.support.live import live_service

EXTENSION = Path(__file__).resolve().parents[2] / "vscode"
LIVE = EXTENSION / "out" / "test" / "live.test.js"
STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@pytest.fixture
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    home = Home(tmp_path / "clank-home")
    home.ensure()
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    yield kernel
    kernel.close()


@pytest.mark.skipif(shutil.which("node") is None or not LIVE.exists(), reason="needs Node and the compiled extension")
def test_the_extensions_client_answers_a_question_recorded_as_you_through_vscode(kernel: Kernel) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    with live_service(kernel) as client:
        environment = {**os.environ, "CLANK_TEST_URL": client.url, "CLANK_TEST_TOKEN": "t", "CLANK_TEST_OPTION": "stop"}
        node = shutil.which("node") or "node"
        done = subprocess.run(
            [node, "--test", str(LIVE)], env=environment, cwd=EXTENSION, capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "pass 1" in done.stdout
    answer = kernel.questions.get(asked.id).answer
    assert answer is not None
    assert (answer.option, answer.by.via) == ("stop", "vscode")
