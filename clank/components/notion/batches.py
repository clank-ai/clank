"""Batches of the agent's proposals (design 0010 §5): each a JSON file in `CLANK_HOME/state/notion/batches/`, so the
owner (and any client) can read every one, and the service reads them again after a restart.

A batch belongs to a workspace and is *open* while the agent stages into it (a workspace has one open batch), *ready*
once submitted for review, then *returned* (sent back with comments), *rejected* or *written* (wholly or in part) after
the owner acts. Its proposals are numbered in order (`p1`, `p2`, ...); a batch is numbered among all batches, newest
last, so they list newest first whatever the clock says.

While a workspace has a batch sent back, the agent stages into it (its next revision) instead of an open batch: a
proposal for an entry the batch already has a proposal for (the same entry, or a new entry of the same title in the
same database) replaces that one, keeping its number and what it was (`previous`), unless anything of it is written;
each proposal says the revision it was staged in. The owner's comments are kept on the batch (`comments`), numbered
`c1`, `c2`, ...
"""

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from clank.kernel.clock import Clock, to_text

STATES = ("open", "ready", "returned", "rejected", "written", "partly written")


class Batches:
    """The batches, kept as files."""

    def __init__(self, folder: Path, clock: Clock) -> None:
        self.folder = folder
        self.clock = clock
        self.lock = threading.RLock()

    def open_batch(self, workspace: str) -> dict[str, Any]:
        """The batch the workspace's agent stages into: the one sent back to it (being revised), else its open batch,
        made when it has none."""
        with self.lock:
            found = self.staging(workspace)
            if found is not None:
                return found
            now = to_text(self.clock.now())
            batch = {
                "id": f"nb-{secrets.token_hex(4)}", "number": self._next_number(), "workspace": workspace,
                "state": "open", "summary": "", "revision": 1, "created": now, "updated": now, "proposals": [],
                "comments": [],
            }  # fmt: skip
            self.save(batch)
            return batch

    def staging(self, workspace: str) -> dict[str, Any] | None:
        """The batch the workspace's agent stages into now, without making one: the newest sent back, else the open
        one."""
        found = self.all(workspace)
        return next((batch for batch in found if batch["state"] == "returned"), None) or next(
            (batch for batch in found if batch["state"] == "open"), None
        )

    def add(self, workspace: str, proposal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """A proposal kept in the batch the workspace's agent stages into, numbered there (or replacing the one for the
        same entry in a batch being revised); the batch and the proposal."""
        with self.lock:
            batch = self.open_batch(workspace)
            revising = batch["state"] == "returned"
            revision = batch["revision"] + 1 if revising else batch["revision"]
            same = (
                next((each for each in batch["proposals"] if _same_entry(each, proposal)), None) if revising else None
            )
            if same is not None and not same.get("done"):
                previous = {key: same[key] for key in ("kind", "fields", "markdown", "why", "sources", "revision")
                            if key in same}  # fmt: skip
                kept = {"id": same["id"], **proposal, "revision": revision, "previous": previous}
                batch["proposals"][batch["proposals"].index(same)] = kept
            else:
                kept = {"id": f"p{len(batch['proposals']) + 1}", **proposal, "revision": revision}
                batch["proposals"].append(kept)
            self.save(batch)
            return batch, kept

    def get(self, id: str) -> dict[str, Any] | None:
        """A batch, or None."""
        path = self.folder / f"{id}.json"
        if not id.startswith("nb-") or not path.is_file():
            return None
        found: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return found

    def all(self, workspace: str | None = None) -> list[dict[str, Any]]:
        """Every batch (of a workspace), newest first."""
        if not self.folder.is_dir():
            return []
        found = [json.loads(path.read_text(encoding="utf-8")) for path in self.folder.glob("nb-*.json")]
        return sorted(
            (batch for batch in found if workspace is None or batch["workspace"] == workspace),
            key=lambda batch: batch["number"],
            reverse=True,
        )

    def save(self, batch: dict[str, Any]) -> None:
        """Keep a batch (whole, replacing the file at once)."""
        with self.lock:
            batch["updated"] = to_text(self.clock.now())
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"{batch['id']}.json"
            partial = path.with_name(f".{path.name}.part")
            partial.write_text(json.dumps(batch, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(partial, path)

    def _next_number(self) -> int:
        return max((batch["number"] for batch in self.all()), default=0) + 1


def view(batch: dict[str, Any]) -> dict[str, Any]:
    """A batch in brief: its state, summary and counts (`left`: the proposals not written whole yet; its comments, those
    not answered, those not sent to the agent yet), not its proposals."""
    kinds = [proposal["kind"] for proposal in batch["proposals"]]
    comments = batch.get("comments") or []
    return {
        **{key: batch[key] for key in ("id", "workspace", "state", "summary", "revision", "created", "updated")},
        "counts": {"new": kinds.count("entry"), "changed": kinds.count("change"), "removed": kinds.count("removal")},
        "left": sum(1 for proposal in batch["proposals"] if not (proposal.get("result") or {}).get("written")),
        "comment_counts": {
            "all": len(comments),
            "open": sum(1 for each in comments if each["state"] == "open"),
            "unsent": sum(1 for each in comments if not each["sent"]),
        },
        "databases": sorted({proposal["database_name"] for proposal in batch["proposals"]}),
    }


def _same_entry(staged: dict[str, Any], proposal: dict[str, Any]) -> bool:
    """Whether two proposals are about the same entry: the same one in Notion, or new entries of the same title in the
    same database."""
    if staged["page"] or proposal["page"]:
        return bool(staged["page"] == proposal["page"])
    return bool(
        staged["database"] == proposal["database"] and staged["title"].casefold() == proposal["title"].casefold()
    )
