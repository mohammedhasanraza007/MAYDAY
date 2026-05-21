from __future__ import annotations

import webbrowser
from datetime import datetime, timezone


class LivePreview:
    def __init__(self) -> None:
        self._previews: list[dict] = []

    def open_browser(self, url: str) -> bool:
        opened = webbrowser.open(url)
        self._previews.append(
            {
                "url": url,
                "opened": bool(opened),
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return bool(opened)

    def get_active_previews(self) -> list[dict]:
        return list(self._previews)
