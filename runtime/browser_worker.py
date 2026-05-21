from __future__ import annotations

import queue
import threading
from typing import Any, Callable

from runtime.browser_session import SessionRegistry


class BrowserWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._lock = threading.Lock()

    def run(self, callback: Callable[[], Any], timeout_seconds: int = 180) -> Any:
        self._ensure_started()
        if threading.get_ident() == self._thread_id:
            return callback()

        result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._queue.put((callback, result_queue))
        ok, payload = result_queue.get(timeout=timeout_seconds)
        if ok:
            return payload
        raise payload

    def close_all_sessions(self) -> None:
        self.run(SessionRegistry._close_all_local)

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="MAYDAYBrowserWorker",
                daemon=True,
            )
            self._thread.start()
        self._ready.wait(timeout=10)

    def _loop(self) -> None:
        self._thread_id = threading.get_ident()
        self._ready.set()
        while True:
            callback, result_queue = self._queue.get()
            try:
                result_queue.put((True, callback()))
            except BaseException as exc:
                result_queue.put((False, exc))


browser_worker = BrowserWorker()
SessionRegistry.set_close_all_dispatcher(browser_worker.close_all_sessions)
