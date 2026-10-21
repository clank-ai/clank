"""Design 0002 §3.2 (M0.1): `clank --version` reports the version of the code that is running.

The version is written once, in `clank/__init__.py`; the package's metadata, the command and `python -m clank` must
all agree with it, from any working folder.
"""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from click.testing import CliRunner

import clank
from clank.cli.main import main


def test_clank_version_prints_the_version_of_the_code() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert result.output == f"clank {clank.__version__}\n"


def test_the_package_metadata_carries_the_same_version() -> None:
    assert version("clank") == clank.__version__


def test_python_dash_m_clank_runs_the_command_from_any_folder(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "clank", "--version"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert done.stdout == f"clank {clank.__version__}\n"


def test_clank_help_shows_how_to_use_it_and_that_clank_alone_opens_the_console_on_this_folder() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert "Usage: " in result.output
    assert "--version" in result.output
    said = " ".join(result.output.split())
    assert "Alone, `clank` opens the console on this folder's page" in said
    assert "`clank work` starts the agent here at once" in said
