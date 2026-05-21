from __future__ import annotations

import os
from typing import Any, Callable

from runtime import browser_audit_log
from runtime.world_state import world_state


class PermissionGate:
    def __init__(self) -> None:
        self._browser_callback: Callable[[str, Any, Any], bool | str] | None = None
        self.cancelled = False
        self.block_reason = ""

    def set_browser_callback(self, callback: Callable[[str, Any, Any], bool | str] | None) -> None:
        self._browser_callback = callback

    def check_browser(self, action: str, target: Any = None, preview: Any = None, already_approved: bool = False) -> bool:
        if self.cancelled:
            browser_audit_log.record(action, target or preview, None, None, user_approved=False)
            return False
        if already_approved:
            browser_audit_log.record(action, target or preview, None, None, user_approved=True)
            return True
        if self._browser_callback is not None:
            decision = self._browser_callback(action, target, preview)
            approved = decision in {True, "ALLOW", "ALLOW_ALWAYS", "APPROVE", "approved"}
            browser_audit_log.record(action, target or preview, None, None, user_approved=approved)
            if not approved:
                self.cancelled = True
                self.block_reason = "user_denied"
                world_state.set_permission_blocked("browser", self.block_reason)
            return approved
        approved = os.environ.get("MAYDAY_AUTO_APPROVE_BROWSER", "").strip().lower() in {"1", "true", "yes", "on"}
        browser_audit_log.record(action, target or preview, None, None, user_approved=approved)
        if not approved:
            self.cancelled = True
            self.block_reason = "user_denied"
            world_state.set_permission_blocked("browser", self.block_reason)
        return approved

    def reset(self) -> None:
        self.cancelled = False
        self.block_reason = ""
        world_state.clear_permission_blocks()


permission_gate = PermissionGate()
