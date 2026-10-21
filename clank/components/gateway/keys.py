"""The cloud providers' keys the gateway holds (design 0016 §5, decision 0106): in memory only, each handed by the
service (behind its local token) for the launch that runs the provider's model, and forgotten when no slot runs it.

A key is named by its provider (`openrouter`), its last four characters, its launch and when it was set; nothing ever
answers with its value. Wherever a value the gateway was handed appears in what it writes (a request's record, the live
view), even echoed back in an answer, it is replaced by `…` and its last four (design 0002 §2.8's last rule): a key
forgotten since is still replaced, for as long as the gateway runs.
"""

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeldKey:
    """A key the gateway holds: its provider, its value, the launch it was handed for, and when it was set."""

    endpoint: str
    value: str
    launch: int | None
    set: str

    def view(self) -> dict[str, Any]:
        """What may be said of it: never its value."""
        return {"endpoint": self.endpoint, "ends": self.value[-4:], "launch": self.launch, "set": self.set}


class Keys:
    """The keys the gateway holds now, and every value it was handed since it started (to keep them out of what it
    writes)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[str, HeldKey] = {}
        self._seen: set[str] = set()

    def put(self, endpoint: str, value: str, launch: int | None, set: str) -> dict[str, Any]:
        """Hold a provider's key for a launch, replacing the one held before."""
        held = HeldKey(endpoint, value, launch, set)
        with self._lock:
            self._held[endpoint] = held
            self._seen.add(value)
        return held.view()

    def forget(self, endpoint: str) -> bool:
        """Forget a provider's key; whether one was held."""
        with self._lock:
            return self._held.pop(endpoint, None) is not None

    def view(self) -> list[dict[str, Any]]:
        """Each key held, by its provider, its last four, its launch and when it was set."""
        with self._lock:
            return [held.view() for held in sorted(self._held.values(), key=lambda each: each.endpoint)]

    def value(self, endpoint: str, launch: int | None = None) -> str | None:
        """The key of a provider, when one is held (for that launch, when one is named)."""
        with self._lock:
            held = self._held.get(endpoint)
        if held is None or (launch is not None and held.launch != launch):
            return None
        return held.value

    def has(self, endpoint: str, launch: int | None) -> bool:
        """Whether the key of a provider is held for a launch."""
        return self.value(endpoint, launch) is not None

    def scrub(self, text: str) -> str:
        """A text with each key's value replaced by `…` and its last four."""
        with self._lock:
            seen = list(self._seen)
        for value in seen:
            if value and value in text:
                text = text.replace(value, "…" + value[-4:])
        return text

    def scrubbed(self, record: Any) -> Any:
        """A record (a dict, a list, a text) with every key's value replaced, in place for dicts and lists."""
        if not self._seen:
            return record
        if isinstance(record, str):
            return self.scrub(record)
        if isinstance(record, dict):
            for name, item in list(record.items()):
                record[name] = self.scrubbed(item)
        elif isinstance(record, list):
            for index, item in enumerate(record):
                record[index] = self.scrubbed(item)
        return record
