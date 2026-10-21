"""The real-engine tests' rules and kernel (design 0003 §9): they run only when asked (`-m real`), on a machine whose
Clank home has hosts, installs and model files (this one), and only while the GPU holds no engine and port 18200 is
free; else they are skipped, saying why. Their kernel has a CLANK_HOME of its own, with the machine's host and
model-file records and its installs copied in, so a test changes nothing of the machine's own Clank; what a test
starts is stopped after it, whatever happened."""

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from clank import registry
from clank.components.runtime.gpu import gpu_memory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.service import Runtime
from clank.components.runtime.state import InstallRecord
from clank.kernel.clock import SystemClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.support.homes import REAL_HOME

PORT = 18200
ENGINE_MIB = 4096  # more than the desktop holds, less than any engine takes


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the real tests unless they were asked for."""
    if "real" in (config.getoption("markexpr") or ""):
        return
    skip = pytest.mark.skip(reason="it starts real engines: run with -m real, on the machine they are installed on")
    for item in items:
        if "real" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def machine(tmp_path: Path) -> Iterator[Kernel]:
    """A kernel with this machine's hosts, installs and model files, in a CLANK_HOME of its own."""
    real = REAL_HOME
    if not (real.config / "hosts").is_dir() or not (real.state / "clank.db").is_file():
        pytest.skip(f"{real.root} has no hosts or installs: this machine runs no engine through Clank")
    gpu = gpu_memory()
    if gpu is None:
        pytest.skip("the GPU's memory cannot be read: nvidia-smi does not answer")
    if gpu.used_mib > ENGINE_MIB:
        pytest.skip(f"the GPU holds {gpu.used_mib:,} MiB: an engine may run, and a test never touches one")
    holder = LocalHost().listener(PORT)
    if holder is not None:
        pytest.skip(f"port {PORT} is held by {holder}")
    home = Home(tmp_path / "clank-home")
    home.ensure()
    for kind in ("hosts", "model-files"):
        if (real.config / kind).is_dir():
            shutil.copytree(real.config / kind, home.config / kind)
    kernel = open_kernel(home, SystemClock(), registry.components())
    runtime: Runtime = kernel.parts["runtime"]
    with closing(sqlite3.connect(f"file:{real.state / 'clank.db'}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT * FROM installs"):
            values = {key: value for key, value in dict(row).items() if key not in ("id", "installed")}
            values["program"] = json.loads(values["program"])
            runtime.state.add_install(InstallRecord.model_validate(values), datetime.fromisoformat(row["installed"]))
    try:
        yield kernel
    finally:
        slot = runtime.state.slot("main")
        if slot.pid is not None and slot.host is not None:
            identity = ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or "")
            runtime.host(slot.host).stop(identity, 60)
        kernel.close()
