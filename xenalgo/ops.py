from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class KillSwitch:
    def __init__(self, store: str | Path) -> None:
        self.store = str(store)
        self._init()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.store)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS risk_state "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_utc TEXT NOT NULL)"
            )

    def activate(self, source: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO risk_state(key, value, updated_utc) VALUES (?, ?, ?)",
                ("kill_switch", source or "active", dt.datetime.now(dt.UTC).isoformat()),
            )

    def is_active(self) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM risk_state WHERE key='kill_switch'"
            ).fetchone()
        return row is not None

    def allow_submission(self) -> bool:
        return not self.is_active()


class DeployGuard:
    def deploy_allowed(self, when: dt.datetime) -> bool:
        local = when.astimezone(IST) if when.tzinfo else when.replace(tzinfo=IST)
        if local.weekday() >= 5:
            return True
        market_open = dt.time(9, 15)
        market_close = dt.time(15, 30)
        return not (market_open <= local.time() <= market_close)
