from __future__ import annotations

import logging
import threading
from typing import Any

from runtime.browser_session import BrowserSession, SessionRegistry

log = logging.getLogger("mayday.browser.manager")

DEAD_BROWSER_MARKERS = (
    "event loop is closed",
    "playwright has stopped",
    "target page, context or browser has been closed",
    "context or browser has been closed",
    "browser has been closed",
    "page closed",
    "target closed",
    "cannot switch to a different thread",
)


def is_browser_runtime_error(exc_or_text: object) -> bool:
    text = str(exc_or_text or "").lower()
    return any(marker in text for marker in DEAD_BROWSER_MARKERS)


class PlaywrightManager:
    _instance: "PlaywrightManager | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "PlaywrightManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_session(self, session_id: str = "") -> BrowserSession:
        with self._lock:
            session = self._get_or_create_session(session_id)
            if self._session_is_usable(session):
                return session
            log.warning("PlaywrightManager: stale browser session detected; restarting")
            return self.restart_session()

    def get_page(
        self,
        session_id: str = "",
        create_new: bool = False,
    ) -> tuple[BrowserSession, Any]:
        with self._lock:
            session = self.get_session(session_id)
            if create_new:
                return session, self._new_page(session)

            live_pages = []
            for page in list(getattr(session, "pages", [])):
                try:
                    if not page.is_closed():
                        _ = page.url
                        live_pages.append(page)
                except Exception as exc:
                    if is_browser_runtime_error(exc):
                        log.warning("PlaywrightManager: page dead: %s", exc)
                        return self.restart()
                    continue
            session.pages = live_pages
            if live_pages:
                return session, live_pages[-1]
            return session, self._new_page(session)

    def restart(self) -> tuple[BrowserSession, Any]:
        session = self.restart_session()
        return session, self._new_page(session)

    def restart_session(self) -> BrowserSession:
        with self._lock:
            log.warning("PlaywrightManager: forced restart")
            try:
                SessionRegistry.close_all()
            except Exception as exc:
                log.warning("PlaywrightManager: close_all during restart failed: %s", exc)
                SessionRegistry._sessions.clear()
                SessionRegistry._latest_session_id = ""
            session = SessionRegistry.create()
            log.info("PlaywrightManager: browser started")
            return session

    def _get_or_create_session(self, session_id: str = "") -> BrowserSession:
        if session_id:
            try:
                return SessionRegistry.get(session_id)
            except RuntimeError:
                log.info("PlaywrightManager: session %s missing; starting fresh session", session_id)
                return SessionRegistry.create()
        try:
            return SessionRegistry.latest()
        except RuntimeError:
            log.info("PlaywrightManager: starting fresh session")
            return SessionRegistry.create()

    def _session_is_usable(self, session: BrowserSession) -> bool:
        if not session.is_alive():
            return False
        try:
            _ = session.context.pages
            return True
        except Exception as exc:
            if is_browser_runtime_error(exc):
                log.warning("PlaywrightManager: browser context dead: %s", exc)
            return False

    def _new_page(self, session: BrowserSession) -> Any:
        page = session.context.new_page()
        session.pages.append(page)
        session.touch()
        return page


_manager = PlaywrightManager()


def get_browser_session(session_id: str = "") -> BrowserSession:
    return _manager.get_session(session_id)


def get_browser_page(
    session_id: str = "",
    create_new: bool = False,
    return_session: bool = False,
):
    session, page = _manager.get_page(session_id=session_id, create_new=create_new)
    if return_session:
        return session, page
    return page


def restart_browser():
    return _manager.restart()
