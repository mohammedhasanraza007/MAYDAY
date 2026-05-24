from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager
from typing import Iterator


class RouteMutex:
    def __init__(self) -> None:
        self._global = threading.RLock()
        self._locks: dict[str, threading.RLock] = {}

    def key_for(self, task_id: str) -> str:
        digest = hashlib.sha256(task_id.encode("utf-8", errors="ignore")).hexdigest()
        return digest[:16]

    @contextmanager
    def acquire(self, task_id: str) -> Iterator[None]:
        key = self.key_for(task_id or "default")
        with self._global:
            lock = self._locks.setdefault(key, threading.RLock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()


route_mutex = RouteMutex()
