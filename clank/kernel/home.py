"""CLANK_HOME: the one folder that holds everything of one user on one machine (design 0001 §7.2, design 0002 §2.16).

It is `~/.clank` unless the environment variable CLANK_HOME names another folder; tests and a developer's working copy
point it elsewhere. The kernel creates its folders on first use, the ones holding secrets and state readable only by
the user where the platform allows it (on Windows the user's own folders are private already).
"""

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENVIRONMENT = "CLANK_HOME"


@dataclass(frozen=True)
class Home:
    """The folders of one CLANK_HOME."""

    root: Path

    @classmethod
    def resolve(cls, environ: Mapping[str, str] | None = None) -> "Home":
        """CLANK_HOME from the environment, else `~/.clank`."""
        value = (os.environ if environ is None else environ).get(ENVIRONMENT)
        return cls(Path(value) if value else Path.home() / ".clank")

    @property
    def id(self) -> str:
        """A short id of this CLANK_HOME, the same every time: what Clank starts carries it (the label `clank.home`), so
        what another CLANK_HOME started is told apart."""
        return hashlib.sha256(os.path.normcase(str(self.root.resolve())).encode("utf-8")).hexdigest()[:12]

    @property
    def config(self) -> Path:
        """The user's settings: one JSON file per record (decision 0007)."""
        return self.root / "config"

    @property
    def secrets(self) -> Path:
        """Keys and tokens, one file each, readable only by the user."""
        return self.root / "secrets"

    @property
    def state(self) -> Path:
        """The state database and the files of the running service."""
        return self.root / "state"

    @property
    def logs(self) -> Path:
        """The gateway's records and the output of the processes Clank runs."""
        return self.root / "logs"

    @property
    def library(self) -> Path:
        """What the user installs: skills, tool servers, modes, shared suites and presets."""
        return self.root / "library"

    @property
    def artifacts(self) -> Path:
        """Files made for the user."""
        return self.root / "artifacts"

    @property
    def database(self) -> Path:
        """The state database (decision 0014)."""
        return self.state / "clank.db"

    def ensure(self) -> None:
        """Create every folder that does not exist yet."""
        for folder in (self.root, self.config, self.logs, self.library, self.artifacts):
            folder.mkdir(parents=True, exist_ok=True)
        for private in (self.secrets, self.state):
            private.mkdir(parents=True, exist_ok=True)
            private.chmod(0o700)
