"""LRU + TTL cache for in-memory play sessions (bounded, multi-worker friendly when size=0)."""

import time
from collections import OrderedDict
from typing import Optional


class GameSessionCache:
    """Stores session_id -> game state dict with TTL and max entry eviction."""

    def __init__(self, ttl_s: float, max_entries: int):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def get(self, key: str) -> Optional[dict]:
        if self.max_entries <= 0:
            return None
        now = time.monotonic()
        item = self._data.get(key)
        if not item:
            return None
        touched, state = item
        if now - touched > self.ttl_s:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        self._data[key] = (now, state)
        return state

    def set(self, key: str, state: dict) -> None:
        if self.max_entries <= 0:
            return
        now = time.monotonic()
        if key in self._data:
            del self._data[key]
        self._data[key] = (now, state)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
