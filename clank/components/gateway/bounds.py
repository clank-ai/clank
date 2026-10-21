"""Each workspace's key at the gateway and how far its requests may go (design 0016 §9; decision 0075's keys, built for
the cloud).

Each workspace's OpenCode, and Clank's MCP server in its container, send a key of the workspace's own to the gateway,
its name there, once the cloud is in play (a provider agreed, or the workspace allowed the cloud; before, they send
`local`, as they always did). The gateway's service makes it then, once (a secret, `workspace/<name>/gateway-key`), and
keeps only its SHA-256 in its own table, with the workspace's bound, kept from the first (without a key until one is
made): `this-machine` (every workspace, until the owner says otherwise)
or `cloud`; when the owner last answered the cloud question for it; and the question open for it now. The workspaces
component gives each bound (decision 0019: it uses the gateway), and the routes the gateway follows carry each key's
hash with its bound, never a key."""

import hashlib
import secrets
from typing import TYPE_CHECKING, Any

from clank.kernel.clock import to_text
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

GATEWAY = Actor(kind="clank", via="gateway")
NAME = "gateway-key"
UNSET = object()


def scope(workspace: str) -> str:
    """Where a workspace's key is kept among the secrets."""
    return f"workspace/{workspace}"


def digest(key: str) -> str:
    """A key's SHA-256, as the routes carry it."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class Bounds:
    """The workspaces' keys and bounds, in the gateway component's table."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel

    def key(self, workspace: str, *, why: str) -> str:
        """A workspace's key, made the first time it is asked for (read through the kernel, recorded with why)."""
        self._keyed(workspace)
        return self.kernel.secrets.value(scope(workspace), NAME, user="gateway", why=why)

    def set(self, workspace: str, *, models: Any = UNSET, answered: Any = UNSET, question: Any = UNSET) -> None:
        """Change a workspace's bound, whether it was answered (True: now), or its open question (None: none); a
        workspace allowed the cloud gets its key now."""
        self._row(workspace)
        if models == "cloud":
            self._keyed(workspace)
        values: dict[str, Any] = {}
        if models is not UNSET:
            values["models"] = str(models)
        if answered is not UNSET:
            values["answered"] = to_text(self.kernel.clock.now()) if answered is True else str(answered or "")
        if question is not UNSET:
            values["question"] = question
        if not values:
            return
        assignments = ", ".join(f"{name} = ?" for name in values)
        with self.kernel.store.transaction() as db:
            db.execute(f"UPDATE workspace_keys SET {assignments} WHERE workspace = ?", (*values.values(), workspace))

    def view(self, workspace: str) -> dict[str, Any] | None:
        """A workspace's bound as the routes carry it, or None when it has no key yet."""
        rows = self.kernel.store.read("SELECT * FROM workspace_keys WHERE workspace = ?", (workspace,))
        return _view(rows[0]) if rows else None

    def answered_at(self, workspace: str) -> str:
        """When the owner last answered the cloud question for a workspace; "" for never."""
        rows = self.kernel.store.read("SELECT answered FROM workspace_keys WHERE workspace = ?", (workspace,))
        return str(rows[0]["answered"]) if rows else ""

    def routes(self) -> dict[str, dict[str, Any]]:
        """Each key's hash, with its workspace's bound."""
        rows = self.kernel.store.read("SELECT * FROM workspace_keys WHERE key_hash IS NOT NULL")
        return {row["key_hash"]: _view(row) for row in rows}

    def _row(self, workspace: str) -> None:
        """Keep a workspace's bound, without a key until one is made."""
        with self.kernel.store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO workspace_keys (workspace) VALUES (?)", (workspace,))

    def _keyed(self, workspace: str) -> None:
        """Make a workspace's key, once, and keep its hash."""
        rows = self.kernel.store.read("SELECT key_hash FROM workspace_keys WHERE workspace = ?", (workspace,))
        if rows and rows[0]["key_hash"]:
            return
        if any(shown.name == NAME for shown in self.kernel.secrets.shown(scope(workspace))):
            key = self.kernel.secrets.value(scope(workspace), NAME, user="gateway", why="its hash kept again")
        else:
            key = "clank-ws-" + secrets.token_urlsafe(32)
            self.kernel.secrets.put(scope(workspace), NAME, key, actor=GATEWAY)
        self._row(workspace)
        with self.kernel.store.transaction() as db:
            db.execute("UPDATE workspace_keys SET key_hash = ? WHERE workspace = ?", (digest(key), workspace))


def _view(row: Any) -> dict[str, Any]:
    return {
        "workspace": row["workspace"],
        "models": row["models"],
        "answered": bool(row["answered"]),
        "question": row["question"],
    }
