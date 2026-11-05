"""Small TTL cache used to avoid hammering the paper APIs."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable


class TTLCache:
    def __init__(self, ttl: int = 300, maxsize: int = 1024):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                self.misses += 1
                return None
            ts, value = item
            if time.time() - ts > self.ttl:
                self._data.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.maxsize:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
            self._data[key] = (time.time(), value)

    def get_or_set(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        return {"entries": len(self._data), "hits": self.hits, "misses": self.misses, "ttl": self.ttl}
