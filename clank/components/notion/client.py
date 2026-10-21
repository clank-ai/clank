"""Notion's API, as the notion component talks to it (design 0010 §3): `Notion-Version: 2025-09-03`, the owner's
integration secret as a bearer token, one request at a time per client, and a request Notion limits (`429`) sent again
after the wait Notion asks for (`Retry-After`), a few times at most.

An error is Notion's own (`NotionError`: its status, its code and its message); a connection that fails is said as one,
with the status 0. `NotionRefused` is Clank's: what cannot be done, said for whoever asked. Only this module sends
requests to Notion.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx2

VERSION = "2025-09-03"
TIMEOUT = 30.0
TRIES = 5  # a request answered 429 this many times in a row is given up
LONGEST_WAIT = 60.0  # the most a single Retry-After is waited


class NotionRefused(Exception):
    """Something asked of Clank's connection to Notion that cannot be done, and why, in words for whoever asked."""


class NotionError(Exception):
    """Notion refused a request, or could not be reached: its status (0 when unreached), its code and its message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class NotionClient:
    """Requests to Notion's API with one secret."""

    def __init__(
        self,
        secret: str,
        *,
        api: str,
        version: str = VERSION,
        transport: httpx2.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.sleep = sleep
        self._lock = threading.Lock()
        self._http = httpx2.Client(
            base_url=api.rstrip("/") + "/v1/",
            headers={"Authorization": f"Bearer {secret}", "Notion-Version": version},
            timeout=TIMEOUT,
            transport=transport,
        )

    def request(self, method: str, path: str, body: Any = None, params: dict[str, Any] | None = None) -> Any:
        """One request: its answer, or `NotionError`."""
        with self._lock:
            for _ in range(TRIES):
                try:
                    answer = self._http.request(method, path.lstrip("/"), json=body, params=params)
                except httpx2.HTTPError as error:
                    raise NotionError(0, "unreachable", f"Notion could not be reached: {error}") from error
                if answer.status_code != 429:
                    return _answer(answer)
                self.sleep(min(_wait(answer), LONGEST_WAIT))
            raise NotionError(429, "rate_limited", f"Notion kept asking Clank to wait ({TRIES} times): try again later")

    def me(self) -> dict[str, Any]:
        """The integration itself: its name, and its workspace's."""
        found: dict[str, Any] = self.request("GET", "users/me")
        return found

    def close(self) -> None:
        """Close its connections."""
        self._http.close()


def _answer(answer: httpx2.Response) -> Any:
    try:
        found = answer.json()
    except ValueError:
        found = None
    if answer.status_code >= 400:
        if isinstance(found, dict):
            raise NotionError(answer.status_code, str(found.get("code") or "error"), str(found.get("message") or ""))
        raise NotionError(answer.status_code, "error", answer.text[:300])
    return found


def _wait(answer: httpx2.Response) -> float:
    try:
        return max(0.0, float(answer.headers.get("Retry-After", "1")))
    except ValueError:
        return 1.0
