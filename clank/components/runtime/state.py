"""The runtime's state (design 0003 §3 and §6): what each slot runs, each launch, each engine installed, in the
runtime's own tables (migration `runtime 0001`), read by clients as the state kinds `slot`, `launch` and `install`.

A slot that never ran is `stopped`. Each change of a slot's state is kept with its time and reason and announced as a
`runtime.slot` event in the same transaction (design 0001 §4.1, §4.8); a slot that stops or fails runs nothing, so its
preset and process identity are cleared, while the last configuration that worked stays with it (§4.3). A launch is
each start of an engine, with its plan, its estimate and what it measured; an install is an engine on a host, with the
command that runs it.
"""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from clank.kernel.clock import Clock, from_text, to_text
from clank.kernel.events import Actor, EventLog, EventType, Subject
from clank.kernel.records import StateKind
from clank.kernel.store import Store

SlotStatus = Literal["stopped", "starting", "ready", "stopping", "failed"]
Outcome = Literal["starting", "ready", "failed", "stopped", "crashed"]
RUNNING_FIELDS = ("preset", "launch_id", "host", "pid", "started", "command", "port")
EVENT_TYPES = [
    EventType(
        "runtime.slot",
        "A slot's state changed: it started, became ready, stopped or failed (design 0001 §4.1).",
        {
            "slot": "The slot, such as main.",
            "status": "Its new state: stopped, starting, ready, stopping or failed.",
            "reason": "Why, in a few words.",
            "preset": "The preset it runs, if any.",
        },
        owner="runtime",
    )
]


class LastGood(BaseModel):
    """The configuration that last reached ready and answered (design 0001 §4.3)."""

    preset: str = Field(title="Preset", description="The preset's id.")
    options: dict[str, Any] = Field(default_factory=dict, title="Options", description="Its options then.")
    time: datetime = Field(title="Time", description="When it last reached ready.")


class SlotRecord(StateKind):
    """What a slot runs now."""

    KIND = "slot"
    LABEL = "Slot"
    HELP = "A seat for a model (design 0001 §1): its state since when and why, what it runs, and on which process."

    name: str = Field(title="Name", description="The slot, such as main.")
    status: SlotStatus = Field(title="State", description="stopped, starting, ready, stopping or failed.")
    since: datetime = Field(title="Since", description="When it reached that state.")
    reason: str = Field("", title="Why", description="Why it is in that state.")
    preset: str | None = Field(None, title="Preset", description="The preset it runs or starts.")
    launch_id: int | None = Field(None, title="Launch", description="The launch that runs now.")
    host: str | None = Field(None, title="Host", description="Where its engine runs.")
    pid: int | None = Field(None, title="Process", description="Its engine's process id on that host.")
    started: str | None = Field(None, title="Process start", description="Its process's start time, as its host says.")
    command: str | None = Field(None, title="Command", description="The SHA-256 of its process's command line.")
    port: int | None = Field(None, title="Port", description="Where its engine listens.")
    last_good: LastGood | None = Field(
        None, title="Last that worked", description="The last configuration that worked."
    )

    @property
    def id(self) -> str:
        """Its id, for clients: its name."""
        return self.name

    @property
    def title(self) -> str:
        """One line on it."""
        return f"{self.name}: {self.status}"


class LaunchRecord(StateKind):
    """One start of an engine."""

    KIND = "launch"
    LABEL = "Launch"
    HELP = "One start of an engine: its plan and estimate, how long it took, what memory it took, how it ended."

    id: int = Field(title="Id", description="Its number.")
    slot: str = Field(title="Slot", description="The slot it was for.")
    preset: str = Field(title="Preset", description="The preset it started.")
    options: dict[str, Any] = Field(default_factory=dict, title="Options", description="The preset's options then.")
    engine: str = Field(title="Serving setup", description="The engine adapter.")
    engine_version: str = Field(title="Engine version", description="The engine's version.")
    host: str = Field(title="Host", description="Where it ran.")
    command_line: str = Field(title="Command line", description="Exactly what ran, its environment first.")
    log: str = Field(title="Log", description="Where its output went.")
    started_at: datetime = Field(title="Started", description="When it was started.")
    ready_at: datetime | None = Field(None, title="Ready", description="When it was ready.")
    ended_at: datetime | None = Field(None, title="Ended", description="When it ended.")
    outcome: Outcome = Field(title="Outcome", description="starting, ready, failed, stopped or crashed.")
    detail: str = Field("", title="Detail", description="Why it failed or ended, in the engine's words.")
    estimate_mib: int | None = Field(None, title="Estimate", description="The GPU memory it was expected to take, MiB.")
    before_mib: int | None = Field(None, title="Before", description="The GPU memory in use before it started, MiB.")
    measured_mib: int | None = Field(None, title="Measured", description="The GPU memory it took once ready, MiB.")
    needed_mib: int | None = Field(
        None,
        title="Needed",
        description="The GPU memory it needed free to start, MiB, when its engine says (one that reserves extra).",
    )
    seconds: float | None = Field(None, title="Time to start", description="From its start to ready, in seconds.")
    endpoint: str = Field(
        "", title="Provider", description="For a cloud preset's launch: the provider it reached; empty for an engine's."
    )
    route: dict[str, Any] | None = Field(
        None, title="Route", description="For a cloud preset's launch: the route it gave the gateway (never a key)."
    )
    cost_usd: float | None = Field(
        None, title="Cost", description="What its own requests cost, in US dollars (a cloud launch's tiny request)."
    )

    @property
    def title(self) -> str:
        """One line on it."""
        return f"{self.preset} on {self.host or self.endpoint}: {self.outcome}"


class InstallRecord(StateKind):
    """An engine installed on a host."""

    KIND = "install"
    LABEL = "Install"
    HELP = "An engine installed on a host: the command that runs it, its folder and libraries, how it got there."

    setup: str = Field(title="Serving setup", description="The engine adapter it is for.")
    version: str = Field(title="Version", description="The engine's version.")
    host: str = Field(title="Host", description="Where it is.")
    program: list[str] = Field(title="Program", description="The command that runs it.")
    folder: str = Field(title="Folder", description="Its folder, where it runs.")
    library_path: str = Field("", title="Libraries", description="Its libraries' folders, for LD_LIBRARY_PATH.")
    how: Literal["adopted", "recipe", "test"] = Field(
        title="How", description="adopted: found where it was; recipe: built or installed by Clank; test: a fake."
    )
    detail: str = Field("", title="Detail", description="Where it came from: a commit, a release, a deviation.")
    installed: datetime | None = Field(None, title="Installed", description="When Clank recorded it.")

    @property
    def id(self) -> str:
        """Its id: setup, version and host."""
        return f"{self.setup}@{self.version}@{self.host}"

    @property
    def title(self) -> str:
        """One line on it."""
        return f"{self.setup} {self.version} on {self.host}"


class RuntimeState:
    """The runtime's tables."""

    def __init__(self, store: Store, events: EventLog, clock: Clock) -> None:
        self._store = store
        self._events = events
        self._clock = clock

    def slot(self, name: str) -> SlotRecord:
        """What a slot runs; a slot that never ran is stopped."""
        rows = self._store.read("SELECT * FROM slots WHERE name = ?", (name,))
        if not rows:
            return SlotRecord(name=name, status="stopped", since=self._clock.now(), reason="never started")
        return _slot(rows[0])

    def slots(self, names: list[str]) -> list[SlotRecord]:
        """The slots of these names."""
        return [self.slot(name) for name in names]

    def set_slot(
        self, name: str, status: SlotStatus, reason: str, *, actor: Actor, keep_since: bool = False, **running: Any
    ) -> SlotRecord:
        """Change a slot's state, keeping why, and announce it; a stopped or failed slot runs nothing. `keep_since`
        keeps when an unchanged state began (an engine adopted after a restart has been ready all along)."""
        unknown = set(running) - set(RUNNING_FIELDS)
        if unknown:
            raise ValueError(f"a slot has no field {', '.join(sorted(unknown))}")
        current = self.slot(name)
        values = {field: getattr(current, field) for field in RUNNING_FIELDS} | running
        if status in ("stopped", "failed"):
            failed = running.get("preset", current.preset) if status == "failed" else None
            values = dict.fromkeys(RUNNING_FIELDS) | {"preset": failed}
        now = current.since if keep_since and status == current.status else self._clock.now()
        good = current.last_good.model_dump_json() if current.last_good else None
        with self._store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO slots (name, status, since, reason, preset, launch_id, host, pid, started,"
                " command, port, last_good) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, status, to_text(now), reason, *(values[field] for field in RUNNING_FIELDS), good),
            )
            self._events.record(
                "runtime.slot",
                summary=f"{name}: {status} ({reason})",
                actor=actor,
                subject=Subject(kind="slot", id=name),
                data={"slot": name, "status": status, "reason": reason, "preset": values["preset"]},
            )
        return self.slot(name)

    def update_slot(self, name: str, **running: Any) -> SlotRecord:
        """Fill in what a slot in its present state runs (its process, once started), without a change to announce."""
        unknown = set(running) - set(RUNNING_FIELDS)
        if unknown:
            raise ValueError(f"a slot has no field {', '.join(sorted(unknown))}")
        assignments = ", ".join(f"{field} = ?" for field in running)
        with self._store.transaction() as db:
            db.execute(f"UPDATE slots SET {assignments} WHERE name = ?", (*running.values(), name))
        return self.slot(name)

    def now(self) -> datetime:
        """The runtime's clock."""
        return self._clock.now()

    def remember_good(self, name: str, good: LastGood) -> None:
        """Keep the configuration that last worked with the slot."""
        current = self.slot(name)
        with self._store.transaction() as db:
            if not self._store.read("SELECT name FROM slots WHERE name = ?", (name,)):
                db.execute(
                    "INSERT INTO slots (name, status, since, reason) VALUES (?, ?, ?, ?)",
                    (name, current.status, to_text(current.since), current.reason),
                )
            db.execute("UPDATE slots SET last_good = ? WHERE name = ?", (good.model_dump_json(), name))

    def add_launch(self, **fields: Any) -> int:
        """Keep a new launch, starting now; returns its number."""
        with self._store.transaction() as db:
            cursor = db.execute(
                "INSERT INTO launches (slot, preset, options, engine, engine_version, host, command_line, log,"
                " started_at, outcome, estimate_mib, before_mib, endpoint, route)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'starting', ?, ?, ?, ?)",
                (
                    fields["slot"],
                    fields["preset"],
                    json.dumps(fields.get("options", {})),
                    fields["engine"],
                    fields["engine_version"],
                    fields["host"],
                    fields["command_line"],
                    fields["log"],
                    to_text(self._clock.now()),
                    fields.get("estimate_mib"),
                    fields.get("before_mib"),
                    fields.get("endpoint", ""),
                    json.dumps(fields["route"]) if fields.get("route") is not None else None,
                ),
            )
            return int(cursor.lastrowid or 0)

    def set_route(self, id: int, route: dict[str, Any]) -> None:
        """The route a cloud launch gives the gateway, once its number is known (the route names it)."""
        with self._store.transaction() as db:
            db.execute("UPDATE launches SET route = ? WHERE id = ?", (json.dumps(route), id))

    def set_log(self, id: int, log: str) -> None:
        """Where a launch's output goes, once it is known (it names the launch)."""
        with self._store.transaction() as db:
            db.execute("UPDATE launches SET log = ? WHERE id = ?", (log, id))

    def finish_launch(self, id: int, outcome: Outcome, *, detail: str = "", **measured: Any) -> None:
        """Keep how a launch went: ready (with what it measured), or how it ended."""
        now = to_text(self._clock.now())
        moment = "ready_at" if outcome == "ready" else "ended_at"
        with self._store.transaction() as db:
            db.execute(
                f"UPDATE launches SET outcome = ?, detail = ?, {moment} = ?,"
                " measured_mib = COALESCE(?, measured_mib), needed_mib = COALESCE(?, needed_mib),"
                " seconds = COALESCE(?, seconds), cost_usd = COALESCE(?, cost_usd) WHERE id = ?",
                (
                    outcome,
                    detail,
                    now,
                    measured.get("measured_mib"),
                    measured.get("needed_mib"),
                    measured.get("seconds"),
                    measured.get("cost_usd"),
                    id,
                ),
            )

    def launch(self, id: int) -> LaunchRecord:
        """A launch; `KeyError` when there is none."""
        rows = self._store.read("SELECT * FROM launches WHERE id = ?", (id,))
        if not rows:
            raise KeyError(f"there is no launch {id}")
        return _launch(rows[0])

    def launches(self, limit: int = 50, *, engine: str | None = None, host: str | None = None) -> list[LaunchRecord]:
        """The newest launches, newest first; of one engine on one host when asked."""
        where, params = "", []
        if engine is not None and host is not None:
            where, params = " WHERE engine = ? AND host = ?", [engine, host]
        rows = self._store.read(f"SELECT * FROM launches{where} ORDER BY id DESC LIMIT ?", (*params, limit))
        return [_launch(row) for row in rows]

    def add_install(self, install: InstallRecord, when: datetime) -> InstallRecord:
        """Keep an engine installed on a host (replacing one of the same setup, version and host)."""
        with self._store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO installs (id, setup, version, host, program, folder, library_path, how, detail,"
                " installed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    install.id,
                    install.setup,
                    install.version,
                    install.host,
                    json.dumps(install.program),
                    install.folder,
                    install.library_path,
                    install.how,
                    install.detail,
                    to_text(when),
                ),
            )
        found = self.install(install.setup, install.version, install.host)
        assert found is not None
        return found

    def remove_install(self, setup: str, version: str, host: str) -> bool:
        """Forget an engine installed on a host; whether there was one."""
        with self._store.transaction() as db:
            gone = db.execute("DELETE FROM installs WHERE id = ?", (f"{setup}@{version}@{host}",)).rowcount
        return bool(gone)

    def install(self, setup: str, version: str, host: str) -> InstallRecord | None:
        """The install of a setup's version on a host, if any."""
        rows = self._store.read("SELECT * FROM installs WHERE id = ?", (f"{setup}@{version}@{host}",))
        return _install(rows[0]) if rows else None

    def installs(self) -> list[InstallRecord]:
        """Every install."""
        return [_install(row) for row in self._store.read("SELECT * FROM installs ORDER BY id")]


def _slot(row: Any) -> SlotRecord:
    values = dict(row)
    values["since"] = from_text(values["since"])
    values["last_good"] = LastGood.model_validate_json(values["last_good"]) if values["last_good"] else None
    return SlotRecord.model_validate(values)


def _launch(row: Any) -> LaunchRecord:
    values = dict(row)
    values["options"] = json.loads(values["options"])
    values["route"] = json.loads(values["route"]) if values.get("route") else None
    for moment in ("started_at", "ready_at", "ended_at"):
        values[moment] = from_text(values[moment]) if values[moment] else None
    return LaunchRecord.model_validate(values)


def _install(row: Any) -> InstallRecord:
    values = dict(row)
    values.pop("id")
    values["program"] = json.loads(values["program"])
    values["installed"] = from_text(values["installed"])
    return InstallRecord.model_validate(values)
