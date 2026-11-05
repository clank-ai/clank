"""The tools component's part (design 0002 §1; the M8.0 plan): the MCP servers Clank knows, and checking one.

A server added for the user (scope `user`) is a settings record, `config/mcp-servers/<name>.json`, holding how to start
or reach it, with the names of its environment variables and headers; their values are secrets (`mcp-server/<name>`,
named `env.<NAME>` and `header.<Name>`), never in the record or an event. A project's servers (scope `project`) are its
`.mcp.json` (`{"mcpServers": {...}}`), the file other harnesses read and write: Clank reads it from the folder a client
names and writes an entry as the standard has it, values included, leaving the rest of the file as it was. A name is a
plain word (letters, digits, `-` and `_`, as other harnesses allow), new in its place whatever its case (Windows does
not tell `Foo.json` from `foo.json`); a name in both places is asked about by `server`, `remove` and `check` until the
scope is given. `check` is an operation (`mcp.check`): it starts or reaches the server, with its secrets (each use
recorded), asks it what it is and what tools it offers, and ends it; given a workspace, it starts the server in that
workspace's running container, with its agent's environment, where the agent will start it (design 0004 §10).
Clank's own server (`clank`, scope `clank`: `send_to_phone`) is in the image, so it is checked in a workspace only. A
project's server is offered, never trusted (design 0002 §2.11), so it is never started on this computer: it is checked
only in its folder's workspace container (the folder's workspace, found when none is named), and with no workspace for
the folder, its container not running, another folder's workspace named, or a server reached by address, the check is
refused, saying how to check it (decision 0166). Its check says whether that workspace's agent may use it as it is now:
allowed, not allowed yet, or changed since it was allowed (`fingerprint`, the digest of its entry the agents component
keeps when the owner allows it: a changed command, argument or environment counts as not allowed until allowed again).

The last check of each server that answered is remembered (`state/mcp-checks.json`): what the server is, its tools with
their parameters, when, and where it ran; `checked` gives it while the server is started or reached as it was then
(a changed command or address is checked again), for the console's MCP servers page.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from clank.components.tools.mcp import McpError, check, parse_entry
from clank.components.tools.mcp import Server as Server  # for the components that use this one (design 0004 §10)
from clank.components.tools.mcp import through as through
from clank.kernel import files
from clank.kernel.api import ApiError
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.settings import SettingsError

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

Scope = Literal["user", "project"]
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
PROJECT_FILE = ".mcp.json"
KIND = "mcp-server"
CHECK_SECONDS = 30.0
CHECKS = "mcp-checks.json"
CLANK = "clank"  # Clank's own server, in the image
EVENT_TYPES = [
    EventType(
        "mcp.changed",
        "An MCP server was added or removed, yours or a project's (whose .mcp.json changes are told no other way).",
        {"name": "The server.", "scope": "user or project.", "how": "added or removed.", "file": "Where it is kept."},
    )
]


class Tools:
    """The tools component, built on the kernel."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        kernel.events.subscribe(self._heard)

    def _heard(self, event: Any) -> None:
        """A cloud provider was added with the owner's agreement (design 0016 §10): the MCP servers the agreement
        screen marked are marked local only (none named: every one already added, since they were added when nothing
        left this machine)."""
        if event.type != "runtime.endpoint_added":
            return
        named = event.data.get("local_mcp")
        mine = [loaded.id for loaded in self._records()]
        for name in mine if named is None else [name for name in named if name in mine]:
            self.set_local(name, True, actor=event.actor)

    def cloud_agreed(self) -> bool:
        """Whether a cloud provider is agreed now (its record's `agreed`, design 0016 §4)."""
        return any(loaded.record.model_dump().get("agreed") for loaded in self.kernel.settings.records("endpoint"))

    def set_local(self, name: str, local_only: bool, *, actor: Actor) -> dict[str, Any]:
        """Mark one of the owner's servers local only, or not (design 0016 §10); a project's server goes with its
        folder, so it has no mark."""
        if not any(loaded.id == name for loaded in self._records()):
            raise ApiError(404, "not_found", f"{name} is not one of your servers; a project's goes with its folder")
        loaded = self.kernel.settings.get(KIND, name)
        values = {**loaded.record.model_dump(), "local_only": local_only}
        if values != loaded.record.model_dump():
            self.kernel.settings.write(KIND, name, values, base=loaded.revision, actor=actor)
        return self.server(name, scope="user")

    def local_only(self) -> list[str]:
        """The owner's servers marked local only."""
        return [loaded.id for loaded in self._records() if loaded.record.model_dump().get("local_only")]

    def servers(self, folder: str = "") -> list[dict[str, Any]]:
        """Every server: the user's, then the project's of the folder, each by name."""
        found = [self._view(loaded.id, "user", self._user(loaded.id)) for loaded in self._records()]
        found += [self._view(name, "project", server, file) for name, server, file in self._project(folder)]
        return found

    def server(self, name: str, folder: str = "", scope: Scope | None = None) -> dict[str, Any]:
        """One server, as a client may see it."""
        where = self._where(name, folder, scope)
        if where == "user":
            return self._view(name, "user", self._user(name))
        server, file = self._in_project(name, folder)
        return self._view(name, "project", server, file)

    def add(
        self,
        name: str,
        entry: dict[str, Any],
        *,
        scope: Scope,
        folder: str,
        actor: Actor,
        local_only: bool | None = None,
    ) -> dict[str, Any]:
        """Add a server in its place: its record and secrets for the user, its entry in the project's `.mcp.json`. One
        of yours is local only as asked; asked nothing, it is while a cloud provider is agreed (design 0016 §10: what
        it gives the agent never goes to the cloud until the owner says it may), and not before."""
        if local_only is None:
            local_only = self.cloud_agreed()
        if not NAME.fullmatch(name):
            raise ApiError(400, "invalid", f"{name!r} cannot be a server's name: letters, digits, '-' and '_' only")
        try:
            server = parse_entry(entry)
        except McpError as error:
            raise ApiError(400, "invalid", str(error)) from error
        taken = [
            found["name"]
            for found in self.servers(folder)
            if found["scope"] == scope and found["name"].lower() == name.lower()
        ]
        if taken:
            raise ApiError(409, "refused", f"{taken[0]} is already a server of {_place(scope)}: remove it first")
        if scope == "project":
            self._write_project(folder, name, server.entry())
            return self._changed(self.server(name, folder, "project"), "added", actor)
        values = {
            "transport": server.transport, "command": server.command, "args": server.args, "env": sorted(server.env),
            "url": server.url, "headers": sorted(server.headers), "local_only": local_only,
        }  # fmt: skip
        try:
            self.kernel.settings.write(KIND, name, values, base=None, actor=actor)
        except SettingsError as error:
            raise ApiError(400, "invalid", str(error)) from error
        for key, value in server.env.items():
            self.kernel.secrets.put(f"{KIND}/{name}", f"env.{key}", value, actor=actor)
        for key, value in server.headers.items():
            self.kernel.secrets.put(f"{KIND}/{name}", f"header.{key}", value, actor=actor)
        return self._changed(self.server(name, folder, "user"), "added", actor)

    def remove(self, name: str, *, scope: Scope | None, folder: str, actor: Actor) -> dict[str, Any]:
        """Remove a server from its place, with its secrets."""
        where = self._where(name, folder, scope)
        file = self.server(name, folder, where)["file"]
        if where == "user":
            loaded = self.kernel.settings.get(KIND, name)
            self.kernel.settings.delete(KIND, name, base=loaded.revision, actor=actor)
            self.kernel.secrets.remove(f"{KIND}/{name}", actor=actor)
        else:
            self._write_project(folder, name, None)
        return self._changed({"name": name, "scope": where, "file": file, "removed": True}, "removed", actor)

    def runnable(self, name: str, folder: str = "", scope: Scope | None = None, *, why: str) -> Server:
        """The server with its secrets' values, for whoever starts or reaches it (each use recorded)."""
        where = self._where(name, folder, scope)
        if where == "project":
            return self._in_project(name, folder)[0]
        server = self._user(name)
        values = {
            key: self.kernel.secrets.value(f"{KIND}/{name}", f"env.{key}", user="tools", why=why) for key in server.env
        }
        headers = {
            key: self.kernel.secrets.value(f"{KIND}/{name}", f"header.{key}", user="tools", why=why)
            for key in server.headers
        }
        return Server(server.transport, server.command, list(server.args), values, server.url, headers)

    def checked(self, name: str, scope: str, folder: str = "") -> dict[str, Any] | None:
        """The last check of a server that answered, while it is started or reached as it was then; None otherwise."""
        try:
            server = self._clank() if scope == CLANK else self._user(name) if scope == "user" else None
            if server is None:
                server = self._in_project(name, folder)[0]
        except (ApiError, SettingsError):
            return None
        return self._remembered(name, scope, server)

    def _remembered(self, name: str, scope: str, server: Server) -> dict[str, Any] | None:
        found = self._checks().get(f"{scope}:{name}")
        return dict(found) if found is not None and found.get("key") == _key_of(server) else None

    def operation_types(self) -> list[OperationType]:
        """Checking a server."""
        return [OperationType("mcp.check", "Check an MCP server", (StepSpec("check"),), self._check, owner="tools")]

    def router(self) -> Any:
        """The servers' routes."""
        from clank.components.tools.api import router

        return router(self)

    async def _check(self, context: OperationContext) -> dict[str, Any]:
        params = context.params
        name, folder = str(params["name"]), str(params.get("folder") or "")
        scope = params.get("scope") or None
        seconds = float(params.get("seconds") or CHECK_SECONDS)
        workspace = str(params.get("workspace") or "")
        allowance: dict[str, Any] = {}
        async with context.step("check"):
            if scope == CLANK:
                if not workspace:
                    raise ApiError(409, "refused", "Clank's own server is in the workspace's image: check it there")
                server, place, box = self._clank(), CLANK, ""
            else:
                server = self.runnable(name, folder, scope, why="a check")
                place, box = self._where(name, folder, scope), ""
            if place == "project":  # never on this computer: in the folder's workspace container alone
                workspace, box = self._projects_workspace(name, folder, workspace, server)
                allowance = self._allowance(name, workspace, server)
            key = self._key(name, place, folder)
            shown = server.command if server.transport == "stdio" else server.url
            if workspace:
                server = self._in_workspace(server, workspace, box)
                context.log(f"in {workspace}'s container, as its agent starts it")
            context.log(f"asking {name} ({server.transport}: {shown}) what it is and what tools it offers")
            try:
                found = await context.run_blocking(check, server, seconds)
            except McpError as error:
                raise ApiError(409, "refused", f"{name}: {error}") from error
            context.log(
                f"{found.name} {found.version} answers (protocol {found.protocol}), with {len(found.tools)} tools"
            )
            if allowance:
                context.log(f"{name}: {allowance['allowed_said']}")
        result = {
            "name": found.name, "version": found.version, "protocol": found.protocol,
            "tools": [
                {"name": tool.name, "description": tool.description, "parameters": [
                    {"name": each.name, "type": each.type, "required": each.required, "description": each.description}
                    for each in tool.parameters
                ], "read_only": tool.read_only}
                for tool in found.tools
            ],
        }  # fmt: skip
        where = f"{workspace}'s container" if workspace else "this computer"
        self._remember(f"{place}:{name}", {**result, "key": key, "where": where})
        return {**result, **allowance}  # whether it is allowed is the workspace's now, never remembered with the check

    def _projects_workspace(self, name: str, folder: str, asked: str, server: Server) -> tuple[str, str]:
        """Where a folder's own server is checked (design 0004 §10): the folder's workspace, found when not named, and
        its running container's name. It is never started on this computer: with no workspace for the folder, its
        container not running, another folder's workspace named, or a server reached by address (nothing but the model
        is reachable from the container), the check is refused, saying how to check it."""
        from clank.components.workspaces.service import Workspaces, WorkspaceUnavailable

        own = (
            f"{name} is this folder's own (.mcp.json): Clank checks it only in the folder's workspace container, "
            "never on this computer"
        )
        if server.transport != "stdio":
            raise ApiError(
                409, "refused", f"{own}, and it is reached by address: nothing but the model is reachable from the "
                "container yet, so it is not checked (nor does the agent get it)",
            )  # fmt: skip
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        found = workspaces.of_folder(folder)
        if found is None:
            raise ApiError(
                409, "refused", f"{own}, and {folder} is no workspace yet: `clank workspace open` makes it one (in the "
                "console, F4 then o); then check it again",
            )  # fmt: skip
        if asked and asked != found:
            raise ApiError(409, "refused", f"{own}, and {asked} is not this folder's workspace: check it in {found}")
        try:
            box = workspaces.container_of(found)
        except WorkspaceUnavailable as error:
            raise ApiError(409, "refused", f"{own}, and {error}; then check it again") from error
        return found, box

    def _allowance(self, name: str, workspace: str, server: Server) -> dict[str, Any]:
        """Whether the workspace's agent may use a folder's own server as it is now (design 0004 §10): allowed as it
        is, not allowed yet, or changed since it was allowed (its command, its arguments or its environment), which
        counts as not allowed until the owner allows it again."""
        allowed = self.kernel.settings.get("workspace", workspace).record.model_dump().get("mcp_allowed") or {}
        how = f"`clank mcp allow {name}` in the folder, or s on the MCP servers page (F3)"
        if name not in allowed:
            said = f"not allowed for {workspace}'s agent yet: {how} allows it as it is now"
        elif allowed[name] != fingerprint(server):
            said = (
                f"its command, arguments or environment changed since you allowed it: {workspace}'s agent does not "
                f"get it until you allow it again ({how})"
            )
        else:
            return {"allowed": True, "allowed_said": f"allowed for {workspace}'s agent as it is now"}
        return {"allowed": False, "allowed_said": said}

    def _clank(self) -> Server:
        from clank.components.workspaces.service import PHONE_PROGRAM

        return Server("stdio", command="python3", args=[PHONE_PROGRAM])

    def _key(self, name: str, scope: str, folder: str) -> str:
        if scope == CLANK:
            return _key_of(self._clank())
        return _key_of(self._user(name) if scope == "user" else self._in_project(name, folder)[0])

    def _checks(self) -> dict[str, dict[str, Any]]:
        file = self.kernel.home.state / CHECKS
        try:
            found = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    def _remember(self, key: str, check: dict[str, Any]) -> None:
        checks = {**self._checks(), key: {**check, "time": self.kernel.clock.now().isoformat()}}
        files.replace(self.kernel.home.state / CHECKS, json.dumps(checks, indent=1) + "\n")

    def _in_workspace(self, server: Server, workspace: str, box: str = "") -> Server:
        """The server started in a workspace's running container (`box`, when just found running), with the agent's
        environment (design 0004 §10)."""
        from clank.components.workspaces.service import Workspaces, WorkspaceUnavailable

        workspaces: Workspaces = self.kernel.parts["workspaces"]
        try:
            base = workspaces.agent_env(workspace)
            return through(
                server,
                lambda argv, env: workspaces.exec_argv(workspace, argv, {**base, **env}, terminal=False, container=box),
            )
        except (McpError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error

    def _changed(self, server: dict[str, Any], how: str, actor: Actor) -> dict[str, Any]:
        where = "yours" if server["scope"] == "user" else "a project's"
        self.kernel.events.record(
            "mcp.changed",
            summary=f"{actor.describe()} {how} the MCP server {server['name']} ({where})",
            actor=actor,
            subject=Subject(kind=KIND, id=server["name"]),
            data={"name": server["name"], "scope": server["scope"], "how": how, "file": server["file"]},
        )
        return server

    def _records(self) -> list[Any]:
        return sorted(self.kernel.settings.records(KIND), key=lambda loaded: loaded.id)

    def _user(self, name: str) -> Server:
        record = self.kernel.settings.get(KIND, name).record
        values = record.model_dump()
        env = dict.fromkeys(values["env"], "")
        headers = dict.fromkeys(values["headers"], "")
        return Server(values["transport"], values["command"], list(values["args"]), env, values["url"], headers)

    def _project(self, folder: str) -> list[tuple[str, Server, str]]:
        if not folder:
            return []
        file = Path(folder) / PROJECT_FILE
        if not file.is_file():
            return []
        found = []
        for name, entry in sorted(self._read_project(file).items()):
            try:
                found.append((name, parse_entry(entry), str(file)))
            except McpError:
                continue  # an entry other harnesses wrote that Clank does not read; left as it is
        return found

    def _in_project(self, name: str, folder: str) -> tuple[Server, str]:
        for found, server, file in self._project(folder):
            if found == name:
                return server, file
        raise ApiError(404, "not_found", f"{name} is not a server of {_place('project')}")

    def _where(self, name: str, folder: str, scope: Scope | None) -> Scope:
        mine = any(loaded.id == name for loaded in self._records())
        theirs = any(found == name for found, _, _ in self._project(folder))
        if (scope == "user" and mine) or (scope == "project" and theirs):
            return scope
        if scope is None and mine and theirs:
            raise ApiError(409, "refused", f"{name} is in both your servers and this project's: say which (--scope)")
        if scope is None and (mine or theirs):
            return "user" if mine else "project"
        raise ApiError(
            404, "not_found", f"{name} is not a server of {_place(scope) if scope else 'yours or this project'}"
        )

    def _view(self, name: str, scope: Scope, server: Server, file: str = "") -> dict[str, Any]:
        shown = self.kernel.secrets.shown(f"{KIND}/{name}") if scope == "user" else []
        return {
            "name": name, "scope": scope, "transport": server.transport, "command": server.command,
            "args": list(server.args), "env": sorted(server.env), "url": server.url, "headers": sorted(server.headers),
            "file": file or str(self.kernel.home.config / "mcp-servers" / f"{name}.json"),
            "secrets": [{"name": secret.name, "set": secret.set, "ends": secret.ends} for secret in shown],
            "checked": self._remembered(name, scope, server),
            "local_only": scope == "user" and bool(self.kernel.settings.get(KIND, name).record.model_dump().get(
                "local_only")),
        }  # fmt: skip

    def _read_project(self, file: Path) -> dict[str, Any]:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ApiError(409, "refused", f"{file} cannot be read as JSON: {error}") from error
        servers = raw.get("mcpServers", {}) if isinstance(raw, dict) else {}
        return servers if isinstance(servers, dict) else {}

    def _write_project(self, folder: str, name: str, entry: dict[str, Any] | None) -> None:
        if not folder or not Path(folder).is_dir():
            raise ApiError(400, "invalid", f"a project's servers need its folder, and {folder!r} is not one")
        file = Path(folder) / PROJECT_FILE
        raw: dict[str, Any] = {}
        if file.is_file():
            try:
                raw = json.loads(file.read_text(encoding="utf-8"))
            except ValueError as error:
                raise ApiError(409, "refused", f"{file} cannot be read as JSON: {error}") from error
        servers = raw.setdefault("mcpServers", {})
        if entry is None:
            servers.pop(name, None)
        else:
            servers[name] = entry
        files.replace(file, json.dumps(raw, indent=2) + "\n")


def fingerprint(server: Server) -> str:
    """A server's entry as the owner allows it, as a short digest: its command, its arguments or its environment
    changed give another, so an allowance holds for the entry allowed alone (design 0004 §10)."""
    return hashlib.sha256(json.dumps(server.entry(), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _key_of(server: Server) -> str:
    """How a server is started or reached, as a short digest: a check is remembered while it stays the same."""
    how = [server.transport, server.command, *server.args, server.url, *sorted(server.env), *sorted(server.headers)]
    return hashlib.sha256(json.dumps(how).encode("utf-8")).hexdigest()[:16]


def _place(scope: Scope | None) -> str:
    return "yours" if scope == "user" else "this project's (.mcp.json)"
