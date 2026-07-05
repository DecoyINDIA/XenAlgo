from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
import os
import sys
import uuid
from typing import TextIO


_run_id = contextvars.ContextVar("xenalgo_run_id", default="-")


def set_run_id(run_id: str) -> None:
    _run_id.set(run_id)


def get_run_id() -> str:
    return _run_id.get()


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = get_run_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(
    *,
    level: str | int = "INFO",
    run_id: str | None = None,
    stream: TextIO | None = None,
) -> str:
    active_run_id = run_id or os.getenv("XENALGO_RUN_ID") or uuid.uuid4().hex
    set_run_id(active_run_id)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RunIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    return active_run_id
