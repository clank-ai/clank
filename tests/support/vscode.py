"""Test support: Clank's VS Code window with the fake `code` (`tests/fakes/code.py`) named in its settings and Clank's
extension as if built, and what the fake was asked. The fake opens no window; the real VS Code is never found in a
test (`tests/conftest.py`)."""

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from clank.components.agents import vscode
from clank.kernel.core import Kernel

FAKE = Path(__file__).resolve().parents[1] / "fakes" / "code.py"


def fake_vscode(kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Name the fake in config/vscode.json and make Clank's extension look built, both in `folder`; the file that keeps
    what the fake is asked."""
    state = folder / "code.json"
    settings = {"schema": "vscode/1", "program": [sys.executable, str(FAKE), str(state)]}
    (kernel.home.config / "vscode.json").write_text(json.dumps(settings) + "\n", encoding="utf-8")
    kernel.settings.reload_changed()
    vsix = folder / "clank-9.9.9.vsix"
    vsix.write_bytes(b"PK")
    monkeypatch.setattr(vscode, "clank_vsix", lambda: vsix)
    return state


def asked(state: Path, opened: int = 1) -> dict[str, Any]:
    """What the fake was asked, once it has opened this many folders (the window is started, not waited for)."""
    deadline = time.monotonic() + 30
    while True:
        try:
            found: dict[str, Any] = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
        except (ValueError, OSError):  # the fake renames its file over the last one: read it again
            found = {}
        if len(found.get("opened", [])) >= opened:
            return found
        assert time.monotonic() < deadline, "the folder was never opened"
        time.sleep(0.05)
