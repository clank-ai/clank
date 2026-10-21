"""The remote component's part in the service (design 0005, decision 0012): the phone page and who may reach it.

Remote access is switched on and off from Clank (`config/remote.json`'s `on`). While it is on, the phone's listener
(`app.py`, its own FastAPI app) listens on this machine only (`port`, 7721) and Tailscale publishes it on the tailnet
only (`https://<machine>.<tailnet>.ts.net:<tailnet_port>`, 8445); while it is off, nothing listens and Tailscale is
told to stop. The background task (`run`) puts that right every few seconds, so a change of the setting, from any
client or an edited file, applies by itself; it refuses to publish when Tailscale cannot say this machine's name and
user, or when Funnel is on for the port (it would face the internet), and says why in the status.

Pairing (`devices.py`): codes are made here, on the computer, by the local API's clients only; the device types the
code on the phone page. The files the agents sent to the phone are read from the workspaces' outboxes (`outbox.py`),
and each new one is recorded (`remote.file_sent`).
"""

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

import anyio
import anyio.to_thread
import uvicorn

from clank.components.remote import outbox, tailnet
from clank.components.remote.devices import Device, Devices, PairingError
from clank.components.remote.kinds import RemoteSettings
from clank.components.remote.traffic import Traffic
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
ROUND_SECONDS = 3.0
LOGIN_SECONDS = 60.0  # this machine's Tailscale user is read again at most this often
EVENT_TYPES = [
    EventType("remote.switched", "Remote access (the phone page) was turned on or off.", {"on": "Whether it is on."}),
    EventType(
        "remote.paired", "A device was paired to reach the phone page.", {"device": "Its id.", "name": "Its name."}
    ),
    EventType("remote.revoked", "A paired device was revoked.", {"device": "Its id.", "name": "Its name."}),
    EventType(
        "remote.pairing_canceled",
        "A pairing code was canceled before a device used it: it no longer pairs.",
        {"name": "The device it was for."},
    ),
    EventType(
        "remote.file_sent",
        "An agent sent a file to the phone (send_to_phone).",
        {"workspace": "The workspace.", "file": "The file in its outbox.", "caption": "What it is."},
    ),
]


def phone_config(app: Any, port: int) -> uvicorn.Config:
    """How the phone's listener is served: on this machine's loopback, quietly, and taking each connection's own
    address, never `X-Forwarded-For`: Tailscale's proxy names the phone's tailnet address there, and Uvicorn, which
    trusts that header from the loopback by default, would hide that the request came through Tailscale on this
    machine."""
    return uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
        timeout_graceful_shutdown=2,
        proxy_headers=False,
    )


class PhoneServer(uvicorn.Server):
    """The phone's listener: Uvicorn inside the service's own loop, which leaves the signals to the service's server."""

    def capture_signals(self) -> Any:
        """The service's own server handles Ctrl+C and the stop; this one is stopped by the remote component."""
        import contextlib

        return contextlib.nullcontext()


class RemoteError(Exception):
    """A remote action that cannot be done, and why."""


class Remote:
    """The remote component, built on the kernel."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        self.devices = Devices(kernel)
        self.traffic = Traffic(kernel.home.logs / "phone")
        self._server: PhoneServer | None = None
        self._problem = ""
        self._published = False
        self._tailnet: tailnet.Tailnet | None = None
        self._tailnet_at = 0.0
        self._seen: set[tuple[str, str]] | None = None
        self._lock = threading.Lock()

    def settings(self) -> RemoteSettings:
        """The remote settings now."""
        loaded = self.kernel.settings.get(RemoteSettings.KIND, RemoteSettings.KIND)
        return RemoteSettings.model_validate(loaded.record.model_dump())

    def status(self) -> dict[str, Any]:
        """Whether remote access is on and listening, its address on the tailnet, why not, and the devices."""
        settings = self.settings()
        here = self._tailnet
        url = f"https://{here.host}:{settings.tailnet_port}/" if here and here.host else ""
        return {
            "on": settings.on,
            "listening": self._server is not None and self._server.started,
            "published": self._published,
            "url": url,
            "login": here.login if here else "",
            "problem": self._problem,
            "devices": [device.view() for device in self.devices.all()],
            "pairing": self.devices.waiting_code(),
        }

    def switch(self, on: bool, *, actor: Actor) -> dict[str, Any]:
        """Turn remote access on or off; the background task applies it within a few seconds."""
        loaded = self.kernel.settings.get(RemoteSettings.KIND, RemoteSettings.KIND)
        values = {**loaded.record.model_dump(), "on": on}
        self.kernel.settings.write(RemoteSettings.KIND, RemoteSettings.KIND, values, base=loaded.revision, actor=actor)
        self.kernel.events.record(
            "remote.switched", summary=f"{actor.describe()} turned remote access {'on' if on else 'off'}",
            actor=actor, data={"on": on},
        )  # fmt: skip
        return self.status()

    def pair(self, name: str, *, actor: Actor) -> dict[str, Any]:
        """A code to pair a device of this name: the code, the page's address, until when."""
        code, expires = self.devices.new_code(name)
        here = self._read_tailnet(fresh=True)
        url = f"https://{here.host}:{self.settings().tailnet_port}/" if here.host else ""
        return {"code": code, "url": url, "expires": to_text(expires), "on": self.settings().on}

    def cancel_pairing(self, *, actor: Actor) -> dict[str, Any]:
        """Cancel the pairing code waiting, if any (recorded): it no longer pairs; the status after."""
        waiting = self.devices.cancel_code()
        if waiting is not None:
            summary = f"{actor.describe()} canceled the pairing code for {waiting['name']}"
            self.kernel.events.record(
                "remote.pairing_canceled", summary=summary, actor=actor, data={"name": waiting["name"]}
            )
        return {**self.status(), "canceled": waiting is not None}

    def paired(self, code: str, login: str) -> tuple[Device, str]:
        """Pair the device that typed this code (the phone page's route); recorded."""
        device, token = self.devices.pair(code, login)
        self.kernel.events.record(
            "remote.paired", summary=f"a device was paired: {device.name}", actor=Actor(kind="device", via=device.name),
            subject=Subject(kind="device", id=device.id), data={"device": device.id, "name": device.name},
        )  # fmt: skip
        return device, token

    def revoke(self, id: str, *, actor: Actor) -> dict[str, Any]:
        """Revoke a paired device."""
        try:
            device = self.devices.revoke(id)
        except PairingError as error:
            raise RemoteError(str(error)) from error
        self.kernel.events.record(
            "remote.revoked", summary=f"{actor.describe()} revoked the device {device.name}", actor=actor,
            subject=Subject(kind="device", id=device.id), data={"device": device.id, "name": device.name},
        )  # fmt: skip
        return device.view()

    def owner_login(self) -> str:
        """The Tailscale login of this machine's user: the only one the phone page answers."""
        return self._read_tailnet().login

    def files(self, limit: int = 100) -> list[dict[str, Any]]:
        """The files the agents sent to the phone, the newest first."""
        return outbox.files(self._folders(), limit)

    def file_path(self, workspace: str, file: str) -> Any:
        """A sent file's path on this machine, or None."""
        folder = dict(self._folders()).get(workspace)
        return outbox.path_of(folder, file) if folder else None

    async def run(self) -> None:
        """Keep the listener and Tailscale as the setting says, and watch the outboxes, every few seconds."""
        async with anyio.create_task_group() as group:
            while True:
                try:
                    await self._keep(group)
                    await anyio.to_thread.run_sync(self._watch)
                except Exception:
                    log.exception("the remote component's round failed")
                await anyio.sleep(ROUND_SECONDS)

    def router(self) -> Any:
        """The local API's routes (the computer's clients: on and off, pairing, devices, files)."""
        from clank.components.remote.api import router

        return router(self)

    async def _keep(self, group: Any) -> None:
        settings = self.settings()
        if settings.on and self._server is None:
            here = await anyio.to_thread.run_sync(lambda: self._read_tailnet(fresh=True))
            if here.problem:
                self._problem = here.problem
                return
            if await anyio.to_thread.run_sync(tailnet.funnel_on, here.host, settings.tailnet_port):
                self._problem = f"Tailscale Funnel is on for port {settings.tailnet_port}: it would face the internet"
                return
            from clank.components.remote.app import create_phone_app

            self._server = PhoneServer(phone_config(create_phone_app(self), settings.port))
            group.start_soon(self._serve, self._server)
            problem = await anyio.to_thread.run_sync(tailnet.publish, settings.port, settings.tailnet_port)
            self._published, self._problem = not problem, problem
        elif not settings.on and self._server is not None:
            self._server.should_exit = True
            self._server = None
            problem = await anyio.to_thread.run_sync(tailnet.unpublish, settings.tailnet_port)
            self._published, self._problem = False, problem

    async def _serve(self, server: PhoneServer) -> None:
        try:
            await server.serve()
        except Exception as error:
            self._problem = f"the phone's listener stopped: {error}"
            log.exception("the phone's listener stopped")
        if self._server is server and not server.started:
            self._server = None  # it never started (its port taken): the next round tries again

    def _read_tailnet(self, fresh: bool = False) -> tailnet.Tailnet:
        if fresh or self._tailnet is None or time.monotonic() - self._tailnet_at > LOGIN_SECONDS:
            self._tailnet, self._tailnet_at = tailnet.read(), time.monotonic()
        return self._tailnet

    def _folders(self) -> list[tuple[str, str]]:
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        return [(row["name"], row["path"]) for row in workspaces.records()]

    def _watch(self) -> None:
        """Record each file sent since the last round (the first round only learns what is there)."""
        found = {(row["workspace"], row["file"]): row for row in self.files(limit=500)}
        with self._lock:
            seen, self._seen = self._seen, set(found)
        if seen is None:
            return
        for key in sorted(set(found) - seen, key=lambda each: found[each]["sent"]):
            row = found[key]
            self.kernel.events.record(
                "remote.file_sent",
                summary=f"{row['workspace']}'s agent sent {row['from'] or row['file']} to the phone",
                actor=Actor(kind="session", via=row["workspace"]),
                data={"workspace": row["workspace"], "file": row["file"], "caption": row["caption"][:200]},
            )
