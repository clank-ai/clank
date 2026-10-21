"""Design 0002 §2.15: the `clank` command writes UTF-8 on every platform, so what it prints reads the same in a
terminal, a pipe or a file (on Windows, Python would otherwise write a pipe in the system's code page)."""

import os
import subprocess
import sys
from pathlib import Path


def test_the_command_writes_utf8_to_a_pipe(tmp_path: Path) -> None:
    environment = {name: value for name, value in os.environ.items() if name not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    environment["CLANK_HOME"] = str(tmp_path / "clank-home")
    done = subprocess.run([sys.executable, "-m", "clank", "doctor"], capture_output=True, env=environment, timeout=120)
    assert "·" in done.stdout.decode("utf-8")
