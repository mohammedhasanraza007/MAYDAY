"""MAYDAY-safe OpenHands logger adapter."""
from __future__ import annotations

import logging
import os
import re
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, MutableMapping


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "").lower() in {"1", "true", "yes", "on"}
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)(['\"]?\s*[:=]\s*['\"]?)([^'\"\s,;]+)"
)


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = _SECRET_PATTERN.sub(r"\1\2******", message)
        for key, value in os.environ.items():
            if value and len(value) > 2 and any(marker in key.upper() for marker in ("SECRET", "TOKEN", "_KEY")):
                message = message.replace(value, "******")
        record.msg = message
        record.args = ()
        return True


class OpenHandsLoggerAdapter(logging.LoggerAdapter):
    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.get("extra")
        if isinstance(extra, dict):
            kwargs["extra"] = {**self.extra, **extra}
        else:
            kwargs["extra"] = self.extra
        return msg, kwargs


def get_file_handler(
    log_dir: str | os.PathLike[str] = LOG_DIR,
    log_level: int = logging.INFO,
    when: str = "d",
    backup_count: int = 7,
    utc: bool = False,
) -> TimedRotatingFileHandler:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        path / "openhands.log",
        when=when,
        backupCount=backup_count,
        utc=utc,
        encoding="utf-8",
    )
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(SensitiveDataFilter())
    return handler


def get_uvicorn_log_config() -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(levelname)s %(name)s %(message)s"},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
        },
        "root": {"level": LOG_LEVEL, "handlers": ["default"]},
    }


openhands_logger = logging.getLogger("openhands")
_level = getattr(logging, LOG_LEVEL, logging.INFO)
openhands_logger.setLevel(_level if isinstance(_level, int) else logging.INFO)
openhands_logger.addFilter(SensitiveDataFilter())
if LOG_TO_FILE:
    openhands_logger.addHandler(get_file_handler())
