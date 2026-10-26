"""The client of the Clank API that Clank's Python clients share: the commands now, the console in M0.5.

It finds the service through `state/connection.json`, proves it is the user with the local token, names itself in the
`X-Clank-Client` header (so what it does is recorded as "you (cli)"), and turns the API's one error shape into a
`ClientError` with the API's own message. It holds no state of its own (design 0002 §1: clients hold no state).
"""

import json
from collections.abc import Callable, Generator
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx2

from clank.kernel.access import CLIENT_HEADER, local_token, read_connection
from clank.kernel.home import Home

PREFIX = "/api/v1/"
START_IT = "start it with `clank serve` (or `clank serve --background`)"


class NotRunning(Exception):
    """The service does not run, or does not answer."""


class ClientError(Exception):
    """The API refused a request; the message is the API's own."""

    def __init__(self, message: str, code: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ServerEvent:
    """One message of the event stream: its name (an event type, or the stream's own: connected, reset, closing),
    its id when kept, and its data."""

    name: str
    id: int | None
    data: dict[str, Any]


class Client:
    """A connection to the Clank API."""

    def __init__(self, url: str, token: str, *, name: str = "cli", http: httpx2.Client | None = None) -> None:
        self.url = url
        self.name = name
        self._token = token
        headers = {"Authorization": f"Bearer {token}", CLIENT_HEADER: name}
        self._http = http or httpx2.Client(base_url=url, headers=headers, timeout=httpx2.Timeout(10.0, read=60.0))
        if http is not None:
            self._http.headers.update(headers)

    @classmethod
    def connect(cls, home: Home | None = None, *, name: str = "cli") -> Self:
        """A client of the service running for a CLANK_HOME (the environment's, by default)."""
        found = home or Home.resolve()
        connection = read_connection(found)
        if connection is None:
            raise NotRunning(f"the Clank service is not running for {found.root}; {START_IT}")
        return cls(connection.url, local_token(found), name=name)

    def clone(self) -> "Client":
        """A connection of its own to the same service, as the same client: for a stream another thread may close."""
        return Client(self.url, self._token, name=self.name)

    def get(self, path: str, **params: Any) -> Any:
        """GET a route under /api/v1/."""
        return self._call("GET", path, params=_clean(params))

    def post(self, path: str, body: Any = None) -> Any:
        """POST to a route under /api/v1/."""
        return self._call("POST", path, json=body if body is not None else {})

    def put(self, path: str, body: Any) -> Any:
        """PUT to a route under /api/v1/."""
        return self._call("PUT", path, json=body)

    def patch(self, path: str, body: Any) -> Any:
        """PATCH a route under /api/v1/: a change of some of a record's fields."""
        return self._call("PATCH", path, json=body)

    def delete(self, path: str, **params: Any) -> Any:
        """DELETE a route under /api/v1/."""
        return self._call("DELETE", path, params=_clean(params))

    def events(
        self,
        *,
        after: int | None = None,
        types: list[str] | None = None,
        follow: bool = True,
        opened: Callable[[httpx2.Response], None] | None = None,
    ) -> Generator[ServerEvent, None, None]:
        """The event stream's messages, as they come; `opened` gets the response once the stream answers, so another
        thread can close it to end the stream."""
        params = _clean({"after": after, "types": ",".join(types) if types else None, "follow": follow})
        yield from self.stream("events", opened=opened, **params)

    def stream(
        self,
        path: str,
        *,
        opened: Callable[[httpx2.Response], None] | None = None,
        quiet: float | None = None,
        **params: Any,
    ) -> Generator[ServerEvent, None, None]:
        """A route's Server-Sent Events (the event stream, a conversation's, design 0023 §3), as they come; `opened`
        gets the response once the stream answers; `quiet` seconds without a line end it as `NotRunning` (None: wait
        as long as it takes, since a stream keeps alive on its own)."""
        try:
            with self._http.stream(
                "GET", PREFIX + path, params=_clean(params), timeout=httpx2.Timeout(10.0, read=quiet)
            ) as answer:
                if answer.status_code >= 400:
                    answer.read()
                    raise _error(answer)
                if opened is not None:
                    opened(answer)
                fields: dict[str, str] = {}
                for line in answer.iter_lines():
                    if not line:
                        if "event" in fields:
                            identity = fields.get("id")
                            yield ServerEvent(
                                fields["event"],
                                int(identity) if identity else None,
                                json.loads(fields.get("data", "{}")),
                            )
                        fields = {}
                    elif not line.startswith(":") and ": " in line:
                        key, value = line.split(": ", 1)
                        fields[key] = value
        except httpx2.TransportError as error:
            raise NotRunning(f"the Clank service at {self.url} does not answer; {START_IT}") from error

    def close(self) -> None:
        """Close the connection."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        self.close()

    def _call(self, method: str, path: str, **options: Any) -> Any:
        try:
            answer = self._http.request(method, PREFIX + path.lstrip("/"), **options)
        except httpx2.TransportError as error:
            raise NotRunning(f"the Clank service at {self.url} does not answer; {START_IT}") from error
        if answer.status_code >= 400:
            raise _error(answer)
        return answer.json()


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in params.items()
        if value is not None
    }


def _error(answer: httpx2.Response) -> ClientError:
    try:
        error = answer.json()["error"]
        return ClientError(str(error["message"]), str(error["code"]), answer.status_code)
    except (ValueError, KeyError, TypeError):
        return ClientError(f"the service answered {answer.status_code}", "http_error", answer.status_code)
