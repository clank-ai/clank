"""The notion component's part (design 0010): the connection to Notion with the owner's integration secret, the
agent's reading of the shared databases (§4), and its proposals, staged in batches for the owner's review (§5).

The secret is kept as a secret (`notion/notion`, name `token`: design 0002 §2.8) only once Notion accepts it
(`users/me`), and read for each piece of work, which records its use; no record, event or answer holds it, and no
event holds Notion's content: a read is recorded with what was asked (what, the ids, how many), never what Notion
answered. Every request goes through `NotionClient` (`client.py`), with the settings' address and API version
(`config/notion.json`); reading is `reading.py`, staging `staging.py`, the batches are files (`batches.py`), the
review's tables are `tables.py`, and writing what the owner approves (whole proposals or some of their parts) is
`applying.py`. The owner's comments (§7: `comments.py`) are kept on the batch; sending it back tells its agent through
the agents component (`agent.py`, replaced by a test's fake), and the agent revises it and answers each comment. No
event holds a comment's words.
Staging is recorded with the batch, the proposal, its kind and its database, never its content. `transport` and
`sleep` are the client's, for a test's fake Notion.
"""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from clank.components.notion import applying, comments, reading, staging, tables
from clank.components.notion.agent import AgentLink
from clank.components.notion.batches import Batches, view
from clank.components.notion.client import NotionClient, NotionError, NotionRefused
from clank.components.notion.kinds import NotionSettings
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.secrets import SecretsError

if TYPE_CHECKING:
    import httpx2

    from clank.kernel.core import Kernel

__all__ = ["NotAllowed", "Notion", "NotionRefused"]

SCOPE, NAME = "notion/notion", "token"
SUBJECT = Subject(kind="notion", id="notion")
HOW = "`clank notion connect` asks for your integration's secret (docs/notion-setup.md says how to make one)"
AGENT = Actor(kind="session", via="the agent")
T = TypeVar("T")

EVENT_TYPES = [
    EventType(
        "notion.connected",
        "Clank was connected to Notion with an integration's secret, which Notion accepted (the secret is never "
        "recorded).",
        {"integration": "The integration's name in Notion.", "workspace": "Its workspace's name."},
    ),
    EventType("notion.disconnected", "Clank's Notion secret was removed.", {}),
    EventType(
        "notion.read",
        "Notion was read for a client (the agent, most often): what was asked, never what Notion answered.",
        {
            "what": "databases, query, page or search.",
            "ids": "The data source or entry asked about, when one was.",
            "count": "How many databases, entries or results came back.",
        },
    ),
    EventType(
        "notion.staged",
        "The agent staged a proposal for the owner's review: a new entry, a change or a removal (nothing is written to "
        "Notion until the owner approves it).",
        {
            "batch": "The batch it joined.",
            "proposal": "Its number in the batch.",
            "kind": "entry, change or removal.",
            "database": "The data source of its database.",
        },
    ),
    EventType(
        "notion.submitted",
        "A batch of proposals was made ready for the owner's review (again, revised for the owner's comments, when its "
        "revision is above 1).",
        {"batch": "The batch.", "count": "How many proposals it holds.", "revision": "Its revision."},
    ),
    EventType(
        "notion.commented",
        "The owner commented on a batch of proposals (the comment's words are kept with the batch, not here).",
        {
            "batch": "The batch.",
            "comment": "The comment's number.",
            "on": "batch, proposal, property or block.",
            "proposal": "The proposal it is on, if any.",
        },
    ),
    EventType(
        "notion.uncommented",
        "The owner took back a comment not sent to the agent yet.",
        {"batch": "The batch.", "comment": "The comment's number."},
    ),
    EventType(
        "notion.returned",
        "The owner sent a batch back to its agent with comments, to revise it.",
        {
            "batch": "The batch.",
            "comments": "How many comments were sent.",
            "session": "The session told.",
            "new": "Whether the session is a new one (the one that submitted it no longer ran).",
        },
    ),
    EventType(
        "notion.replied",
        "The agent answered a comment of the owner's.",
        {"batch": "The batch.", "comment": "The comment's number."},
    ),
    EventType(
        "notion.written",
        "The owner approved proposals of a batch, and Clank wrote them to Notion.",
        {
            "batch": "The batch.",
            "written": "How many proposals were written this time.",
            "failed": "How many could not be (each one's result says why).",
            "left": "How many of the batch are not written yet.",
        },
    ),
    EventType(
        "notion.rejected",
        "The owner rejected a batch of proposals, with a reason; nothing of it is written.",
        {"batch": "The batch."},
    ),
]


class NotAllowed(NotionRefused):
    """Something only the owner may do, asked by the agent."""


class Notion:
    """Clank's connection to Notion."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        self.transport: httpx2.BaseTransport | None = None  # a test's fake Notion
        self.sleep: Callable[[float], None] = time.sleep
        self.store = Batches(kernel.home.state / "notion" / "batches", kernel.clock)
        self.agent: Any = AgentLink(kernel)  # how a batch sent back reaches its agent (a test's fake)

    def settings(self) -> NotionSettings:
        """Where Notion's API is, and the version Clank speaks."""
        return NotionSettings.model_validate(self.kernel.settings.get("notion", "notion").record.model_dump())

    def connect(self, secret: str, *, actor: Actor) -> dict[str, Any]:
        """Keep the integration's secret once Notion accepts it; the status."""
        secret = secret.strip()
        if not secret:
            raise NotionRefused(f"no secret was given: {HOW}")
        client = self._client(secret)
        try:
            me = client.me()
        except NotionError as error:
            if error.status in (401, 403):
                raise NotionRefused(
                    f"Notion refused the secret ({error}): copy the integration's whole Internal Integration Secret"
                ) from error
            raise NotionRefused(f"Notion could not check the secret: {error}") from error
        finally:
            client.close()
        self.kernel.secrets.put(SCOPE, NAME, secret, actor=actor)
        names = _names(me)
        self.kernel.events.record(
            "notion.connected",
            summary=f"{actor.describe()} connected Clank to Notion: {names['integration']} in {names['workspace']}",
            actor=actor,
            subject=SUBJECT,
            data=names,
        )
        return self._status(names, "")

    def disconnect(self, *, actor: Actor) -> dict[str, Any]:
        """Remove the secret; the status."""
        if self.kernel.secrets.shown(SCOPE):
            self.kernel.secrets.remove(SCOPE, actor=actor)
            self.kernel.events.record(
                "notion.disconnected", summary=f"{actor.describe()} disconnected Clank from Notion", actor=actor,
                subject=SUBJECT,
            )  # fmt: skip
        return self.status()

    def status(self) -> dict[str, Any]:
        """Whether Clank has a secret, what Notion says it is, and any problem asking it."""
        if not self.kernel.secrets.shown(SCOPE):
            return self._status({"integration": "", "workspace": ""}, f"not connected: {HOW}")
        try:
            me = self.using(lambda client: client.me(), why="the connection's status")
        except NotionError as error:
            return self._status({"integration": "", "workspace": ""}, str(error))
        return self._status(_names(me), "")

    def databases(self, *, actor: Actor = AGENT) -> list[dict[str, Any]]:
        """The shared databases (their data sources), with their properties described."""
        found = self._read(lambda client: reading.describe(reading.shared_sources(client)), "the shared databases")
        self._record_read(actor, "databases", [], len(found))
        return found

    def query(
        self,
        database: str,
        *,
        text: str = "",
        filter: dict[str, Any] | None = None,
        limit: int = 25,
        cursor: str | None = None,
        actor: Actor = AGENT,
    ) -> dict[str, Any]:
        """A shared database's entries as compact rows, filtered by their title's words or Notion's own filter."""

        def work(client: NotionClient) -> dict[str, Any]:
            source = reading.resolve(reading.shared_sources(client), database)
            return {"database": source["id"], **reading.rows(
                client, source, text=text, filter=filter, limit=limit, cursor=cursor
            )}  # fmt: skip

        found = self._read(work, database)
        self._record_read(actor, "query", [found["database"]], len(found["rows"]))
        return found

    def page(self, page: str, *, actor: Actor = AGENT) -> dict[str, Any]:
        """An entry: its properties, and its page as Markdown."""
        found = self._read(lambda client: reading.entry(client, page, reading.shared_sources(client)), page)
        self._record_read(actor, "page", [found["id"]], 1)
        return found

    def search(self, text: str, *, actor: Actor = AGENT) -> list[dict[str, Any]]:
        """Entries and databases whose title holds the words."""
        found = self._read(lambda client: reading.search(client, text, reading.shared_sources(client)), "a search")
        self._record_read(actor, "search", [], len(found))
        return found

    def propose_entry(
        self,
        workspace: str,
        database: str,
        properties: dict[str, Any],
        *,
        markdown: str = "",
        why: str = "",
        sources: list[str] | None = None,
        actor: Actor = AGENT,
    ) -> dict[str, Any]:
        """Stage a new entry of a shared database in the workspace's open batch."""
        return self._staged(actor, database, lambda client: staging.entry(
            client, self.store, workspace, database, properties, markdown, why, list(sources or [])
        ))  # fmt: skip

    def propose_change(
        self,
        workspace: str,
        page: str,
        *,
        properties: dict[str, Any] | None = None,
        markdown: str = "",
        why: str = "",
        sources: list[str] | None = None,
        actor: Actor = AGENT,
    ) -> dict[str, Any]:
        """Stage a change to a shared entry (some of its properties, its page) in the workspace's open batch."""
        return self._staged(actor, page, lambda client: staging.change(
            client, self.store, workspace, page, dict(properties or {}), markdown, why, list(sources or [])
        ))  # fmt: skip

    def propose_removal(self, workspace: str, page: str, *, why: str = "", actor: Actor = AGENT) -> dict[str, Any]:
        """Stage the removal of a shared entry (to Notion's trash) in the workspace's open batch."""
        return self._staged(actor, page, lambda client: staging.removal(client, self.store, workspace, page, why))

    def submit(self, workspace: str, summary: str, *, actor: Actor = AGENT) -> dict[str, Any]:
        """Make the workspace's open batch ready for the owner's review, with the agent's summary (or the batch sent
        back to it, as its next revision); the batch. The session most recently active in the workspace is kept as
        the one that submitted it."""
        session = self.agent.session(workspace)
        with self.store.lock:
            batch = self.store.staging(workspace)
            if batch is None or (batch["state"] == "open" and not batch["proposals"]):
                raise NotionRefused("nothing is staged: propose entries, changes or removals first, then submit them")
            if batch["state"] == "returned":
                batch["revision"] += 1
            left = [each for each in batch["proposals"] if applying.left(each)]
            written = any(each.get("done") for each in batch["proposals"])
            batch["state"] = "written" if not left else "partly written" if written else "ready"
            batch["summary"] = summary.strip() or batch["summary"]
            batch["session"] = session
            self.store.save(batch)
        self.kernel.events.record(
            "notion.submitted",
            summary=f"{actor.describe()} made batch {batch['id']} ready for review ({len(batch['proposals'])}, "
            f"revision {batch['revision']})",
            actor=actor,
            subject=Subject(kind="notion-batch", id=batch["id"]),
            data={"batch": batch["id"], "count": len(batch["proposals"]), "revision": batch["revision"]},
        )
        return view(batch)

    def comment(
        self,
        id: str,
        text: str,
        *,
        proposal: str | None = None,
        field: str | None = None,
        block: int | None = None,
        actor: Actor,
    ) -> dict[str, Any]:
        """The owner's comment on a batch, a proposal, a property of it or a block of its page; the comment."""
        if actor.kind == "session":
            raise NotAllowed("the agent does not comment on its own proposals: it answers the owner's (notion_reply)")
        with self.store.lock:
            batch = self.batch(id)
            if batch["state"] not in ("ready", "partly written", "returned"):
                raise NotionRefused(f"batch {id} is {batch['state']}: comments are for a batch being reviewed")
            made = comments.made(batch, text, proposal, field, block, "you", to_text(self.kernel.clock.now()))
            batch.setdefault("comments", []).append(made)
            self.store.save(batch)
        on = "block" if block is not None else "property" if field else "proposal" if proposal else "batch"
        self.kernel.events.record(
            "notion.commented",
            summary=f"{actor.describe()} commented on batch {id} ({made['id']}, on its {on})",
            actor=actor,
            subject=Subject(kind="notion-batch", id=id),
            data={"batch": id, "comment": made["id"], "on": on, "proposal": proposal},
        )
        return made

    def uncomment(self, id: str, comment: str, *, actor: Actor) -> dict[str, Any]:
        """Take back a comment not sent to the agent yet; the batch in brief."""
        if actor.kind == "session":
            raise NotAllowed("only the owner takes back a comment")
        with self.store.lock:
            batch = self.batch(id)
            found = next((each for each in batch.get("comments") or [] if each["id"] == comment), None)
            if found is None:
                raise NotionRefused(f"batch {id} has no comment {comment}")
            if found["sent"]:
                raise NotionRefused(f"{comment} was sent to the agent already: it stays with the batch")
            batch["comments"].remove(found)
            self.store.save(batch)
        self.kernel.events.record(
            "notion.uncommented", summary=f"{actor.describe()} took back {comment} of batch {id}", actor=actor,
            subject=Subject(kind="notion-batch", id=id), data={"batch": id, "comment": comment},
        )  # fmt: skip
        return view(batch)

    def send_back(self, id: str, *, actor: Actor) -> dict[str, Any]:
        """Send a batch back to its agent with the comments not sent yet: one message to the session that submitted it
        (or a new one in the workspace's window); the batch in brief, where it went and what it said."""
        if actor.kind == "session":
            raise NotAllowed("only the owner sends a batch back")
        batch = self.batch(id)
        if batch["state"] not in ("ready", "partly written", "returned"):
            raise NotionRefused(f"batch {id} is {batch['state']}: only a batch being reviewed is sent back")
        unsent = [each for each in batch.get("comments") or [] if not each["sent"]]
        if not unsent:
            raise NotionRefused("comment first: the agent revises the batch for your comments")
        text = comments.message(batch)
        sent_to = self.agent.send(
            batch["workspace"], text, batch.get("session"), title=f"Revise Notion batch {id}", actor=actor
        )
        with self.store.lock:
            batch = self.batch(id)
            for each in batch["comments"]:
                if each["id"] in {sent["id"] for sent in unsent}:
                    each["sent"] = True
            batch["state"] = "returned"
            batch["returned"] = {"at": to_text(self.kernel.clock.now()), "to": sent_to}
            self.store.save(batch)
        self.kernel.events.record(
            "notion.returned",
            summary=f"{actor.describe()} sent batch {id} back to its agent with {len(unsent)} comments",
            actor=actor,
            subject=Subject(kind="notion-batch", id=id),
            data={"batch": id, "comments": len(unsent), "session": sent_to["session"], "new": sent_to["new"]},
        )
        return {**view(batch), "sent_to": sent_to, "message": text}

    def reply(self, workspace: str, comment: str, text: str, *, actor: Actor = AGENT) -> dict[str, Any]:
        """The agent's answer to a comment of the workspace's newest batch that has it; the comment."""
        if not text.strip():
            raise NotionRefused("the answer says nothing: say what you did, or why not")
        with self.store.lock:
            for batch in self.store.all(workspace):
                found = next((each for each in batch.get("comments") or [] if each["id"] == comment), None)
                if found is not None and batch["state"] in ("returned", "ready", "partly written"):
                    break
            else:
                raise NotionRefused(f"no comment {comment} waits for an answer in the batches of {workspace}")
            by = "the agent" if actor.kind == "session" else "you"
            found["replies"].append({"text": text.strip(), "by": by, "at": to_text(self.kernel.clock.now())})
            found["state"] = "answered"
            self.store.save(batch)
        self.kernel.events.record(
            "notion.replied", summary=f"{actor.describe()} answered {comment} of batch {batch['id']}", actor=actor,
            subject=Subject(kind="notion-batch", id=batch["id"]), data={"batch": batch["id"], "comment": comment},
        )  # fmt: skip
        return dict(found)

    def approve(
        self,
        id: str,
        *,
        proposals: list[str] | None = None,
        parts: dict[str, list[str]] | None = None,
        actor: Actor,
    ) -> dict[str, Any]:
        """Write a submitted batch's proposals to Notion, in order: all of them, those named, or some parts of them
        (`parts`: by proposal, its properties' names, `page`, or `removal`); the batch, with how many proposals were
        written (whole or in part), failed and are left."""
        if actor.kind == "session":
            raise NotAllowed("the agent cannot approve its own proposals: only the owner approves them")
        batch = self.batch(id)
        if batch["state"] == "open":
            raise NotionRefused(f"batch {id} is still being staged: the agent submits it first")
        if batch["state"] == "rejected":
            raise NotionRefused(f"batch {id} was rejected: nothing of it is written")
        ids = [each["id"] for each in batch["proposals"]]
        if parts is None:
            parts = {each: [] for each in (ids if proposals is None else proposals)}
        unknown = [each for each in parts if each not in ids]
        if unknown:
            raise NotionRefused(f"batch {id} has no proposal {', '.join(unknown)} (it has {', '.join(ids)})")
        chosen = [(each, asked) for each in batch["proposals"] if each["id"] in parts
                  for asked in [_asked(each, parts[each["id"]])] if asked]  # fmt: skip
        now = to_text(self.kernel.clock.now())
        self._read(lambda client: applying.write(client, batch, chosen, now), id)
        whole = [each for each in batch["proposals"] if not applying.left(each)]
        if len(whole) == len(batch["proposals"]):
            batch["state"] = "written"
        elif any(each.get("done") for each in batch["proposals"]):
            batch["state"] = "partly written"
        self.store.save(batch)
        counts = {
            "written": sum(1 for each, _ in chosen if "error" not in each["result"]),
            "failed": sum(1 for each, _ in chosen if "error" in each["result"]),
            "left": len(batch["proposals"]) - len(whole),
        }
        self.kernel.events.record(
            "notion.written",
            summary=f"{actor.describe()} approved batch {id}: {counts['written']} written, {counts['failed']} not",
            actor=actor,
            subject=Subject(kind="notion-batch", id=id),
            data={"batch": id, **counts},
        )
        return {**view(batch), **counts}

    def reject(self, id: str, reason: str, *, actor: Actor) -> dict[str, Any]:
        """Reject a batch with a reason: nothing of it is written."""
        if actor.kind == "session":
            raise NotAllowed("the agent cannot reject its own proposals: only the owner rejects them")
        batch = self.batch(id)
        if batch["state"] in ("written", "rejected"):
            raise NotionRefused(f"batch {id} is {batch['state']} already")
        batch["state"], batch["reason"] = "rejected", reason.strip()
        self.store.save(batch)
        self.kernel.events.record(
            "notion.rejected", summary=f"{actor.describe()} rejected batch {id}", actor=actor,
            subject=Subject(kind="notion-batch", id=id), data={"batch": id},
        )  # fmt: skip
        return view(batch)

    def batches(self, *, workspace: str | None = None) -> list[dict[str, Any]]:
        """The batches (of a workspace), newest first, in brief."""
        return [view(batch) for batch in self.store.all(workspace)]

    def batch(self, id: str) -> dict[str, Any]:
        """A batch, whole."""
        found = self.store.get(id)
        if found is None:
            raise NotionRefused(f"there is no batch {id}")
        return found

    def tables(self, id: str, *, everything: bool = False) -> list[dict[str, Any]]:
        """Each database a batch touches as a table of its entries now, marked with the batch's proposals: the
        changed ones and their neighbors, or every one."""
        batch = self.batch(id)
        return self._read(lambda client: tables.tables(client, batch, everything=everything), id)

    def _staged(self, actor: Actor, target: str, work: Callable[[NotionClient], tuple[dict[str, Any], dict[str, Any]]]
                ) -> dict[str, Any]:  # fmt: skip
        batch, proposal = self._read(work, target)
        self.kernel.events.record(
            "notion.staged",
            summary=f"{actor.describe()} staged a {proposal['kind']} in batch {batch['id']} ({proposal['id']})",
            actor=actor,
            subject=Subject(kind="notion-batch", id=batch["id"]),
            data={"batch": batch["id"], "proposal": proposal["id"], "kind": proposal["kind"],
                  "database": proposal["database"]},
        )  # fmt: skip
        said = f"staged as {proposal['id']} of batch {batch['id']}: the owner reviews it once submitted"
        return {"batch": batch["id"], "proposal": proposal["id"], "notes": proposal["notes"], "staged": said}

    def using(self, work: Callable[[NotionClient], T], *, why: str) -> T:
        """Do a piece of work with a client holding the secret (its use recorded, with why)."""
        secret = self.kernel.secrets.value(SCOPE, NAME, user="notion", why=why)
        client = self._client(secret)
        try:
            return work(client)
        finally:
            client.close()

    def _read(self, work: Callable[[NotionClient], T], target: str) -> T:
        """A piece of reading, each failure said for whoever asked."""
        try:
            return self.using(work, why="reading Notion")
        except SecretsError as error:
            raise NotionRefused(f"Clank is not connected to Notion: {HOW}") from error
        except NotionError as error:
            if error.status == 404:
                raise NotionRefused(
                    f"{reading.bare(target)} is not shared with Clank's integration, or does not exist: share its "
                    "database (or the page holding it) with the Clank integration in Notion"
                ) from error
            raise NotionRefused(f"Notion answered: {error}") from error

    def _record_read(self, actor: Actor, what: str, ids: list[str], count: int) -> None:
        self.kernel.events.record(
            "notion.read",
            summary=f"{actor.describe()} read Notion: {what} ({count})",
            actor=actor,
            subject=SUBJECT,
            data={"what": what, "ids": ids, "count": count},
        )

    def _client(self, secret: str) -> NotionClient:
        settings = self.settings()
        return NotionClient(
            secret, api=settings.api, version=settings.version, transport=self.transport, sleep=self.sleep
        )

    def _status(self, names: dict[str, str], problem: str) -> dict[str, Any]:
        shown = self.kernel.secrets.shown(SCOPE)
        secret = {"set": shown[0].set, "ends": shown[0].ends} if shown else None
        return {"connected": secret is not None, **names, "secret": secret, "problem": problem}

    def router(self) -> Any:
        """The component's routes."""
        from clank.components.notion.api import router

        return router(self)


def _asked(proposal: dict[str, Any], asked: list[str]) -> list[str]:
    """The parts of a proposal to write now: those asked (none named: all of them) that are not written yet; a new entry
    is made only with its title."""
    known = applying.parts(proposal)
    strange = [part for part in asked if part not in known]
    if strange:
        raise NotionRefused(f"{proposal['id']} has no part {', '.join(strange)} (its parts: {', '.join(known)})")
    wanted = [part for part in applying.left(proposal) if not asked or part in asked]
    title = applying.title_name(proposal)
    if wanted and proposal["kind"] == "entry" and not proposal.get("done") and title not in wanted:
        raise NotionRefused(
            f"{proposal['id']} is a new entry and needs its title ({title}) to be made: approve it with the other parts"
        )
    return wanted


def _names(me: dict[str, Any]) -> dict[str, str]:
    bot = me.get("bot") or {}
    return {"integration": str(me.get("name") or "the integration"), "workspace": str(bot.get("workspace_name") or "")}
